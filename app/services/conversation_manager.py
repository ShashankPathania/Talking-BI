"""Conversation orchestration for Talking BI v3.5 (Autonomous Agent)."""

from __future__ import annotations

import asyncio
from uuid import uuid4
from typing import Any, List, Dict

from app.api.schemas.query import QueryRequest
from app.core.state import (
    BIResponse,
    ChatMessage,
    DataLayer,
    DebugPayload,
    ExecutionPlan,
    QueryHistoryEntry,
    QueryResult,
    QueryState,
    SessionState,
    utc_now,
    AgentReflection
)
from app.services.datasets import DatasetService
from app.services.db_connectors import DatabaseConnector
from app.services.insight_engine import InsightEngine
from app.services.llm.reasoning import LLMReasoningService
from app.services.memory.session_store import SessionStore
from app.services.planner import QueryPlanner
from app.services.result_cache import ResultCache
from app.services.visualization.plotly_builder import PlotlyBuilder

# v3.5 Agent Components
from app.services.agent.classifier import QueryClassifier
from app.services.agent.planner import AgentPlanner
from app.services.agent.executor import AgentExecutor


class ConversationManager:
    def __init__(
        self,
        store: SessionStore | None = None,
        planner: QueryPlanner | None = None,
        dataset_service: DatasetService | None = None,
        db_connector: DatabaseConnector | None = None,
        insight_engine: InsightEngine | None = None,
        llm_reasoning: LLMReasoningService | None = None,
        result_cache: ResultCache | None = None,
        plotly_builder: PlotlyBuilder | None = None,
    ) -> None:
        self.db_connector = db_connector or DatabaseConnector()
        self.store = store or SessionStore()
        self.dataset_service = dataset_service or DatasetService(db_connector=self.db_connector)
        self.insight_engine = insight_engine or InsightEngine()
        self.llm_reasoning = llm_reasoning or LLMReasoningService()
        self.result_cache = result_cache or ResultCache()
        self.plotly_builder = plotly_builder or PlotlyBuilder()
        
        # v3.5 Agent Core
        self.agent_planner = AgentPlanner(self.llm_reasoning.client)
        self.agent_classifier = QueryClassifier(self.llm_reasoning.client)
        self.agent_executor = AgentExecutor(
            planner=self.agent_planner,
            duckdb_store=self.dataset_service.duckdb,
            max_steps=5
        )

    async def handle_query(self, request: QueryRequest) -> BIResponse:
        session_id = request.session_id or str(uuid4())
        session = await self.store.get_or_create(session_id, request.dataset_id)
        
        # 1. Update Session and Setup State
        session.messages.append(ChatMessage(role="user", content=request.message))
        chat_history = [{"role": m.role, "content": m.content} for m in session.messages]
        
        base_state = session.query_state or QueryState()
        if request.dataset_id:
            session.dataset_id = request.dataset_id
            base_state = self.dataset_service.attach_to_state(base_state, request.dataset_id)

        # 2. Query Classification (The v3.5 Gate)
        classification = await self.agent_classifier.classify(request.message, chat_history)
        
        # Pillar #4: Fallback to Agent if uncertain (< 0.6)
        is_truly_conversational = classification.is_greeting and classification.conversational_reply
        is_confident = classification.confidence >= 0.6
        
        if (is_truly_conversational or classification.mode == "simple" and classification.conversational_reply) and is_confident:
            return await self._handle_simple_request(session, session_id, base_state, request, classification)

        # 3. Agentic Execution Loop
        return await self._handle_agentic_request(session, session_id, base_state, request)

    async def _handle_simple_request(
        self, 
        session: SessionState, 
        session_id: str, 
        state: QueryState, 
        request: QueryRequest,
        classification: Any
    ) -> BIResponse:
        """Low-latency path for greetings and simple queries."""
        reply = classification.conversational_reply or "I'm ready to help you analyze your data. What's on your mind?"
        
        response_state = state.model_copy(deep=True)
        response_state.meta.reasoning = {"reasoning_mode": "simple_classification", "notes": [classification.reason]}
        
        session.query_state = response_state
        session.messages.append(ChatMessage(role="assistant", content=reply))
        await self.store.save(session)
        
        return BIResponse(
            session_id=session_id,
            explanation=reply,
            query_state=response_state,
            execution_plan=QueryPlanner().build(None, response_state, None),
            debug=DebugPayload(reasoning_mode="simple_classification", notes=[classification.reason])
        )

    async def _handle_agentic_request(
        self, 
        session: SessionState, 
        session_id: str, 
        state: QueryState, 
        request: QueryRequest
    ) -> BIResponse:
        """Recursive autonomous reasoning loop."""
        
        # Execute the Agent Loop
        agent_result = await self.agent_executor.run_agent_loop(request.message, state)
        
        # Extract Results from Observations (v4.0 Multi-Asset Support)
        final_sql_result = None
        all_charts = []
        
        for obs in agent_result["observations"]:
            if obs["tool"] == "run_sql_query" and obs["result"]["status"] == "success":
                final_sql_result = obs["result"]["data"]
            
            if obs["tool"] == "generate_chart" and obs["result"]["status"] == "success":
                # Create a temporary state for this specific chart view
                viz_config = obs["result"]["data"]
                temp_state = state.model_copy(deep=True)
                temp_state.visualization.chart_type = viz_config["chart_type"]
                temp_state.visualization.x_axis = viz_config["x_axis"]
                temp_state.visualization.y_axis = viz_config["y_axis"]
                temp_state.visualization.title = viz_config["title"]
                temp_state.visualization.color_by = viz_config.get("color_by")
                
                # Build chart payload
                # v4.6 Contextual Binding: Always prioritize the specific context stored in the observation
                step_sql_res = obs["result"].get("sql_context")
                if not step_sql_res:
                    print(f"Warning: Chart for '{viz_config['title']}' missing contextual binding. Falling back to latest SQL result.")
                    step_sql_res = final_sql_result
                
                if step_sql_res:
                    step_q_res = QueryResult(
                        rows=step_sql_res["rows"],
                        row_count=step_sql_res["row_count"],
                        schema=state.data.schema_map,
                        execution_mode="sql"
                    )
                    chart_payload = self.plotly_builder.build(temp_state, step_q_res, [])
                    if chart_payload:
                        all_charts.append(chart_payload)

        # Build QueryResult for the system (Global synthesis grounding)
        result = QueryResult(
            rows=final_sql_result["rows"] if final_sql_result else [],
            row_count=final_sql_result["row_count"] if final_sql_result else 0,
            schema=state.data.schema_map,
            execution_mode="sql",
            profile=final_sql_result.get("profile", {}) if final_sql_result else {}
        )

        # Update State with multi-chart meta
        updated_state = state.model_copy(deep=True)
        updated_state.meta.charts = all_charts

        # Generate Synthesis (Combined Insights)
        explanation = agent_result["synthesis"]
        insights = await self.llm_reasoning.generate_dynamic_insights(updated_state, result, [], {})
        
        # Build Final Response
        primary_chart = all_charts[0] if all_charts else None
        
        response = BIResponse(
            session_id=session_id,
            explanation=explanation,
            insights=insights,
            chart=primary_chart,
            charts=all_charts,
            query_state=updated_state,
            data_preview=result.rows[:5],
            execution_plan=ExecutionPlan(
                steps=[s["step"] for s in agent_result["steps"]],
                rationale=explanation[:200]
            ),
            agent_steps=agent_result["steps"],
            debug=DebugPayload(
                reasoning_mode="agent_v3.5",
                notes=[f"Agent took {len(agent_result['steps'])} steps to complete analysis."]
            )
        )

        session.query_state = updated_state
        session.last_result = result
        session.messages.append(ChatMessage(role="assistant", content=explanation))
        await self.store.save(session)
        
        return response

    @staticmethod
    def _apply_report_mode(state: QueryState) -> QueryState:
        # Legacy placeholder for now
        return state

    @staticmethod
    def _reset_analytical_state(state: QueryState, full_reset: bool = False) -> QueryState:
        reset_state = state.model_copy(deep=True)
        # Clear analytical state
        reset_state.transformation.filters = []
        reset_state.transformation.group_by = []
        reset_state.transformation.aggregations = []
        reset_state.visualization.chart_type = "table"
        return reset_state
