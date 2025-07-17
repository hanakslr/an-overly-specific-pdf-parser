from typing import Literal, Tuple, Union

from pydantic import BaseModel

from post_processing.williston_extraction_schema import ActionTable, StrategyItem
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


class ActionTableBlock(Block):
    type: Literal["action_table"] = "action_table"
    content: ActionTable

    attrs: Literal[None] = None

    def get_text(self):
        """
        Just return objectives for now. TODO: update this.
        """

        def actions(strategy: StrategyItem):
            return "\n".join([f"{a.label}: {a.text}" for a in strategy.actions])

        objectives_text = "\n".join(
            [f"{o.label}. {o.text}" for o in self.content.objectives]
        )
        strategies = [
            f"""
            {s.label}: {s.text}
            Actions: {actions(s)}
        """
            for s in self.content.strategies
        ]
        return f"""
Objectives: 
{objectives_text}

Strategies and Actions:
{strategies}
        """


class CustomBlock(Block):
    """
    A generic custom block - whose contents are not prosemirror nodes.
    """

    type: Literal["custom"] = "custom"
    content: dict

    class Attrs(BaseModel):
        type: str

    attrs: Attrs


BlockUnion = Union[
    GoalItemBlock,
    FactItemBlock,
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
    CustomBlock,
    ActionTableBlock,
]

# After all models are defined, rebuild the models that use forward references
GoalItemBlock.model_rebuild()
FactItemBlock.model_rebuild()
ActionTableBlock.model_rebuild()
