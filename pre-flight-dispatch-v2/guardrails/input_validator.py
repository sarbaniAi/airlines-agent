"""
Pre-Flight Dispatch V2 — Input Validation Guardrail.

Validates and sanitizes all user inputs before they reach the LLM
or the database layer.
"""

import re
import logging
from typing import Any

logger = logging.getLogger("guardrails.input_validator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Flight ID format: AI-XXX where XXX is 3-digit number (100-999)
FLIGHT_ID_PATTERN = re.compile(r"^AI-\d{3}$")

# Maximum lengths
MAX_CHAT_MESSAGE_LENGTH = 2000
MAX_FLIGHT_ID_LENGTH = 6

# Prompt injection patterns (case-insensitive)
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if",
    r"new\s+system\s+prompt",
    r"override\s+system\s+prompt",
    r"<\s*system\s*>",
    r"\{\{.*system.*\}\}",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    r"ignore\s+safety",
    r"bypass\s+guardrails",
    r"<!--.*-->",
    r"<script",
    r"javascript:",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__",
    r"subprocess",
    r"os\.system",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM",
    r"INSERT\s+INTO",
    r"UPDATE\s+.*SET",
    r"UNION\s+SELECT",
    r";\s*SELECT",
    r"--\s+",
    r"1\s*=\s*1",
    r"OR\s+1\s*=\s*1",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# Dangerous characters to strip
DANGEROUS_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Validation Functions
# ---------------------------------------------------------------------------

def validate_flight_id(flight_id: str) -> dict[str, Any]:
    """
    Validate a flight ID.

    Checks:
        - Not empty
        - Matches format AI-XXX (3 digits)
        - Within valid numeric range (100-999)

    Args:
        flight_id: The flight ID string to validate.

    Returns:
        {valid: bool, error: str | None, sanitized: str | None}
    """
    if not flight_id:
        return {"valid": False, "error": "Flight ID is required", "sanitized": None}

    flight_id = flight_id.strip().upper()

    if len(flight_id) > MAX_FLIGHT_ID_LENGTH:
        return {"valid": False, "error": f"Flight ID too long (max {MAX_FLIGHT_ID_LENGTH} chars)", "sanitized": None}

    if not FLIGHT_ID_PATTERN.match(flight_id):
        return {
            "valid": False,
            "error": f"Invalid flight ID format: '{flight_id}'. Expected format: AI-XXX (e.g., AI-680)",
            "sanitized": None,
        }

    # Check numeric range
    num = int(flight_id.split("-")[1])
    if num < 100 or num > 999:
        return {
            "valid": False,
            "error": f"Flight number {num} out of range (100-999)",
            "sanitized": None,
        }

    return {"valid": True, "error": None, "sanitized": flight_id}


def validate_chat_input(message: str) -> dict[str, Any]:
    """
    Validate a chat message for prompt injection and safety.

    Checks:
        - Not empty
        - Within maximum length
        - No prompt injection patterns detected
        - No dangerous characters

    Args:
        message: The user chat message to validate.

    Returns:
        {valid: bool, error: str | None, sanitized: str | None, warnings: list[str]}
    """
    warnings: list[str] = []

    if not message or not message.strip():
        return {
            "valid": False,
            "error": "Message cannot be empty",
            "sanitized": None,
            "warnings": warnings,
        }

    message = message.strip()

    if len(message) > MAX_CHAT_MESSAGE_LENGTH:
        return {
            "valid": False,
            "error": f"Message too long ({len(message)} chars). Maximum is {MAX_CHAT_MESSAGE_LENGTH}.",
            "sanitized": None,
            "warnings": warnings,
        }

    # Check for prompt injection
    injection_matches = []
    for pattern in _COMPILED_PATTERNS:
        match = pattern.search(message)
        if match:
            injection_matches.append(match.group())

    if injection_matches:
        logger.warning(
            f"Prompt injection detected in chat input. Patterns matched: {injection_matches}"
        )
        return {
            "valid": False,
            "error": "Message contains disallowed content. Please rephrase your question about the flight dispatch.",
            "sanitized": None,
            "warnings": [f"Blocked pattern: {m}" for m in injection_matches],
        }

    # Check for excessive special characters (potential obfuscated injection)
    special_ratio = sum(1 for c in message if not c.isalnum() and c not in " .,?!;:'-/()@#") / max(len(message), 1)
    if special_ratio > 0.4:
        warnings.append("High ratio of special characters detected")
        logger.warning(f"Suspicious input: high special char ratio ({special_ratio:.2f})")

    # Sanitize
    sanitized = sanitize_input(message)

    return {
        "valid": True,
        "error": None,
        "sanitized": sanitized,
        "warnings": warnings,
    }


def sanitize_input(text: str) -> str:
    """
    Strip dangerous characters from input text while preserving
    legitimate aviation terminology and punctuation.

    Args:
        text: Raw input text.

    Returns:
        Sanitized text string.
    """
    if not text:
        return ""

    # Remove control characters
    text = DANGEROUS_CHARS.sub("", text)

    # Remove null bytes
    text = text.replace("\x00", "")

    # Normalize whitespace (but keep newlines for readability)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def validate_api_request(request_data: dict) -> dict[str, Any]:
    """
    Validate a complete API request payload.

    Args:
        request_data: The parsed request body.

    Returns:
        {valid: bool, error: str | None, sanitized_data: dict | None}
    """
    if not isinstance(request_data, dict):
        return {"valid": False, "error": "Request body must be a JSON object", "sanitized_data": None}

    sanitized = {}

    # Validate flight_id if present
    if "flight_id" in request_data:
        fid_result = validate_flight_id(request_data["flight_id"])
        if not fid_result["valid"]:
            return {"valid": False, "error": fid_result["error"], "sanitized_data": None}
        sanitized["flight_id"] = fid_result["sanitized"]

    # Validate message if present
    if "message" in request_data:
        msg_result = validate_chat_input(request_data["message"])
        if not msg_result["valid"]:
            return {"valid": False, "error": msg_result["error"], "sanitized_data": None}
        sanitized["message"] = msg_result["sanitized"]

    return {"valid": True, "error": None, "sanitized_data": sanitized}
