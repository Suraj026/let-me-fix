"""LangGraph graph definition — orchestrates the 3-agent pipeline."""

from langgraph.graph import StateGraph, START, END
from src.graph.state import GraphState
from src.agents.intake import run_intake
from src.agents.context import run_context_collector
from src.agents.hypothesis import run_hypothesis


def build_graph() -> StateGraph:
    """Build LangGraph with 3 agents."""
    builder = StateGraph(GraphState)

    builder.add_node("intake", run_intake)
    builder.add_node("context_collector", run_context_collector)
    builder.add_node("hypothesis", run_hypothesis)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "context_collector")
    builder.add_edge("context_collector", "hypothesis")
    builder.add_edge("hypothesis", END)

    return builder.compile()

def run_pipeline(bug_trace: str, project_path: str) -> GraphState:
    """Run the full Phase 1 pipeline and return final state."""
    graph = build_graph()
    initial_state = GraphState(
        bug_trace=bug_trace,
        project_path=project_path,
    )
    result = graph.invoke(initial_state)
    # LangGraph returns a dict with Pydantic schemas — convert back to model
    if isinstance(result, dict):
        return GraphState(**result)
    return result


def stream_pipeline(bug_trace: str, project_path: str):
    """Run pipeline with streaming. Yields (node_name, state_update) per node.

    After all nodes complete, yields ("final", GraphState) with the complete state.
    """
    graph = build_graph()
    initial_state = GraphState(
        bug_trace=bug_trace,
        project_path=project_path,
    )

    # Collect all state updates as nodes execute
    merged_state = {}
    for event in graph.stream(initial_state):
        for node_name, updates in event.items():
            merged_state.update(updates)
            # Yield the updates for this node so CLI can show progress
            yield node_name, updates

    # Build final GraphState from initial + merged updates
    full = initial_state.model_dump()
    full.update(merged_state)
    yield "final", GraphState(**full)