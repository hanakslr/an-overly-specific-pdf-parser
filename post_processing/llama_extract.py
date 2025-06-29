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
    extractor = LlamaExtract(api_key=os.getenv("LLAMA_PARSE_API_KEY"))

    # agent = extractor.create_agent(
    #     "townplan_table_parser", data_schema=ExtractedData.model_json_schema()
    # )
    agent = extractor.get_agent(name="townplan_table_parser")
    result = agent.extract(pdf_path)
    return result.data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python llama_extract.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        result = extract(pdf_path)

        output_filename = "output/llamaparse/llama_extract_pydantic.json"

        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
