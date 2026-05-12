from typing import Literal, Dict, Optional, List

# Stage 2: Intent-to-Chart Mapping
# This abstracts the 'Analytic Goal' from the 'Visual Implementation'
INTENT_TO_CHART: Dict[str, str] = {
    "distribution": "histogram",
    "comparison": "bar",
    "trend": "line",
    "relationship": "scatter",
    "composition": "pie"
}

AVAILABLE_CHARTS: List[str] = [
    "line",
    "bar",
    "scatter",
    "histogram",
    "pie",
    "table"
]

def resolve_chart(intent: Optional[str], requested_type: Optional[str]) -> str:
    """
    Main resolution logic for the Visualization Layer.
    Guarantees that we return a supported chart type.
    """
    # 1. If type is requested and supported, use it
    if requested_type and requested_type in AVAILABLE_CHARTS:
         return requested_type
         
    # 2. If intent is provided, map it
    if intent and intent in INTENT_TO_CHART:
        return INTENT_TO_CHART[intent]
        
    # 3. Final Fallback
    return "bar"
