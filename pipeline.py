import sys

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from extract_structured_pdf import PyMuPDFOutput, extract
from parse_with_llama_parse import LlamaParseOutput, parse
from pipeline_state_helpers import draw_pipeline, resume_from_latest, save_output
from rule_registry import ConversionRuleRegistry
from tiptap_models import DocNode
from zip_llama_pymupdf import UnifiedBlock, ZippedOutputsPage, match_blocks


class PipelineState(BaseModel):
    pdf_path: str
    llama_parse_output: LlamaParseOutput = None
    pymupdf_output: PyMuPDFOutput = None

    zipped_page: ZippedOutputsPage = None

    prose_mirror_doc: DocNode = None

    block_index: int = 0
    current_block: UnifiedBlock = None


def is_node_completed(state: PipelineState, step: str) -> bool:
    # Make this smarter as state gets more complicated.
    return hasattr(state, step) and getattr(state, step) is not None


def llama_parse(state: PipelineState):
    # Check if already completed
    if is_node_completed(state, "llama_parse_output"):
        print("⏭️  LlamaParse already completed, skipping...")
        return {}

    print("🔄 Running LlamaParse...")
    result = parse(state.pdf_path)
    # Convert the list of dictionaries to LlamaParseOutput
    # The parse function returns a list, but we expect a single LlamaParseOutput
    llama_parse_output = LlamaParseOutput(**result[0])
    return {"llama_parse_output": llama_parse_output}


def pymupdf_extract(state: PipelineState):
    # Check if already completed
    if is_node_completed(state, "pymupdf_output"):
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
    # Just for page 1 right now.

    lp_page = state.llama_parse_output.pages[0]
    pm_page = state.pymupdf_output.pages[0]
    zipped_page = ZippedOutputsPage(
        page=1,
        llama_parse_page=lp_page,
        pymupdf_page=pm_page,
        unified_blocks=match_blocks(lp_page, pm_page),
    )

    return {"zipped_page": zipped_page}


def init_prose_mirror_doc(state: PipelineState):
    return {"prose_mirror_doc": DocNode(content=[])}


def get_next_block(state: PipelineState):
    """
    Get the next block to process. If no more blocks, return None to end the pipeline.
    """
    # Initialize block index if not present

    # Check if we have more blocks to process
    if state.block_index >= len(state.zipped_page.unified_blocks):
        # No more blocks, end the pipeline
        return {}

    # Get the current block
    current_block = state.zipped_page.unified_blocks[state.block_index]

    # Return the current block and increment the index
    return {"current_block": current_block, "block_index": state.block_index + 1}


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

        if pymupdf_input and rule.match_condition(
            state.current_block.llama_item, pymupdf_input
        ):
            # Found a matching rule
            return {
                "current_block": state.current_block.model_copy(
                    update={"conversion_rule": rule.id}
                )
            }

    # No matching rule found
    return {}


def should_emit_block(state: PipelineState) -> str:
    """
    Conditional edge function to determine next step after rule checking.
    Returns 'EmitBlock' if a conversion rule was found, 'END' otherwise.
    """
    if state.current_block.conversion_rule is not None:
        return "EmitBlock"
    else:
        return "END"


def should_continue_processing(state: PipelineState) -> bool:
    """
    Conditional edge function to determine if we should continue processing blocks.
    Returns 'GetNextBlock' if there are more blocks, 'END' otherwise.
    """
    # Check if we have more blocks to process
    if state.block_index < len(state.zipped_page.unified_blocks):
        return "GetNextBlock"
    else:
        return "END"


def make_rule_for_block(state: PipelineState):
    pass


def emit_block(state: PipelineState):
    """
    Construct a node using the conversion rule and add it to the prose mirror document.
    """
    # Get the conversion rule by ID
    rule_class = ConversionRuleRegistry._rules.get(state.current_block.conversion_rule)
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
    constructed_node = rule.construct_node(
        state.current_block.llama_item, pymupdf_input
    )

    # Add the constructed node to the prose mirror document content
    updated_content = state.prose_mirror_doc.content + [constructed_node]

    return {
        "prose_mirror_doc": state.prose_mirror_doc.model_copy(
            update={"content": updated_content}
        )
    }


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

    # Now we want to parse the contents
    builder.add_node("GetNextBlock", RunnableLambda(get_next_block))
    builder.add_node("RuleForBlock", get_rule_for_block)
    builder.add_node("MakeRuleForBlock", make_rule_for_block)
    builder.add_node("EmitBlock", emit_block)

    builder.add_edge("InitProseMirror", "GetNextBlock")
    builder.add_edge("GetNextBlock", "RuleForBlock")
    builder.add_conditional_edges(
        "RuleForBlock", should_emit_block, {"EmitBlock": "EmitBlock", "END": END}
    )
    builder.add_conditional_edges(
        "EmitBlock",
        should_continue_processing,
        {"GetNextBlock": "GetNextBlock", "END": END},
    )

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
        else:
            initial_state = PipelineState(pdf_path=pdf_path)
    else:
        initial_state = PipelineState(pdf_path=pdf_path)

    graph = build_pipeline()

    draw_pipeline(graph)

    memory = MemorySaver()

    final_state = graph.invoke(initial_state, config={"memory": memory})
    output_filename = save_output(pdf_path, final_state)

    print(f"✅ Pipeline complete. Output saved to: {output_filename}")
