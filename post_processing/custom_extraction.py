from typing import List, Optional

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from post_processing.llama_extract import extract
from post_processing.williston_extraction_schema import ExtractedData
from tiptap.tiptap_models import DocNode, TiptapNode

load_dotenv()


class CustomExtractionState(BaseModel):
    pdf_path: str
    custom_extracted_data: Optional[ExtractedData] = None  # ExtractedData
    prose_mirror_doc: Optional[DocNode] = None
    custom_nodes: List[TiptapNode] = []


def convert_to_prosemirror(state: CustomExtractionState):
    print(" converting custom structures to prosemirror nodes")
    nodes = []

    return {"custom_nodes": nodes}


def extract_custom(state: CustomExtractionState):
    if state.custom_extracted_data:
        print("⏭️   Already extracted.")
        return {}

    return {"custom_extracted_data": extract(state.pdf_path)}


def build_custom_extraction_graph():
    workflow = StateGraph(CustomExtractionState)
    workflow.add_node("extract", extract_custom)
    workflow.add_node("convert", convert_to_prosemirror)
    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "convert")
    workflow.add_edge("convert", END)
    return workflow.compile()
