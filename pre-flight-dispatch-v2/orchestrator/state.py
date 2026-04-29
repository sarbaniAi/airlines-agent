"""
LangGraph state definition for Pre-Flight Dispatch V2.
"""

from typing import TypedDict, Optional


class DispatchState(TypedDict):
    """State that flows through the LangGraph dispatch pipeline."""

    # Input
    flight_id: str

    # Loaded from UC
    flight_info: dict

    # Agent results (None until their node runs)
    aircraft_health: Optional[dict]
    crew_legality: Optional[dict]
    weather_notam: Optional[dict]
    regulatory_compliance: Optional[dict]
    genie_analytics: Optional[dict]

    # Final decision
    decision: Optional[dict]

    # Messaging / progress
    messages: list
    current_agent: str
    retry_count: int
