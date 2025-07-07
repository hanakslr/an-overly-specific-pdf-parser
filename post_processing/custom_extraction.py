import re
from typing import List, Optional

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from post_processing.extract_strategies import extract_strategies
from post_processing.llama_extract import extract
from post_processing.williston_extraction_schema import (
    ActionTable,
    ExtractedData,
    ObjectiveItem,
)
from schema.block import Block
from schema.portable_schema import (
    ActionTableBlock,
    CustomBlock,
    FactItemBlock,
    GoalItemBlock,
)
from schema.tiptap_models import (
    HeadingNode,
    ImageheaderNode,
    ImageNode,
    ParagraphNode,
    TextNode,
)

load_dotenv()


class CustomExtractionState(BaseModel):
    pdf_path: str
    custom_extracted_data: Optional[ExtractedData] = None  # ExtractedData
    blocks: list[Block] = []


def extract_separate_fact_paragraphs(
    content: List[Block], start_index: int, table_name: str
) -> tuple[bool, List[FactItemBlock], int]:
    """
    Try to extract facts from 6 separate paragraphs following the pattern:
    1. CAPITALIZED HEADING
    Body text
    2. CAPITALIZED HEADING
    Body text
    3. CAPITALIZED HEADING
    Body text

    Returns:
        tuple: (success, fact_items, blocks_consumed)
    """
    if start_index + 6 >= len(content):
        return False, [], 0

    # Check if we have 6 paragraphs in the expected pattern
    fact_data = []

    for j in range(3):
        heading_idx = start_index + 1 + (j * 2)
        body_idx = start_index + 2 + (j * 2)

        if heading_idx >= len(content) or body_idx >= len(content):
            return False, [], 0

        heading_block = content[heading_idx]
        body_block = content[body_idx]

        # Check if heading block is a paragraph with numbered, capitalized content
        if heading_block.get_text().upper() == heading_block.get_text():
            # Check if body block is a paragraph with normal text
            if body_block.type == "paragraph" and len(body_block.content) == 1:
                heading_text = heading_block.content[0].text.strip()

                body_text = body_block.content[0].text.strip()

                fact_data.append((heading_text, body_text))
            else:
                return False, [], 0
        else:
            return False, [], 0

    if len(fact_data) != 3:
        return False, [], 0

    # Create fact items from the 6 separate paragraphs
    fact_items = []
    for j, (heading_text, body_text) in enumerate(fact_data):
        fact_items.append(
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
                        content=[TextNode(text=heading_text)],
                    ),
                    ParagraphNode(content=[TextNode(text=body_text)]),
                ],
            )
        )

    return True, fact_items, 6  # 6 paragraphs consumed TODO - this may be off by one


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
    #### Hard coding for now to see what the best flow would be

    if not state.blocks:
        return {}

    if not state.custom_extracted_data:
        return {}

    ## Image header
    new_blocks = create_image_header(state.blocks)
    new_blocks = convert_goals(new_blocks)

    if not any([e for e in new_blocks if e.type == "action_table"]):
        new_blocks = extract_osa_table(new_blocks)

    new_blocks = citations(state, new_blocks)

    return {
        "blocks": new_blocks,
    }


def citations(state: CustomExtractionState, blocks: List[Block]) -> List[Block]:
    """
    We extracted citations with LlamaExtract. They may be scattered everywhere, OR
    all at the end in End Notes. Remove endnote if they exist. Add a block for citation
    if they exist.
    """
    if not state.custom_extracted_data.citations:
        return blocks

    if [e for e in blocks if e.type == "custom" and e.attrs.type == "citations"]:
        print("✅ Already did citations")
        return blocks

    new_content = []
    i = 0

    while i < len(blocks):
        if (
            blocks[i].type == "heading"
            and blocks[i].content[0].text.lower() == "end notes"
        ):
            return new_content

        new_content.append(blocks[i])
        i += 1
    return new_content


def create_image_header(content: List[Block]) -> List[Block]:
    """
    Iterate through content and find 3 images in a row.
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


def convert_goals(content: List[Block]) -> List[Block]:
    """
    ITerate through our blocks until we find a header where content[0].text.starts with Goals: In 2050.
    Then convert the following elements into a table.
    There should be 3 headings and paragraphs for Livable, Resilient, Equitable
    """
    new_content = []
    i = 0
    while i < len(content):
        block = content[i]
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

            # Try the original approach first - single paragraph that can be split
            try:
                if len(n.content) == 1 and n.type == "paragraph":
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
                                    ParagraphNode(
                                        content=[TextNode(text=res[(j * 2) + 1])]
                                    ),
                                ],
                            )
                        )

                    i += 2
                    continue
                else:
                    raise Exception(
                        "Not a single paragraph, trying alternative approach"
                    )

            except Exception:
                # Alternative approach - try to extract from 6 separate paragraphs
                success, fact_items, blocks_consumed = extract_separate_fact_paragraphs(
                    content, i, table_name
                )

                print(f"{success=}\n{fact_items=}\n{blocks_consumed=}")

                if success:
                    new_content.extend(fact_items)
                    i += 1 + blocks_consumed  # Skip the heading + consumed paragraphs
                    continue

                # If neither approach worked, raise an exception
                raise Exception(
                    f"Could not parse Three Things section. Expected either a single paragraph that can be split, or 6 separate paragraphs in the pattern: numbered heading, body text (x3). Got: {[content[i + j].type for j in range(min(7, len(content) - i))]}"
                )

        else:
            new_content.append(content[i])
            i += 1

    return new_content


def extract_osa_table(blocks: List[Block]) -> List[Block]:
    new_content = []
    i = 0

    while i < len(blocks):
        block = blocks[i]
        if (
            block.type == "heading"
            and block.content[0].text.lower().replace(",", "")
            == "objectives strategies and actions"
        ):
            i += 1
            objective_heading_block = blocks[i]

            assert (
                objective_heading_block.type == "heading"
                and objective_heading_block.content[0].text == "Objectives"
            ), "Unexpected objectives block"

            objectives: list[ObjectiveItem] = []  # label, text

            i += 1
            while blocks[i].content[0].text != "Strategies":
                # find all the objectives until we hit the strategies header

                if (
                    blocks[i].type == "heading"
                    and re.search(r"^\d+.[A-Z]+$", blocks[i].content[0].text)
                    and blocks[i + 1].type == "paragraph"
                ):
                    # found one
                    objectives.append(
                        ObjectiveItem(
                            label=blocks[i].content[0].text,
                            text=blocks[i + 1].content[0].text,
                        )
                    )
                    i += 2
                elif blocks[i].type == "paragraph" and re.search(
                    r"(\*\*)?(\d+.[A-Z])(\*\*)?(.*?)(?:\\n|$)",
                    blocks[i].content[0].text,
                ):
                    text = blocks[i].content[0].text
                    print(text)
                    pattern = r"(?:\*\*)?(\d+.[A-Z])(?:\*\*)?(.*?)(?=(\n\n|\Z))"
                    matches = re.findall(pattern, text, re.DOTALL)
                    for match in matches:
                        objectives.append(
                            ObjectiveItem(
                                label=match[0].strip(),
                                text=match[1].strip(),
                            )
                        )
                    i += 1
                else:
                    raise Exception(
                        f"Unexpected objectives {blocks[i]} and {blocks[i + 1]}"
                    )

            i += 1

            strategies_text = []

            while i < len(blocks) and not (
                blocks[i].type == "heading" and blocks[i].get_text() == "End Notes"
            ):
                # All of our strategies and actions.
                # Get them together and just pass them to an LLM
                print("appending strat text")
                strategies_text.append(blocks[i].get_text())
                i += 1

            # Pass the actions and strategies to an llm for categorization.
            print("Extracting strategies w LLM")
            strategies = extract_strategies("\n".join(strategies_text))

            print(f"Making new action block with:\n{strategies=}\n{objectives=}")
            new_content.append(
                ActionTableBlock(
                    content=ActionTable(strategies=strategies, objectives=objectives),
                )
            )

        else:
            new_content.append(block)
            i += 1

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
