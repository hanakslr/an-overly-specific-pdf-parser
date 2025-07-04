"""
Usage:  uv run parse_with_llama_parse.py input_files/chap1.pdf
"""

import json
import os
import sys
from typing import List

from dotenv import load_dotenv
from llama_cloud_services import LlamaExtract
from llama_cloud_services.parse.types import JobMetadata, Page
from pydantic import BaseModel

load_dotenv()


class LlamaParseOutput(BaseModel):
    pages: List[Page]
    job_metadata: JobMetadata
    job_id: str  # UUID
    file_path: str


def extract(pdf_path: str):
    cache_dir = ".cache/llama_extract"
    os.makedirs(cache_dir, exist_ok=True)

    pdf_filename = os.path.basename(pdf_path)
    cache_filepath = os.path.join(cache_dir, f"{pdf_filename}.json")

    if os.path.exists(cache_filepath):
        print(f"INFO: Loading cached extraction results from {cache_filepath}")
        with open(cache_filepath, "r") as f:
            return json.load(f)

    print("INFO: No cache found. Running fresh extraction...")
    extractor = LlamaExtract(api_key=os.getenv("LLAMA_PARSE_API_KEY"))

    # agent = extractor.create_agent(
    #     "townplan_table_parser", data_schema=ExtractedData.model_json_schema()
    # )
    agent = extractor.get_agent(name="townplan_table_parser")
    result = agent.extract(pdf_path)
    data = result.data

    with open(cache_filepath, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    print(f"INFO: Saved extraction results to {cache_filepath}")

    return data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python llama_extract.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        result = extract(pdf_path)

        output_filename = "output/llamaparse/llama_extract_pydantic.json"

        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
