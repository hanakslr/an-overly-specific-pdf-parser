from typing import List, Optional

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from post_processing.llama_extract import extract
from post_processing.williston_extraction_schema import ExtractedData
from tiptap.tiptap_models import (
    BlockNode,
    DocNode,
    ImageheaderNode,
    ImageNode,
    TiptapNode,
)

load_dotenv()


class CustomExtractionState(BaseModel):
    pdf_path: str
    custom_extracted_data: Optional[ExtractedData] = None  # ExtractedData
    prose_mirror_doc: Optional[DocNode] = None
    custom_nodes: List[TiptapNode] = []


def convert_to_prosemirror(state: CustomExtractionState):
    print(f"{state.prose_mirror_doc=}")
    print(" converting custom structures to prosemirror nodes")
    nodes = []

    #### Hard coding for now to see what the best flow would be

    ## Image header
    prose_mirror_doc = create_image_header(state)

    return {
        "custom_nodes": nodes,
        "prose_mirror_doc": prose_mirror_doc,
    }


def create_image_header(state: CustomExtractionState) -> DocNode:
    """
    Iterate through state.prose_mirror_doc.content and find 3 images in a row.
    Serialize them back into ImageNode and replace them with an ImageheaderNode.
    """
    if not state.prose_mirror_doc or not state.prose_mirror_doc.content:
        return state.prose_mirror_doc

    # There is only one image header, if we have already made it we can return
    if [e for e in state.prose_mirror_doc.content if e.type == "imageHeader"]:
        print("✅ Already did image header")
        return state.prose_mirror_doc

    new_content = []
    i = 0
    content = state.prose_mirror_doc.content
    while i < len(content):
        if (
            i + 2 < len(content)
            and isinstance(content[i], ImageNode)
            and isinstance(content[i + 1], ImageNode)
            and isinstance(content[i + 2], ImageNode)
        ):
            image1 = content[i]
            image2 = content[i + 1]
            image3 = content[i + 2]
            image_header = ImageheaderNode(content=(image1, image2, image3))
            new_content.append(image_header)
            i += 3
        else:
            new_content.append(content[i])
            i += 1
    return state.prose_mirror_doc.model_copy(update={"content": new_content})


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
