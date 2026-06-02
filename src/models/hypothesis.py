"""
Represents a root cause hypothesis and the result of investigating it.
Agent 3 generates a list of Hypothesis objects. 
The sandbox agents will investigate and create InvestigationResult. 
"""

from pydantic import BaseModel, Field
from typing import List, Optional

# Possible explanation for the bug
class Hypothesis(BaseModel):
    id : str = Field(..., description="Unique identifier for this hypothesis")
    description : str = Field(..., description="A clear, concise statement of the hypothesis")
    evidence_files : List[str] = Field(..., description="List of file paths that support this hypothesis")
    confidence : float = Field(..., description="Agent's confidence in this hypothesis (0-1)")
    verification_steps : List[str] = Field(..., description="Steps to verify this hypothesis (if known)")
    confirmed : Optional[bool] = Field(default=None, description="Whether this hypothesis has been confirmed or refuted (True/False)")
    rejection_reason : Optional[str] = Field(default=None, description="Reason for rejection if the hypothesis is rejected")

#  Outcome of checking a hypothesis
class InvestigationResult(BaseModel):
    hypothesis_id : str = Field(..., description="ID of the hypothesis being investigated")
    confirmed : bool = Field(..., description="Whether the hypothesis was confirmed or refuted")
    evidence : str = Field(..., description="Summary of what was found during investigation")
    tool_output : List[dict] = Field(..., description="Output from any tools used during investigation") 