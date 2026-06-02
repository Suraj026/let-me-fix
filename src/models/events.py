"""
Tracks all events that happen during debugging — like a log of what each agent is doing, 
for display or debugging. Every agent creates TraceEvent objects. They get stored in 
GraphState.events list. UI will render these for the user to see what's happening.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal, Any

EventType = Literal["thinking", "tool_call", "tool_result", "milestone", "error"]

class TraceEvent(BaseModel):
    agent : str = Field(..., description="Name of the agent that generated this event")
    event_type : EventType = Field(..., description="Type of event")
    content : str = Field(..., description="Main content of the event (e.g., thought text, tool call details, etc.)")
    metadata : Optional[dict[str, Any]] = Field(default_factory=dict, description="Any additional structured data relevant to this event (e.g., tool name, parameters, etc.)")
    timestamp : str = Field(..., description="ISO format timestamp of when this event occurred")
    def __init__(self, **data):
        if "timestamp" not in data:
            from datetime import datetime, timezone
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        super().__init__(**data)