from pydantic import BaseModel, Field
from typing import List, Optional


class TopGroup(BaseModel):
    label: str
    count: int
    percentage: float


class AggregationResult(BaseModel):
    summary: str
    top_groups: List[TopGroup]
    total_matches: int
    key_insight: str


class JoinedResult(BaseModel):
    executive_summary: str
    key_findings: List[str]
    real_examples: List[str]
    risk_indicators: List[str]
    recommendations: List[str]
