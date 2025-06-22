"""
Usage:  uv run parse_with_llama_parse.py input_files/chap1.pdf
"""

import json
import os
import sys
from llama_parse import LlamaParse
from langchain.schema import Document
from dotenv import load_dotenv

load_dotenv()

def parse_with_llamaparse(pdf_path: str, output_path: str = "output/llamaparse_output.json"):
    # Initialize the parser
    parser = LlamaParse(api_key=os.getenv("LLAMA_PARSE_API_KEY"), verbose=True, premium_mode=True)
    
    json_objs = parser.get_json_result(file_path=pdf_path)
    # Save to JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_objs, f, indent=2, ensure_ascii=False)

    metadata= json_objs[0]["job_metadata"]

    print(json.dumps(metadata,indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_with_llamaparse.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        parse_with_llamaparse(pdf_path)
