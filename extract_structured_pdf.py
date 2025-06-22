from dataclasses import asdict, dataclass, is_dataclass
from typing import Any
import pymupdf  # PyMuPDF
import json
import os

class Item:
    type: str
    page: int

@dataclass
class TextItem(Item):
    type: str
    page: int
    text: str
    font: str
    size: float

@dataclass
class ImageItem(Item):
    type: str
    page: int
    src: str
    bbox: Any


    
@dataclass
class PageResult:
    page: int
    content: list[Item]

def extract_structured_content(pdf_path) -> list[PageResult]:
    doc = pymupdf.open(pdf_path)
    result = []

    for page_num, page in enumerate(doc, start=1):
        page_items: list[Item] = []
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            block_type = block.get("type")

            if block_type == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span["text"].strip():  # skip empty
                            page_items.append(TextItem(
                                type="text",
                                text= span["text"].strip(),
                                font=span["font"],
                                size=span["size"],
                                page=page_num))
                    

            elif block_type == 1:  # Image block
                bbox = block.get("bbox")
                image_name = f"page_{page_num}_image_{len(page_items)+1}.png"
                # Save the image by xref
                try:
                    img_index = block.get("image", {}).get("xref")
                    if img_index:
                        pix = pymupdf.Pixmap(doc, img_index)
                        if pix.n < 5:  # RGB
                            pix.save(image_name)
                        else:  # CMYK or grayscale
                            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                            pix.save(image_name)
                        page_items.append(ImageItem(
                            type= "image",
                            src=image_name,
                            bbox= bbox,
                            page= page_num
                        ))
                except Exception as e:
                    print(f"⚠️ Could not extract image on page {page_num}: {e}")

        result.append(PageResult(
            page=page_num,
            content=page_items
        ))

    return result


def condense_matching_elements(result: list[PageResult]):
    """
    Iterate through the contents on each page, and concat consecutive text elements that have the same text 
    styles
    """

    for page in result: 
        condensed_contents = []
        for item in page.content:
            if item.type == "text" and condensed_contents:
                prev_element = condensed_contents[-1]
                if prev_element.type == "text" and prev_element.font == item.font and prev_element.size == item.size:
                    prev_element.text = f'{prev_element.text} {item.text}'
                    continue

            condensed_contents.append(item)

        page.content = condensed_contents


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python extract_pdf_structured.py town_plan.pdf")
    else:
        output_json="output/pymupdf_output_condensed.json"
        result = extract_structured_content(sys.argv[1])
        
        # Condense matching text elements
        condense_matching_elements(result)

        # Write to JSON file
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, cls=DataclassJSONEncoder)

        print(f"✅ Extraction complete: {output_json}")
