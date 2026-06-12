"""LangGraph graph definition — orchestrates the 6-agent pipeline."""
from langgraph.graph import StateGraph, START, END
from src.graph.state import GraphState
from src.agents.intake import run_intake
from src.agents.context import run_context_collector
from src.agents.hypothesis import run_hypothesis
from src.agents.investigation import run_investigation
from src.agents.fix import run_fix
from src.agents.verification import run_verification

def route_from_verification(state: GraphState) -> str:
    """After verification: retry fix if failed, otherwise end."""
    if state.verification is None:
        return "end"
    if state.verification.get("success"):
        return "end"
    if state.retry_count < state.max_retries:
        return "fix"
    return "end"

def build_graph() -> StateGraph:
    """Build LangGraph with 6 agents."""
    builder = StateGraph(GraphState)

    builder.add_node("intake", run_intake)
    builder.add_node("context_collector", run_context_collector)
    builder.add_node("hypothesis", run_hypothesis)
    builder.add_node("investigation", run_investigation)
    builder.add_node("fix", run_fix)
    builder.add_node("verification", run_verification)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "context_collector")
    builder.add_edge("context_collector", "hypothesis")
    builder.add_edge("hypothesis", "investigation")
    builder.add_edge("investigation", "fix")
    builder.add_edge("fix", "verification")
    builder.add_conditional_edges( "verification", route_from_verification, {"fix": "fix", "end": END})

    return builder.compile()

def run_pipeline(bug_trace: str, project_path: str) -> GraphState:
    """Run the full pipeline and return final state."""
    graph = build_graph()
    initial_state = GraphState(
        bug_trace=bug_trace,
        project_path=project_path,
    )
    result = graph.invoke(initial_state)
    if isinstance(result, dict):
        return GraphState(**result)
    return result

def stream_pipeline(bug_trace: str, project_path: str):
    """Run pipeline with streaming. Yields (node_name, state_update) per node."""
    graph = build_graph()
    initial_state = GraphState(
        bug_trace=bug_trace,
        project_path=project_path,
    )
    merged_state = {}
    for event in graph.stream(initial_state):
        for node_name, updates in event.items():
            merged_state.update(updates)
            yield node_name, updates
    full = initial_state.model_dump()
    full.update(merged_state)
    yield "final", GraphState(**full)
