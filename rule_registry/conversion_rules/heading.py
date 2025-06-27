from llama_cloud_services.parse.types import PageItem
from tiptap_models import HeadingNode, TextNode

from etl.pymupdf_parse import Item
from rule_registry import ConversionRule, RuleCondition


class HeadingConversion(ConversionRule):
    id: str = "heading"
    description: str = "standard heading element"
    conditions: list[RuleCondition] = [
        RuleCondition(source="llamaparse", field="type", operator="==", value="heading")
    ]
    output_node_type: str = "heading"

    def construct_node(
        cls, llamaparse_input: PageItem, pymupdf_inputs: list[Item]
    ) -> HeadingNode:
        return HeadingNode(
            attrs={"level": llamaparse_input.lvl},
            content=[TextNode(text=llamaparse_input.value)],
        )
