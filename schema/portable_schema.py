from typing import Annotated, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from schema.block import Block
from schema.tiptap_models import (
    BlockquoteNode,
    BulletlistNode,
    CodeblockNode,
    HeadingNode,
    HorizontalruleNode,
    ImageheaderNode,
    ImageNode,
    OrderedlistNode,
    ParagraphNode,
    TableNode,
)

BlockUnion = Union[
    "GoalItemBlock",
    "FactItemBlock",
    "CitationBlock",
    BlockquoteNode,
    BulletlistNode,
    CodeblockNode,
    HeadingNode,
    HorizontalruleNode,
    ImageNode,
    ImageheaderNode,
    OrderedlistNode,
    ParagraphNode,
    TableNode,
]


class GoalItemBlock(Block):
    type: Literal["goal_item"] = "goal_item"
    content: Tuple[ParagraphNode]

    class Attrs(BaseModel):
        trait: Union[Literal["livable"], Literal["resilient"], Literal["equitable"]]

    attrs: Attrs


class FactItemBlock(Block):
    type: Literal["fact_item"] = "fact_item"
    content: Tuple[HeadingNode, ParagraphNode]

    class Attrs(BaseModel):
        label: str
        collection: Union[Literal["facts"], Literal["public_engagement"]]

    attrs: Attrs


class CitationBlock(Block):
    type: Literal["citation"] = "citation"
    content: Tuple[ParagraphNode]

    class Attrs(BaseModel):
        label: str

    attrs: Attrs


class ActionItemBlock(Block):
    type: Literal["action_item"] = "action_item"
    content: Tuple[ParagraphNode]

    class Attrs(BaseModel):
        strategy_id: str
        label: str
        time_frame: Optional[str]
        responsibility: Optional[list[str]]
        cost: Optional[str]

    attrs: Attrs


class StrategyItemBlock(Block):
    type: Literal["strategy_item"] = "strategy_item"
    content: Tuple[ParagraphNode]

    class Attrs(BaseModel):
        label: str

    attrs: Attrs


class ObjectiveItemBlock(Block):
    type: Literal["objective_item"] = "objective_item"
    content: Tuple[ParagraphNode]

    class Attrs(BaseModel):
        label: str

    attrs: Attrs
