"""
Usage:  uv run parse_with_llama_parse.py input_files/chap1.pdf
"""

import glob
import json
import os
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from llama_cloud_services import LlamaParse
from llama_cloud_services.parse.types import JobMetadata, Page
from pydantic import BaseModel

load_dotenv()


class LlamaParseOutput(BaseModel):
    pages: List[Page]
    job_metadata: JobMetadata
    job_id: str  # UUID
    file_path: str


def parse(pdf_path: str):
    """
    Given an input path, parse the file with llamaparse and then return them.
    """
    cache_dir = ".cache/llama_parse"
    os.makedirs(cache_dir, exist_ok=True)

    pdf_filename = os.path.basename(pdf_path)
    cache_filepath = os.path.join(cache_dir, f"{pdf_filename}.json")

    if os.path.exists(cache_filepath):
        print(f"INFO: Loading cached parse results from {cache_filepath}")
        with open(cache_filepath, "r") as f:
            cached_data = json.load(f)
        return LlamaParseOutput(**cached_data)

    print("INFO: No cache found. Running fresh parse...")
    # Initialize the parser
    parser = LlamaParse(
        api_key=os.getenv("LLAMA_PARSE_API_KEY"),
        verbose=True,
        premium_mode=True,
        system_prompt_append="Do not include the page numbers at the bottom right of pages. Do not generate tables for images elements that look like charts. Ignore all images in your output.",
    )
    json_objs = parser.get_json_result(file_path=pdf_path)

    # Save the raw JSON response to cache
    with open(cache_filepath, "w") as f:
        json.dump(json_objs[0], f, indent=2, sort_keys=True)
    print(f"INFO: Saved parse results to {cache_filepath}")

    image_dir = f"output/images/llamaparse/{Path(pdf_path).stem}"

    save_images(parser, json_objs, image_dir)

    metadata = json_objs[0]["job_metadata"]

    print(json.dumps(metadata, indent=2))

    # Convert the list of dictionaries to LlamaParseOutput
    # The parse function returns a list, but we expect a single LlamaParseOutput
    return LlamaParseOutput(**json_objs[0])


def save_images(parser, json_objs, image_dir):
    """
    Download and save the image that were identified in this doc.
    """
    job_id = json_objs[0]["job_id"]
    metadata = json_objs[0]["job_metadata"]

    if metadata["job_is_cache_hit"]:
        print("Cache hit - images already downloaded.")
        return

    # Create image output directory

    os.makedirs(image_dir, exist_ok=True)

    # Download images
    print(f"📥 Downloading images to {image_dir}...")
    try:
        downloaded_images = parser.get_images(json_objs, download_path=image_dir)
        print(f"✅ Downloaded {len(downloaded_images)} images")

        # Rename images to remove job ID prefix
        # Get all downloaded image files
        image_files = glob.glob(f"{image_dir}/*")

        for img_file in image_files:
            if os.path.isfile(img_file):
                # Extract filename without path
                filename = os.path.basename(img_file)

                # Remove job ID prefix (assuming it's at the beginning followed by underscore)
                # Pattern: job_id_original_name.ext
                clean_name = filename.replace(f"{job_id}-", "")

                if clean_name != filename:
                    new_path = os.path.join(image_dir, clean_name)
                    try:
                        os.rename(img_file, new_path)
                    except Exception as e:
                        print(f"  ⚠️ Could not rename {filename}: {e}")

    except Exception as e:
        print(f"⚠️ Could not download images: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_with_llamaparse.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        result = parse(pdf_path)

        # Save to JSON using Pydantic serialization
        with open(
            "output/llamaparse/llamaparse_output.json", "w", encoding="utf-8"
        ) as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
