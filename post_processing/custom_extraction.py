import re
from typing import List, Optional

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from post_processing.llama_extract import extract
from post_processing.williston_extraction_schema import (
    ExtractedData,
)
from schema.portable_schema import FactItemBlock, GoalItemBlock
from schema.tiptap_models import (
    BlockNode,
    DocNode,
    HeadingNode,
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


def split_facts(text: str) -> List[str]:
    """Parse an enumerated *Three Things* paragraph into individual title/body strings.

    The source ``text`` is expected to contain *exactly* three facts in the form::

        1. SOME HEADING IN ALL CAPS

           Body text possibly spanning multiple lines.

        2. ANOTHER HEADING

           Body text …

        3. THIRD HEADING

           Body text …

    The function returns a list of six strings ordered as::

        [heading1, body1, heading2, body2, heading3, body3]

    If the parsing does not yield six parts an ``Exception`` is raised so that the
    calling code can fail fast and draw attention to unexpected input.
    """

    # Normalise new-lines for predictable processing.
    text = text.replace("\r\n", "\n")

    # Pattern to capture an item number followed by a heading (everything up to the
    # end of that line).
    item_pattern = re.compile(r"(^|\n)\s*(\d+)\.\s+([^\n]+)", re.MULTILINE)

    matches = list(item_pattern.finditer(text))

    if len(matches) != 3:
        raise Exception(
            f"Expected to find exactly 3 numbered headings, found {len(matches)}.\n"
            f"Text provided:\n{text}"
        )

    parts: List[str] = []

    for idx, match in enumerate(matches):
        # Extract the heading (without the leading number and dot)
        heading = match.group(3).strip()

        # Everything after the heading until the start of the next numbered heading
        # (or end of the text for the last item) is the body.
        body_start = match.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()

        # Collapse internal whitespace/new-lines to single spaces for cleanliness.
        body = re.sub(r"\s+", " ", body)

        # Remove any leading bullet/indent markup.
        body = body.lstrip("-• ")

        parts.extend([heading, body])

    if len(parts) != 6:
        raise Exception(
            f"Expected to get 6 results splitting facts - got {len(parts)} ({parts})"
        )

    return parts


def convert_to_prosemirror(state: CustomExtractionState):
    print(" converting custom structures to prosemirror nodes")
    nodes = []

    #### Hard coding for now to see what the best flow would be

    if not state.prose_mirror_doc or not state.prose_mirror_doc.content:
        return {}

    if not state.custom_extracted_data:
        return {}

    ## Image header
    content = create_image_header(state.prose_mirror_doc.content)
    content = convert_goals(content)

    prose_mirror_doc = state.prose_mirror_doc.model_copy(update={"content": content})

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

            new_content.append(image_header)
            i += 3
        else:
            new_content.append(content[i])
            i += 1
    return new_content


def convert_goals(content: List[BlockNode]) -> List[BlockNode]:
    """
    ITerate through our blocks until we find a header where content[0].text.starts with Goals: In 2050.
    Then convert the following elements into a table.
    There should be 3 headings and paragraphs for Livable, Resilient, Equitable
    """
    new_content = []
    i = 0
    while i < len(content):
        block = content[i]
        print(i)
        if block.type == "heading" and block.content[0].text.startswith(
            "Goals: In 2050"
        ):
            goal_items = []
            for j, trait in enumerate(["livable", "resilient", "equitable"]):
                potential_heading = content[i + (j * 2) + 1]
                potential_body = content[i + (j * 2) + 2]
                if (
                    potential_heading.type == "heading"
                    and potential_heading.get_text().lower() == trait
                    and isinstance(potential_body, ParagraphNode)
                ):
                    goal_items.append(
                        GoalItemBlock(
                            content=[potential_body],
                            attrs=GoalItemBlock.Attrs(trait=trait),
                        )
                    )
                    continue
                else:
                    raise Exception("Unexpected format for goals table")

            new_content.extend(goal_items)
            i += 7

        elif block.type == "heading" and block.content[0].text.startswith(
            "Three Things"
        ):
            table_name = block.content[0].text.lower().strip()
            n = content[i + 1]

            if len(n.content) != 1 and n.type != "paragraph":
                raise Exception(f"Expected fact content to be length 1 - got {n}")
            res = split_facts(n.content[0].text)

            for j in range(3):
                title = re.sub(r"^/d+. ", "", res[j * 2])
                new_content.append(
                    FactItemBlock(
                        attrs=FactItemBlock.Attrs(
                            label=str(j),
                            collection="facts"
                            if table_name == "three things to know"
                            else "public_engagement",
                        ),
                        content=[
                            HeadingNode(
                                attrs=HeadingNode.Attrs(level=3),
                                content=[TextNode(text=title.strip())],
                            ),
                            ParagraphNode(content=[TextNode(text=res[(j * 2) + 1])]),
                        ],
                    )
                )

            i += 2

        else:
            new_content.append(content[i])
            i += 1

    return new_content


def remove_osa_table_and_citations(content: List[BlockNode]) -> List[BlockNode]:
    new_content = []
    i = 0
    while i < len(content):
        block = content[i]
        if block.type == "heading" and block.content[0].text.startswith(
            "Goals: In 2050"
        ):
            pass
        else:
            new_content.append(content[i])

    return new_content


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
