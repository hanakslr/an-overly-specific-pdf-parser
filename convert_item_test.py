from llama_cloud_services.parse.types import PageItem

from extract_structured_pdf import Item, TextItem
from rule_registry import (
    ConversionRule,
    ConversionRuleRegistry,
    RuleCondition,
)
from tiptap_models import TextNode

# Test data
llamaparse_item = {
    "type": "heading",
    "lvl": 1,
    "value": "1 WILLISTON'S PEOPLE",
    "md": "# 1 WILLISTON'S PEOPLE",
    "bBox": {"x": 110.52, "y": 487.56, "w": 429.6, "h": 235.88},
}

pymupdf_items = [
    {
        "type": "text",
        "page": 1,
        "text": "1 Williston's People",
        "font": "BumperSticker-Regular",
        "size": 27.959999084472656,
    }
]


def create_dynamic_rule():
    """Create a new rule programmatically and register it."""

    # Create a new rule class dynamically
    class DynamicTextRule(ConversionRule):
        id: str = "dynamic_text"
        description: str = "dynamically created text rule"
        conditions: list[RuleCondition] = [
            RuleCondition(source="pymupdf", field="type", operator="==", value="text")
        ]
        output_node_type: str = "paragraph"

        def construct_node(
            cls, llamaparse_input: PageItem, pymupdf_input: Item
        ) -> TextNode:
            return TextNode(text=pymupdf_input.text)

    # The rule is automatically registered via __init_subclass__
    # Access the id through the model schema
    rule_id = DynamicTextRule.model_fields["id"].default
    print(f"Created and registered new rule: {rule_id}")

    return DynamicTextRule


def test_rule_registry():
    """Test the rule registry with the provided test data."""

    # Convert test data to proper objects
    llamaparse_obj = PageItem(**llamaparse_item)
    pymupdf_obj = TextItem(**pymupdf_items[0])

    # Test 1: Initial rules (only HeadingConversion)
    print("=== TEST 1: Initial Rules ===")
    print("Discovering conversion rules...")
    rules = ConversionRuleRegistry.get_all_rules()
    print(f"Found {len(rules)} rules")

    for rule in rules:
        print(f"  - {rule.id}: {rule.description}")

    print()

    # Test 2: Add a new rule programmatically
    print("=== TEST 2: Adding Dynamic Rule ===")
    create_dynamic_rule()

    # Test 3: Check rules again (should now include the new rule)
    print("=== TEST 3: Rules After Dynamic Addition ===")
    rules = ConversionRuleRegistry.get_all_rules()
    print(f"Found {len(rules)} rules")

    for rule in rules:
        print(f"  - {rule.id}: {rule.description}")

    print()

    # Test 4: Test all rules against the data
    print("=== TEST 4: Testing All Rules ===")
    print(f"LlamaParse item: {llamaparse_obj}")
    print(f"PyMuPDF item: {pymupdf_obj}")
    print()

    for rule in rules:
        print(f"Testing rule: {rule.id}")
        print(f"Description: {rule.description}")
        print(f"Conditions: {rule.conditions}")

        # Check if rule matches
        matches = rule.match_condition(llamaparse_obj, pymupdf_obj)
        print(f"Rule matches: {matches}")

        if matches:
            # Generate the node
            node = rule.construct_node(llamaparse_obj, pymupdf_obj)
            print(f"Generated node: {node}")
        else:
            print("Rule does not match, skipping node generation")

        print("-" * 50)


if __name__ == "__main__":
    test_rule_registry()
