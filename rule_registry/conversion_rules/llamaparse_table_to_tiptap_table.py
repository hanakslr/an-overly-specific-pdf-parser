from llama_cloud_services.parse.types import PageItem

from etl.pymupdf_parse import Item
from rule_registry.conversion_rules import ConversionRule, RuleCondition
from tiptap.tiptap_models import (
    ParagraphNode,
    TablecellNode,
    TableNode,
    TablerowNode,
    TextNode,
)


class LlamaparseTableToTiptapTableConversion(ConversionRule):
    id: str = "llamaparse_table_to_tiptap_table"
    description: str = "Converts LlamaParse table items to Tiptap table nodes"
    conditions: list[RuleCondition] = [
        RuleCondition(source="llamaparse", field="type", operator="==", value="table")
    ]
    output_node_type: str = "table"

    def construct_node(
        cls, llamaparse_input: PageItem, pymupdf_inputs: list[Item]
    ) -> TableNode:
        rows = []
        for row in llamaparse_input.rows:
            cells = [
                TablecellNode(content=[ParagraphNode(content=[TextNode(text=cell)])])
                for cell in row
            ]
            rows.append(TablerowNode(content=cells))
        return TableNode(content=rows)
