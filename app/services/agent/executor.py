import asyncio
import time
from typing import List, Dict, Any, Optional
from app.core.state import QueryState, QueryResult, BIResponse, AgentReflection, ChatMessage
from app.services.agent.planner import AgentPlanner, AgentPlan
from app.services.tools.base import BaseTool, ToolResult
from app.services.tools.sql import SQLQueryTool
from app.services.tools.schema import SchemaIntrospectTool
from app.services.tools.viz import ChartConfigTool
from app.services.tools.reflection import ReflectionTool
from app.services.data.duckdb_store import DuckDBStore
from app.services.persistence.cache import PersistentCache

class AgentExecutor:
    def __init__(
        self, 
        planner: AgentPlanner,
        duckdb_store: DuckDBStore,
        cache: Optional[PersistentCache] = None,
        max_steps: int = 5
    ):
        self.planner = planner
        self.duckdb = duckdb_store
        self.cache = cache or PersistentCache()
        self.max_steps = max_steps
        
        # Initialize Tool Registry
        self.tools: Dict[str, BaseTool] = {
            "run_sql_query": SQLQueryTool(duckdb_store),
            "get_schema": SchemaIntrospectTool(duckdb_store),
            "generate_chart": ChartConfigTool(),
            "reflect": ReflectionTool()
        }

    async def run_agent_loop(self, query: str, state: QueryState) -> Dict[str, Any]:
        """The core Plan-Execute-Observe-Reflect loop (v3.9 Stabilized)."""
        start_time = time.time()
        observations: List[Dict[str, Any]] = []
        steps_taken: List[Dict[str, Any]] = []
        
        # Stage 3: State Tracking (v4.0 Self-Regulation)
        state.meta.coverage = {
            "kpi": False, "distribution": False, "trend": False, "top_n": False
        }
        state.meta.satisfaction = {
            "has_visualization": False, "explicit_goal_met": False
        }
        state.meta.generated_views = []

        # 1. Initial Schema Sniff (Production Tweak #2)
        if state.data.active_dataset_id and state.data.table_name:
            schema_obs = await self.tools["get_schema"].execute(table_name=state.data.table_name)
            observations.append({"tool": "get_schema", "result": schema_obs.model_dump()})
            steps_taken.append({"step": "Initial Schema Sniff", "summary": schema_obs.summary})
            state.meta.schema_done = True

        # 2. Initial High-Level Plan
        context = f"Table: {state.data.table_name}. Schema: {state.data.schema_map}"
        plan = await self.planner.create_initial_plan(query, context)
        
        # 3. Execution Loop
        final_synthesis = None
        current_step = 0
        
        local_max_steps = 7 if any(k in query.lower() for k in ["dashboard", "report", "overview", "overall"]) else self.max_steps
        
        while current_step < local_max_steps:
            current_step += 1
            
            # Decision Step (Pillar #5: Structured Logging)
            print(f"--- [v3.9 Agent] Step {current_step}: Deciding... ---")
            decision = await self.planner.decide_next_step(query, plan, observations, current_step)
            
            # Stage 2: Hard Transition Rules (v3.9 Pillar)
            # IF schema_done AND NOT sql_done: force run_sql_query (unless it's a dashboard, which needs autonomy)
            if state.meta.schema_done and not state.meta.satisfaction["explicit_goal_met"] and not decision.finish:
                is_report = any(k in query.lower() for k in ["dashboard", "report", "overview", "overall", "comprehensive"])
                if decision.next_tool != "run_sql_query" and not is_report:
                    print("Override: Forcing SQL query after schema discovery.")
                    decision.next_tool = "run_sql_query"
                    decision.args = {"query": f"SELECT * FROM {state.data.table_name} LIMIT 10"}
                    decision.reasoning = "System override to ensure forward progress (Schema -> SQL)."
                elif is_report and decision.next_tool == "get_schema":
                    # KPI Discovery Injector: If a dashboard is requested, probe for numbers early
                    print("Metric Probe: Injecting KPI discovery for dashboard.")
                    decision.next_tool = "run_sql_query"
                    decision.args = {"query": f"SELECT COUNT(*) as total_rows FROM {state.data.table_name}"}
                    decision.reasoning = "Metric Probe: Discovering global dataset size for dashboard context."

            # Stage 6: Chart Loop Guard (v3.10+)
            if decision.next_tool == "generate_chart" and state.meta.last_tool == "generate_chart":
                print("Chart already generated. Forcing loop termination to prevent exhaustion.")
                decision.finish = True
                decision.synthesis = "I have generated the chart based on the data. You can see the result below."

            # Stage 3: Anti-Repetition Guard
            if decision.next_tool == state.meta.last_tool and not decision.finish:
                state.meta.no_progress_steps += 1
                if state.meta.no_progress_steps >= 2:
                    print(f"Loop Detected: Forcing transition away from {decision.next_tool}")
                    decision.finish = True
                    decision.synthesis = "I encountered a reasoning loop and stopped to prevent exhaustion."
            else:
                state.meta.no_progress_steps = 0

            print(f"Decision: {decision.next_tool or 'FINISH'} | Reasoning: {decision.reasoning}")
            
            # v4.2 Sanitization & Routing Layer
            decision = self._sanitize_decision(decision, observations, state)
            
            # Stage 2: Completion Awareness (v4.1 Precision)
            is_report = any(k in query.lower() for k in ["dashboard", "report", "overview", "overall", "comprehensive"])
            
            if decision.finish:
                # Dashboard requires at least one chart
                if is_report and not state.meta.satisfaction["has_visualization"]:
                    print("Completion Override: Dashboard requires at least one chart. Continuing...")
                    decision.finish = False
                    decision.next_tool = "run_sql_query" if not state.meta.satisfaction["explicit_goal_met"] else "generate_chart"
                
                # General goal tracking
                elif not state.meta.satisfaction["explicit_goal_met"]:
                    print("Completion Override: Core goal not met. Continuing...")
                    decision.finish = False
                    decision.next_tool = "run_sql_query" 
                
                elif not state.meta.satisfaction["has_visualization"] and any(k in query.lower() for k in ["show", "plot", "chart", "distribution"]):
                    print("Completion Override: Visualization requested but missing. Continuing...")
                    decision.finish = False
                    decision.next_tool = "generate_chart"
            
            # Stage 3: Failure Inversion (v4.2 High-Integrity Recovery)
            if "LLM failure" in (decision.reasoning or "") and not decision.next_tool:
                print("Failure Inversion: LLM failed. Attempting strategic recovery...")
                decision.finish = False
                
                # RECOVERY 1: Use harvested chart args if we have them
                if state.meta.last_tool != "generate_chart" and any(k in state.meta.coverage for k in ["distribution", "top_n"]):
                     # This is a bit complex, let's stick to the direct harvested check
                     pass

                if not state.meta.satisfaction["explicit_goal_met"]:
                    # RECOVERY: If we have context from a previous TURN, use it
                    if state.meta.last_sql_result:
                        print("Failure Inversion: Using last_sql_result from history.")
                        decision.next_tool = "generate_chart"
                        decision.args = {"chart_intent": "comparison", "chart_type": "bar"}
                    else:
                        decision.next_tool = "run_sql_query"
                        decision.args = {"query": f"SELECT * FROM {state.data.table_name} LIMIT 10"}
                else:
                    # Strategic Guess for chart if we have data
                    decision.next_tool = "generate_chart"
                    decision.args = {"chart_intent": "comparison", "chart_type": "bar"}
                    
                    # Try to pick axes from harvested args OR last_sql_result
                    if hasattr(state.meta, "harvested_args") and state.meta.harvested_args:
                        print("Recovery: Using harvested arguments for forced chart.")
                        decision.args.update(state.meta.harvested_args)
                    elif state.meta.last_sql_result:
                        print("Recovery: Guessing axes from last successful SQL result.")
                        # Pick first string and first numeric column if possible
                        cols = state.meta.last_sql_result.get("rows", [{}])[0].keys() if state.meta.last_sql_result.get("rows") else []
                        if cols:
                             decision.args["x_axis"] = list(cols)[0]
                             decision.args["y_axis"] = list(cols)[-1] if len(cols) > 1 else list(cols)[0]

            # v4.5 Fact-Checking Reflection: Detect "Hollow Finish"
            if decision.finish and not state.meta.satisfaction["has_visualization"] and is_report:
                print("Fact-Checking: Agent claims finish but no visual produced. Forcing continuity...")
                decision.finish = False
                decision.next_tool = "run_sql_query"
                decision.reasoning = "Fact-check override: Need to produce data before finishing report."

            # v4.5 Predictive SQL Injection: The "Cart before the Horse" fix
            if decision.next_tool == "generate_chart" and not decision.finish:
                x_axis = decision.args.get("x_axis")
                y_axis = decision.args.get("y_axis")
                available_cols = list(state.meta.last_sql_result["rows"][0].keys()) if state.meta.last_sql_result and "rows" in state.meta.last_sql_result and state.meta.last_sql_result["rows"] else []
                
                # If axes are missing from last result, inject a SQL fetch
                if x_axis and x_axis not in available_cols:
                    print(f"Predictive Injection: Data for '{x_axis}' missing. Injecting SQL fetch.")
                    decision.next_tool = "run_sql_query"
                    # Guess a sensible aggregation
                    agg_y = f"SUM({y_axis})" if y_axis and y_axis != "count" else "COUNT(*)"
                    decision.args = {"query": f"SELECT {x_axis}, {agg_y} AS {y_axis or 'count'} FROM {state.data.table_name} GROUP BY {x_axis} ORDER BY 2 DESC"}
                    decision.reasoning = f"Predictive Injection: Fetching {x_axis} data before visualization."

            # Finish ONLY if no tool is pending and satisfaction is met
            if decision.finish and not decision.next_tool:
                final_synthesis = decision.synthesis
                break
            
            if not decision.next_tool or decision.next_tool not in self.tools:
                if decision.finish: # Double check for finish without tool
                    final_synthesis = decision.synthesis
                    break
                print(f"Warning: Low-quality LLM decision ({decision.next_tool}). Self-Correcting with 'get_schema'...")
                decision.next_tool = "get_schema"
                decision.args = {"table_name": state.data.table_name or "main"}

            # 1. Check Cache (v3.5 Optimization)
            cache_key = self.cache.make_key(
                state.data.active_dataset_id or "global", 
                {"tool": decision.next_tool, "args": decision.args}
            )
            cached_res = self.cache.get(cache_key)
            
            if cached_res:
                print(f"Cache Hit for {decision.next_tool}")
                tool_result = ToolResult.model_validate(cached_res)
                steps_taken.append({"step": f"Step {current_step}: {decision.next_tool}", "summary": f"(Cached) {tool_result.summary}"})
            else:
                # Execution Step (Stage 4: Tool Contract)
                print(f"Executing Tool: {decision.next_tool} with args: {decision.args}")
                tool = self.tools[decision.next_tool]
                try:
                    tool_result = await tool.execute(**decision.args)
                except Exception as e:
                    print(f"Tool Execution Error: {str(e)}")
                    tool_result = ToolResult(status="error", summary=f"Execution failed: {str(e)}", data={})

                # Store in Cache if successful
                if tool_result.status == "success":
                    self.cache.set(cache_key, state.data.active_dataset_id or "global", tool_result.model_dump())
            
            # Update State Flags & Coverage (v4.0 Stage 3)
            current_tool_name = decision.next_tool
            state.meta.last_tool = current_tool_name

            if current_tool_name == "get_schema":
                state.meta.schema_done = True
            elif current_tool_name == "run_sql_query" and tool_result.status == "success":
                state.meta.satisfaction["explicit_goal_met"] = True
                state.meta.last_sql_result = tool_result.data # v4.3 Analytical Memory
                
                sql_q = decision.args.get("query", "").lower()
                if any(x in sql_q for x in ["sum", "count", "avg", "total"]):
                    state.meta.coverage["kpi"] = True
            elif current_tool_name == "generate_chart" and tool_result.status == "success":
                state.meta.satisfaction["has_visualization"] = True
                c_type = tool_result.data.get("chart_type")
                if c_type == "pie": state.meta.coverage["distribution"] = True
                elif c_type == "bar": state.meta.coverage["top_n"] = True
                elif c_type == "line": state.meta.coverage["trend"] = True
                
                # Redundancy Guard (Stage 6)
                view_sig = f"{c_type}_{decision.args.get('x_axis')}_{decision.args.get('y_axis')}"
                state.meta.generated_views.append(view_sig)
            
            # Stage 5: Logical Reflection (v3.11 Simplified)
            reflection_result_data = {
                "success": (tool_result.status == "success"),
                "useful": (tool_result.status == "success" and bool(tool_result.data))
            }

            # Stage 1: Contextual Binding (v4.6 Sticky Results)
            # If we just generated a chart, snapshot the data it was built from
            tool_result_dict = tool_result.model_dump() if hasattr(tool_result, "model_dump") else tool_result
            if current_tool_name == "generate_chart" and state.meta.last_sql_result:
                print("Contextual Binding: Locking chart to current SQL result.")
                tool_result_dict["sql_context"] = state.meta.last_sql_result

            # Record Observation (Stage 5: Structured Capture)
            obs = {
                "step": current_step,
                "tool": decision.next_tool,
                "args": decision.args,
                "result": tool_result_dict,
                "reflection": reflection_result_data
            }
            observations.append(obs)
            steps_taken.append({"step": f"Step {current_step}: {decision.next_tool}", "summary": tool_result.summary})
            
            # Stage 1: Check for Early Finish Override
            if decision.finish and not decision.next_tool:
                 break

        latency = int((time.time() - start_time) * 1000)
        
        # Pillar #2: Hard Synthesis Fallback
        has_data = any(obs["tool"] == "run_sql_query" and obs["result"]["status"] == "success" for obs in observations)
        if not has_data and not final_synthesis:
            final_synthesis = "I explored the table structure but was unable to fetch specific data rows to answer your question fully. Please try rephrasing or asking about specific columns."

        return {
            "synthesis": final_synthesis or "I've completed my analysis. You can see the results below.",
            "observations": observations,
            "steps": steps_taken,
            "latency_ms": latency
        }

    def _sanitize_decision(self, decision: Any, observations: List[Dict[str, Any]], state: QueryState) -> Any:
        """v4.2 High-Integrity Routing: Corrects LLM hallucinations on the fly."""
        if not decision.next_tool:
            return decision

        tool_name = decision.next_tool.lower()
        
        # 1. Tool Aliasing
        ALIASES = {
            "visualize": "generate_chart",
            "plot": "generate_chart",
            "chart": "generate_chart",
            "query": "run_sql_query",
            "sql": "run_sql_query"
        }
        if tool_name in ALIASES:
            print(f"Sanitization: Aliasing {tool_name} -> {ALIASES[tool_name]}")
            decision.next_tool = ALIASES[tool_name]
            tool_name = decision.next_tool

        # 2. Argument Pollution Recovery (SQL <-> Chart)
        # If model sends chart args to SQL or SQL args to Chart, fix it.
        CHART_ARGS = ["chart_type", "chart_intent", "x_axis", "y_axis", "color_by"]
        
        # Harvest valid args for persistence
        current_harvest = {k: v for k, v in decision.args.items() if k in CHART_ARGS}
        if current_harvest:
            if not hasattr(state.meta, "harvested_args"):
                state.meta.harvested_args = {}
            state.meta.harvested_args.update(current_harvest)

        if tool_name == "run_sql_query":
            # If it has chart args but no 'query', it probably meant generate_chart
            if any(k in decision.args for k in CHART_ARGS) and "query" not in decision.args:
                print("Sanitization: Re-routing run_sql_query to generate_chart based on args.")
                decision.next_tool = "generate_chart"
            elif any(k in decision.args for k in CHART_ARGS):
                # Clean up pollution
                print("Sanitization: Stripping chart arguments from run_sql_query.")
                decision.args = {k: v for k, v in decision.args.items() if k not in CHART_ARGS}
        
        elif tool_name == "generate_chart":
            # If it has a 'query' arg, it probably meant run_sql_query first
            if "query" in decision.args and len(decision.args) == 1:
                print("Sanitization: Re-routing generate_chart to run_sql_query.")
                decision.next_tool = "run_sql_query"
            elif "query" in decision.args:
                 print("Sanitization: Stripping SQL query from generate_chart.")
                 decision.args = {k: v for k, v in decision.args.items() if k != "query"}
            
            # Auto-Fill missing axes from harvest if available
            if hasattr(state.meta, "harvested_args") and state.meta.harvested_args:
                for k, v in state.meta.harvested_args.items():
                    if k not in decision.args:
                        decision.args[k] = v
            
            # v4.4 Validation Guard: Fuzzy Match axes against last_sql_result
            if state.meta.last_sql_result and "rows" in state.meta.last_sql_result:
                available_cols = list(state.meta.last_sql_result["rows"][0].keys()) if state.meta.last_sql_result["rows"] else []
                if available_cols:
                    for axis_key in ["x_axis", "y_axis"]:
                        val = decision.args.get(axis_key)
                        if val and isinstance(val, str) and val not in available_cols:
                            # Fuzzy Match
                            match = self._fuzzy_match_col(val, available_cols)
                            if match:
                                print(f"Validation Guard: Correcting {axis_key} '{val}' -> '{match}'")
                                decision.args[axis_key] = match

        return decision

    def _fuzzy_match_col(self, target: str, columns: list[str]) -> str | None:
        """Case-insensitive and substring matching for axis validation."""
        t_low = target.lower().strip()
        # Case-insensitive
        for col in columns:
            if col.lower() == t_low: return col
        # Substring
        for col in columns:
            c_low = col.lower()
            if t_low in c_low or c_low in t_low: return col
        return None
