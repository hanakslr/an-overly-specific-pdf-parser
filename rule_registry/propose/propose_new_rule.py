import importlib.util
import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from doc_server.helpers import append_to_document
from etl.zip_llama_pymupdf import UnifiedBlock
from rule_registry.conversion_rules import ConversionRuleRegistry, RuleCondition
from tiptap.tiptap_models import TiptapNode


class RuleProposal(BaseModel):
    id: str = Field(
        description="A unique slug-like identifier for this conversion rule. Should be relevant to what the rule does."
    )
    description: str = Field(
        description="A human-readable description of what this rule does, e.g., 'Converts LlamaParse heading items to Tiptap heading nodes'"
    )
    conditions: list[RuleCondition] = Field(
        description="A list of conditions that must be met for this rule to apply. Each condition specifies a source (llamaparse or pymupdf), field, operator, and value. It should be as general as possible."
    )
    output_node_type: str = Field(
        description="The type of Tiptap node this rule produces, e.g., 'heading', 'paragraph', 'listItem', etc. This comes directly from the type field of the relevant TiptapNode sublass that is being created."
    )
    construct_node_function: str = Field(
        description="The function body of python code as a string that constructs the Tiptap node. It's signature is `def construct_node(cls, llamaparse_input: PageItem, pymupdf_inputs: list[Item])` and returns a TiptapNode. Example: 'return HeadingNode(attrs={\"level\": llamaparse_input.lvl}, content=[TextNode(text=llamaparse_input.value)])' This should only be the function body and not include the signature."
    )


# ---- Tool to query existing rules that match ----
def _query_similar_rules_impl(block: UnifiedBlock, top_k: int = 5) -> str:
    """
    Internal implementation of query_similar_rules without tool decoration.
    """
    all_rules = ConversionRuleRegistry.get_all_rules()
    matches = []
    for rule in all_rules:
        try:
            if rule.match_condition(
                block.llama_item, block.fitz_items[0] if block.fitz_items else None
            ):
                matches.append(
                    {
                        "id": rule.id,
                        "description": rule.description,
                        "output_node_type": rule.output_node_type,
                    }
                )
        except Exception:
            continue
    return json.dumps(matches[:top_k], indent=2)


def test_rule_with_block(temp_file_path: Path, block: UnifiedBlock) -> tuple[bool, str]:
    """
    Test the rule by dynamically importing it and calling construct_node with the block.
    Returns a tuple of (success: bool, message: str).
    """
    try:
        # Dynamically import the temporary rule file
        spec = importlib.util.spec_from_file_location("temp_rule", temp_file_path)
        temp_module = importlib.util.module_from_spec(spec)
        sys.modules["temp_rule"] = temp_module
        spec.loader.exec_module(temp_module)

        # Find the ConversionRule class in the module
        rule_class = None
        for attr_name in dir(temp_module):
            attr = getattr(temp_module, attr_name)
            if hasattr(attr, "__bases__") and any(
                "ConversionRule" in str(base) for base in attr.__bases__
            ):
                rule_class = attr
                break

        if not rule_class:
            return False, "Could not find ConversionRule class in the file"

        # Create an instance of the rule class
        rule_instance = rule_class()

        # Test if the rule matches the block
        if not rule_instance.match_condition(
            block.llama_item, block.fitz_items[0] if block.fitz_items else None
        ):
            return False, "Rule conditions do not match the block"

        # Call construct_node with the block
        result_node = rule_instance.construct_node(block.llama_item, block.fitz_items)

        # Check if the result is a valid TiptapNode

        if isinstance(result_node, TiptapNode):
            message = (
                f"Rule generated valid {type(result_node).__name__}: {result_node}"
            )
            # Append to document
            append_to_document([result_node])
            return True, message
        else:
            return (
                False,
                f"Rule returned {type(result_node).__name__}, expected TiptapNode",
            )

    except Exception as e:
        return False, f"Error testing rule: {e}"


# ------- Conversion class ----------
def generate_conversion_class(rule: RuleProposal) -> str:
    print("Generating class")
    # Format each condition line
    condition_lines = ",\n        ".join(
        [
            f'RuleCondition(source="{c.source}", field="{c.field}", operator="{c.operator}", value="{c.value}")'
            for c in rule.conditions
        ]
    )

    return f'''from rule_registry.conversion_rules import ConversionRule, RuleCondition
from tiptap.tiptap_models import TextNode, {rule.output_node_type.title()}Node
from llama_cloud_services.parse.types import PageItem

from etl.pymupdf_parse import Item

class {rule.id.title().replace("_", "")}Conversion(ConversionRule):
    id: str = "{rule.id}"
    description: str = "{rule.description}"
    conditions: list[RuleCondition] = [
        {condition_lines}
    ]
    output_node_type: str = "{rule.output_node_type}"

    def construct_node(cls, llamaparse_input: PageItem, pymupdf_inputs: list[Item]) -> {rule.output_node_type.title()}Node:
        {rule.construct_node_function}
'''


# ---- Main entry point ----
def propose_new_rule_node(state):
    """
    Function that extracts the current block from PipelineState
    and generates a new conversion rule using the new agentic graph.
    """
    from rule_registry.propose.new_rule_graph import propose_new_rule_graph

    # Extract the current block from the state
    block = state.current_block

    # Generate the rule by invoking the graph
    result = propose_new_rule_graph(block)

    print(f"Graph finished with result: {result}")

    new_block = state.current_block.model_copy(
        update={"conversion_rule": result["rule"].id if result.get("rule") else None}
    )

    state.update_current_block(new_block)

    # Return the result in the format expected by the pipeline
    return {"current_block": state.current_block}
