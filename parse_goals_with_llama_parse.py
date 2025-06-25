"""
Usage:  uv run parse_with_llama_parse.py input_files/chap1.pdf
"""

import json
import os
import sys
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


def parse(pdf_path: str):
    """
    Given an input path, parse the file with llamaparse and then return them.
    """
    # Initialize the parser
    parser = LlamaParse(
        api_key=os.getenv("LLAMA_PARSE_API_KEY"),
        structured_output=True,
        structured_output_json_schema=json.dumps(goals_schema),
        target_pages="0-2",
    )
    json_objs = parser.get_json_result(file_path=pdf_path)

    # save_images(parser, json_objs, image_dir)

    metadata = json_objs[0]["job_metadata"]

    print(json.dumps(metadata, indent=2))

    return json_objs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_with_llamaparse.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        result = parse(pdf_path)

        # Save to JSON using Pydantic serialization
        with open(
            "output/llamaparse/llamaparse_output_goals_4.json", "w", encoding="utf-8"
        ) as f:
            # Convert the result to a list of Pydantic models and then serialize
            # Since result is a list of dicts, we need to convert each dict to a LlamaParseOutput model
            pydantic_models = [LlamaParseOutput(**item) for item in result]
            json_data = [model.model_dump() for model in pydantic_models]
            json.dump(json_data, f, indent=2, ensure_ascii=False)
