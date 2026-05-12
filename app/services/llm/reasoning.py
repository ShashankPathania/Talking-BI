"""Hybrid LLM reasoning helpers with deterministic safety guards."""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

from app.core.state import (
    AggregationSpec,
    ColumnProfile,
    ExecutionPlan,
    FilterCondition,
    InsightItem,
    QueryResult,
    QueryState,
    ReportSection,
    SortSpec,
)
from app.services.llm.client import LLMClient


class LLMReasoningService:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def enabled(self) -> bool:
        return self.client.enabled()

    async def infer_schema(self, state: QueryState) -> ColumnProfile | None:
        if not self.enabled() or not state.data.schema_map:
            return None

        system_prompt = (
            "You are a BI schema assistant. Return JSON with metrics, dimensions, and time_column. "
            "Use only columns that exist in the schema."
        )
        user_prompt = (
            "Infer BI-friendly schema roles from this dataset schema.\n"
            f"Schema: {state.data.schema_map}\n"
            "Return JSON like "
            '{"metrics":["revenue"],"dimensions":["region"],"time_column":"date"}'
        )
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="light",
        )
        if not payload:
            return None

        schema_keys = set(state.data.schema_map.keys())
        metrics = [
            item for item in payload.get("metrics", [])
            if isinstance(item, str) and item in schema_keys
        ]
        dimensions = [
            item for item in payload.get("dimensions", [])
            if isinstance(item, str) and item in schema_keys
        ]
        time_column = payload.get("time_column")
        if not isinstance(time_column, str) or time_column not in schema_keys:
            time_column = None
        return ColumnProfile(
            metrics=metrics,
            dimensions=dimensions,
            time_column=time_column,
        )

    async def classify_user_intent(
        self,
        message: str,
        chat_history: list[dict[str, str]],
    ) -> dict[str, Any]:
        fallback = {"is_greeting": False, "conversational_reply": None, "is_new_topic": False, "is_visualization_only": False, "is_full_report": False}
        if not self.enabled():
            return fallback

        system_prompt = (
            "You are a routing supervisor for a Conversational BI system. "
            "Analyze the user's incoming message against recent chat history. "
            "Your goal is to determine if the user is asking a data question or just chatting. "
            "Return only JSON. "
            "- is_greeting: Set to True if the message is a greeting (hello, hi), a thank you, a request for help, or any general chat/question NOT requiring a dataset query. "
            "- conversational_reply: If is_greeting is True, provide a direct, warm, and helpful response. If the user asks a non-data question, answer it naturally. "
            "- is_new_topic: Set to True if the user is switching context or starting a completely new analysis. "
            "- is_visualization_only: Set to True if the user only wants to change the chart type of the current data. "
            "- is_full_report: Set to True if the user wants an overview/dashboard of the entire dataset."
        )
        user_prompt = (
            f"User message: {message}\n"
            f"Recent chat history: {chat_history[-4:]}\n"
            "Respond with a JSON object containing the keys: is_greeting, conversational_reply, is_new_topic, is_visualization_only, is_full_report."
        )
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="light",
        )
        if not payload:
            return fallback

        return {
            "is_greeting": bool(payload.get("is_greeting", False)),
            "conversational_reply": payload.get("conversational_reply") if isinstance(payload.get("conversational_reply"), str) else None,
            "is_new_topic": bool(payload.get("is_new_topic", False)),
            "is_visualization_only": bool(payload.get("is_visualization_only", False)),
            "is_full_report": bool(payload.get("is_full_report", False)),
        }

    async def suggest_state_update(
        self,
        current_state: QueryState,
        proposed_state: QueryState,
        message: str,
        chat_history: list[dict[str, str]],
    ) -> QueryState | None:
        if not self.enabled():
            return None

        system_prompt = (
            "Conversational BI state update engine. Return JSON only. "
            "Produce partial updates grounded in schema and state. "
            "Never invent columns or return full SQL."
        )
        user_prompt = (
            f"User message: {message}\n"
            f"Chat history: {chat_history[-6:]}\n"
            f"Current state: {current_state.model_dump(mode='json', by_alias=True)}\n"
            f"Heuristic proposal: {proposed_state.model_dump(mode='json', by_alias=True)}\n"
            "Return JSON with optional keys: "
            '{"intent":{"type":"","goal":"","confidence":0.0},'
            '"transformation":{"filters":[],"group_by":[],"aggregations":[],"time_granularity":null,"sort":null,"limit":null},'
            '"analysis":{"type":[],"parameters":{}},'
            '"visualization":{"chart_type":"","x_axis":"","y_axis":[],"color_by":"","title":"","options":{}}}'
        )
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="heavy",
        )
        if not payload:
            return None
        return self._merge_state_safely(proposed_state, payload)

    async def interpret_query(
        self,
        current_state: QueryState,
        seeded_state: QueryState | None,
        message: str,
        chat_history: list[dict[str, str]],
    ) -> tuple[QueryState | None, dict[str, Any] | None, dict[str, Any] | None]:
        if not self.enabled():
            return None, None, None

        system_prompt = (
            "Primary BI reasoning engine. Map queries to schema and return JSON. "
            "Validate answerability. Recommend multiple visual perspectives for charts. "
            "If the user is asking a general question or just chatting, set is_answerable to false "
            "and provide a natural response in unanswerable_reason. "
            "Provide read-only SQL for database sources."
        )
        
        data_preview = current_state.data.preprocessing_profile.get("data_preview", [])
        
        user_prompt = (
            f"User message: {message}\n"
            f"Recent chat history: {chat_history[-8:]}\n"
            f"Current state: {current_state.model_dump(mode='json', by_alias=True)}\n"
            f"Dataset schema: {current_state.data.schema_map}\n"
            f"Allowed Canonical Column Names: {list(current_state.data.schema_map.keys())}\n"
            f"Sample Data Rows: {data_preview}\n"
            "CRITICAL RULES:\n"
            "1. Validate Answerability: Set is_answerable to false and provide unanswerable_reason if the data/schema cannot support the query. "
            "If it's a greeting or general question, provide the answer in unanswerable_reason.\n"
            "2. You MUST ONLY use columns from the 'Allowed Canonical Column Names' array above in your JSON (filters, aggregations, x_axis, y_axis, etc).\n"
            "3. If the user asks for a dimension or metric not present in the allowed columns, DO NOT hallucinate it. Put it in 'missing_terms'.\n"
            "4. Do NOT use wildcards (*) in aggregation columns. Always explicitly name the column being counted.\n"
            "Return JSON with keys: "
            '{'
            '"is_answerable": true,'
            '"unanswerable_reason": null,'
            '"intent":{"type":"","goal":"","confidence":0.0},'
            '"transformation":{"filters":[],"group_by":[],"aggregations":[],"time_granularity":null,"sort":null,"limit":null},'
            '"analysis":{"type":[],"parameters":{}},'
            '"recommended_visualizations":[{"chart_type":"","x_axis":null,"y_axis":[],"color_by":null,"title":"","options":{}}],'
            '"dataset_match":{"matched_columns":[],"missing_terms":[],"notes":[]},'
            '"sql":{"query":null}'
            '}'
        )
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="heavy",
        )
        if not payload:
            return None, None, None

        merge_base = seeded_state.model_copy(deep=True) if seeded_state is not None else current_state.model_copy(deep=True)
        state = self._merge_state_safely(merge_base, payload)
        dataset_match = payload.get("dataset_match") if isinstance(payload.get("dataset_match"), dict) else None
        sql_block = payload.get("sql") if isinstance(payload.get("sql"), dict) else None
        
        is_answerable = payload.get("is_answerable", True)
        unanswerable_reason = payload.get("unanswerable_reason")
        recommended_visualizations = payload.get("recommended_visualizations", [])

        if dataset_match:
            state.meta.reasoning = {
                "matched_columns": dataset_match.get("matched_columns", []),
                "missing_terms": dataset_match.get("missing_terms", []),
                "notes": dataset_match.get("notes", []),
                "reasoning_mode": "llm_primary",
            }
        else:
            state.meta.reasoning = {"reasoning_mode": "llm_primary"}
            
        if sql_block and isinstance(sql_block.get("query"), str):
            normalized_query = self._normalize_sql_query(sql_block["query"], state)
            validated_query = self._validate_read_only_sql(normalized_query, state)
            sql_block["query"] = validated_query
            
        metadata = {
            "is_answerable": is_answerable,
            "unanswerable_reason": unanswerable_reason,
            "recommended_visualizations": recommended_visualizations
        }

        return state, (sql_block or None), metadata

    async def refine_plan(
        self,
        previous_state: QueryState | None,
        state: QueryState,
        previous_result: QueryResult | None,
        deterministic_plan: ExecutionPlan,
    ) -> ExecutionPlan | None:
        if not self.enabled():
            return None

        system_prompt = "BI planning assistant. Return JSON. Recommend actions grounded in state delta and result availability. Don't invent tools."
        user_prompt = (
            f"Previous state: {previous_state.model_dump(mode='json', by_alias=True) if previous_state else None}\n"
            f"Current state: {state.model_dump(mode='json', by_alias=True)}\n"
            f"Previous result available: {previous_result is not None}\n"
            f"Deterministic baseline plan: {deterministic_plan.model_dump(mode='json', by_alias=True)}\n"
            "Return JSON like "
            '{"reuse_previous_data":false,"update_visualization_only":false,"run_analysis":true,'
            '"steps":["load_data","transform_data"],"rationale":"..."}'
        )
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="light",
        )
        if not payload:
            return None

        plan = deterministic_plan.model_copy(deep=True)
        safe_reuse = bool(payload.get("reuse_previous_data")) and deterministic_plan.reuse_previous_data
        safe_visual_only = bool(payload.get("update_visualization_only")) and deterministic_plan.update_visualization_only
        safe_run_analysis = deterministic_plan.run_analysis and bool(payload.get("run_analysis", True))

        plan.reuse_previous_data = safe_reuse
        plan.update_visualization_only = safe_visual_only
        plan.needs_new_fetch = not safe_reuse
        plan.run_analysis = False if safe_visual_only else safe_run_analysis

        steps = payload.get("steps", [])
        if isinstance(steps, list):
            plan.steps = [step for step in steps if isinstance(step, str)] or plan.steps
        rationale = payload.get("rationale")
        if isinstance(rationale, str) and rationale.strip():
            plan.rationale = rationale.strip()
        return plan

    async def build_grounded_explanation(
        self,
        state: QueryState,
        result: QueryResult,
        insights: list[InsightItem],
        plan: ExecutionPlan,
    ) -> str | None:
        if not self.enabled():
            return None

        system_prompt = "BI response writer. Use only grounded facts. Don't invent values/causality. Keep it concise."
        user_prompt = (
            f"Query state: {self._make_json_safe(state.model_dump(mode='json', by_alias=True))}\n"
            f"Execution plan: {self._make_json_safe(plan.model_dump(mode='json', by_alias=True))}\n"
            f"Result profile: {self._make_json_safe(result.model_dump(by_alias=True))}\n"
            f"Grounded insights: {self._make_json_safe([item.model_dump(mode='json') for item in insights])}\n"
            "Write a short explanation for the user."
        )
        text = await self.client.complete_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="light",
        )
        return text.strip() if text else None

    async def generate_dynamic_insights(
        self,
        state: QueryState,
        result: QueryResult,
        anomalies: list[dict[str, Any]],
        correlation_info: dict[str, Any] | None,
    ) -> list[InsightItem]:
        if not self.enabled() or not result.rows:
            return []

        system_prompt = (
            "You are a Senior BI Analyst. Author 2-4 key insights from the data provided.\n"
            "STRICT RULES:\n"
            "1. Each insight must have a 'title', 'detail' (max 2 sentences), and 'confidence'.\n"
            "2. Confidence MUST BE exactly 'high', 'medium', or 'low'.\n"
            "3. Ground your insights in the numeric summaries and anomalies provided.\n"
            "4. If data is sparse, lower the confidence.\n"
            "Return JSON object with 'insights' array."
)
        user_prompt = (
            f"Query intent: {state.intent.goal}\n"
            f"Primary metric: {state.visualization.y_axis}\n"
            f"Numeric profile: {self._make_json_safe(result.profile.get('numeric_summary', {}))}\n"
            f"Anomalies: {self._make_json_safe(anomalies)}\n"
            f"Correlations: {self._make_json_safe(correlation_info)}\n"
            'Return: {"insights": [{"title": "", "detail": "", "confidence": "high|medium|low"}]}'
        )
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="light",
        )
        if not payload or "insights" not in payload:
            return []
            
        generated = []
        for item in payload.get("insights", []):
            if isinstance(item, dict):
                # Map confidence to required Literal
                raw_conf = str(item.get("confidence", "medium")).lower()
                confidence = "medium"
                if "high" in raw_conf or (raw_conf.replace(".", "").isdigit() and float(raw_conf) >= 0.7):
                    confidence = "high"
                elif "low" in raw_conf or (raw_conf.replace(".", "").isdigit() and float(raw_conf) <= 0.3):
                    confidence = "low"
                
                generated.append(
                    InsightItem(
                        title=str(item.get("title", "Observation")),
                        detail=str(item.get("detail", "")),
                        confidence=confidence,
                    )
                )
        return generated

    async def build_sql_query(
        self,
        state: QueryState,
        message: str,
        chat_history: list[dict[str, str]],
    ) -> str | None:
        if (
            not self.enabled()
            or state.data.source_type not in {"database", "csv", "excel"}
            or not state.data.table_name
        ):
            return None

        system_prompt = (
            "SQL generator for BI. Return JSON key 'query'. Use ONLY Canonical column names. "
            "Single read-only SELECT/WITH. No mutations. Assume SQLite for files."
        )
        user_prompt = (
            f"User message: {message}\n"
            f"Recent chat history: {chat_history[-8:]}\n"
            f"Query state: {state.model_dump(mode='json', by_alias=True)}\n"
            f"Table: {state.data.table_name}\n"
            f"Canonical schema: {state.data.schema_map}\n"
            f"Display labels to canonical names: {state.data.column_labels}\n"
            f"Aliases to canonical names: {state.data.column_aliases}\n"
            "Important: the SQL must reference only canonical names from the canonical schema.\n"
            'Return JSON like {"query":"SELECT ..."}'
        )
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="heavy",
        )
        if not payload:
            return None
        query = payload.get("query")
        if not isinstance(query, str):
            return None
        normalized_query = self._normalize_sql_query(query, state)
        return self._validate_read_only_sql(normalized_query, state)

    def canonicalize_state(self, state: QueryState) -> QueryState:
        normalized = state.model_copy(deep=True)

        normalized.transformation.group_by = [
            resolved
            for item in normalized.transformation.group_by
            for resolved in [self._resolve_column_name(item, normalized)]
            if isinstance(resolved, str)
        ]

        normalized.transformation.filters = [
            FilterCondition(
                column=resolved,
                operator=item.operator,
                value=item.value,
            )
            for item in normalized.transformation.filters
            for resolved in [self._resolve_column_name(item.column, normalized)]
            if isinstance(resolved, str)
        ]

        normalized.transformation.aggregations = [
            AggregationSpec(column=resolved, operation=item.operation)
            for item in normalized.transformation.aggregations
            for resolved in [self._resolve_column_name(item.column, normalized)]
            if isinstance(resolved, str)
        ]

        if normalized.transformation.sort:
            resolved_sort = self._resolve_column_name(normalized.transformation.sort.column, normalized)
            if isinstance(resolved_sort, str):
                normalized.transformation.sort = SortSpec(
                    column=resolved_sort,
                    order=normalized.transformation.sort.order,
                )
            else:
                normalized.transformation.sort = None

        resolved_x = self._resolve_column_name(normalized.visualization.x_axis, normalized)
        normalized.visualization.x_axis = resolved_x

        normalized.visualization.y_axis = [
            resolved
            for item in normalized.visualization.y_axis
            for resolved in [self._resolve_column_name(item, normalized)]
            if isinstance(resolved, str)
        ]

        resolved_color = self._resolve_column_name(normalized.visualization.color_by, normalized)
        normalized.visualization.color_by = resolved_color

        normalized.meta.reasoning["matched_columns"] = [
            resolved or item
            for item in normalized.meta.reasoning.get("matched_columns", [])
            for resolved in [self._resolve_column_name(item, normalized)]
        ]

        return normalized

    def _merge_state_safely(self, base_state: QueryState, payload: dict[str, Any]) -> QueryState:
        merged = base_state.model_copy(deep=True)
        schema_keys = set(merged.data.schema_map.keys())
        known_columns = schema_keys | set(merged.data.columns.metrics) | set(merged.data.columns.dimensions)

        intent = payload.get("intent")
        if isinstance(intent, dict):
            intent_type = intent.get("type")
            if isinstance(intent_type, str):
                merged.intent.type = intent_type
            goal = intent.get("goal")
            if isinstance(goal, str):
                merged.intent.goal = goal
            confidence = intent.get("confidence")
            if isinstance(confidence, (int, float)):
                merged.intent.confidence = max(0.0, min(1.0, float(confidence)))

        transformation = payload.get("transformation")
        if isinstance(transformation, dict):
            filters = transformation.get("filters")
            if isinstance(filters, list):
                parsed_filters: list[FilterCondition] = []
                for item in filters:
                    if not isinstance(item, dict):
                        continue
                    column = item.get("column")
                    operator = item.get("operator")
                    value = item.get("value")
                    resolved_column = self._resolve_column_name(column, merged)
                    if (
                        isinstance(resolved_column, str)
                        and isinstance(operator, str)
                        and (not known_columns or resolved_column in known_columns)
                        and operator in {"=", "!=", ">", ">=", "<", "<=", "in", "contains"}
                    ):
                        parsed_filters.append(
                            FilterCondition(column=resolved_column, operator=operator, value=value)
                        )
                if parsed_filters:
                    merged.transformation.filters = parsed_filters

            group_by = transformation.get("group_by")
            if isinstance(group_by, list):
                merged.transformation.group_by = [
                    resolved
                    for item in group_by
                    for resolved in [self._resolve_column_name(item, merged)]
                    if isinstance(resolved, str) and (not known_columns or resolved in known_columns)
                ]

            aggregations = transformation.get("aggregations")
            if isinstance(aggregations, list):
                parsed_aggregations: list[AggregationSpec] = []
                for item in aggregations:
                    if not isinstance(item, dict):
                        continue
                    column = item.get("column")
                    operation = item.get("operation")
                    resolved_column = self._resolve_column_name(column, merged)
                    if (
                        isinstance(resolved_column, str)
                        and isinstance(operation, str)
                        and (not known_columns or resolved_column in known_columns)
                        and operation in {"sum", "avg", "count", "min", "max"}
                    ):
                        parsed_aggregations.append(
                            AggregationSpec(column=resolved_column, operation=operation)
                        )
                if parsed_aggregations or merged.intent.goal == "correlation":
                    merged.transformation.aggregations = parsed_aggregations

            time_granularity = transformation.get("time_granularity")
            if time_granularity in {"daily", "monthly", "quarterly", "yearly", None}:
                merged.transformation.time_granularity = time_granularity

            sort = transformation.get("sort")
            if isinstance(sort, dict):
                column = sort.get("column")
                order = sort.get("order")
                resolved_column = self._resolve_column_name(column, merged)
                if (
                    isinstance(resolved_column, str)
                    and isinstance(order, str)
                    and order in {"asc", "desc"}
                ):
                    merged.transformation.sort = SortSpec(column=resolved_column, order=order)

            limit = transformation.get("limit")
            if isinstance(limit, int) and limit > 0:
                merged.transformation.limit = limit

        analysis = payload.get("analysis")
        if isinstance(analysis, dict):
            analysis_types = analysis.get("type")
            if isinstance(analysis_types, list):
                merged.analysis.type = [
                    item for item in analysis_types if isinstance(item, str)
                ]
            parameters = analysis.get("parameters")
            if isinstance(parameters, dict):
                updated_params = deepcopy(merged.analysis.parameters.model_dump())
                updated_params.update(parameters)
                merged.analysis.parameters = type(merged.analysis.parameters).model_validate(updated_params)

        visualization = payload.get("visualization")
        if isinstance(visualization, dict):
            chart_type = visualization.get("chart_type")
            if chart_type in {"line", "bar", "scatter", "histogram", "table"}:
                merged.visualization.chart_type = chart_type

            x_axis = visualization.get("x_axis")
            resolved_x = self._resolve_column_name(x_axis, merged)
            if isinstance(resolved_x, str) and (not known_columns or resolved_x in known_columns):
                merged.visualization.x_axis = resolved_x

            y_axis = visualization.get("y_axis")
            if isinstance(y_axis, list):
                merged.visualization.y_axis = [
                    resolved
                    for item in y_axis
                    for resolved in [self._resolve_column_name(item, merged)]
                    if isinstance(resolved, str) and (not known_columns or resolved in known_columns)
                ]

            color_by = visualization.get("color_by")
            resolved_color_by = self._resolve_column_name(color_by, merged)
            if resolved_color_by is None or (isinstance(resolved_color_by, str) and (not known_columns or resolved_color_by in known_columns)):
                merged.visualization.color_by = resolved_color_by

            # Process single visualization block for backwards compatibility or single chart scenarios
            title = visualization.get("title")
            if isinstance(title, str) and title.strip():
                merged.visualization.title = title.strip()

            options = visualization.get("options")
            if isinstance(options, dict):
                if "highlight_anomalies" in options:
                    merged.visualization.options.highlight_anomalies = bool(options["highlight_anomalies"])
                if "show_legend" in options:
                    merged.visualization.options.show_legend = bool(options["show_legend"])
                    
        # Apply the primary visualization from recommended visualizations if present
        recommended_visualizations = payload.get("recommended_visualizations")
        if isinstance(recommended_visualizations, list) and len(recommended_visualizations) > 0:
            primary_viz = recommended_visualizations[0]
            if isinstance(primary_viz, dict):
                chart_type = primary_viz.get("chart_type")
                if chart_type in {"line", "bar", "scatter", "histogram", "table"}:
                    merged.visualization.chart_type = chart_type

                x_axis = primary_viz.get("x_axis")
                resolved_x = self._resolve_column_name(x_axis, merged)
                if isinstance(resolved_x, str) and (not known_columns or resolved_x in known_columns):
                    merged.visualization.x_axis = resolved_x

                y_axis = primary_viz.get("y_axis")
                if isinstance(y_axis, list):
                    merged.visualization.y_axis = [
                        resolved
                        for item in y_axis
                        for resolved in [self._resolve_column_name(item, merged)]
                        if isinstance(resolved, str) and (not known_columns or resolved in known_columns)
                    ]

                color_by = primary_viz.get("color_by")
                resolved_color_by = self._resolve_column_name(color_by, merged)
                if resolved_color_by is None or (isinstance(resolved_color_by, str) and (not known_columns or resolved_color_by in known_columns)):
                    merged.visualization.color_by = resolved_color_by

        return merged

    @staticmethod
    def _validate_read_only_sql(query: str, state: QueryState) -> str | None:
        cleaned = query.strip().strip(";")
        upper = cleaned.upper()
        if not cleaned:
            return None
        if not (upper.startswith("SELECT") or upper.startswith("WITH")):
            return None
        forbidden = [
            "INSERT ",
            "UPDATE ",
            "DELETE ",
            "DROP ",
            "ALTER ",
            "TRUNCATE ",
            "CREATE ",
            "ATTACH ",
            "PRAGMA ",
            "GRANT ",
            "REVOKE ",
        ]
        if any(token in upper for token in forbidden):
            return None
        if ";" in cleaned:
            return None
        table_name = state.data.table_name
        if table_name and table_name.lower() not in cleaned.lower():
            return None
        return cleaned

    @staticmethod
    def _normalize_sql_query(query: str, state: QueryState) -> str:
        rewritten = query
        
        # 1. Normalize Table Name
        # Find likely table names after FROM or JOIN and replace with canonical table_name
        target_table = state.data.table_name or "dataset"
        # Matches patterns like FROM "old_table", FROM `old_table`, or FROM old_table
        table_patterns = [
            r'(?i)(FROM|JOIN)\s+"[^"]+"',
            r"(?i)(FROM|JOIN)\s+`[^`]+`",
            r"(?i)(FROM|JOIN)\s+([a-zA-Z0-9_]+)",
        ]
        for pattern in table_patterns:
            def _table_replacer(match):
                keyword = match.group(1)
                return f'{keyword} "{target_table}"'
            rewritten = re.sub(pattern, _table_replacer, rewritten)

        # 2. Normalize Columns
        alias_pairs: list[tuple[str, str]] = []
        for alias, canonical in state.data.column_aliases.items():
            alias_pairs.append((alias, canonical))
        for canonical, label in state.data.column_labels.items():
            alias_pairs.append((label, canonical))
        alias_pairs.sort(key=lambda item: len(str(item[0])), reverse=True)

        for source_name, canonical in alias_pairs:
            if not source_name or source_name == canonical:
                continue
            flexible = LLMReasoningService._flexible_identifier_pattern(str(source_name))
            patterns = [
                rf'(?i)"{re.escape(str(source_name))}"',
                rf"(?i)`{re.escape(str(source_name))}`",
                rf'(?i)(?<!["`])\b{re.escape(str(source_name))}\b(?!["`])',
                rf'(?i)(?<!["`])\b{flexible}\b(?!["`])',
            ]
            for pattern in patterns:
                rewritten = re.sub(pattern, f'"{canonical}"', rewritten)
        rewritten = re.sub(r'"{2,}([a-zA-Z0-9_]+)"{2,}', r'"\1"', rewritten)
        return rewritten

    @staticmethod
    def _flexible_identifier_pattern(source_name: str) -> str:
        parts = [re.escape(part) for part in re.split(r"[^a-zA-Z0-9]+", source_name) if part]
        if not parts:
            return re.escape(source_name)
        return r"[\s_]*".join(parts)

    async def generate_report_sections(
        self,
        state: QueryState,
        result: QueryResult,
        raw_facts: dict[str, Any],
    ) -> list[ReportSection]:
        if not self.enabled():
            return []

        system_prompt = "BI reporter. Author structured report from facts/stats. Natural, insightful language. No dry templates."
        
        user_prompt = (
            f"Query State: {state.model_dump(mode='json')}\n"
            f"Result Info: {result.row_count} rows in {result.execution_mode} mode.\n"
            f"Raw Facts: {raw_facts}\n"
            "Return JSON array of sections: "
            '[{"title": "Section Title", "summary": "Analytical paragraph...", "bullets": ["Key point...", "Unexpected finding..."]}]'
        )

        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="light",
        )
        if not payload or not isinstance(payload, list):
            return []

        sections = []
        for item in payload:
            if isinstance(item, dict) and "title" in item and "summary" in item:
                sections.append(ReportSection(
                    title=item["title"],
                    summary=item["summary"],
                    bullets=item.get("bullets", [])
                ))
        return sections

    @staticmethod
    def _resolve_column_name(column: Any, state: QueryState) -> str | None:
        if not isinstance(column, str):
            return None
        if column in state.data.schema_map:
            return column
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", column.strip().lower()).strip("_")
        if not normalized:
            return None
        if normalized in state.data.schema_map:
            return normalized
        if normalized in state.data.column_aliases:
            return state.data.column_aliases[normalized]
        for canonical, label in state.data.column_labels.items():
            if normalized == re.sub(r"[^a-zA-Z0-9]+", "_", label.strip().lower()).strip("_"):
                return canonical
        return column if not state.data.schema_map else None

    @staticmethod
    def _make_json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {
                str(key): LLMReasoningService._make_json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [LLMReasoningService._make_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [LLMReasoningService._make_json_safe(item) for item in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if hasattr(value, "item"):
            return LLMReasoningService._make_json_safe(value.item())
        return str(value)
