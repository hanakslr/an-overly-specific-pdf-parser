import io
import json
import os
from typing import Any, List, Union

import pymupdf  # PyMuPDF
from PIL import Image
from pydantic import BaseModel


class Item(BaseModel):
    type: str
    page: int


class TextItem(Item):
    type: str = "text"
    page: int
    text: str
    color: tuple[int, int, int]
    font: str
    size: int
    bbox: tuple[float, float, float, float]  # [x0, y0, x1, y1]


class ImageItem(Item):
    type: str = "image"
    page: int
    src: str
    bbox: tuple[float, float, float, float]  # [x0, y0, x1, y1]


PyMuPdfItem = Union[TextItem, ImageItem]


class PageResult(BaseModel):
    page: int
    content: List[PyMuPdfItem]


class PyMuPDFOutput(BaseModel):
    pages: List[PageResult]


def extract(file_path: str) -> dict:
    result = extract_structured_content(file_path)

    # Condense matching text elements
    condense_matching_elements(result)

    return result


def extract_structured_content(pdf_path) -> List[PageResult]:
    doc = pymupdf.open(pdf_path)
    result = []

    # We will store images in images/pymupdf/{pdf_path}
    # Ensure the image output directory exists
    output_dir = f"output/images/pymupdf/{os.path.basename(pdf_path)}"
    os.makedirs(output_dir, exist_ok=True)

    for page_num, page in enumerate(doc, start=1):
        page_items: List[Union[TextItem, ImageItem]] = []
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            block_type = block.get("type")

            if block_type == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span["text"].strip():  # skip empty
                            page_items.append(
                                TextItem(
                                    text=span["text"].strip(),
                                    color=pymupdf.sRGB_to_rgb(span["color"]),
                                    font=span["font"],
                                    size=round(span["size"]),
                                    page=page_num,
                                    bbox=span.get("bbox"),  # Get bbox from span
                                )
                            )

            elif block_type == 1:  # Image block
                try:
                    image_data = block.get("image")
                    if not isinstance(image_data, bytes):
                        continue

                    # Use Pillow to check if the image is all black
                    img = Image.open(io.BytesIO(image_data))
                    if img.convert("L").getextrema() == (0, 0):
                        # This is a black box image, so we skip it
                        print(f"Skipping all-black image on page {page_num}")
                        continue

                    bbox = block.get("bbox")
                    image_name = f"page_{page_num}_image_{len(page_items) + 1}.png"

                    with open(f"{output_dir}/{image_name}", "wb") as f:
                        f.write(image_data)

                    page_items.append(
                        ImageItem(
                            src=f"{os.path.basename(pdf_path)}/{image_name}",
                            bbox=bbox,
                            page=page_num,
                        )
                    )
                except Exception as e:
                    print(f"⚠️ Could not process image on page {page_num}: {e}")
        result.append(PageResult(page=page_num, content=page_items))

    return result


def condense_matching_elements(result: List[PageResult]):
    """
    Iterate through the contents on each page, and concat consecutive text elements that have the same text
    styles
    """

    for page in result:
        condensed_contents = []
        for item in page.content:
            if item.type == "text" and condensed_contents:
                prev_element = condensed_contents[-1]
                if (
                    prev_element.type == "text"
                    and prev_element.font == item.font
                    and prev_element.color == item.color
                    and prev_element.size == item.size
                ):
                    prev_element.text = f"{prev_element.text} {item.text}"
                    continue

            condensed_contents.append(item)

        page.content = condensed_contents


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python extract_pdf_structured.py town_plan.pdf")
    else:
        output_json = "output/pymupdf/pymupdf_output_condensed.json"
        result = extract_structured_content(sys.argv[1])

        # Condense matching text elements
        condense_matching_elements(result)

        # Write to JSON file using Pydantic's JSON serialization
        with open(output_json, "w", encoding="utf-8") as f:
            # Convert to dict and then to JSON for better control
            json_data = [page.model_dump() for page in result]
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Extraction complete: {output_json}")
