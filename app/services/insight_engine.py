"""Execution-grounded insight generation."""

from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Any

from app.core.state import InsightItem, KpiCard, QueryResult, QueryState, ReportSection


class InsightEngine:
    def generate(self, state: QueryState, result: QueryResult) -> list[InsightItem]:
        if result.row_count == 0:
            return [
                InsightItem(
                    title="No rows returned",
                    detail="The current state produced no rows. Check filters, source selection, or schema mapping.",
                    confidence="medium",
                )
            ]

        insights: list[InsightItem] = [
            InsightItem(
                title="Rows processed",
                detail=f"The pipeline returned {result.row_count} rows in {result.execution_mode} mode.",
                confidence="high",
            )
        ]

        preprocessing = state.data.preprocessing_profile or {}
        duplicate_rows = preprocessing.get("duplicate_rows")
        if isinstance(duplicate_rows, int) and duplicate_rows > 0:
            insights.append(
                InsightItem(
                    title="Duplicate rows detected",
                    detail=f"The uploaded dataset contains {duplicate_rows} duplicate row(s), which may affect aggregate analysis.",
                    confidence="medium",
                )
            )

        outlier_counts = preprocessing.get("outlier_counts", {})
        if isinstance(outlier_counts, dict):
            flagged = [f"{column}: {count}" for column, count in outlier_counts.items() if isinstance(count, int) and count > 0]
            if flagged:
                insights.append(
                    InsightItem(
                        title="Potential outliers in raw data",
                        detail="Potential outlier counts by metric before query filtering: " + ", ".join(flagged[:4]) + ".",
                        confidence="medium",
                    )
                )

        if state.transformation.group_by:
            insights.append(
                InsightItem(
                    title="Grouped analysis",
                    detail=f"Results are grouped by {', '.join(state.transformation.group_by)}.",
                    confidence="high",
                )
            )

        numeric_summary = result.profile.get("numeric_summary", {})
        metric = state.visualization.y_axis[0] if state.visualization.y_axis else None
        metric_for_summary = metric if metric and metric in numeric_summary else next(iter(numeric_summary.keys()), None)
        if metric_for_summary and metric_for_summary in numeric_summary:
            summary = numeric_summary[metric_for_summary]
            insights.append(
                InsightItem(
                    title=f"{metric_for_summary.title()} range",
                    detail=(
                        f"{metric_for_summary.title()} ranges from {summary['min']:.2f} to {summary['max']:.2f}, "
                        f"with an average of {summary['mean']:.2f}."
                    ),
                    confidence="high",
                )
            )

        if metric and state.intent.goal == "trend_analysis":
            trend_insight = self._build_trend_insight(state, result, metric)
            if trend_insight is not None:
                insights.append(trend_insight)

        if metric and state.intent.goal == "comparison":
            comparison_insight = self._build_comparison_insight(state, result, metric)
            if comparison_insight is not None:
                insights.append(comparison_insight)

        if state.intent.goal == "correlation":
            correlation_insight = self._build_correlation_insight(state, result)
            if correlation_insight is not None:
                insights.append(correlation_insight)

        if metric and "anomaly" in state.analysis.type:
            anomaly_insights = self._build_anomaly_insights(result, metric)
            if anomaly_insights:
                insights.extend(anomaly_insights)
            else:
                insights.append(
                    InsightItem(
                        title="Anomaly scan enabled",
                        detail="Anomaly highlighting is enabled, but no strong outliers were detected in the current result set.",
                        confidence="medium",
                    )
                )

        # v4.7 Dashboard Autonomy: Always provide a primary metric lead if possible
        if not any(i.title.startswith("Primary metric") for i in insights):
             primary_metric = self._pick_primary_metric(state, result)
             if primary_metric:
                 insights.append(
                     InsightItem(
                         title=f"Primary metric identified: {primary_metric.title()}",
                         detail=f"I have detected '{primary_metric}' as the main metric for this analysis.",
                         confidence="medium"
                     )
                 )

        return insights

    def build_kpis(self, state: QueryState, result: QueryResult) -> list[KpiCard]:
        profile = result.profile or {}
        numeric_summary = profile.get("numeric_summary", {})
        preprocessing = state.data.preprocessing_profile or {}
        kpis = [
            KpiCard(label="Rows", value=str(result.row_count)),
            KpiCard(label="Columns", value=str(profile.get("column_count", len(result.schema_map)))),
        ]

        primary_metric = self._pick_primary_metric(state, result)
        if primary_metric and primary_metric in numeric_summary:
            summary = numeric_summary[primary_metric]
            kpis.append(
                KpiCard(
                    label=f"Avg {self._labelize(primary_metric)}",
                    value=self._format_number(summary.get("mean")),
                    context=f"Range {self._format_number(summary.get('min'))} to {self._format_number(summary.get('max'))}",
                )
            )

        missing_counts = preprocessing.get("missing_counts", {})
        if isinstance(missing_counts, dict):
            missing_total = sum(count for count in missing_counts.values() if isinstance(count, int))
            kpis.append(KpiCard(label="Missing cells", value=str(missing_total)))

        duplicate_rows = preprocessing.get("duplicate_rows")
        if isinstance(duplicate_rows, int):
            kpis.append(KpiCard(label="Duplicate rows", value=str(duplicate_rows)))

        return kpis[:6]

    def get_raw_report_facts(
        self,
        state: QueryState,
        result: QueryResult,
    ) -> dict[str, Any]:
        preprocessing = state.data.preprocessing_profile or {}
        numeric_summary = result.profile.get("numeric_summary", {})
        primary_metric = self._pick_primary_metric(state, result)
        top_dimension = self._pick_top_dimension(result)

        facts = {
            "row_count": result.row_count,
            "execution_mode": result.execution_mode,
            "group_by": state.transformation.group_by,
            "primary_metric": primary_metric,
            "top_dimension": top_dimension,
            "numeric_summary": {
                k: v for k, v in list(numeric_summary.items())[:5]
            },
            "quality_signals": {
                "missing_counts": preprocessing.get("missing_counts", {}),
                "duplicate_rows": preprocessing.get("duplicate_rows", 0),
                "outlier_counts": preprocessing.get("outlier_counts", {}),
            }
        }
        
        if top_dimension:
            counts = Counter(str(row.get(top_dimension)) for row in result.rows)
            facts["dimension_distribution"] = dict(counts.most_common(5))
            
        return facts

    @staticmethod
    def _build_trend_insight(
        state: QueryState,
        result: QueryResult,
        metric: str,
    ) -> InsightItem | None:
        x_axis = state.visualization.x_axis
        if not x_axis or len(result.rows) < 2:
            return None
        if x_axis not in result.rows[0] or metric not in result.rows[0]:
            return None

        first = result.rows[0]
        last = result.rows[-1]
        try:
            first_value = float(first[metric])
            last_value = float(last[metric])
        except (TypeError, ValueError):
            return None

        delta = last_value - first_value
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "stayed flat"
        if first_value != 0:
            pct = (delta / first_value) * 100
            pct_text = f" ({pct:+.1f}%)"
        else:
            pct_text = ""

        return InsightItem(
            title="Trend change",
            detail=(
                f"{metric.title()} {direction} from {first_value:.2f} at {first[x_axis]} "
                f"to {last_value:.2f} at {last[x_axis]}{pct_text}."
            ),
            confidence="high",
        )

    @staticmethod
    def _build_comparison_insight(
        state: QueryState,
        result: QueryResult,
        metric: str,
    ) -> InsightItem | None:
        group_column = state.transformation.group_by[0] if state.transformation.group_by else state.visualization.x_axis
        if not group_column or len(result.rows) < 2:
            return None
        if group_column not in result.rows[0] or metric not in result.rows[0]:
            return None

        try:
            ordered = sorted(result.rows, key=lambda row: float(row[metric]), reverse=True)
        except (TypeError, ValueError):
            return None

        top = ordered[0]
        bottom = ordered[-1]
        gap = float(top[metric]) - float(bottom[metric])

        return InsightItem(
            title="Top comparison",
            detail=(
                f"{top[group_column]} leads {metric} with {float(top[metric]):.2f}, "
                f"ahead of {bottom[group_column]} by {gap:.2f}."
            ),
            confidence="high",
        )

    @staticmethod
    def _build_anomaly_insights(result: QueryResult, metric: str) -> list[InsightItem]:
        values = []
        for row in result.rows:
            try:
                values.append(float(row[metric]))
            except (TypeError, ValueError, KeyError):
                continue
        if len(values) < 3:
            return []

        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std_dev = sqrt(variance)
        if std_dev == 0:
            return []

        threshold = 1.5
        anomalies: list[tuple[dict, float, float]] = []
        for row in result.rows:
            try:
                value = float(row[metric])
            except (TypeError, ValueError, KeyError):
                continue
            z_score = abs((value - mean) / std_dev)
            if z_score >= threshold:
                anomalies.append((row, value, z_score))

        if not anomalies:
            return []

        anomalies.sort(key=lambda item: item[2], reverse=True)
        top_anomalies = anomalies[:3]

        ranked_items: list[InsightItem] = []
        for index, (row, value, z_score) in enumerate(top_anomalies, start=1):
            context_label = next((key for key in row.keys() if key != metric), metric)
            severity = "high" if z_score >= 2.5 else "medium"
            ranked_items.append(
                InsightItem(
                    title=f"Potential anomaly #{index}",
                    detail=(
                        f"{context_label.title()}={row.get(context_label)} stands out with {metric} at {value:.2f} "
                        f"(z-score {z_score:.2f})."
                    ),
                    confidence=severity,  # type: ignore[arg-type]
                )
            )

        summary = InsightItem(
            title="Anomaly summary",
            detail=(
                f"Detected {len(anomalies)} potential outlier(s) for {metric}. "
                f"The strongest anomaly is {top_anomalies[0][1]:.2f} with z-score {top_anomalies[0][2]:.2f}."
            ),
            confidence="medium",
        )
        return [summary, *ranked_items]

    @staticmethod
    def _build_correlation_insight(
        state: QueryState,
        result: QueryResult,
    ) -> InsightItem | None:
        x_metric = state.visualization.x_axis
        y_metric = state.visualization.y_axis[0] if state.visualization.y_axis else None
        if not x_metric or not y_metric or len(result.rows) < 2:
            return None
        if x_metric not in result.rows[0] or y_metric not in result.rows[0]:
            return None

        pairs: list[tuple[float, float]] = []
        for row in result.rows:
            try:
                pairs.append((float(row[x_metric]), float(row[y_metric])))
            except (TypeError, ValueError, KeyError):
                continue
        if len(pairs) < 2:
            return None

        xs = [pair[0] for pair in pairs]
        ys = [pair[1] for pair in pairs]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
        x_denominator = sqrt(sum((x - x_mean) ** 2 for x in xs))
        y_denominator = sqrt(sum((y - y_mean) ** 2 for y in ys))
        if x_denominator == 0 or y_denominator == 0:
            return None

        correlation = numerator / (x_denominator * y_denominator)
        abs_corr = abs(correlation)
        if abs_corr >= 0.8:
            strength = "strong"
            confidence = "high"
        elif abs_corr >= 0.5:
            strength = "moderate"
            confidence = "medium"
        else:
            strength = "weak"
            confidence = "medium"
        direction = "positive" if correlation > 0 else "negative" if correlation < 0 else "neutral"

        return InsightItem(
            title="Correlation summary",
            detail=(
                f"{x_metric.title()} and {y_metric.title()} show a {strength} {direction} correlation "
                f"(r={correlation:.2f})."
            ),
            confidence=confidence,  # type: ignore[arg-type]
        )

    @staticmethod
    def _pick_primary_metric(state: QueryState, result: QueryResult) -> str | None:
        candidate_order = []
        if state.visualization.y_axis:
            candidate_order.extend(state.visualization.y_axis)
        candidate_order.extend(["revenue", "sales", "cost", "profit", "quantity"])
        candidate_order.extend(result.profile.get("numeric_summary", {}).keys())
        seen: set[str] = set()
        for candidate in candidate_order:
            if not isinstance(candidate, str) or candidate in seen:
                continue
            seen.add(candidate)
            if candidate in result.profile.get("numeric_summary", {}):
                return candidate
        return None

    @staticmethod
    def _pick_top_dimension(result: QueryResult) -> str | None:
        if not result.rows:
            return None
        first = result.rows[0]
        for column, value in first.items():
            if isinstance(value, str):
                return column
        return None

    @staticmethod
    def _labelize(value: str) -> str:
        return value.replace("_", " ").title()

    @staticmethod
    def _format_number(value: float | int | None) -> str:
        if value is None:
            return "n/a"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if abs(number) >= 1000:
            return f"{number:,.2f}"
        return f"{number:.2f}"
