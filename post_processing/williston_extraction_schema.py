from typing import List

from pydantic import BaseModel, Field


class ObjectiveItem(BaseModel):
    label: str = Field(..., description="Ex: 1.4, 1.B, etc")
    text: str = Field(..., description="Corresponding content of the objective")


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


class StrategyItem(BaseModel):
    label: str = Field(..., description="Ex: 1.1, 1.2, etc")
    text: str = Field(..., description="Corresponding conetnt of the strategy")
    actions: list[ActionItem]


class Strategies(BaseModel):
    strategies: list[StrategyItem]


class CitationItem(BaseModel):
    label: str = Field(
        ...,
        description="Superscript indicator, typically a number, of the citation label",
    )
    source: str = Field(..., description="Citation information")


class ExtractedData(BaseModel):
    citations: List[CitationItem] = Field(
        ...,
        description="A list of cited sources referenced by number throughout the text. Occurs at the very end of the document after End Notes.",
    )
