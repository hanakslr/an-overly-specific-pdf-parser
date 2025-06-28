import uuid
from difflib import SequenceMatcher
from typing import Optional

from llama_cloud_services.parse.types import Page, PageItem
from pydantic import BaseModel

from etl.pymupdf_parse import Item, PageResult, PyMuPdfItem, TextItem


class UnifiedBlock(BaseModel):
    match_method: str
    llama_item: PageItem
    fitz_items: Optional[list[Item]]
    conversion_rule: Optional[str] = None

    id: str  # UUID


class ZippedOutputsPage(BaseModel):
    page: int

    llama_parse_page: Page
    pymupdf_page: PageResult

    unified_blocks: list[UnifiedBlock] = None


def fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    a_norm = a.lower().strip()
    b_norm = b.lower().strip()
    return SequenceMatcher(None, a_norm, b_norm).ratio() > threshold


def find_text_match(
    llama_text: str, pymupdf_items: list[PyMuPdfItem], used_indices: set[int]
) -> list[PyMuPdfItem]:
    """
    Find the first sequence of PyMuPDF text items that match the llama text.
    Returns the matching items and marks their indices as used.
    """
    if not llama_text:
        return []

    llama_text_norm = llama_text.lower().strip()

    # Try to find exact matches first
    for i, item in enumerate(pymupdf_items):
        if i in used_indices or not isinstance(item, TextItem):
            continue

        # Check if this single item matches
        if fuzzy_match(item.text, llama_text):
            used_indices.add(i)
            return [item]

        # Check if we can build a match by combining consecutive text items
        combined_text = item.text
        matched_items = [item]
        current_indices = {i}

        # Try to combine with subsequent text items
        for j in range(i + 1, len(pymupdf_items)):
            if j in used_indices or not isinstance(pymupdf_items[j], TextItem):
                break

            # Add space between text items
            combined_text += " " + pymupdf_items[j].text

            if fuzzy_match(combined_text, llama_text):
                # Found a match! Mark all items as used
                used_indices.update(current_indices)
                used_indices.add(j)
                matched_items.append(pymupdf_items[j])
                return matched_items
            elif len(combined_text) > len(llama_text_norm) * 1.5:
                # Stop if we've exceeded reasonable length
                break
            else:
                # Continue building the combination
                current_indices.add(j)
                matched_items.append(pymupdf_items[j])

    return []


def match_blocks(
    llama_parse_page: Page, pymupdf_page: PageResult
) -> list[UnifiedBlock]:
    """
    Given the output of a llama parse and a pymupdf,
    match up the individual items into a single list using text-based matching.
    Items are processed in order and each PyMuPDF item is only used once.
    """
    unified = []
    used_pymupdf_indices = set()

    for llama_item in llama_parse_page.items:
        # Find matching PyMuPDF text items
        fitz_matches = find_text_match(
            llama_item.value, pymupdf_page.content, used_pymupdf_indices
        )

        if fitz_matches:
            unified.append(
                UnifiedBlock(
                    match_method="text",
                    llama_item=llama_item,
                    fitz_items=fitz_matches,
                    id=str(uuid.uuid4()),
                )
            )
        else:
            unified.append(
                UnifiedBlock(
                    match_method="none",
                    llama_item=llama_item,
                    fitz_items=[],
                    id=str(uuid.uuid4()),
                )
            )

    return unified
