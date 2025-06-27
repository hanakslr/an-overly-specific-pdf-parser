from llama_cloud_services.parse.types import PageItem

from etl.pymupdf_parse import Item
from rule_registry.conversion_rules import ConversionRule, RuleCondition
from tiptap.tiptap_models import ParagraphNode, TextNode


class LlamaparseTextToParagraphConversion(ConversionRule):
    id: str = "llamaparse_text_to_paragraph"
    description: str = "Converts LlamaParse text items to Tiptap paragraph nodes"
    conditions: list[RuleCondition] = [
        RuleCondition(source="llamaparse", field="type", operator="==", value="text")
    ]
    output_node_type: str = "paragraph"

    def construct_node(
        cls, llamaparse_input: PageItem, pymupdf_inputs: list[Item]
    ) -> ParagraphNode:
        return ParagraphNode(content=[TextNode(text=llamaparse_input.value)])
