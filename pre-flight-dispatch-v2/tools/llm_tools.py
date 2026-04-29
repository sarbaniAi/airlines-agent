"""
LLM calling tools — all calls go through ai_query via SQL Statement Execution SDK.
The app's service principal CANNOT call serving endpoints directly.
Includes token tracking for cost estimation.
"""

import json
import logging
import time
import threading

try:
    import mlflow
    HAS_MLFLOW = True
except ImportError:
    HAS_MLFLOW = False

from config import LLM_MODEL
from tools.sql_tools import execute_raw

logger = logging.getLogger("tools.llm")


# ═══════════════════════════════════════════════════════════════════════════
# Token Tracker — Global session-level metrics
# ═══════════════════════════════════════════════════════════════════════════
class TokenTracker:
    """Thread-safe token usage tracker."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.total_calls = 0
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_latency_ms = 0
            self.calls = []  # per-call details
            self.session_start = time.time()

    def record(self, input_tokens: int, output_tokens: int, latency_ms: float, model: str = "", purpose: str = ""):
        with self._lock:
            self.total_calls += 1
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_latency_ms += latency_ms
            self.calls.append({
                "call_num": self.total_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "latency_ms": round(latency_ms, 1),
                "model": model,
                "purpose": purpose,
                "timestamp": time.time(),
            })

    def get_stats(self) -> dict:
        with self._lock:
            total_tokens = self.total_input_tokens + self.total_output_tokens
            elapsed = time.time() - self.session_start
            # Cost estimation (approximate for GPT-OSS-120B pay-per-token)
            # Input: ~$0.00027/1K tokens, Output: ~$0.0011/1K tokens
            input_cost = (self.total_input_tokens / 1000) * 0.00027
            output_cost = (self.total_output_tokens / 1000) * 0.0011
            return {
                "total_calls": self.total_calls,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": total_tokens,
                "total_latency_ms": round(self.total_latency_ms, 1),
                "avg_latency_ms": round(self.total_latency_ms / max(self.total_calls, 1), 1),
                "estimated_cost_usd": round(input_cost + output_cost, 4),
                "input_cost_usd": round(input_cost, 4),
                "output_cost_usd": round(output_cost, 4),
                "model": LLM_MODEL,
                "session_duration_sec": round(elapsed, 1),
                "tokens_per_second": round(total_tokens / max(elapsed, 0.1), 1),
                "recent_calls": self.calls[-10:],  # last 10 calls
            }

    def get_for_flight(self, start_time: float) -> dict:
        """Get token stats for calls after start_time (for per-dispatch tracking)."""
        with self._lock:
            flight_calls = [c for c in self.calls if c["timestamp"] >= start_time]
            input_t = sum(c["input_tokens"] for c in flight_calls)
            output_t = sum(c["output_tokens"] for c in flight_calls)
            input_cost = (input_t / 1000) * 0.00027
            output_cost = (output_t / 1000) * 0.0011
            return {
                "calls": len(flight_calls),
                "input_tokens": input_t,
                "output_tokens": output_t,
                "total_tokens": input_t + output_t,
                "estimated_cost_usd": round(input_cost + output_cost, 4),
            }


# Global tracker instance
token_tracker = TokenTracker()


def _estimate_tokens(text: str) -> int:
    """Estimate token count (~4 chars per token for English)."""
    return max(1, len(text) // 4)


def _escape_sql_string(text: str) -> str:
    """Escape single quotes for safe SQL embedding."""
    return text.replace("'", "''")


def _truncate(text: str, max_chars: int = 12000) -> str:
    """Truncate long prompts to stay within ai_query limits."""
    if len(text) > max_chars:
        return text[:max_chars] + "\n...(truncated)"
    return text


def llm_call(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> str:
    """
    Call the LLM via ai_query through the SQL warehouse.

    Args:
        system_prompt: System-level instructions.
        user_prompt: The user / task prompt.
        max_tokens: Maximum response tokens (informational — ai_query has its own limits).
        temperature: Sampling temperature (informational).

    Returns:
        The LLM's text response, or empty string on failure.
    """
    combined = f"System: {system_prompt}\n\nUser: {user_prompt}"
    escaped = _escape_sql_string(_truncate(combined))

    sql = f"SELECT ai_query('{LLM_MODEL}', '{escaped}') AS response"

    input_tokens = _estimate_tokens(combined)
    start = time.time()

    span = None
    try:
        if HAS_MLFLOW:
            span = mlflow.start_span(name="llm_call", span_type="LLM")
            span.set_inputs({
                "system_prompt": system_prompt[:200],
                "user_prompt": user_prompt[:200],
                "model": LLM_MODEL,
            })
    except Exception:
        span = None

    try:
        rows = execute_raw(sql)
        latency = (time.time() - start) * 1000

        if rows and rows[0].get("response"):
            response_text = rows[0]["response"]
            output_tokens = _estimate_tokens(response_text)
            token_tracker.record(input_tokens, output_tokens, latency, LLM_MODEL, "llm_call")

            try:
                if span is not None:
                    span.set_outputs({
                        "response": response_text[:500],
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "latency_ms": round(latency, 1),
                    })
                    span.end()
            except Exception:
                pass

            return response_text

        token_tracker.record(input_tokens, 0, latency, LLM_MODEL, "llm_call_empty")

        try:
            if span is not None:
                span.set_outputs({"response": "", "input_tokens": input_tokens, "output_tokens": 0})
                span.end()
        except Exception:
            pass

        return ""
    except Exception as e:
        latency = (time.time() - start) * 1000
        token_tracker.record(input_tokens, 0, latency, LLM_MODEL, "llm_call_error")
        logger.error("llm_call failed: %s", e)

        try:
            if span is not None:
                span.set_outputs({"error": str(e)})
                span.end()
        except Exception:
            pass

        return ""


def llm_structured_call(
    system_prompt: str,
    user_prompt: str,
    output_schema: dict | None = None,
    max_tokens: int = 2000,
) -> dict:
    """
    Call the LLM and parse the response as structured JSON.

    If ai_query's modelParameters are not available, we embed the schema
    request in the prompt and parse the JSON from the response.

    Args:
        system_prompt: System-level instructions.
        user_prompt: The user / task prompt.
        output_schema: Optional JSON schema dict describing expected output.
        max_tokens: Maximum tokens.

    Returns:
        Parsed dict, or {"error": "..."} on failure.
    """
    schema_instruction = ""
    if output_schema:
        schema_instruction = (
            "\n\nIMPORTANT: Respond ONLY with valid JSON matching this schema "
            "(no markdown, no extra text):\n"
            + json.dumps(output_schema, indent=2)
        )

    full_system = system_prompt + schema_instruction

    raw = llm_call(full_system, user_prompt, max_tokens=max_tokens, temperature=0.1)

    if not raw:
        return {"error": "Empty LLM response"}

    # Try to extract JSON from the response
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Handle markdown-wrapped JSON
    for delimiter in ("```json", "```"):
        if delimiter in raw:
            try:
                json_str = raw.split(delimiter)[1].split("```")[0]
                return json.loads(json_str.strip())
            except (json.JSONDecodeError, IndexError):
                continue

    logger.warning("Could not parse structured response — returning raw text under 'raw' key")
    return {"raw": raw}
