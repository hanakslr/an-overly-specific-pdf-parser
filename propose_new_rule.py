import json
from typing import Optional

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt.tool_node import ToolNode
from pydantic import BaseModel

from rule_registry import ConversionRuleRegistry, RuleCondition
from zip_llama_pymupdf import UnifiedBlock

my_llm = ChatOpenAI(model="gpt-4o", temperature=0)


class RuleProposal(BaseModel):
    id: str
    description: str
    conditions: list[RuleCondition]
    output_node_type: str
    tiptap_node: dict


# ---- Tool to enumerate all available node types ----
def _list_available_node_types_impl() -> str:
    """
    Internal implementation of list_available_node_types without tool decoration.
    """
    import inspect

    from tiptap_models import TiptapNode

    node_info = {}
    for cls in TiptapNode.__subclasses__():
        sig = inspect.signature(cls)
        node_info[cls.__name__] = {
            "type": getattr(cls, "type", cls.__name__.lower()),
            "constructor": str(sig),
        }
    return json.dumps(node_info, indent=2)


@tool
def list_available_node_types() -> str:
    """
    Return a JSON list of available Tiptap node types and their constructor signatures.
    """
    return _list_available_node_types_impl()


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


# ---- LangChain LLM chain to propose a new rule ----
def make_llm_chain(llm):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert in document parsing. You generate rules to convert UnifiedBlocks into Tiptap nodes.",
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

Propose a new conversion rule in the following JSON format:
{{
  "id": "...",
  "description": "...",
  "conditions": [...],
  "output_node_type": "...",
  "tiptap_node": {{ ... }}
}}
""",
            ),
        ]
    )
    parser = PydanticOutputParser(pydantic_object=RuleProposal)

    # Create the chain
    chain = prompt | llm | parser

    return chain


# ---- LangGraph-compatible tool node for proposing a rule ----
class ProposeNewRuleInput(BaseModel):
    block: UnifiedBlock


class ProposeNewRuleTool:
    def __init__(self, llm):
        self.llm_chain = make_llm_chain(llm)

    def __call__(
        self, inputs: ProposeNewRuleInput, config: Optional[RunnableConfig] = None
    ) -> RuleProposal:
        block = inputs.block
        matches = _query_similar_rules_impl(block)
        return self.llm_chain.invoke({"block": block, "matches": matches})


@tool
def propose_new_rule(block: UnifiedBlock) -> RuleProposal:
    """Given a UnifiedBlock that contains input from LlamaParse and PyMuPdf,
    propose a rule that converts it into a TiptapNode (a representation of
    a prosemirror node)

    Args:
        block: A UnifiedBlock containing LlamaParse and PyMuPDF data

    Returns:
        A RuleProposal containing the proposed conversion rule
    """
    matches = query_similar_rules(block)
    node_types = list_available_node_types()
    return make_llm_chain(my_llm).invoke(
        {"block": block, "matches": matches, "node_types": node_types}
    )


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
    node_types = _list_available_node_types_impl()

    # Create the LLM chain
    llm_chain = make_llm_chain(my_llm)

    # Generate the rule
    result = llm_chain.invoke(
        {"block": block, "matches": matches, "node_types": node_types}
    )

    # Return the result in the format expected by the pipeline
    return {
        "current_block": state.current_block.model_copy(
            update={"conversion_rule": result.id}
        )
    }
