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
from pydantic import BaseModel, Field

load_dotenv()


class LlamaParseOutput(BaseModel):
    pages: List[Page]
    job_metadata: JobMetadata
    job_id: str  # UUID
    file_path: str


class Goals(BaseModel):
    livable: str = Field(
        ..., description="The text under the Livable heading, in the blue table"
    )
    resilient: str = Field(
        ..., description="The text under the Resilient heading, in the blue table"
    )
    equitable: str = Field(
        ..., description="The text under the Equitable heading, in the blue table"
    )


class FactItem(BaseModel):
    fact: str = Field(..., description="Main fact text next to red number")
    detail: str = Field(..., description="Explaination text beneath it")


class ObjectiveItem(BaseModel):
    label: str = Field(..., description="Ex: 1.4, 1.B, etc")
    text: str = Field(..., description="Corresponding content of the objective")


class StrategyItem(BaseModel):
    label: str = Field(..., description="Ex: 1.1, 1.2, etc")
    text: str = Field(..., description="Corresponding conetnt of the strategy")


class ActionItem(BaseModel):
    strategy: str = Field(
        ...,
        description="The label of the strategy this action corresponds to. Ex: 1.1, 1.2",
    )
    label: str = Field(..., description="Ex: 1.1.1, 1.1.2, etc")
    text: str = Field(..., description="Corresponding description of the action")
    responsibility: str = Field(
        ..., description="Department responsible. The column next to text"
    )
    timeframe: str
    cost: str = Field(..., description="An indicator in $ signs.")


class ObjectivesStrategiesActionsTable(BaseModel):
    objectives: List[ObjectiveItem] = Field(
        ..., description="Ordered lists of elements under the Objectives subtitle"
    )
    strategies: List[StrategyItem] = Field(
        ...,
        description="Ordered list of elements under the Strategies subtitle. Can span multiple pages. Each strategy can have actions associated with it.",
    )
    actions: List[ActionItem] = Field(
        ..., description="Ordered list of actions underneath a strategy"
    )


class CitationItem(BaseModel):
    label: str = Field(
        ...,
        description="Superscript indicator, typically a number, of the citation label",
    )
    source: str = Field(..., description="Citation information")


class ExtractedData(BaseModel):
    goals: Goals = Field(
        ...,
        description="A blue table with a dark blue border that has a header of Goals: In 2050 Williston is...",
    )
    three_facts_table: List[FactItem] = Field(
        ..., description="A red table that has a header of Three Things To Know"
    )
    three_public_engagement_table: List[FactItem] = Field(
        ...,
        description="A green table that has a header of Three Things Public Engagement Told Us",
    )
    objectives_strategies_actions_table: ObjectivesStrategiesActionsTable = Field(
        ...,
        description="A yellow table near the end of the chapter with header Objectives, Strategies, and Actions. Spans multiple pages.",
    )
    citations: List[CitationItem] = Field(
        ...,
        description="A list of cited sources referenced by number throughout the text. Occurs at the very end of the document after End Notes.",
    )


def extract(pdf_path: str):
    extractor = LlamaExtract(api_key=os.getenv("LLAMA_PARSE_API_KEY"))

    agent = extractor.create_agent(
        "townplan_table_parser", data_schema=ExtractedData.model_json_schema()
    )
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
