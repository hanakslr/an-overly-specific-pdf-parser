from typing import List, Optional

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from post_processing.llama_extract import extract
from post_processing.williston_extraction_schema import ActionItem, ExtractedData
from tiptap.tiptap_models import (
    ActionitemNode,
    BlockNode,
    DocNode,
    ImageheaderNode,
    ImageNode,
    ParagraphNode,
    TextNode,
    TiptapNode,
)

load_dotenv()


class CustomExtractionState(BaseModel):
    pdf_path: str
    custom_extracted_data: Optional[ExtractedData] = None  # ExtractedData
    prose_mirror_doc: Optional[DocNode] = None
    custom_nodes: List[TiptapNode] = []


def convert_to_prosemirror(state: CustomExtractionState):
    print(" converting custom structures to prosemirror nodes")
    nodes = []

    #### Hard coding for now to see what the best flow would be

    if not state.prose_mirror_doc or not state.prose_mirror_doc.content:
        return {}

    ## Image header
    content = create_image_header(state.prose_mirror_doc.content)

    if state.custom_extracted_data.objectives_strategies_actions_table.actions:
        content = create_action_items(
            content,
            state.custom_extracted_data.objectives_strategies_actions_table.actions,
        )

    prose_mirror_doc = state.prose_mirror_doc.model_copy(update={"content": content})

    print(f"New {prose_mirror_doc=}")

    return {
        "custom_nodes": nodes,
        "prose_mirror_doc": prose_mirror_doc,
    }


def create_image_header(content: List[BlockNode]) -> List[BlockNode]:
    """
    Iterate through state.prose_mirror_doc.content and find 3 images in a row.
    If the following element is a level 1 header, insert the ImageheaderNode after the header.
    If there's a paragraph with "[Three photographs..." text after the heading, skip it.
    Otherwise, replace the 3 images with an ImageheaderNode.
    """
    # There is only one image header, if we have already made it we can return
    if [e for e in content if e.type == "imageHeader"]:
        print("✅ Already did image header")
        return content

    new_content = []
    i = 0
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

            # Check if the next element after the 3 images is a level 1 heading
            new_content.append(image_header)
            i += 3
        else:
            new_content.append(content[i])
            i += 1
    return new_content


def create_action_items(
    content: List[BlockNode], actions: List[ActionItem]
) -> List[BlockNode]:
    if [e for e in content if e.type == "actionItem"]:
        print("✅ Already did action items")
        return []

    for action in actions:
        content.append(
            ActionitemNode(
                content=ParagraphNode(content=[TextNode(text=action.text)]),
                attrs=ActionitemNode.Attrs(
                    strategy=action.strategy,
                    label=action.label,
                    responsibility=action.responsibility,
                    timeframe=action.timeframe,
                    cost=action.cost,
                ),
            )
        )

    print(f"Found {len(actions)} action items")
    return content


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
