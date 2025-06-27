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


goals_schema = {
    "type": "object",
    "$schema": "http://json-schema.org/draft-04/schema#",
    "properties": {
        "goals": {
            "type": "object",
            "description": "A blue table with a dark blue border that has a header of Goals: In 2050 Williston is...",
            "properties": {
                "livable": {
                    "type": "string",
                    "description": "The text under the Livable heading, in the blue table",
                },
                "resilient": {
                    "type": "string",
                    "description": "The text under the Resilient heading, in the blue table",
                },
                "equitable": {
                    "type": "string",
                    "description": "The text under the Equitable heading, in the blue table",
                },
            },
        },
        "three_facts_table": {
            "type": "array",
            "description": "A red table that has a header of Three Things To Know",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "Main fact text next to red number",
                    },
                    "detail": {
                        "type": "string",
                        "description": "Explaination text beneath it",
                    },
                },
            },
        },
        "three_public_engagement_table": {
            "type": "array",
            "description": "A green table that has a header of Three Things Public Engagement Told Us",
            "items": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "Main fact text next to green number",
                    },
                    "detail": {
                        "type": "string",
                        "description": "Explaination text beneath it",
                    },
                },
            },
        },
    },
}


def extract(pdf_path: str):
    extractor = LlamaExtract(api_key=os.getenv("LLAMA_PARSE_API_KEY"))

    # agent = extractor.create_agent("townplan_table_parser", data_schema=goals_schema)
    agent = extractor.get_agent(name="townplan_table_parser")
    result = agent.extract(pdf_path)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python llama_extract.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        result = extract(pdf_path)

        # Save to JSON using Pydantic serialization
        with open("output/llamaparse/llama_extract.json", "w", encoding="utf-8") as f:
            json.dump(result.json(), f, indent=2, ensure_ascii=False)
