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
        "image_header": {
            "type": "array",
            "description": "Image source info for the image header at the beginning of the chapter. Should be 3 images.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "How it would be referred in a standard llamaparse job, Example: img_p0_1.png",
                    },
                    "index": {
                        "type": "number",
                        "description": "Postion in header row",
                    },
                },
            },
        },
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
        "objectives_strategies_actions_table": {
            "type": "object",
            "description": "A yellow table near the end of the chapter with header Objectives, Strategies, and Actions. Spans multiple pages.",
            "properties": {
                "objectives": {
                    "description": "Ordered lists of elements under the Objectives subtitle",
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Ex: 1.4, 1.B, etc",
                            },
                            "text": {
                                "type": "string",
                                "description": "Corresponding content of the objective",
                            },
                        },
                    },
                },
                "strategies": {
                    "description": "Ordered list of elements under the Strategies subtitle. Can span multiple pages. Each strategy can have actions associated with it.",
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Ex: 1.1, 1.2, etc",
                            },
                            "text": {
                                "type": "string",
                                "description": "Corresponding conetnt of the strategy",
                            },
                        },
                    },
                },
                "actions": {
                    "type": "array",
                    "description": "Ordered list of actions underneath a strategy",
                    "items": {
                        "type": "object",
                        "properties": {
                            "strategy": {
                                "type": "string",
                                "description": "The label of the strategy this action corresponds to. Ex: 1.1, 1.2",
                            },
                            "label": {
                                "type": "string",
                                "description": "Ex: 1.1.1, 1.1.2, etc",
                            },
                            "text": {
                                "type": "string",
                                "description": "Corresponding description of the action",
                            },
                            "responsibility": {
                                "type": "string",
                                "description": "Department responsible. The column next to text",
                            },
                            "timeframe": {
                                "type": "string",
                            },
                            "cost": {
                                "type": "string",
                                "description": "An indicator in $ signs.",
                            },
                        },
                    },
                },
            },
        },
        "citations": {
            "type": "array",
            "description": "A list of cited sources referenced by number throughout the text. Occurs at the very end of the document after End Notes.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Superscript indicator, typically a number, of the citation label",
                    },
                    "source": {"type": "string", "description": "Citation information"},
                },
            },
        },
    },
}


def extract(pdf_path: str):
    extractor = LlamaExtract(api_key=os.getenv("LLAMA_PARSE_API_KEY"))

    agent = extractor.create_agent("townplan_table_parser_3", data_schema=goals_schema)
    agent = extractor.get_agent(name="townplan_table_parser_3")
    result = agent.extract(pdf_path)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python llama_extract.py <path-to-pdf>")
    else:
        pdf_path = sys.argv[1]
        result = extract(pdf_path)

        # Save to JSON using Pydantic serialization
        with open("output/llamaparse/llama_extract.json", "w") as f:
            json.dump(result.json(), f, indent=2)
