from pydantic import BaseModel, Field
from typing import List, Literal, Optional


class PlanNode(BaseModel):
    node_id: str
    operation: Literal["SCAN", "FILTER", "EXTRACT", "JOIN", "AGGREGATE"]
    target_source: Optional[str] = Field(
        default=None, description="The data source, e.g. 'support_transcripts'"
    )
    instruction: str
    depends_on: List[str] = Field(
        default_factory=list,
        description="List of node_ids that must complete first",
    )

class LogicalPlan(BaseModel):
    plan_id: str
    nodes: List[PlanNode]
