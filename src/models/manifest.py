""" 
Describes files in the project being debugged and how relevant they are 
to the bug. This is used to help the system understand which files to focus on when 
generating fixes.
Agent 1 builds a list of FileInfo for the project. Tools like grep/ChromaDB return ScoredFile. 
Agent 2 collects ScoredFile lists and passes them to Agent 3.
"""

from pydantic import BaseModel, Field
from typing import Optional

#  Metadata about a single file
class FileInfo(BaseModel):
    path : str = Field(..., description="File path relative to project root")
    size : int = Field(..., description="File size in bytes")
    is_notebook : bool = Field(default=False, description="Whether this file is a Jupyter notebook")
    language : Optional[str] = Field(default=None, description="Programming language (e.g., Python)")

# A file with a relevance score (used after searching)
class ScoredFile(BaseModel):
    file_info : FileInfo = Field(..., description="Metadata about the file")
    relevance_score : float = Field(..., description="Score indicating how relevant this file is to the bug (0-1)")
    match_reason : str = Field(..., description="Explanation of why this file is relevant")