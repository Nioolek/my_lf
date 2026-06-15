"""Agent graph for LangGraph API demo - think & respond pattern."""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
import operator


class AgentState(TypedDict):
    """Agent state with query, reasoning steps, and answer."""
    query: str
    steps: Annotated[list[str], operator.add]
    answer: str


def think(state: AgentState) -> AgentState:
    """Think about the query."""
    return {"steps": [f"Thinking about: {state['query']}"]}


def respond(state: AgentState) -> AgentState:
    """Generate a response."""
    return {"answer": f"Answer to '{state['query']}': 42"}


# Build the graph
builder = StateGraph(AgentState)
builder.add_node("think", think)
builder.add_node("respond", respond)
builder.set_entry_point("think")
builder.add_edge("think", "respond")
builder.add_edge("respond", END)

# Compile without checkpointer for registration
graph = builder.compile()
