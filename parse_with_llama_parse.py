"""
Usage:  uv run parse_with_llama_parse.py input_files/chap1.pdf
"""

import json
import os
import sys
from typing import TypedDict
from llama_cloud_services import LlamaParse
from llama_cloud_services.parse.types import Page, JobMetadata
from dotenv import load_dotenv
import glob
import re

load_dotenv()

class LlamaParseOutput(TypedDict):
    pages: list[Page]
    job_metadata: JobMetadata
    job_id: str # UUID
    file_path: str

def parse(pdf_path: str, output_path: str = "output/llamaparse_output.json"):
    """
    Given an input path, parse the file with llamaparse, dump the results to json,
    and then return them.
    """
    # Initialize the parser
    parser = LlamaParse(api_key=os.getenv("LLAMA_PARSE_API_KEY"), verbose=True, premium_mode=True)
    json_objs = parser.get_json_result(file_path=pdf_path)
    image_dir = f"images/llamaparse/{os.path.basename(pdf_path)}"
    
    save_images(parser, json_objs, image_dir)

    # Save to JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_objs, f, indent=2, ensure_ascii=False)

    metadata= json_objs[0]["job_metadata"]

    print(json.dumps(metadata,indent=2))

    return json_objs

def save_images(parser, json_objs, image_dir):
    """
    Download and save the image that were identified in this doc.
    """
    job_id = json_objs[0]["job_id"]
    
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
                clean_name = filename.replace(f'{job_id}-', '')
                
                if clean_name != filename:
                    new_path = os.path.join(image_dir, clean_name)
                    try:
                        os.rename(img_file, new_path)
                        print(f"  🔄 Renamed: {filename} → {clean_name}")
                    except Exception as e:
                        print(f"  ⚠️ Could not rename {filename}: {e}")
        
    except Exception as e:
        print(f"⚠️ Could not download images: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_with_llamaparse.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        parse(pdf_path)
