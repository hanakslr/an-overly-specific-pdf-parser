import sys
from typing import TypedDict

from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

from extract_structured_pdf import PyMuPDFOutput, extract
from parse_with_llama_parse import LlamaParseOutput, parse
from pipeline_state_helpers import draw_pipeline, resume_from_latest, save_output


class PipelineState(TypedDict):
    pdf_path: str
    llama_parse_output: LlamaParseOutput
    pymupdf_output: PyMuPDFOutput


def is_node_completed(state, step):
    # Make this smarter as state gets more complicated.
    return step in state and state[step]


def llama_parse(state: PipelineState):
    # Check if already completed
    if is_node_completed(state, "llama_parse_output"):
        print("⏭️  LlamaParse already completed, skipping...")
        return {}

    print("🔄 Running LlamaParse...")
    result = parse(state["pdf_path"])
    return {"llama_parse_output": result}


def pymupdf_extract(state: PipelineState):
    # Check if already completed
    if is_node_completed(state, "pymupdf_output"):
        print("⏭️  PyMuPDF extraction already completed, skipping...")
        return {}

    print("🔄 Running PyMuPDF extraction...")
    result = extract(state["pdf_path"])
    return {"pymupdf_output": result}


def build_pipeline():
    builder = StateGraph(state_schema=PipelineState)

    builder.add_node("LlamaParse", RunnableLambda(llama_parse))
    builder.add_node("PyMuPDFExtract", RunnableLambda(pymupdf_extract))

    builder.set_entry_point("LlamaParse")
    builder.add_edge("LlamaParse", "PyMuPDFExtract")

    builder.set_finish_point("PyMuPDFExtract")

    return builder.compile()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <pdf_path> [--resume-latest]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    resume_latest = "--resume-latest" in sys.argv

    # Initialize state
    if resume_latest:
        initial_state = resume_from_latest(pdf_path)
    else:
        initial_state = {"pdf_path": pdf_path}

    graph = build_pipeline()

    draw_pipeline(graph)

    memory = MemorySaver()

    final_state = graph.invoke(initial_state, config={"memory": memory})
    output_filename = save_output(pdf_path, final_state)

    print(f"✅ Pipeline complete. Output saved to: {output_filename}")
