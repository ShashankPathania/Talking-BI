from typing import Literal, Dict, Any
from app.services.tools.base import BaseTool, ToolResult
from app.core.state import AgentReflection

class ReflectionTool(BaseTool):
    @property
    def name(self) -> str:
        return "reflect"

    @property
    def description(self) -> str:
        return (
            "Analyzes the results of the previous tool execution to decide on the next step. "
            "Use this after every analytical tool call. "
            "Required arguments: "
            "'success' (bool), "
            "'useful' (bool), "
            "'next_action' (continue|retry|finish), "
            "'reason' (str)."
        )

    async def execute(
        self, 
        success: bool = True, 
        useful: bool = True, 
        next_action: Literal["continue", "retry", "finish"] = "continue",
        reason: str = "",
        **kwargs
    ) -> ToolResult:
        # This tool returns a structured AgentReflection object
        # which will be parsed by the Execution Controller.
        reflection = AgentReflection(
            success=success,
            useful=useful,
            error_detected=not success,
            next_action=next_action,
            reason=reason
        )

        summary = f"Reflection: Agent decided to {next_action}. Reason: {reason}"
        return self._success(reflection.model_dump(), summary)
