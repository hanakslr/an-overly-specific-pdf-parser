from typing import TypedDict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langchain_core.runnables import RunnableLambda

from extract_structured_pdf import PyMuPDFOutput, extract
from parse_with_llama_parse import LlamaParseOutput, parse

class PipelineState(TypedDict):
    pdf_path: str
    llama_parse_output: LlamaParseOutput
    pymupdf_output: PyMuPDFOutput

def llama_parse(state: PipelineState):
    result = parse(state["pdf_path"])
    return {"llama_parse_output": result}

def pymupdf_extract(state: PipelineState):
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
    import sys
    import json

    pdf_path = sys.argv[1]
    graph = build_pipeline()
    memory = MemorySaver()

    final_state = graph.invoke({"pdf_path": pdf_path}, config={"memory": memory})

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(final_state, f, indent=2, ensure_ascii=False)

    print("✅ Pipeline complete.")