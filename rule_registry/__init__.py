"""
Rules are how our structured PDF input gets translated to ProseMirror JSON.
"""

import importlib
import os
from pathlib import Path
from typing import Any, Literal, Optional

from llama_cloud_services.parse.types import PageItem
from pydantic import BaseModel

from extract_structured_pdf import Item
from tiptap_models import TiptapNode


class RuleCondition(BaseModel):
    source: Literal["pymupdf", "llamaparse"]
    field: str  # e.g., "font.size" or "type"
    operator: Literal["==", ">", "<", ">=", "<=", "in"]
    value: Any  # e.g., "heading", 18.0, ["section", "header"]


class ConversionRuleRegistry:
    """Registry for managing conversion rules."""

    _rules = {}
    _initialized = False

    @classmethod
    def _discover_and_import_rules(cls):
        """Dynamically discover and import all rule files in this directory."""
        if cls._initialized:
            return

        # Get the directory containing this __init__.py file
        current_dir = Path(__file__).parent

        # Find all Python files in the directory (excluding __init__.py and __pycache__)
        for file_path in current_dir.glob("*.py"):
            if file_path.name in ["__init__.py", "__pycache__"]:
                continue

            # Import the module to trigger __init_subclass__ registration
            module_name = f"rule_registry.{file_path.stem}"
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                print(f"Warning: Could not import {module_name}: {e}")

        cls._initialized = True

    @classmethod
    def register_instance(cls, rule_instance):
        """Register a rule instance (for dynamic registration)."""
        cls._discover_and_import_rules()
        cls._rules[rule_instance.id] = type(rule_instance)
        return rule_instance

    @classmethod
    def get_all_rules(cls):
        """Get all registered rules as instances."""
        cls._discover_and_import_rules()
        return [rule_class() for rule_class in cls._rules.values()]

    @classmethod
    def clear(cls):
        """Clear all registered rules (useful for testing)."""
        cls._rules.clear()
        cls._initialized = False


class ConversionRule(BaseModel):
    id: str  # for debugging
    description: str
    conditions: list[RuleCondition]
    output_node_type: str

    def __init_subclass__(cls, **kwargs):
        """Automatically register subclasses when they're defined."""
        super().__init_subclass__(**kwargs)
        # Register the class after it's fully defined
        ConversionRuleRegistry._rules[cls.id] = cls

    def match_condition(
        cls, llamaparse_input: PageItem, pymupdf_input: Optional[Item]
    ) -> bool:
        for condition in cls.conditions:
            # Get the appropriate input object based on source
            if condition.source == "llamaparse":
                input_obj = llamaparse_input
            else:  # pymupdf
                input_obj = pymupdf_input

            # Extract the field value using the field path
            field_value = getattr(input_obj, condition.field, None)

            # Apply the operator
            condition_matches = False
            if condition.operator == "==":
                condition_matches = field_value == condition.value
            elif condition.operator == ">":
                condition_matches = field_value > condition.value
            elif condition.operator == "<":
                condition_matches = field_value < condition.value
            elif condition.operator == ">=":
                condition_matches = field_value >= condition.value
            elif condition.operator == "<=":
                condition_matches = field_value <= condition.value
            elif condition.operator == "in":
                condition_matches = field_value in condition.value

            # If any condition fails, the rule doesn't match
            if not condition_matches:
                return False

        # All conditions matched
        return True

    def construct_node(
        llamaparse_input: PageItem, pymupdf_inputs: list[Item]
    ) -> TiptapNode:
        pass
