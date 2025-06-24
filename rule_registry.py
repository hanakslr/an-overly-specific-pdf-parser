"""
Rules are how our structured PDF input gets translated to ProseMirror JSON.
"""

from typing import Literal

from llama_cloud_services.parse.types import PageItem
from pydantic import BaseModel

from extract_structured_pdf import Item
from tiptap_models import HeadingNode, TextNode, TiptapNode


class RuleCondition(BaseModel):
    source: Literal["pymupdf", "llamaparse"]
    field: str  # e.g., "font.size" or "type"
    operator: Literal["==", ">", "<", ">=", "<=", "in"]
    value: any  # e.g., "heading", 18.0, ["section", "header"]


class ConversionRule(BaseModel):
    id: str  # for debugging
    description: str
    conditions: list[RuleCondition]
    output_node_type: str

    def construct_node(llamaparse_input: PageItem, pymupdf_input: Item) -> TiptapNode:
        pass


class HeadingConversion(ConversionRule):
    id = "heading"
    description = "standard heading element"
    conditions = [
        RuleCondition(source="llamaparse", field="type", operator="==", value="heading")
    ]
    output_node_type = "heading"

    def construct_node(llamaparse_input: PageItem, pymupdf_input: Item) -> HeadingNode:
        return HeadingNode(
            attrs={"level": llamaparse_input.lvl},
            content=[TextNode(text=llamaparse_input.value)],
        )
