import subprocess
from pathlib import Path
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from etl.zip_llama_pymupdf import UnifiedBlock
from rule_registry.propose.propose_new_rule import (
    RuleProposal,
    _query_similar_rules_impl,
    generate_conversion_class,
    test_rule_with_block,
)
from rule_registry.propose.tiptap_node_summary import generate_node_types_summary


# ---- Tools ----
@tool
def query_similar_rules(block: UnifiedBlock) -> str:
    """
    Queries the rule registry for existing rules that are most similar to the given block.
    This should be one of the first tools you use to get context.
    """
    return _query_similar_rules_impl(block)


@tool
def get_available_node_types() -> str:
    """
    Returns a summary of all available Tiptap node types that can be created.
    Use this to see what kind of output nodes you can generate.
    """
    return generate_node_types_summary()


@tool
def codebase_search(query: str) -> str:
    """
    Performs a semantic search of the codebase to find relevant code snippets.
    Useful for finding examples of how to implement a specific conversion or to resolve
    an ImportError if the test phase fails. For example, if a test fails because
    'TableNode' is not defined, you can search for 'TableNode' to find its definition.
    """
    # This is a placeholder for the actual search call, using hardcoded results for now.
    # In a real scenario, this would be a live call to the codebase_search tool.
    print(f"---SEARCHING CODEBASE FOR: {query}---")
    search_results = """
rule_registry/conversion_rules/heading.py:
class HeadingConversion(ConversionRule):
    id: str = "heading"
    ...
    def construct_node(...) -> HeadingNode: ...

rule_registry/conversion_rules/llamaparse_text_to_paragraph.py:
class LlamaparseTextToParagraphConversion(ConversionRule):
    id: str = "llamaparse_text_to_paragraph"
    ...
    def construct_node(...) -> ParagraphNode: ...
"""
    return search_results


# ---- LLM ----
# We bind the RuleProposal Pydantic model as a tool, so the agent can call it to submit its final answer.
my_llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [query_similar_rules, get_available_node_types, codebase_search]
llm_with_tools = my_llm.bind_tools(tools + [RuleProposal])


# ---- Graph State ----
class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        messages: The history of messages in the conversation.
        block: The unified block to be converted.
        rule_proposal: The AI-generated proposal for the new rule.
        generated_code: The Python code for the new rule class.
        test_result: The outcome of testing the generated code.
        retries_left: The number of attempts left for the agent to fix the code.
        final_code: The validated and accepted code.
        file_path: The path where the final rule is saved.
        user_choice: The user's decision from the review step.
    """

    messages: Annotated[list, add_messages]
    block: UnifiedBlock
    rule_proposal: Optional[RuleProposal]
    generated_code: Optional[str]
    test_result: Optional[str]
    retries_left: int
    final_code: Optional[str]
    file_path: Optional[str]
    user_choice: Optional[str]


# ---- Graph Nodes ----
def agent_node(state: GraphState):
    """
    The primary agent node. It decides which tool to use, or whether to propose a final rule.
    """
    print("---AGENT: THINKING---")
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


def process_agent_response(state: GraphState):
    """
    Processes the agent's response to extract the final RuleProposal or tool calls.
    This is where we'll update the state with the proposal.
    """
    print("---PROCESSING AGENT RESPONSE---")
    last_message = state["messages"][-1]

    if not last_message.tool_calls:
        raise ValueError("Agent returned no tool calls.")

    # Check if the proposal tool was called
    proposal_calls = [
        call for call in last_message.tool_calls if call["name"] == "RuleProposal"
    ]
    if proposal_calls:
        # The agent is submitting its final proposal
        print("Agent proposed a rule.")
        proposal_args = proposal_calls[0]["args"]
        rule_proposal = RuleProposal(**proposal_args)
        # We officially set the rule_proposal in the state here
        return {"rule_proposal": rule_proposal}
    else:
        # The agent is calling a standard tool, no proposal yet.
        # The ToolNode will handle the calls, so we don't need to return anything here.
        print("Agent is calling a tool.")
        return {}


def generate_code(state: GraphState):
    """Generates the Python class code from the RuleProposal."""
    print("---GENERATING CODE---")
    if not state["rule_proposal"]:
        raise ValueError("Rule proposal is missing.")
    code = generate_conversion_class(state["rule_proposal"])
    return {"generated_code": code, "final_code": None}


def test_generated_code(state: GraphState):
    """Tests the generated Python code."""
    print("---TESTING GENERATED CODE---")
    code = state.get("final_code") or state.get("generated_code")
    block = state["block"]
    rule_id = state["rule_proposal"].id
    if not code:
        return {"test_result": "Error: No code was generated."}

    temp_file_path = Path(f"temp_rule_test_{rule_id}.py")
    try:
        temp_file_path.write_text(code)
        test_success, message = test_rule_with_block(temp_file_path, block)
        if test_success:
            print("✅ Test passed!")
            return {"test_result": "success", "final_code": code}
        else:
            print(f"❌ Test failed: {message}")
            return {"test_result": f"Failed: {message}"}
    except Exception as e:
        return {"test_result": f"Exception during test: {str(e)}"}
    finally:
        temp_file_path.unlink(missing_ok=True)


def human_review(state: GraphState):
    """Presents the code to the user for review."""
    print("---HUMAN REVIEW---")
    # Use the successfully tested code if available, otherwise fall back to the last generated code.
    code_to_review = state.get("final_code") or state.get("generated_code")
    if not code_to_review:
        print("❌ No code available for review.")
        return {"user_choice": "reject"}

    rule_id = state["rule_proposal"].id
    temp_file_path = Path(f"rule_registry/conversion_rules/temp_review_{rule_id}.py")
    temp_file_path.write_text(code_to_review)

    while True:
        print("\nFinal proposed rule is ready for review.")
        subprocess.call(["cursor", str(temp_file_path)])
        print("\nPlease review the code. Options:")
        print("  a - Accept and save.")
        print("  e - I have edited the file. Test the new version.")
        print("  r - Reject and exit.")
        choice = input("Choose (a/e/r): ").lower().strip()

        if choice == "a":
            return {"user_choice": "accept"}
        elif choice == "e":
            edited_code = temp_file_path.read_text()
            return {"user_choice": "edit", "final_code": edited_code}
        elif choice == "r":
            temp_file_path.unlink(missing_ok=True)
            return {"user_choice": "reject"}


def save_rule(state: GraphState):
    """Saves the final, accepted code."""
    print("---SAVING RULE---")
    final_code = state.get("final_code")
    rule_id = state["rule_proposal"].id
    if not final_code:
        return {}

    rule_registry_dir = Path("rule_registry/conversion_rules")
    rule_registry_dir.mkdir(exist_ok=True)
    final_file_path = rule_registry_dir / f"{rule_id}.py"
    final_file_path.write_text(final_code)
    print(f"✅ Rule saved to: {final_file_path}")
    Path(f"rule_registry/conversion_rules/temp_review_{rule_id}.py").unlink(
        missing_ok=True
    )
    return {"file_path": str(final_file_path)}


def handle_test_failure(state: GraphState):
    """
    Handles the logic for a failed code test. It decrements the retry counter
    and adds a descriptive error message to the conversation history to guide
    the agent's next attempt. It also cleans up the previous proposal tool call.
    """
    print("---HANDLING TEST FAILURE---")
    retries_left = state.get("retries_left", 0) - 1
    test_result = state.get("test_result", "Unknown error")

    # Find the last assistant message that contained the RuleProposal tool call and remove it.
    # This is important to prevent the API from seeing an unanswered tool call on the next loop.
    messages = state["messages"]
    last_assistant_message_index = -1
    for i in range(len(messages) - 1, -1, -1):
        if (
            hasattr(messages[i], "tool_calls")
            and messages[i].tool_calls
            and any(call["name"] == "RuleProposal" for call in messages[i].tool_calls)
        ):
            last_assistant_message_index = i
            break

    if last_assistant_message_index != -1:
        # Remove the message with the proposal tool call
        messages.pop(last_assistant_message_index)

    # Add a new human-readable error message for the agent to process
    error_message = f"""
The previous attempt to generate and test a rule failed.
Here is the error:
<error>
{test_result}
</error>

Please analyze this error and generate a new, corrected `RuleProposal`. Do not make the same mistake again.
"""

    return {
        "messages": [HumanMessage(content=error_message)],
        "retries_left": retries_left,
        "rule_proposal": None,  # Clear the old proposal
    }


# ---- Conditional Edges ----
def should_call_tools_or_generate(state: GraphState):
    """
    After the agent has responded, decide whether to call tools or generate the final code.
    """
    print("---ROUTING---")
    if state.get("rule_proposal"):
        # A proposal has been set by process_agent_response
        return "generate_code"
    else:
        # No proposal yet, so we must be calling a tool
        return "call_tool"


def should_retry_or_review(state: GraphState):
    """After a test, decide whether to retry, review, or exit."""
    test_result = state.get("test_result", "")
    retries_left = state.get("retries_left", 0)

    if "success" in test_result.lower():
        return "human_review"
    elif retries_left > 0:
        # Go back to the agent to fix the error
        return "handle_failure"
    else:
        print(
            "❌ Agent failed to generate valid code. Proceeding to human review for manual correction."
        )
        return "human_review"


def after_human_review(state: GraphState):
    """Routes after the user has reviewed the code."""
    user_choice = state.get("user_choice")
    if user_choice == "accept":
        return "save_rule"
    elif user_choice == "edit":
        return "test_code"
    else:
        return END


# ---- Graph Definition ----
def build_graph():
    workflow = StateGraph(GraphState)

    # Nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("process_agent_response", process_agent_response)
    tool_node = ToolNode(tools)
    workflow.add_node("tools", tool_node)
    workflow.add_node("generate_code", generate_code)
    workflow.add_node("test_code", test_generated_code)
    workflow.add_node("handle_failure", handle_test_failure)
    workflow.add_node("human_review", human_review)
    workflow.add_node("save_rule", save_rule)

    # Edges
    workflow.set_entry_point("agent")
    workflow.add_edge("agent", "process_agent_response")
    workflow.add_conditional_edges(
        "process_agent_response",
        should_call_tools_or_generate,
        {"call_tool": "tools", "generate_code": "generate_code"},
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge("generate_code", "test_code")
    workflow.add_conditional_edges(
        "test_code",
        should_retry_or_review,
        {
            "human_review": "human_review",
            "handle_failure": "handle_failure",
            END: END,
        },
    )
    workflow.add_edge("handle_failure", "agent")
    workflow.add_conditional_edges(
        "human_review",
        after_human_review,
        {
            "save_rule": "save_rule",
            "test_code": "test_code",
            END: END,
        },
    )
    workflow.add_edge("save_rule", END)

    return workflow.compile()


# --- Main execution logic ---
def propose_new_rule_graph(block: UnifiedBlock):
    """The main function to run the rule proposal graph."""
    app = build_graph()

    initial_prompt = f"""
You are an expert in document parsing. A 'UnifiedBlock' of data needs to be converted into a Tiptap node.
Your goal is to generate a valid `RuleProposal` that can be used to perform this conversion.

Use the available tools to gather context about existing rules and available output formats.
Once you have enough information, call the `RuleProposal` tool to submit your final answer.

The block to convert is:
{block.model_dump_json(indent=2)}
"""

    print(f"""
Generating a new rule for {block.model_dump_json(indent=2)}
          """)

    initial_messages = [HumanMessage(content=initial_prompt)]

    # Start the graph execution
    final_state = app.invoke(
        {"messages": initial_messages, "block": block, "retries_left": 3}
    )

    return {
        "rule": final_state.get("rule_proposal"),
        "code": final_state.get("final_code"),
        "file_path": final_state.get("file_path"),
    }
