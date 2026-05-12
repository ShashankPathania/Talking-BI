from typing import Literal, Dict, Any, Optional
from pydantic import BaseModel
from app.services.llm.client import LLMClient

class ClassificationResult(BaseModel):
    mode: str = "simple"
    reason: str = ""
    is_greeting: bool = False
    conversational_reply: Optional[str] = None
    confidence: float = 1.0 # New in v3.6

class QueryClassifier:
    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient()

    DATA_KEYWORDS = {
        "show", "find", "top", "average", "avg", "sum", "total",
        "trend", "plot", "chart", "analyze", "analysis",
        "dataset", "rows", "columns", "report", "kpi", "compare",
        "calculate", "metric", "difference", "growth", "percentage", "distribution", "share"
    }

    async def classify(self, query: str, chat_history: list) -> ClassificationResult:
        """Bifurcate query with rule-based override + LLM fallback."""
        
        # 1. Rule-Based Override (Pillar #1)
        lower_query = query.lower()
        if any(keyword in lower_query for keyword in self.DATA_KEYWORDS):
            return ClassificationResult(
                mode="agentic",
                reason="Rule-based override: Data keyword detected.",
                is_greeting=False
            )

        # 2. LLM Classification (with Pillar #2: Validation Pipeline)
        """Dynamic next-step decision based on execution observations and reflection."""
        system_prompt = (
            "You are a high-level query router for an Autonomous Data Analyst. "
            "Your job is to decide if a query requires database access (AGENTIC) or is just conversational chatter (SIMPLE). "
            "\n"
            "Classification Rules:\n"
            "1. SIMPLE: ONLY for direct greetings (hi, hello), thank yous, small talk, or requests for help/instructions. If no data is needed, choose SIMPLE.\n"
            "2. AGENTIC: FOR ALL DATA QUESTIONS. Even if the request seems small, the analyst loop is required for safety.\n"
            "\n"
            "Return JSON with keys: 'mode' (simple|agentic), 'reason', 'is_greeting' (bool), 'conversational_reply' (str|null)."
        )
        
        user_prompt = f"User Query: {query}\nChat History: {chat_history[-3:]}"
        
        try:
            payload = await self.client.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                task_size="light"
            )
            
            if not payload:
                raise ValueError("Empty payload from LLM")

            # Normalization & Validation Pipeline (Pillar #2)
            mode = payload.get("mode", "simple").lower()
            return ClassificationResult(
                mode="agentic" if mode == "agentic" else "simple",
                reason=payload.get("reason", "Decided by classifier prompt."),
                is_greeting=payload.get("is_greeting", False),
                conversational_reply=payload.get("conversational_reply"),
                confidence=payload.get("confidence", 1.0)
            )
        except Exception as e:
            # Fallback logic: If it's not a clear greeting, assume it is agentic to be safe
            is_probably_greeting = any(word in lower_query for word in ["hi", "hello", "hey"])
            return ClassificationResult(
                mode="simple" if is_probably_greeting else "agentic",
                reason=f"Classifier error ({str(e)}). Falling back based on keyword heuristic.",
                is_greeting=is_probably_greeting,
                confidence=0.5 # Low confidence on fallback
            )
