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

load_dotenv()

class LlamaParseOutput(TypedDict):
    pages: list[Page]
    job_metadata: JobMetadata
    job_id: str # UUID
    file_path: str

def parse(pdf_path: str, output_path: str = "output/llamaparse_output.json"):
    # Initialize the parser
    parser = LlamaParse(api_key=os.getenv("LLAMA_PARSE_API_KEY"), verbose=True, premium_mode=True)
    json_objs = parser.get_json_result(file_path=pdf_path)
    # Save to JSON
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_objs, f, indent=2, ensure_ascii=False)

    metadata= json_objs[0]["job_metadata"]

    print(json.dumps(metadata,indent=2))

    return json_objs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_with_llamaparse.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        parse(pdf_path)
