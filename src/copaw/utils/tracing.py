# -*- coding: utf-8 -*-
import logging
import os

logger = logging.getLogger(__name__)


def setup_langfuse() -> bool:
    """Monkey-patch openai SDK with Langfuse instrumentation.

    Reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from env.
    No-ops silently if keys are missing or langfuse is not installed.
    """
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return False
    try:
        from langfuse.openai import openai  # noqa: F401 - side-effect import
        logger.info("Langfuse tracing enabled")
        return True
    except ImportError:
        logger.debug("langfuse not installed, tracing disabled")
        return False


def create_trace(session_id: str, user_id: str, input_preview: str = ""):
    """Create a Langfuse trace for one agent query. Returns trace or None."""
    try:
        from langfuse import Langfuse
        return Langfuse().trace(
            name="agent_query",
            session_id=session_id,
            user_id=user_id,
            input=input_preview,
        )
    except Exception:
        return None


def flush():
    """Flush pending Langfuse events (call at end of each request)."""
    try:
        from langfuse import Langfuse
        Langfuse().flush()
    except Exception:
        pass
