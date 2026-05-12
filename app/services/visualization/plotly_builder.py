"""Plotly chart generation from query state and execution output."""

from __future__ import annotations

import base64
import json
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
from plotly.utils import PlotlyJSONEncoder

from app.core.state import ChartPayload, InsightItem, QueryResult, QueryState


class PlotlyBuilder:
    def build(
        self,
        state: QueryState,
        result: QueryResult,
        insights: list[InsightItem],
    ) -> ChartPayload | None:
        if not result.rows:
            return None

        frame = pd.DataFrame(result.rows)
        # Drop columns that are completely missing so they aren't plotted as empty boxes
        frame = frame.dropna(axis=1, how="all")
        if frame.empty:
            return None

        chart_type = state.visualization.chart_type

        # "table" is a valid visualization type that means "no chart needed"
        if chart_type == "table":
            return None

        title = state.visualization.title
        
        # v4.4 High-Recall Column Mapping
        x_axis = self._find_column(state.visualization.x_axis, frame.columns)
        requested_y = state.visualization.y_axis[0] if state.visualization.y_axis else None
        y_axis = self._find_column(requested_y, frame.columns)
        
        color_by = self._find_column(state.visualization.color_by, frame.columns)

        # v4.7 Dashboard Autonomy: Metric Hunting
        # If the agent gave us generic data but no axes, find the best KPIs
        if (not x_axis or not y_axis) and len(frame.columns) > 0:
            numeric_cols = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
            categorical_cols = [c for c in frame.columns if not pd.api.types.is_numeric_dtype(frame[c])]
            metric_prio = ["revenue", "sales", "profit", "total", "quantity", "cost", "age", "count"]
            
            # Goal: Pick a category for X and a high-prio numeric for Y
            if not y_axis and numeric_cols:
                # Prioritize metrics in the prio list
                y_axis = next((c for c in metric_prio if c in [col.lower() for col in numeric_cols]), numeric_cols[0])
                # Resolve the actual column name (original case)
                y_axis = next((c for c in numeric_cols if c.lower() == y_axis.lower()), y_axis)
                
            if not x_axis:
                 if categorical_cols:
                     x_axis = categorical_cols[0]
                 elif len(numeric_cols) > 1:
                     # Use the first numeric column that isn't the Y-axis
                     x_axis = next((c for c in numeric_cols if c != y_axis), numeric_cols[0])

        if color_by and color_by == x_axis:
            color_by = None

        # v4.4 Analytical Polish: Sorting & Trimming
        if chart_type in ["bar", "pie"] and y_axis in frame.columns:
            frame = frame.sort_values(y_axis, ascending=False)
            if chart_type == "bar":
                frame = frame.head(15) # Keep bars manageable
            elif chart_type == "pie" and len(frame) > 10:
                # Group small slices into 'Others'
                top_9 = frame.head(9).copy()
                others_val = frame.iloc[9:][y_axis].sum()
                others_row = pd.DataFrame([{x_axis: "Others", y_axis: others_val}])
                frame = pd.concat([top_9, others_row], ignore_index=True)

        # Auto-generate a descriptive title when the default "Analysis" is used
        title = self._auto_title(title, chart_type, x_axis, y_axis, color_by)

        # v4.4 Premium Design System: Layout & Colors
        LAYOUT_CONFIG = {
            "template": "plotly_dark",
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)",
            "margin": dict(l=40, r=40, t=60, b=40),
            "font": dict(family="Inter, sans-serif", size=12),
            "colorway": ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52"]
        }

        figure = None

        try:
            if chart_type == "line" and x_axis in frame.columns and y_axis in frame.columns:
                figure = px.line(frame, x=x_axis, y=y_axis, color=color_by, title=title)
            elif chart_type == "bar" and x_axis in frame.columns and y_axis in frame.columns:
                figure = px.bar(frame, x=x_axis, y=y_axis, color=color_by, title=title)
            elif chart_type == "scatter" and x_axis in frame.columns and y_axis in frame.columns:
                figure = px.scatter(frame, x=x_axis, y=y_axis, color=color_by, title=title)
            elif chart_type == "histogram":
                hist_col = y_axis if y_axis in frame.columns else (x_axis if x_axis in frame.columns else None)
                if hist_col:
                    figure = px.histogram(frame, x=hist_col, color=color_by, title=title)
            elif chart_type == "pie" and x_axis in frame.columns and y_axis in frame.columns:
                figure = px.pie(frame, names=x_axis, values=y_axis, title=title, hole=0.4)
            
            if figure:
                figure.update_layout(**LAYOUT_CONFIG)
                
        except Exception as e:
            print(f"Plotly Rendering Error: {str(e)}. Falling back to Bar chart.")
            figure = None

        # Fallback: try to build a sensible bar chart from available columns
        if figure is None:
            numeric_cols = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
            non_numeric_cols = [c for c in frame.columns if c not in numeric_cols]
            if numeric_cols and non_numeric_cols:
                fb_x = non_numeric_cols[0]
                fb_y = numeric_cols[0]
                title = self._auto_title(title, "bar", fb_x, fb_y, None)
                figure = px.bar(frame.head(15), x=fb_x, y=fb_y, title=title)
                chart_type = "bar"
            elif numeric_cols and len(numeric_cols) >= 2:
                fb_x = numeric_cols[0]
                fb_y = numeric_cols[1]
                title = self._auto_title(title, "bar", fb_x, fb_y, None)
                figure = px.bar(frame.head(15), x=fb_x, y=fb_y, title=title)
                chart_type = "bar"
            elif len(frame.columns) >= 2:
                figure = px.bar(frame.head(15), x=frame.columns[0], y=frame.columns[1], title=title)
                chart_type = "bar"
            else:
                # Single column — show a histogram
                figure = px.histogram(frame, x=frame.columns[0], title=title or f"Distribution of {frame.columns[0].replace('_', ' ').title()}")
                chart_type = "histogram"

        return ChartPayload(
            figure=self._sanitize_plotly_payload(
                json.loads(json.dumps(figure.to_plotly_json(), cls=PlotlyJSONEncoder))
            ),
            chart_type=chart_type,
            title=title,
        )

    def build_dashboard(self, state: QueryState, result: QueryResult) -> list[ChartPayload]:
        if not result.rows:
            return []

        frame = pd.DataFrame(result.rows).dropna(axis=1, how="all")
        if frame.empty:
            return []

        charts: list[ChartPayload] = []
        numeric_columns = [
            column for column in frame.columns
            if pd.api.types.is_numeric_dtype(frame[column])
        ]
        dimension_columns = [column for column in frame.columns if column not in numeric_columns]
        metric_priority = ["revenue", "sales", "profit", "cost", "quantity"]
        numeric_columns = sorted(
            numeric_columns,
            key=lambda column: (
                metric_priority.index(column) if column in metric_priority else len(metric_priority),
                column,
            ),
        )
        time_column = next((column for column in frame.columns if "date" in column.lower() or "time" in column.lower()), None)
        primary_metric = numeric_columns[0] if numeric_columns else None

        if time_column and primary_metric:
            time_frame = frame.copy()
            time_frame[time_column] = pd.to_datetime(time_frame[time_column], errors="coerce")
            time_frame = time_frame.dropna(subset=[time_column]).sort_values(time_column)
            if not time_frame.empty:
                figure = px.line(
                    time_frame,
                    x=time_column,
                    y=primary_metric,
                    title=f"{primary_metric.replace('_', ' ').title()} over time",
                )
                charts.append(self._payload_from_figure(figure, "line", figure.layout.title.text))

        if dimension_columns and primary_metric:
            top_dim = self._best_dimension(frame, dimension_columns)
            grouped = (
                frame.groupby(top_dim, as_index=False)[primary_metric]
                .sum()
                .sort_values(primary_metric, ascending=False)
                .head(10)
            )
            if not grouped.empty:
                figure = px.bar(
                    grouped,
                    x=top_dim,
                    y=primary_metric,
                    title=f"{primary_metric.replace('_', ' ').title()} by {top_dim.replace('_', ' ').title()}",
                )
                charts.append(self._payload_from_figure(figure, "bar", figure.layout.title.text))

        if primary_metric:
            figure = px.histogram(
                frame,
                x=primary_metric,
                title=f"Distribution of {primary_metric.replace('_', ' ').title()}",
            )
            charts.append(self._payload_from_figure(figure, "histogram", figure.layout.title.text))

        if len(dimension_columns) >= 2 and primary_metric:
            sunburst_frame = (
                frame.groupby(dimension_columns[:2], as_index=False)[primary_metric]
                .sum()
                .sort_values(primary_metric, ascending=False)
                .head(20)
            )
            if not sunburst_frame.empty:
                figure = px.sunburst(
                    sunburst_frame,
                    path=dimension_columns[:2],
                    values=primary_metric,
                    title=f"{primary_metric.replace('_', ' ').title()} hierarchy",
                )
                charts.append(self._payload_from_figure(figure, "sunburst", figure.layout.title.text))

        if len(numeric_columns) >= 2:
            figure = px.scatter(
                frame,
                x=numeric_columns[0],
                y=numeric_columns[1],
                color=dimension_columns[0] if dimension_columns else None,
                title=f"{numeric_columns[0].replace('_', ' ').title()} vs {numeric_columns[1].replace('_', ' ').title()}",
            )
            charts.append(self._payload_from_figure(figure, "scatter", figure.layout.title.text))

        return charts[:5]

    @staticmethod
    def _auto_title(
        current_title: str | None,
        chart_type: str,
        x_axis: str | None,
        y_axis: str | None,
        color_by: str | None,
    ) -> str:
        """Generate a descriptive title when the current one is the generic default."""
        if current_title and current_title not in {"Analysis", "", None}:
            return current_title

        def _label(name: str) -> str:
            return name.replace("_", " ").title()

        if y_axis and x_axis:
            base = f"{_label(y_axis)} by {_label(x_axis)}"
        elif y_axis:
            base = f"{_label(y_axis)} Overview"
        elif x_axis:
            base = f"{_label(x_axis)} Overview"
        else:
            return current_title or "Analysis"

        type_labels = {
            "line": "Trend",
            "bar": "Comparison",
            "scatter": "Correlation",
            "histogram": "Distribution",
        }
        suffix = type_labels.get(chart_type, "")
        if suffix:
            base = f"{base} — {suffix}"
        if color_by:
            base += f" (colored by {_label(color_by)})"
        return base

    @staticmethod
    def _best_dimension(frame: pd.DataFrame, dimension_columns: list[str]) -> str:
        ranked = sorted(
            dimension_columns,
            key=lambda column: (
                frame[column].nunique(dropna=True),
                column,
            ),
        )
        return ranked[0] if ranked else dimension_columns[0]

    @staticmethod
    def _payload_from_figure(figure, chart_type: str, title: str | None) -> ChartPayload:
        return ChartPayload(
            figure=PlotlyBuilder._sanitize_plotly_payload(
                json.loads(json.dumps(figure.to_plotly_json(), cls=PlotlyJSONEncoder))
            ),
            chart_type=chart_type,
            title=title,
        )

    @staticmethod
    def _sanitize_plotly_payload(value):
        if isinstance(value, dict):
            if set(value.keys()) == {"dtype", "bdata"}:
                try:
                    decoded = base64.b64decode(value["bdata"])
                    return np.frombuffer(decoded, dtype=np.dtype(value["dtype"])).tolist()
                except Exception:
                    return value
            return {
                key: PlotlyBuilder._sanitize_plotly_payload(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [PlotlyBuilder._sanitize_plotly_payload(item) for item in value]
        return value

    def _find_column(self, target: Optional[str], columns: list[str]) -> str | None:
        """v4.4 High-Recall Matcher: Case-insensitive and fuzzy matching."""
        if not target:
            return None
        
        # Exact match
        if target in columns:
            return target
        
        # Case-insensitive
        target_lower = target.lower().strip()
        for col in columns:
            if col.lower() == target_lower:
                return col
        
        # Substring/Fuzzy (e.g., 'revenue' matches 'total_revenue')
        for col in columns:
            col_lower = col.lower()
            if target_lower in col_lower or col_lower in target_lower:
                return col
        
        return None
