import sys
from typing import Optional, Type, Dict, List

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
from etl.chapter_detection import ChapterDetectionResult, ChapterRange, detect_chapter_headers, get_user_approval
from etl.pdf_chapter_extractor import extract_all_approved_chapters
from pipeline_state_helpers import draw_pipeline, resume_from_latest, save_output
from post_processing.custom_extraction import (
    CustomExtractionState,
    build_custom_extraction_graph,
)
from post_processing.insert_images import insert_images
from post_processing.williston_extraction_schema import ExtractedData
from rule_registry.conversion_rules import ConversionRule, ConversionRuleRegistry
from rule_registry.propose.propose_new_rule import propose_new_rule_node
from tiptap.tiptap_models import BaseAttrs, DocNode, TiptapNode


class ChapterPipelineState(BaseModel):
    """State for processing a single chapter"""
    chapter: ChapterRange
    chapter_pdf_path: str
    llama_parse_output: LlamaParseOutput = None
    pymupdf_output: PyMuPDFOutput = None
    custom_extracted_data: Optional[ExtractedData] = None
    zipped_pages: list[ZippedOutputsPage] = None
    prose_mirror_doc: DocNode = None
    custom_nodes: list[TiptapNode] = []
    block_index: Optional[int] = -1
    page_index: Optional[int] = -1
    completed: bool = False
    
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


class PipelineState(BaseModel):
    pdf_path: str
    
    # Multi-chapter support
    chapter_detection_result: Optional[ChapterDetectionResult] = None
    chapters: Dict[str, ChapterPipelineState] = {}  # chapter_id -> state
    current_chapter_id: Optional[str] = None
    processing_mode: str = "single"  # "single" or "multi"
    
    # Legacy single-chapter fields (maintained for backward compatibility)
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
    def current_chapter_state(self) -> Optional[ChapterPipelineState]:
        """Get the current chapter state being processed"""
        if self.current_chapter_id and self.current_chapter_id in self.chapters:
            return self.chapters[self.current_chapter_id]
        return None

    @computed_field
    @property
    def current_block(self) -> Optional[UnifiedBlock]:
        # In multi-chapter mode, delegate to current chapter state
        if self.processing_mode == "multi" and self.current_chapter_state:
            return self.current_chapter_state.current_block
        
        # Legacy single-chapter mode
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
        # In multi-chapter mode, delegate to current chapter state
        if self.processing_mode == "multi" and self.current_chapter_state:
            self.current_chapter_state.update_current_block(new_block)
            return
        
        # Legacy single-chapter mode
        if self.page_index is None or self.block_index is None:
            raise IndexError("page_index or block_index is not set")

        self.zipped_pages[self.page_index].unified_blocks[self.block_index] = new_block


# Multi-chapter processing functions
def detect_chapters(state: PipelineState):
    """Detect chapters in the PDF and get user approval"""
    if state.chapter_detection_result:
        print("⏭️  Chapter detection already completed, skipping...")
        return {}
    
    print("🔍 Detecting chapters...")
    detection_result = detect_chapter_headers(state.pdf_path)
    
    if not detection_result.detected_chapters:
        print("❌ No chapters detected. Processing as single document.")
        return {"processing_mode": "single"}
    
    # Get user approval for detected chapters
    approved_result = get_user_approval(detection_result)
    
    approved_chapters = [c for c in approved_result.detected_chapters if c.approved]
    if not approved_chapters:
        print("❌ No chapters approved. Processing as single document.")
        return {"processing_mode": "single"}
    
    print(f"✅ {len(approved_chapters)} chapters approved for processing")
    return {
        "chapter_detection_result": approved_result,
        "processing_mode": "multi"
    }


def extract_chapters(state: PipelineState):
    """Extract individual chapter PDFs from the main PDF"""
    if not state.chapter_detection_result or state.processing_mode != "multi":
        return {}
    
    if state.chapters:
        print("⏭️  Chapter extraction already completed, skipping...")
        return {}
    
    print("📄 Extracting individual chapter PDFs...")
    extracted_chapters = extract_all_approved_chapters(
        state.pdf_path, 
        state.chapter_detection_result.detected_chapters
    )
    
    # Initialize chapter states
    chapters = {}
    for chapter_range, chapter_pdf_path in extracted_chapters:
        chapter_id = f"chapter_{chapter_range.chapter_number or 'unknown'}_{chapter_range.title.replace(' ', '_')}"
        chapters[chapter_id] = ChapterPipelineState(
            chapter=chapter_range,
            chapter_pdf_path=chapter_pdf_path
        )
    
    return {"chapters": chapters}


def should_process_multi_chapter(state: PipelineState) -> str:
    """Conditional edge to determine if we should process multiple chapters or single"""
    if state.processing_mode == "multi" and state.chapters:
        return "ProcessNextChapter"
    else:
        return "LlamaParse"


def process_next_chapter(state: PipelineState):
    """Set the next unprocessed chapter as current, or finish if all are done"""
    if state.processing_mode != "multi" or not state.chapters:
        return {}
    
    # Find the next unprocessed chapter
    for chapter_id, chapter_state in state.chapters.items():
        if not chapter_state.completed:
            print(f"🔄 Processing chapter: {chapter_state.chapter.title}")
            return {"current_chapter_id": chapter_id}
    
    # All chapters processed
    print("✅ All chapters completed!")
    return {"current_chapter_id": None}


def should_continue_chapter_processing(state: PipelineState) -> str:
    """Conditional edge to determine if we should continue with more chapters"""
    if state.processing_mode != "multi":
        return "END"
    
    # Check if there are more unprocessed chapters
    unprocessed = [c for c in state.chapters.values() if not c.completed]
    if unprocessed:
        return "ProcessNextChapter"
    else:
        return "CombineChapterOutputs"


def mark_chapter_complete(state: PipelineState):
    """Mark the current chapter as completed"""
    if state.current_chapter_state:
        state.current_chapter_state.completed = True
        print(f"✅ Completed chapter: {state.current_chapter_state.chapter.title}")
    return {}


def combine_chapter_outputs(state: PipelineState):
    """Combine all chapter outputs into a final document"""
    if state.processing_mode != "multi" or not state.chapters:
        return {}
    
    print("📖 Combining all chapter outputs...")
    
    # Create a combined document with all chapter content
    combined_content = []
    combined_custom_data = []
    
    for chapter_id in sorted(state.chapters.keys()):
        chapter_state = state.chapters[chapter_id]
        if chapter_state.prose_mirror_doc and chapter_state.prose_mirror_doc.content:
            combined_content.extend(chapter_state.prose_mirror_doc.content)
        
        if chapter_state.custom_extracted_data:
            combined_custom_data.append(chapter_state.custom_extracted_data)
    
    combined_doc = DocNode(content=combined_content)
    
    return {
        "prose_mirror_doc": combined_doc,
        "custom_extracted_data": combined_custom_data[0] if combined_custom_data else None
    }


def is_node_completed(state: PipelineState, step: str) -> bool:
    # Make this smarter as state gets more complicated.
    return hasattr(state, step) and getattr(state, step) is not None


def llama_parse(state: PipelineState):
    # Multi-chapter mode: process current chapter PDF
    if state.processing_mode == "multi" and state.current_chapter_state:
        current_chapter = state.current_chapter_state
        if current_chapter.llama_parse_output:
            print("⏭️  LlamaParse already completed for current chapter, skipping...")
            return {}
        
        print(f"🔄 Running LlamaParse for chapter: {current_chapter.chapter.title}")
        llama_parse_output = parse(current_chapter.chapter_pdf_path)
        
        # Update the current chapter state
        current_chapter.llama_parse_output = llama_parse_output
        return {"chapters": state.chapters}
    
    # Legacy single-chapter mode
    if state.llama_parse_output:
        print("⏭️  LlamaParse already completed, skipping...")
        return {}

    print("🔄 Running LlamaParse...")
    llama_parse_output = parse(state.pdf_path)
    return {"llama_parse_output": llama_parse_output}


def pymupdf_extract(state: PipelineState):
    # Multi-chapter mode: process current chapter PDF
    if state.processing_mode == "multi" and state.current_chapter_state:
        current_chapter = state.current_chapter_state
        if current_chapter.pymupdf_output:
            print("⏭️  PyMuPDF extraction already completed for current chapter, skipping...")
            return {}
        
        print(f"🔄 Running PyMuPDF extraction for chapter: {current_chapter.chapter.title}")
        result = extract(current_chapter.chapter_pdf_path)
        pymupdf_output = PyMuPDFOutput(pages=result)
        
        # Update the current chapter state
        current_chapter.pymupdf_output = pymupdf_output
        return {"chapters": state.chapters}
    
    # Legacy single-chapter mode
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
    # Multi-chapter mode: process current chapter
    if state.processing_mode == "multi" and state.current_chapter_state:
        current_chapter = state.current_chapter_state
        if current_chapter.zipped_pages:
            print("⏭️  Zipping pages already completed for current chapter, skipping...")
            return {}

        print(f"🧹  Zipping pages for chapter: {current_chapter.chapter.title}")

        assert len(current_chapter.llama_parse_output.pages) == len(current_chapter.pymupdf_output.pages)

        pages = []
        for i in range(len(current_chapter.llama_parse_output.pages)):
            lp_page = current_chapter.llama_parse_output.pages[i]
            pm_page = current_chapter.pymupdf_output.pages[i]
            zipped_page = ZippedOutputsPage(
                page=i + 1,
                llama_parse_page=lp_page,
                pymupdf_page=pm_page,
                unified_blocks=match_pages(lp_page, pm_page),
            )
            pages.append(zipped_page)

        current_chapter.zipped_pages = pages
        return {"chapters": state.chapters}
    
    # Legacy single-chapter mode
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
    # Multi-chapter mode: initialize current chapter's doc
    if state.processing_mode == "multi" and state.current_chapter_state:
        current_chapter = state.current_chapter_state
        if current_chapter.prose_mirror_doc:
            print("⏭️  ProseMirror init already completed for current chapter, skipping...")
            return {}
        
        print(f"📄 Initializing ProseMirror doc for chapter: {current_chapter.chapter.title}")
        current_chapter.prose_mirror_doc = DocNode(content=[])
        return {"chapters": state.chapters}
    
    # Legacy single-chapter mode
    if state.prose_mirror_doc:
        print("⏭️  ProseMirror init already completed, skipping...")
        return {}
    return {"prose_mirror_doc": DocNode(content=[])}


def get_next_block(state: PipelineState):
    """
    Get the next block to process. If no more blocks, return None to end the pipeline.
    """
    # Multi-chapter mode: work with current chapter
    if state.processing_mode == "multi" and state.current_chapter_state:
        current_chapter = state.current_chapter_state
        print(f"\n➡️  Getting next block for chapter '{current_chapter.chapter.title}' after {current_chapter.page_index=} {current_chapter.block_index=}")

        # Did we already finish this chapter?
        if current_chapter.block_index is None and current_chapter.page_index is None:
            return {}

        # Check if we have more blocks to process on our current page
        if current_chapter.block_index < len(current_chapter.zipped_pages[current_chapter.page_index].unified_blocks) - 1:
            current_chapter.block_index = current_chapter.block_index + 1
            current_chapter.page_index = max(current_chapter.page_index, 0)
            return {"chapters": state.chapters}

        # No more blocks on the page - got any more pages?
        if current_chapter.page_index < len(current_chapter.zipped_pages) - 1:
            current_chapter.block_index = 0
            current_chapter.page_index = current_chapter.page_index + 1
            return {"chapters": state.chapters}

        # No more pages and no more blocks in this chapter
        current_chapter.block_index = None
        current_chapter.page_index = None
        return {"chapters": state.chapters}
    
    # Legacy single-chapter mode
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


def should_continue_processing_blocks(state: PipelineState) -> str:
    """
    Conditional edge function to determine if we should continue processing blocks.
    Returns 'RuleForBlock' if there is a block we should process, 'InsertImages' otherwise.
    """
    # Multi-chapter mode: check current chapter
    if state.processing_mode == "multi" and state.current_chapter_state:
        current_chapter = state.current_chapter_state
        if current_chapter.block_index is not None and current_chapter.page_index is not None:
            return "RuleForBlock"
        else:
            return "InsertImages"
    
    # Legacy single-chapter mode
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

    # Multi-chapter mode: update current chapter's document
    if state.processing_mode == "multi" and state.current_chapter_state:
        current_chapter = state.current_chapter_state
        updated_content = current_chapter.prose_mirror_doc.content + [constructed_node]
        current_chapter.prose_mirror_doc = current_chapter.prose_mirror_doc.model_copy(
            update={"content": updated_content}
        )
        return {"chapters": state.chapters}
    
    # Legacy single-chapter mode
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

    # Multi-chapter pipeline steps
    builder.add_node("DetectChapters", RunnableLambda(detect_chapters))
    builder.add_node("ExtractChapters", RunnableLambda(extract_chapters))
    builder.add_node("ProcessNextChapter", RunnableLambda(process_next_chapter))
    builder.add_node("MarkChapterComplete", RunnableLambda(mark_chapter_complete))
    builder.add_node("CombineChapterOutputs", RunnableLambda(combine_chapter_outputs))

    # Core processing steps (work for both single and multi-chapter)
    builder.add_node("LlamaParse", RunnableLambda(llama_parse))
    builder.add_node("PyMuPDFExtract", RunnableLambda(pymupdf_extract))
    builder.add_node("ZipOutputs", RunnableLambda(zip_outputs))
    builder.add_node("InitProseMirror", RunnableLambda(init_prose_mirror_doc))
    builder.add_node("GetNextBlock", RunnableLambda(get_next_block))
    builder.add_node("RuleForBlock", get_rule_for_block)
    builder.add_node("ProposeNewRule", propose_new_rule_node)
    builder.add_node("EmitBlock", emit_block)
    builder.add_node("InsertImages", insert_images)
    builder.add_node("CustomNodes", custom_extraction_subgraph)
    builder.add_node("UpdateLiveEditor", RunnableLambda(update_live_editor))

    # Entry point: detect chapters first
    builder.set_entry_point("DetectChapters")
    
    # Chapter detection flow
    builder.add_edge("DetectChapters", "ExtractChapters")
    
    # Conditional: multi-chapter vs single-chapter processing
    builder.add_conditional_edges(
        "ExtractChapters",
        should_process_multi_chapter,
        {"ProcessNextChapter": "ProcessNextChapter", "LlamaParse": "LlamaParse"}
    )

    # Multi-chapter processing loop
    builder.add_edge("ProcessNextChapter", "LlamaParse")

    # Core pipeline (same for both modes)
    builder.add_edge("LlamaParse", "PyMuPDFExtract")
    builder.add_edge("PyMuPDFExtract", "ZipOutputs")
    builder.add_edge("ZipOutputs", "InitProseMirror")
    builder.add_edge("InitProseMirror", "GetNextBlock")

    # Block processing loop
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
    
    # After processing all blocks in a chapter
    builder.add_edge("InsertImages", "UpdateLiveEditor")
    builder.add_edge("InsertImages", "CustomNodes")
    builder.add_edge("CustomNodes", "UpdateLiveEditor")
    
    # Multi-chapter: mark chapter complete and continue with next chapter
    builder.add_edge("CustomNodes", "MarkChapterComplete")
    
    # Conditional: continue with next chapter or finish
    builder.add_conditional_edges(
        "MarkChapterComplete",
        should_continue_chapter_processing,
        {
            "ProcessNextChapter": "ProcessNextChapter",
            "CombineChapterOutputs": "CombineChapterOutputs",
            "END": END
        }
    )
    
    # Final step: combine all chapter outputs and finish
    builder.add_edge("CombineChapterOutputs", "UpdateLiveEditor")
    builder.add_edge("CombineChapterOutputs", END)

    return builder.compile()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <pdf_path> [options]")
        print("Options:")
        print("  --resume-latest          Resume from latest saved state")
        print("  --single-chapter         Force single-chapter mode (skip chapter detection)")
        print("  --chapter <chapter_id>   Process only specific chapter (requires existing chapter state)")
        print("  --list-chapters         List available chapters from previous runs")
        sys.exit(1)

    pdf_path = sys.argv[1]
    resume_latest = "--resume-latest" in sys.argv
    single_chapter = "--single-chapter" in sys.argv
    list_chapters = "--list-chapters" in sys.argv
    
    specific_chapter = None
    if "--chapter" in sys.argv:
        chapter_idx = sys.argv.index("--chapter")
        if chapter_idx + 1 < len(sys.argv):
            specific_chapter = sys.argv[chapter_idx + 1]

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

    # Handle list chapters
    if list_chapters:
        if initial_state.chapters:
            print("📚 Available chapters:")
            for chapter_id, chapter_state in initial_state.chapters.items():
                status = "✅ Completed" if chapter_state.completed else "⏳ Pending"
                print(f"  {chapter_id}: {chapter_state.chapter.title} ({status})")
        else:
            print("❌ No chapters found. Run without --list-chapters to detect chapters.")
        sys.exit(0)

    # Handle specific chapter processing
    if specific_chapter:
        if not initial_state.chapters or specific_chapter not in initial_state.chapters:
            print(f"❌ Chapter '{specific_chapter}' not found. Use --list-chapters to see available chapters.")
            sys.exit(1)
        
        print(f"🎯 Processing specific chapter: {specific_chapter}")
        initial_state.processing_mode = "multi"
        initial_state.current_chapter_id = specific_chapter
        # Reset chapter completion to allow reprocessing
        initial_state.chapters[specific_chapter].completed = False

    # Force single-chapter mode if requested
    if single_chapter:
        print("📄 Forcing single-chapter mode")
        initial_state.processing_mode = "single"

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
