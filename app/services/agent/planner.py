from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from app.services.llm.client import LLMClient

class AgentTask(BaseModel):
    id: int
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    reason: str

class AgentPlan(BaseModel):
    tasks: List[AgentTask] = Field(default_factory=list)
    final_goal: str

class NextStepDecision(BaseModel):
    next_tool: Optional[str] = None
    args: Dict[str, Any] = Field(default_factory=dict)
    finish: bool = False
    synthesis: Optional[str] = None # Final answer if finish is True
    confidence: float = Field(default=1.0, ge=0.0, le=1.0) # Trust metric
    based_on: List[str] = Field(default_factory=list) # Evidence for confidence
    reasoning: str

class AgentPlanner:
    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()

    async def create_initial_plan(self, query: str, schema_context: str) -> AgentPlan:
        """Create a high-level multi-step plan to solve the user's query."""
        system_prompt = (
            "You are a Senior Data Analyst Planner. "
            "Given a query and data schema, break it down into logical steps. "
            "Available tools: get_schema, run_sql_query, generate_chart.\n"
            "Guidelines:\n"
            "1. Start with 'get_schema' if you don't fully know the table structure.\n"
            "2. Use 'run_sql_query' for all data fetching and aggregations.\n"
            "3. Use 'generate_chart' only after you have data.\n"
            "Return JSON only."
        )
        
        user_prompt = f"Query: {query}\nContext: {schema_context}"
        
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="heavy"
        )
        
        if not payload:
            return AgentPlan(final_goal=query)

        tasks = [AgentTask(**t) for t in payload.get("tasks", [])]
        return AgentPlan(tasks=tasks, final_goal=payload.get("final_goal", query))

    async def decide_next_step(
        self, 
        query: str, 
        plan: AgentPlan, 
        observations: List[Dict[str, Any]],
        step_count: int
    ) -> NextStepDecision:
        """Dynamic next-step decision based on execution observations and reflection."""
        system_prompt = (
            "You are an Autonomous Data Analyst Agent.\n\n"
            "Your goal is to fully satisfy the user’s query using data and visualizations.\n\n"
            "GENERAL RULES:\n"
            "- Always fetch data using SQL before answering.\n"
            "- Use visualizations when helpful.\n"
            "- Avoid unnecessary repetition.\n"
            "- Make forward progress in each step.\n\n"
            "COMPLETION RULES:\n"
            "- If the user asks for a specific visualization:\n"
            "  → Generate that visualization and stop.\n"
            "- If the user asks for general analysis:\n"
            "  → Generate 1–2 useful visualizations.\n"
            "- If the user asks for a report/dashboard:\n"
            "  → Explore multiple perspectives before finishing.\n"
            "- DO NOT stop until the user’s request is clearly satisfied.\n"
            "- DO NOT generate extra charts once the request is satisfied.\n\n"
            "VISUALIZATION GUIDELINES:\n"
            "- distribution → pie\n"
            "- comparison → bar\n"
            "- trend → line\n\n"
            "LOGICAL SEQUENTIALITY (STRICT):\n"
            "- NEVER visualize a column (e.g., 'total_revenue') before you have fetched it via SQL.\n"
            "- ALWAYS fetch at least 10 rows of data BEFORE your first generate_chart call.\n"
            "- If a chart fails, check the schema and fetch the correct columns before retrying.\n\n"
            "TOOL SCHEMAS (STRICT):\n"
            "- run_sql_query: {\"query\": \"SELECT ...\"}\n"
            "- generate_chart: {\"chart_intent\": \"...\", \"chart_type\": \"...\", \"x_axis\": \"...\", \"y_axis\": \"...\"}\n"
            "- get_schema: {\"table_name\": \"...\"}\n\n"
            "DIVERSITY RULE:\n"
            "- Avoid generating the same chart repeatedly.\n"
            "- Prefer different perspectives when generating multiple charts.\n\n"
            "OUTPUT FORMAT (STRICT JSON):\n"
            "{\n"
            "  \"next_tool\": \"tool_name OR null\",\n"
            "  \"args\": {\n"
            "    \"chart_intent\": \"composition|comparison|trend|distribution|relationship\",\n"
            "    \"chart_type\": \"pie|bar|line|histogram|scatter\",\n"
            "    \"x_axis\": \"column_name\",\n"
            "    \"y_axis\": \"column_name\"\n"
            "  },\n"
            "  \"finish\": false,\n"
            "  \"synthesis\": \"Final answer string\",\n"
            "  \"confidence\": 0.0-1.0,\n"
            "  \"based_on\": [\"raw data\", \"aggregations\"],\n"
            "  \"reasoning\": \"short explanation\"\n"
            "}"
        )
        
        # v4.3 Payload Resilience: Proactive Compression
        # If observations are getting too large, we condense them
        compact_observations = self._compact_observations_sync(observations)
        
        user_prompt = (
            f"Original Query: {query}\n"
            f"Plan: {plan.model_dump_json()}\n"
            f"Observations: {compact_observations}\n"
            f"Steps Taken: {step_count}\n"
        )
        
        payload = await self.client.complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="heavy"
        )
        
        # v4.1 Resilience: Fallback to light model if heavy fails
        if not payload:
            print("Planner: Heavy task failed. Retrying with Light model...")
            payload = await self.client.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                task_size="light"
            )
        
        if not payload:
            return NextStepDecision(finish=True, synthesis="I encountered an internal error and couldn't complete the analysis.", reasoning="LLM failure after retry.")

        return NextStepDecision(
            next_tool=payload.get("next_tool"),
            args=payload.get("args", {}),
            finish=payload.get("finish", False),
            synthesis=payload.get("synthesis"),
            confidence=payload.get("confidence", 1.0),
            based_on=payload.get("based_on", []),
            reasoning=payload.get("reasoning", "Decided by executor.")
        )

    async def compress_observations(self, observations: List[Dict[str, Any]]) -> str:
        """Summarize tool results to fit within LLM context limits."""
        if not observations:
            return "No observations yet."
            
        system_prompt = (
            "You are a Context Compression Assistant. "
            "Given a list of tool execution results, summarize them into a dense, high-information paragraph. "
            "Focus on column names discovered, row counts returned, and key data points. "
            "Ignore technical details like internal IDs or verbose JSON structures."
        )
        
        user_prompt = f"Observations to compress: {observations}"
        
        summary = await self.client.complete_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            task_size="light"
        )
        return summary or "Context compression failed."

    def _compact_observations_sync(self, observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deterministic truncation of observations to avoid 413 errors."""
        compact = []
        for obs in observations:
            c_obs = obs.copy()
            # If the result has huge data, trim it
            if "result" in c_obs and isinstance(c_obs["result"], dict) and "data" in c_obs["result"]:
                data = c_obs["result"]["data"]
                if isinstance(data, dict) and "rows" in data and len(data["rows"]) > 5:
                    # Keep only first 5 rows for context
                    c_obs["result"]["data"] = data.copy()
                    c_obs["result"]["data"]["rows"] = data["rows"][:5]
                    c_obs["result"]["data"]["_meta"] = "Truncated for context"
            compact.append(c_obs)
        return compact
