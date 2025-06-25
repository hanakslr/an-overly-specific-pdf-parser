import sys

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from llama_cloud_services.parse.types import Page
from pydantic import BaseModel

from extract_structured_pdf import PageResult, PyMuPDFOutput, extract
from parse_with_llama_parse import LlamaParseOutput, parse
from pipeline_state_helpers import draw_pipeline, resume_from_latest, save_output
from tiptap_models import DocNode


class ZippedOutputsPage(BaseModel):
    page: int

    llama_parse_page: Page
    pymupdf_page: PageResult


class PipelineState(BaseModel):
    pdf_path: str
    llama_parse_output: LlamaParseOutput = None
    pymupdf_output: PyMuPDFOutput = None

    zipped_page: ZippedOutputsPage = None

    prose_mirror_doc: DocNode = None


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

    zipped_page = ZippedOutputsPage(
        page=1,
        llama_parse_page=state.llama_parse_output.pages[0],
        pymupdf_page=state.pymupdf_output.pages[0],
    )

    return {"zipped_page": zipped_page}


def init_prose_mirror_doc(state: PipelineState):
    return {"prose_mirror_doc": DocNode(content=[])}


def get_next_block(state: PipelineState):
    pass


def get_rule_for_block(state: PipelineState):
    pass


def make_rule_for_block(state: PipelineState):
    pass


def emit_block(state: PipelineState):
    pass


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
    builder.add_node("GetNextBlock", get_next_block)
    builder.add_node("RuleForBlock", get_rule_for_block)
    builder.add_node("MakeRuleForBlock", make_rule_for_block)
    builder.add_node("EmitBlock", emit_block)

    builder.add_edge("InitProseMirror", "GetNextBlock")
    builder.add_edge("GetNextBlock", "RuleForBlock")
    builder.add_edge("RuleForBlock", "EmitBlock")
    builder.add_edge("EmitBlock", END)

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
