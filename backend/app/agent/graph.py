"""Request-scoped orchestration; durable memory remains in SQLAlchemy.

No checkpointer is used: replaying a graph could repeat commerce/client writes.
Each request executes at most one selected tool, followed by response assembly.
"""
from __future__ import annotations

from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.router import CopilotRouter, TOOL_CONTEXT_ERRORS
from app.services.action_recommender import recommend_actions
from app.services.copilot_router import detect_intent


class CopilotState(TypedDict, total=False):
    message: str
    context: dict[str, Any]
    user_id: str | None
    load_memory: bool
    intent: str
    result: dict[str, Any]
    routing_error: str | None
    output: dict[str, Any]


class CopilotGraph:
    def __init__(self, router: CopilotRouter, memory_loader: Callable[[str], dict[str, Any]]):
        self.router = router
        self.memory_loader = memory_loader
        graph = StateGraph(CopilotState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("detect_intent", self._detect_intent)
        graph.add_node("tool", self._execute)
        graph.add_node("chat", self._execute)
        graph.add_node("fallback", self._fallback)
        graph.add_node("respond", self._respond)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "detect_intent")
        graph.add_conditional_edges("detect_intent", lambda s: "chat" if s["intent"] == "general_chat" else "tool")
        for node in ("tool", "chat"):
            graph.add_conditional_edges(node, lambda s: "fallback" if s.get("routing_error") else "respond")
        graph.add_edge("fallback", "respond")
        graph.add_edge("respond", END)
        self.graph = graph.compile()

    def route(self, message: str, context: dict[str, Any] | None = None,
              *, user_id: str | None = None, load_memory: bool = False) -> dict[str, Any]:
        return self.graph.invoke({"message": message, "context": dict(context or {}),
                                  "user_id": user_id, "load_memory": load_memory,
                                  "routing_error": None})["output"]

    def _load_context(self, state: CopilotState) -> dict[str, Any]:
        context = dict(state["context"])
        if state["load_memory"]:
            memory = self.memory_loader(state["user_id"] or "demo-user")
            context["memory"] = memory
            for key in ("profile", "bag", "recent_plans", "recent_scans", "recent_messages"):
                context.setdefault(key, memory.get(key))
            # Explicit current context wins over saved defaults, including []
            # (for example an intentionally cleared bag).
            for key, value in memory["profile"].items():
                if key != "user_id":
                    context.setdefault("days_per_week" if key == "training_days" else key, value)
            plans = memory.get("recent_plans", {}).get("meal_plans", [])
            if plans:
                context.setdefault("meal_plan", plans[0]["plan"])
            scans = memory.get("recent_scans", [])
            if scans and isinstance(scans[0].get("scan", {}).get("product"), dict):
                context.setdefault("product", scans[0]["scan"]["product"])
        return {"context": context}

    def _detect_intent(self, state: CopilotState) -> dict[str, Any]:
        return {"intent": detect_intent(state["message"])}

    def _execute(self, state: CopilotState) -> dict[str, Any]:
        try:
            return {"result": self.router._dispatch(state["intent"], state["message"], state["context"])}
        except TOOL_CONTEXT_ERRORS as exc:
            return {"routing_error": f"{state['intent']}: {exc}"}

    def _fallback(self, state: CopilotState) -> dict[str, Any]:
        try:
            result = self.router._general_chat(state["message"], state["context"], routing_failed=True)
        except TOOL_CONTEXT_ERRORS:
            result = self.router._deterministic_chat(state["context"], routing_failed=True)
        return {"intent": "general_chat", "result": {**result, "mode": "routing_fallback", "tool_result": None}}

    def _respond(self, state: CopilotState) -> dict[str, Any]:
        result = state["result"]
        return {"output": {"intent": state["intent"], "response": result["response"],
                           "suggested_actions": recommend_actions(state["context"], state["intent"]),
                           "tool_result": result.get("tool_result"), "mode": result.get("mode", "tool"),
                           "routing_error": state.get("routing_error"), "context_used": state["context"]}}
