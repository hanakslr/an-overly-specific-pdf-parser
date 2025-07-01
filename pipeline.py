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
from post_processing.custom_extraction import (
    CustomExtractionState,
    build_custom_extraction_graph,
)
from post_processing.insert_images import insert_images
from post_processing.williston_extraction_schema import ExtractedData
from rule_registry.conversion_rules import ConversionRule, ConversionRuleRegistry
from rule_registry.propose.propose_new_rule import propose_new_rule_node
from schema.tiptap_models import BaseAttrs, DocNode, TiptapNode


class PipelineState(BaseModel):
    pdf_path: str
    llama_parse_output: LlamaParseOutput = None
    pymupdf_output: PyMuPDFOutput = None

    custom_extracted_data: Optional[ExtractedData] = None

    zipped_pages: list[ZippedOutputsPage] = None

    prose_mirror_doc: DocNode = None
    custom_nodes: list[TiptapNode] = []

    block_index: Optional[int] = -1
    page_index: Optional[int] = -1

    @computed_field
    @property
    def current_block(self) -> Optional[UnifiedBlock]:
        if not self.zipped_pages:
            return None

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
    llama_parse_output = parse(state.pdf_path)
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


def custom_extraction_subgraph(state: PipelineState):
    """
    Run the custom extraction subgraph to find and convert
    special structures from the document into prosemirror nodes.
    """
    print("✨ Running custom extraction subgraph")
    custom_extraction_graph = build_custom_extraction_graph()
    initial_state = CustomExtractionState(
        pdf_path=state.pdf_path,
        prose_mirror_doc=state.prose_mirror_doc,
        custom_extracted_data=state.custom_extracted_data,
    )
    final_state = custom_extraction_graph.invoke(initial_state)
    final_state_model = CustomExtractionState(**final_state)

    return {
        "custom_extracted_data": final_state_model.custom_extracted_data,
        "prose_mirror_doc": final_state_model.prose_mirror_doc,
    }


def update_live_editor(state: PipelineState):
    if state.prose_mirror_doc:
        print("👀  Updating live editor")
        try:
            update_document(state.prose_mirror_doc)
        except Exception as e:
            print(f"Something went wrong: {e}")


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
    builder.add_node("CustomNodes", custom_extraction_subgraph)

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
    builder.add_edge("InsertImages", "CustomNodes")
    builder.add_edge("CustomNodes", "UpdateLiveEditor")
    builder.add_edge("CustomNodes", END)

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
            config={"memory": memory, "recursion_limit": 500},
            stream_mode="debug",
        ):
            ## There is a state bug here. It only store the state input so
            ## the output of the last job wont be saved.
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
