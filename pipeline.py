import sys
from typing import Optional, Type

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, computed_field

from doc_server.helpers import update_document
from etl.llama_parse import LlamaParseOutput, parse
from etl.pymupdf_parse import PyMuPDFOutput, extract
from etl.zip_llama_pymupdf import (
    UnifiedBlock,
    ZippedOutputsPage,
    match_pages,
)
from pipeline_state_helpers import draw_pipeline, resume_from_latest, save_output
from rule_registry.conversion_rules import ConversionRule, ConversionRuleRegistry
from rule_registry.propose.propose_new_rule import propose_new_rule_node
from tiptap.tiptap_models import BaseAttrs, DocNode, ImageNode, TiptapNode


class PipelineState(BaseModel):
    pdf_path: str
    llama_parse_output: LlamaParseOutput = None
    pymupdf_output: PyMuPDFOutput = None

    zipped_pages: list[ZippedOutputsPage] = None

    prose_mirror_doc: DocNode = None

    block_index: Optional[int] = -1
    page_index: Optional[int] = -1

    @computed_field
    @property
    def current_block(self) -> Optional[UnifiedBlock]:
        if self.page_index is None or self.block_index is None:
            return None

        if self.page_index >= len(self.zipped_pages):
            return None

        if self.block_index >= len(self.zipped_pages[self.page_index].unified_blocks):
            return None

        return self.zipped_pages[self.page_index].unified_blocks[self.block_index]

    def update_current_block(self, new_block: UnifiedBlock):
        """Safely update the block at the current page/block index."""
        if self.page_index is None or self.block_index is None:
            raise IndexError("page_index or block_index is not set")

        self.zipped_pages[self.page_index].unified_blocks[self.block_index] = new_block


def is_node_completed(state: PipelineState, step: str) -> bool:
    # Make this smarter as state gets more complicated.
    return hasattr(state, step) and getattr(state, step) is not None


def llama_parse(state: PipelineState):
    # Check if already completed
    if state.llama_parse_output:
        print("⏭️  LlamaParse already completed, skipping...")
        return {}

    print("🔄 Running LlamaParse...")
    result = parse(state.pdf_path)
    llama_parse_output = LlamaParseOutput(result)
    return {"llama_parse_output": llama_parse_output}


def pymupdf_extract(state: PipelineState):
    # Check if already completed
    if state.pymupdf_output:
        print("⏭️  PyMuPDF extraction already completed, skipping...")
        return {}

    print("🔄 Running PyMuPDF extraction...")
    result = extract(state.pdf_path)
    # Convert the list of PageResult objects to PyMuPDFOutput
    # The extract function returns a list, but we expect a PyMuPDFOutput with pages field
    pymupdf_output = PyMuPDFOutput(pages=result)
    return {"pymupdf_output": pymupdf_output}


def zip_outputs(state: PipelineState):
    """
    Given both llama parse output and pymupdf output, zip them together.
    """
    if state.zipped_pages:
        print("⏭️  Zipping pages already completed, skipping...")
        return {}

    print("🧹  Zipping pages")

    assert len(state.llama_parse_output.pages) == len(state.pymupdf_output.pages)

    pages = []
    for i in range(len(state.llama_parse_output.pages)):
        lp_page = state.llama_parse_output.pages[i]
        pm_page = state.pymupdf_output.pages[i]
        zipped_page = ZippedOutputsPage(
            page=i + 1,
            llama_parse_page=lp_page,
            pymupdf_page=pm_page,
            unified_blocks=match_pages(lp_page, pm_page),
        )
        pages.append(zipped_page)

    return {"zipped_pages": pages}


def init_prose_mirror_doc(state: PipelineState):
    if state.prose_mirror_doc:
        print("⏭️  ProseMirror init already completed, skipping...")
        return {}
    return {"prose_mirror_doc": DocNode(content=[])}


def get_next_block(state: PipelineState):
    """
    Get the next block to process. If no more blocks, return None to end the pipeline.
    """
    print(f"\n➡️  Getting next block after {state.page_index=} {state.block_index=}")

    # Did we already finish?
    if state.block_index is None and state.page_index is None:
        return {}

    # Check if we have more blocks to process on our current page
    if state.block_index < len(state.zipped_pages[state.page_index].unified_blocks) - 1:
        return {
            "block_index": state.block_index + 1,
            "page_index": max(state.page_index, 0),
        }

    # No more block on the page - got any more pages?
    if state.page_index < len(state.zipped_pages) - 1:
        return {"block_index": 0, "page_index": state.page_index + 1}

    # No more pages and no more blocks
    return {"block_index": None, "page_index": None}


def get_rule_for_block(state: PipelineState):
    """
    Check if any conversion rules are applicable to the current block.
    If a rule matches, set the conversion_rule field to the rule's ID.
    """
    if state.current_block.conversion_rule is not None:
        # Rule already set, no need to check again
        return {}

    # Get all available conversion rules
    rules = ConversionRuleRegistry.get_all_rules()

    # Test each rule against the current block
    for rule in rules:
        # For now, we'll test against the first PyMuPDF item if available
        # In the future, we might want to test against all items or use a different strategy
        pymupdf_input = (
            state.current_block.fitz_items[0]
            if state.current_block.fitz_items
            else None
        )

        if rule.match_condition(state.current_block.llama_item, pymupdf_input):
            # Found a matching rule
            new_block = state.current_block.model_copy(
                update={"conversion_rule": rule.id}
            )
            state.update_current_block(new_block)
            return {"current_block": state.current_block}

    # No matching rule found
    return {}


def should_emit_block(state: PipelineState) -> str:
    """
    Conditional edge function to determine next step after rule checking.
    Returns 'EmitBlock' if a conversion rule was found, 'ProposeNewRule' otherwise.
    """
    if state.current_block.conversion_rule is not None:
        return "EmitBlock"
    else:
        return "ProposeNewRule"


def should_continue_processing_blocks(state: PipelineState) -> bool:
    """
    Conditional edge function to determine if we should continue processing blocks.
    Returns 'RuleForBlock' if there is a block we should process, 'InsertImages' otherwise.
    """
    # Check if we have more blocks to process
    if state.block_index is not None and state.page_index is not None:
        return "RuleForBlock"
    else:
        return "InsertImages"


def emit_block(state: PipelineState):
    """
    Construct a node using the conversion rule and add it to the prose mirror document.
    """
    print(f"✏️  Emiting node using {state.current_block.conversion_rule}")
    # Get the conversion rule by ID
    rule_class: Type[ConversionRule] = ConversionRuleRegistry._rules.get(
        state.current_block.conversion_rule
    )
    if not rule_class:
        raise ValueError(
            f"Conversion rule '{state.current_block.conversion_rule}' not found"
        )

    # Create an instance of the rule
    rule = rule_class()

    # Get the PyMuPDF input (use first item if available)
    pymupdf_input = (
        state.current_block.fitz_items[0] if state.current_block.fitz_items else None
    )

    # Construct the node using the rule
    constructed_node: TiptapNode = rule.construct_node(
        state.current_block.llama_item, pymupdf_input
    )

    if constructed_node:
        if not constructed_node.attrs:
            # If attrs is None, we need to find the correct Attrs class to instantiate.
            # It could be BaseAttrs or a node-specific subclass.
            # The type hint for the attrs field on the node class will tell us.
            constructed_node.attrs = BaseAttrs()

        # Now we can safely set the unified_block_id
        constructed_node.attrs.unified_block_id = state.current_block.id

    # Add the constructed node to the prose mirror document content
    updated_content = state.prose_mirror_doc.content + [constructed_node]

    return {
        "prose_mirror_doc": state.prose_mirror_doc.model_copy(
            update={"content": updated_content}
        )
    }


def insert_images(state: PipelineState):
    """
    After all blocks have been processed, iterate through the pages and insert images
    in the correct positions without reordering the entire document.
    """
    print("🖼️ Inserting images...")
    content = list(state.prose_mirror_doc.content)

    # First, get the src of all existing images in the document
    existing_image_srcs = {
        node.attrs.src
        for node in content
        if node.type == "image" and node.attrs and node.attrs.src
    }

    # Create lookups for block information
    block_id_to_page_num = {
        block.id: page.page
        for page in state.zipped_pages
        for block in page.unified_blocks
    }
    block_id_to_block = {
        block.id: block for page in state.zipped_pages for block in page.unified_blocks
    }

    # Gather all images to be inserted that are not already present
    images_to_insert = []
    for page in state.zipped_pages:
        for item in page.pymupdf_page.content:
            if item.type == "image" and item.src not in existing_image_srcs:
                images_to_insert.append(item)

    # Sort images by page and then by vertical position to ensure correct insertion order
    images_to_insert.sort(key=lambda img: (img.page, img.bbox[1]))

    if not images_to_insert:
        print("👍 No new images to insert.")
        return {}  # Return early if there's nothing to do

    for image_item in images_to_insert:
        image_page = image_item.page
        image_y0 = image_item.bbox[1]

        # Find the correct insertion index in the content list
        insertion_index = -1
        for i, node in enumerate(content):
            node_page = -1
            # Check for existing images we may have just inserted
            if node.type == "image" and node.attrs and node.attrs.title:
                try:
                    # e.g., "Page 1 image"
                    node_page = int(node.attrs.title.split(" ")[1])
                except (ValueError, IndexError):
                    pass  # Not an image title we can parse
            elif node.attrs and node.attrs.unified_block_id:
                node_page = block_id_to_page_num.get(node.attrs.unified_block_id, -1)

            if node_page == -1:
                continue  # Cannot determine page for this node

            # If node is on a later page, we've found our insertion spot
            if node_page > image_page:
                insertion_index = i
                break

            if node_page < image_page:
                continue  # Image goes on a later page, so keep searching

            # On the same page, compare vertical position
            # We only use bboxes from fitz items for reliable positioning
            node_y0 = float("inf")  # Default to bottom of page
            if node.attrs and node.attrs.unified_block_id:
                block = block_id_to_block.get(node.attrs.unified_block_id)
                if block and block.fitz_items:
                    node_y0 = block.fitz_items[0].bbox[1]

            if image_y0 < node_y0:
                insertion_index = i
                break

        image_node = ImageNode(
            attrs=ImageNode.Attrs(
                src=image_item.src,
                alt="An image from the PDF",
                title=f"Page {image_item.page} image",
            )
        )

        if insertion_index != -1:
            content.insert(insertion_index, image_node)
        else:
            # If no spot was found, it belongs at the end
            content.append(image_node)

    return {
        "prose_mirror_doc": state.prose_mirror_doc.model_copy(
            update={"content": content}
        )
    }


def update_live_editor(state: PipelineState):
    if state.prose_mirror_doc:
        print("👀  Updating live editor")
        update_document(state.prose_mirror_doc)


def build_pipeline():
    builder = StateGraph(state_schema=PipelineState)

    builder.add_node("LlamaParse", RunnableLambda(llama_parse))
    builder.add_node("PyMuPDFExtract", RunnableLambda(pymupdf_extract))

    builder.set_entry_point("LlamaParse")
    builder.add_edge("LlamaParse", "PyMuPDFExtract")

    builder.add_node("ZipOutputs", RunnableLambda(zip_outputs))
    builder.add_edge("PyMuPDFExtract", "ZipOutputs")

    builder.add_node("InitProseMirror", RunnableLambda(init_prose_mirror_doc))
    builder.add_edge("ZipOutputs", "InitProseMirror")

    builder.add_node("UpdateLiveEditor", RunnableLambda(update_live_editor))

    # Now we want to parse the contents
    builder.add_node("GetNextBlock", RunnableLambda(get_next_block))
    builder.add_node("RuleForBlock", get_rule_for_block)
    builder.add_node("ProposeNewRule", propose_new_rule_node)
    builder.add_node("EmitBlock", emit_block)
    builder.add_node("InsertImages", insert_images)

    builder.add_edge("InitProseMirror", "GetNextBlock")

    builder.add_conditional_edges(
        "GetNextBlock",
        should_continue_processing_blocks,
        {"RuleForBlock": "RuleForBlock", "InsertImages": "InsertImages"},
    )

    builder.add_conditional_edges(
        "RuleForBlock",
        should_emit_block,
        {"EmitBlock": "EmitBlock", "ProposeNewRule": "ProposeNewRule"},
    )
    builder.add_edge("ProposeNewRule", "EmitBlock")
    builder.add_edge("EmitBlock", "UpdateLiveEditor")
    builder.add_edge("EmitBlock", "GetNextBlock")
    builder.add_edge("InsertImages", "UpdateLiveEditor")
    builder.add_edge("InsertImages", END)

    return builder.compile()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <pdf_path> [--resume-latest]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    resume_latest = "--resume-latest" in sys.argv

    # Initialize state
    if resume_latest:
        state_dict = resume_from_latest(pdf_path)
        if state_dict:
            # Convert dictionary to PipelineState object
            initial_state = PipelineState(**state_dict)
            update_live_editor(initial_state)
        else:
            initial_state = PipelineState(pdf_path=pdf_path)
    else:
        initial_state = PipelineState(pdf_path=pdf_path)

    graph = build_pipeline()

    draw_pipeline(graph)

    memory = MemorySaver()
    state = initial_state

    try:
        for state_snapshot in graph.stream(
            initial_state,
            config={"memory": memory, "recursion_limit": 200},
            stream_mode="debug",
        ):
            payload = state_snapshot.get("payload", None)
            if payload:
                input = payload.get("input")
                if input:
                    state = input
    except Exception as e:
        print(f"Got error: {e=}")
    finally:
        output_filename = save_output(pdf_path, state)

    print(f"✅ Pipeline complete. Output saved to: {output_filename}")
