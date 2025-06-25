from difflib import SequenceMatcher

from llama_cloud_services.parse.types import BBox, Page, PageItem
from pydantic import BaseModel

from extract_structured_pdf import PageResult, PyMuPdfItem, TextItem


class UnifiedBlock(BaseModel):
    match_method: str
    llama_item: PageItem
    fitz_items: list[PyMuPdfItem]


class ZippedOutputsPage(BaseModel):
    page: int

    llama_parse_page: Page
    pymupdf_page: PageResult

    unified_blocks: list[UnifiedBlock] = None


def span_intersects_block(
    span: tuple[float, float, float, float], block_bbox: BBox, margin: float = 5.0
) -> bool:
    x0, y0, x1, y1 = span
    bx0 = block_bbox.x - margin
    by0 = block_bbox.y - margin
    bx1 = block_bbox.x + block_bbox.w + margin
    by1 = block_bbox.y + block_bbox.h + margin
    return not (x1 < bx0 or x0 > bx1 or y1 < by0 or y0 > by1)


def fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    a_norm = a.lower().strip()
    b_norm = b.lower().strip()
    return SequenceMatcher(None, a_norm, b_norm).ratio() > threshold


def match_blocks(
    llama_parse_page: Page, pymupdf_page: PageResult
) -> list[UnifiedBlock]:
    """
    Given the output of a llama parse and a pymupdf,
    match up the individual items into a single list using bounding
    boxes and fuzzy matching.
    """
    unified = []

    for llama_item in llama_parse_page.items:
        fitz_matches = [
            fitz_item
            for fitz_item in pymupdf_page.content
            if span_intersects_block(fitz_item.bbox, llama_item.bBox)
        ]

        if fitz_matches:
            unified.append(
                UnifiedBlock(
                    match_method="bbox", llama_item=llama_item, fitz_items=fitz_matches
                )
            )
            continue

        # If we didn't have overlap by bbox, check by text content
        fitz_fuzzy_matches = [
            fitz_item
            for fitz_item in pymupdf_page.content
            if isinstance(fitz_item, TextItem)
            and fuzzy_match(fitz_item.text, llama_item.value)
        ]

        if fitz_fuzzy_matches:
            unified.append(
                UnifiedBlock(
                    match_method="fuzzy",
                    llama_item=llama_item,
                    fitz_items=fitz_fuzzy_matches,
                )
            )
        else:
            unified.append(
                UnifiedBlock(match_method="none", llama_item=llama_item, fitz_items=[])
            )

    return unified
