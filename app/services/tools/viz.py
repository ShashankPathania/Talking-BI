from typing import List, Literal, Optional, Dict, Any, Union
from app.services.tools.base import BaseTool, ToolResult
from app.services.visualization.chart_resolver import resolve_chart

class ChartConfigTool(BaseTool):
    @property
    def name(self) -> str:
        return "generate_chart"

    @property
    def description(self) -> str:
        return (
            "Configures a visualization for a given result set. "
            "Arguments: "
            "'chart_intent' (composition|comparison|trend|distribution|relationship), "
            "'chart_type' (optional: line|bar|scatter|histogram|pie), "
            "'x_axis' (str), "
            "'y_axis' (str or list of str), "
            "'title' (str), "
            "'color_by' (optional str)."
        )

    async def execute(
        self, 
        chart_intent: Optional[str] = None,
        chart_type: Optional[str] = None, 
        x_axis: str = "", 
        y_axis: Union[str, List[str]] = None, 
        title: str = "",
        color_by: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        if not x_axis or not y_axis:
            return self._error("x_axis and y_axis must be specified to generate a chart.")

        # Stage 4: Normalize y_axis (Fixes Pydantic Warning)
        if isinstance(y_axis, str):
            y_axis = [y_axis]

        # Stage 5: Resolve Chart Type via Intent Logic
        final_type = resolve_chart(intent=chart_intent, requested_type=chart_type)

        # This tool returns a visualization state that the synthesis layer 
        # will use to call the PlotlyBuilder.
        viz_config = {
            "chart_type": final_type,
            "x_axis": x_axis,
            "y_axis": y_axis,
            "title": title or f"{final_type.title()} Analysis",
            "color_by": color_by
        }

        summary = f"Configured a {final_type} chart for '{x_axis}' (Intent: {chart_intent or 'direct'})."
        return self._success(viz_config, summary)
