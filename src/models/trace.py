""" 
Represents a parsed bug trace - the raw error info in a Python stack trace
and the structured data extracted from it. This is the main input to the system.
Agent 1 (Bug Intake) populates this after parsing a trace file. 
Agents 2 and 3 read it to decide what to investigate.
"""

from pydantic import BaseModel, Field
from typing import List, Optional

# Holds the error itself
class ErrorSignature(BaseModel):
    type : str = Field(..., description="Type of error (e.g., SyntaxError, TypeError)")
    message : str = Field(..., description="Error message")
    file : Optional[str] = Field(default=None, description="File where the error occurred")
    line : Optional[int] = Field(default=None, description="Line number of the error")
    function : Optional[str] = Field(default=None, description="Function where the error occurred")
# Full parsed output
class ParsedTrace(BaseModel):
    error : ErrorSignature = Field(..., description="The parsed error signature")
    traceback_lines : List[str] = Field(..., description="List of lines from the traceback")
    raw_text : str = Field(..., description="The full raw traceback text")