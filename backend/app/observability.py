"""Optional LangSmith tracing for FastAPI, graph nodes, and ordinary services."""
from functools import lru_cache, wraps
import logging
import os
import inspect

from langsmith import Client, get_current_run_tree, traceable, tracing_context

logger = logging.getLogger(__name__)


def tracing_enabled() -> bool:
    return os.getenv("LANGSMITH_TRACING", "false").lower() in {"true", "1"} and bool(os.getenv("LANGSMITH_API_KEY"))


@lru_cache(maxsize=1)
def get_trace_client() -> Client:
    return Client(
        hide_inputs=os.getenv("LANGSMITH_HIDE_INPUTS", "true").lower() != "false",
        hide_outputs=os.getenv("LANGSMITH_HIDE_OUTPUTS", "true").lower() != "false",
    )


def observed(name: str, run_type: str = "chain"):
    """Trace once, preserving application return values and exceptions.

    Setting the context also connects automatic LangGraph spans and OpenAI
    wrapper spans to the same project/client, including its payload policy.
    """
    def decorate(function):
        @wraps(function)
        def with_outcome(*args, **kwargs):
            result = function(*args, **kwargs)
            run = get_current_run_tree()
            if run is not None and isinstance(result, dict):
                run.add_metadata({
                    "outcome": "fallback" if result.get("errors") or result.get("routing_error") else "completed",
                    "validation_error_count": len(result.get("errors") or []),
                    **({"intent": result["intent"]} if isinstance(result.get("intent"), str) else {}),
                })
            return result

        instrumented = traceable(name=name, run_type=run_type)(with_outcome)

        @wraps(function)
        def wrapped(*args, **kwargs):
            enabled = tracing_enabled()
            client = None
            if enabled:
                try:
                    client = get_trace_client()
                except Exception:
                    logger.warning("LangSmith client initialization failed; tracing disabled")
                    enabled = False
            with tracing_context(enabled=enabled, client=client,
                                 project_name=os.getenv("LANGSMITH_PROJECT") or "food-safety-ai-agent",
                                 tags=["guiltless"], metadata={"service": "guiltless-api"}):
                return instrumented(*args, **kwargs)
        # FastAPI resolves annotations on the wrapper's module unless supplied
        # an evaluated signature; preserve request-body and response contracts.
        wrapped.__signature__ = inspect.signature(function, eval_str=True)
        return wrapped
    return decorate


def flush_traces() -> None:
    if get_trace_client.cache_info().currsize:
        try:
            get_trace_client().flush(timeout=5)
        except Exception:
            logger.warning("LangSmith flush did not complete before shutdown")
