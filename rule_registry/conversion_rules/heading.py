from llama_cloud_services.parse.types import PageItem

from etl.pymupdf_parse import Item
from rule_registry.conversion_rules import ConversionRule, RuleCondition
from schema.tiptap_models import HeadingNode, TextNode


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
            attrs=HeadingNode.Attrs(level=llamaparse_input.lvl),
            content=[TextNode(text=llamaparse_input.value or " ")],
        )
