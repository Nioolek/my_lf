"""Simple demo graph for LangGraph API."""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
import operator


class State(TypedDict):
    """Graph state with a counter and message history."""
    count: Annotated[int, operator.add]  # Accumulates across calls
    messages: Annotated[list[str], operator.add]  # Accumulates messages


def increment(state: State) -> State:
    """Increment the counter."""
    return {"count": 1, "messages": ["Incremented by 1"]}


def double(state: State) -> State:
    """Double the counter."""
    return {"count": state["count"], "messages": ["Doubled!"]}


def check_threshold(state: State) -> str:
    """Route based on count threshold."""
    if state["count"] >= 10:
        return "done"
    return "continue"


# Build the graph
builder = StateGraph(State)

# Add nodes
builder.add_node("increment", increment)
builder.add_node("double", double)

# Set entry point
builder.set_entry_point("increment")

# Add conditional edge
builder.add_conditional_edges(
    "increment",
    check_threshold,
    {
        "continue": "double",
        "done": END,
    },
)

# Add edge from double back to increment (loop)
builder.add_edge("double", "increment")

# Compile without checkpointer for stateless demo
graph = builder.compile()

# Also export a checkpointer version for stateful runs
from langgraph.checkpoint.memory import MemorySaver
stateful_graph = builder.compile(checkpointer=MemorySaver())