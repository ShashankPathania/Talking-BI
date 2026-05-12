from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field

class ToolResult(BaseModel):
    status: Literal["success", "error"]
    data: Dict[str, Any] = Field(default_factory=dict)
    summary: str = "" # Pillar #4: Required for reflection
    error: Optional[str] = None # Pillar #4

class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the tool for the agent."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Detailed description of what the tool does and when to use it."""
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execution logic for the tool."""
        pass

    def _success(self, data: Any, summary: str) -> ToolResult:
        return ToolResult(status="success", data=data, summary=summary)

    def _error(self, message: str) -> ToolResult:
        return ToolResult(status="error", data={}, summary="", error=message)
