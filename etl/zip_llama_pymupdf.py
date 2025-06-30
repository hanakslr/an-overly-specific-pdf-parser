import json
import uuid
from typing import Optional

from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from llama_cloud_services.parse.types import Page, PageItem
from pydantic import BaseModel, Field

from etl.pymupdf_parse import PageResult, PyMuPdfItem


class UnifiedBlock(BaseModel):
    match_method: str
    llama_item: PageItem
    fitz_items: Optional[list[PyMuPdfItem]]
    conversion_rule: Optional[str] = None

    id: str  # UUID


class ZippedOutputsPage(BaseModel):
    page: int

    llama_parse_page: Page
    pymupdf_page: PageResult

    unified_blocks: list[UnifiedBlock] = None


# For LLM-based matching
class MatchedIds(BaseModel):
    llama_id: int = Field(
        description="The id of the LlamaParse item in the provided list."
    )
    pymupdf_ids: Optional[list[int]] = Field(
        description="A list of ids for the matching PyMuPDF items from the provided list."
    )


class MatchingResult(BaseModel):
    matches: list[MatchedIds] = Field(description="The list of all matches found.")


def match_pages(llama_parse_page: Page, pymupdf_page: PageResult) -> list[UnifiedBlock]:
    """
    Given the examples below, return a list of UnifiedBlocks by prefiltering the lists
    of llamaparse items down to type= headings or text, and then
    """
    llama_items_to_match = [
        {"id": index, "text": item.value}
        for index, item in enumerate(llama_parse_page.items)
        if item.type in ["heading", "text"]
    ]

    pymupdf_items_to_match = [
        {"id": index, "text": item.text}
        for index, item in enumerate(pymupdf_page.content)
        if item.type == "text"
    ]

    my_llm = ChatOpenAI(model="gpt-4o", temperature=0)
    output_parser = PydanticOutputParser(pydantic_object=MatchingResult)

    prompt_template = """
You are an expert at matching text blocks from two different sources of a PDF document.
One source is from LlamaParse, and the other is from PyMuPDF.
Your task is to match each item from the LlamaParse output to one or more items from the PyMuPDF output.

- The items are mostly in the same order in both lists.
- Each PyMuPDF item can only be assigned to one LlamaParse item.
- Some LlamaParse items might not have a corresponding PyMuPDF item. In this case, pymupdf_indexes should be null or an empty list.
- You MUST assign every PyMuPDF item to a LlamaParse item.
- For each LlamaParse item you were given, you must provide a corresponding match object in your response. The `llama_index` in your response should be the index of the item in the input list, NOT the original index contained in the item object.

Here are the items from LlamaParse (with their original index):
{llama_items}

Here are the items from PyMuPDF (with their original index):
{pymupdf_items}

Based on the text content, please provide the matching pairs of indexes.

{format_instructions}
"""
    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["llama_items", "pymupdf_items"],
        partial_variables={
            "format_instructions": output_parser.get_format_instructions()
        },
    )

    chain = prompt | my_llm | output_parser

    result: MatchingResult = chain.invoke(
        {
            "llama_items": json.dumps(llama_items_to_match, indent=2),
            "pymupdf_items": json.dumps(pymupdf_items_to_match, indent=2),
        }
    )

    # Create a map from original llama_item index to list of pymupdf original indexes
    llama_to_pymupdf_map = {}
    for match in result.matches:
        if match.pymupdf_ids:
            llama_to_pymupdf_map[match.llama_id] = [i for i in match.pymupdf_ids]

    unified_blocks = []
    for i, llama_item in enumerate(llama_parse_page.items):
        fitz_items = []
        match_method = "none"
        if i in llama_to_pymupdf_map:
            match_method = "llm"
            pymupdf_indices = llama_to_pymupdf_map[i]
            fitz_items = [pymupdf_page.content[j] for j in pymupdf_indices]

        unified_blocks.append(
            UnifiedBlock(
                match_method=match_method,
                llama_item=llama_item,
                fitz_items=fitz_items,
                id=str(uuid.uuid4()),
            )
        )

    return unified_blocks
