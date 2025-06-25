import json

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from generate_tiptap_node_schema import generate_node_types_summary
from rule_registry import ConversionRuleRegistry, RuleCondition
from zip_llama_pymupdf import UnifiedBlock

my_llm = ChatOpenAI(model="gpt-4o", temperature=0)


class RuleProposal(BaseModel):
    id: str = Field(
        description="A unique slug-like identifier for this conversion rule. Should be relevant to what the rule does."
    )
    description: str = Field(
        description="A human-readable description of what this rule does, e.g., 'Converts LlamaParse heading items to Tiptap heading nodes'"
    )
    conditions: list[RuleCondition] = Field(
        description="A list of conditions that must be met for this rule to apply. Each condition specifies a source (llamaparse or pymupdf), field, operator, and value"
    )
    output_node_type: str = Field(
        description="The type of Tiptap node this rule produces, e.g., 'heading', 'paragraph', 'listItem', etc. This comes directly from the type field of the relevant TiptapNode sublass that is being created."
    )
    construct_node_function: str = Field(
        description="Python code as a string that constructs the Tiptap node. It's signature is `def construct_node(cls, llamaparse_input: PageItem, pymupdf_inputs: list[Item])` and returns a TiptapNode. Example: 'return HeadingNode(attrs={\"level\": llamaparse_input.lvl}, content=[TextNode(text=llamaparse_input.value)])'"
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


@tool
def query_similar_rules(block: UnifiedBlock, top_k: int = 5) -> str:
    """
    Return top K rules that match this block. Returns JSON summary of matches.
    """
    return _query_similar_rules_impl(block, top_k)


def human_approval_step(rule_proposal):
    print("\n--- Proposed Rule ---")
    print(rule_proposal.model_dump_json(indent=2))
    approval = input("Approve this rule? (y/n): ").strip().lower()

    if approval == "y":
        return rule_proposal  # Pass it on
    else:
        raise ValueError("Rule proposal rejected by human.")


human_approval = RunnableLambda(human_approval_step)


# ---- LangChain LLM chain to propose a new rule ----
def make_llm_chain(llm, parser):
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

    # Create the chain
    chain = prompt | llm | parser | human_approval

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
    llm_chain = make_llm_chain(my_llm, parser)

    # Generate the rule
    result = llm_chain.invoke(
        {
            "block": block,
            "matches": matches,
            "node_types": node_types,
            "format_instructions": format_instructions,
        }
    )

    # Return the result in the format expected by the pipeline
    return {
        "current_block": state.current_block.model_copy(
            update={"conversion_rule": result.id}
        )
    }
