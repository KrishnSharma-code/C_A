"""
LangGraph orchestrator - defines the multi-agent graph with checkpointing.
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from backend.agents.state import AnalysisState
from backend.agents.agent_nodes import (
    file_structure_agent,
    code_chunking_agent,
    api_extractor_agent,
    web_search_agent,
    sde_doc_agent,
    pm_doc_agent,
    diagram_agent
)


def build_analysis_graph():
    """Build and compile the LangGraph analysis graph."""

    graph = StateGraph(AnalysisState)

    graph.add_node("file_structure_agent", file_structure_agent)
    graph.add_node("code_chunking_agent", code_chunking_agent)
    graph.add_node("api_extractor_agent", api_extractor_agent)
    graph.add_node("web_search_agent", web_search_agent)
    graph.add_node("sde_doc_agent", sde_doc_agent)
    graph.add_node("pm_doc_agent", pm_doc_agent)
    graph.add_node("diagram_agent", diagram_agent)

    graph.add_edge(START, "file_structure_agent")
    graph.add_edge("file_structure_agent", "code_chunking_agent")
    graph.add_edge("code_chunking_agent", "api_extractor_agent")
    graph.add_edge("api_extractor_agent", "web_search_agent")
    graph.add_edge("web_search_agent", "sde_doc_agent")
    graph.add_edge("sde_doc_agent", "pm_doc_agent")
    graph.add_edge("pm_doc_agent", "diagram_agent")
    graph.add_edge("diagram_agent", END)

    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)
    return compiled


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_analysis_graph()
    return _graph
