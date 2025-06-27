import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from doc_server.helpers import append_to_document
from etl.zip_llama_pymupdf import UnifiedBlock
from rule_registry.conversion_rules import ConversionRuleRegistry, RuleCondition
from rule_registry.propose.tiptap_node_summary import generate_node_types_summary
from tiptap.tiptap_models import TiptapNode

my_llm = ChatOpenAI(model="gpt-4o", temperature=0)


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


def human_approval_step(rule_proposal):
    print("\n--- Proposed Rule ---")
    print(rule_proposal.model_dump_json(indent=2))
    approval = input("Approve this rule? (y/n): ").strip().lower()

    if approval == "y":
        return rule_proposal  # Pass it on
    else:
        raise ValueError("Rule proposal rejected by human.")


human_approval = RunnableLambda(human_approval_step)


def test_rule_with_block(temp_file_path: Path, block: UnifiedBlock):
    """
    Test the rule by dynamically importing it and calling construct_node with the block.
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
            print("❌ Could not find ConversionRule class in the file")
            return False

        # Create an instance of the rule class
        rule_instance = rule_class()

        # Test if the rule matches the block
        if not rule_instance.match_condition(
            block.llama_item, block.fitz_items[0] if block.fitz_items else None
        ):
            print("❌ Rule conditions do not match the block")
            return False

        # Call construct_node with the block
        result_node = rule_instance.construct_node(block.llama_item, block.fitz_items)

        # Check if the result is a valid TiptapNode

        if isinstance(result_node, TiptapNode):
            print(f"✅ Rule generated valid {type(result_node).__name__}")
            print(f"Node content: {result_node}")

            # Append to document
            append_to_document([result_node])
            print("✅ Node appended to document")
            return True
        else:
            print(f"❌ Rule returned {type(result_node).__name__}, expected TiptapNode")
            return False

    except Exception as e:
        print(f"❌ Error testing rule: {e}")
        return False


def review_and_compile(rule_and_context):
    # Extract rule and block from the context
    if isinstance(rule_and_context, dict):
        rule = rule_and_context.get("rule")
        block = rule_and_context.get("block")
    else:
        rule = rule_and_context
        block = None

    # 1. Generate class text
    class_code = generate_conversion_class(rule)

    # 2. Open in Cursor editor - create file in rule_registry directory
    rule_registry_dir = Path("rule_registry/conversion_rules")
    temp_file_path = rule_registry_dir / f"temp_{rule.id}_conversion.py"

    # Write the generated code to the file
    temp_file_path.write_text(class_code)
    edited_code = class_code

    def reload():
        nonlocal edited_code
        edited_code = temp_file_path.read_text()
        print("[bold blue]Final Edited Rule Class:[/bold blue]")
        print(edited_code)

        # Test the rule with the block if available
        if block:
            print("\n🧪 Testing rule with current block...")
            test_rule_with_block(temp_file_path, block)

    while True:
        # Show block context if available
        if block:
            print("\n[bold yellow]Block being converted:[/bold yellow]")
            print(f"LlamaParse: {block.llama_item}")
            print(f"PyMuPDF items: {len(block.fitz_items)} items")
            print("---")

        # Open in Cursor
        subprocess.call(["cursor", str(temp_file_path)])

        # 4. Ask for user decision
        print("\nOptions:")
        print("a - Accept and save rule")
        print("r - Reload and edit again")
        print("x - Reject and exit")

        choice = input("Choose (a/r/x): ").lower().strip()

        if choice == "a":
            # Accept and save the rule
            final_file_path = rule_registry_dir / f"{rule.id}.py"
            final_file_path.write_text(edited_code)

            # Clean up the temporary file
            temp_file_path.unlink(missing_ok=True)

            print(f"✅ Rule saved to: {final_file_path}")
            return {
                "rule": rule,
                "code": edited_code,
                "file_path": str(final_file_path),
            }

        elif choice == "r":
            # Reload - continue the loop to edit again
            reload()
            print("🔄 Reloading for editing...")
            continue

        elif choice == "x":
            # Reject - clean up and raise exception
            temp_file_path.unlink(missing_ok=True)
            raise ValueError("Rule was rejected by user")

        else:
            print("Invalid choice. Please enter 'a', 'r', or 'x'.")
            continue


# ------- Conversion class ----------
def generate_conversion_class(rule: RuleProposal) -> str:
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


# ---- LangChain LLM chain to propose a new rule ----
def make_llm_chain(llm, parser, block):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert in document parsing, you are given the same content in multiple structures and your job is to resolve them into a ProseMirror/Tiptap node. You generate rules to convert UnifiedBlocks into Tiptap nodes.",
            ),
            (
                "human",
                """Here is a block of structured content:

Block:
{block}

Here are the top matching existing rules:
{matches}

Available node types:
{node_types}

Propose a new RuleProposal.

Return the result as JSON following this schema:
{format_instructions}
""",
            ),
        ]
    )

    # Create a function that combines the rule with the block context
    def combine_rule_with_context(rule):
        return {"rule": rule, "block": block}

    # Create the chain
    chain = (
        prompt
        | llm
        | parser
        | RunnableLambda(combine_rule_with_context)
        | RunnableLambda(review_and_compile)
    )

    return chain


# Create a simple function that works with the pipeline
def propose_new_rule_node(state):
    """
    Function that extracts the current block from PipelineState
    and generates a new conversion rule using the LLM.
    """
    # Extract the current block from the state
    block = state.current_block

    # Get similar rules
    matches = _query_similar_rules_impl(block)

    # Get available node types
    node_types = generate_node_types_summary()

    parser = PydanticOutputParser(pydantic_object=RuleProposal)
    format_instructions = parser.get_format_instructions()

    # Create the LLM chain
    llm_chain = make_llm_chain(my_llm, parser, block)

    # Generate the rule
    result = llm_chain.invoke(
        {
            "block": block,
            "matches": matches,
            "node_types": node_types,
            "format_instructions": format_instructions,
        }
    )

    print(f"Results of chain: {result}")

    # Return the result in the format expected by the pipeline
    return {
        "current_block": state.current_block.model_copy(
            update={"conversion_rule": result["rule"].id}
        )
    }
