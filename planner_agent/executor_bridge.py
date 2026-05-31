"""
Translates a LogicalPlan + PhysicalPlan into the flat inputs that
executor_agent.run_executor expects.
"""
from pathlib import Path
from typing import Dict, Optional

from .models import LogicalPlan
from query_optimizer.query_optimizer import PhysicalPlan

# Maps the abstract source names used by the planner to real file paths.
# Override by passing source_registry to run_planner().
DEFAULT_SOURCE_REGISTRY: Dict[str, str] = {
    "transcripts": str(
        Path(__file__).resolve().parents[1] / "backend" / "complaints_clean.csv"
    ),
}

# How the optimization goal maps to the executor's execution mode.
_GOAL_TO_MODE: Dict[str, str] = {
    "cost": "C",      # parallel async chunks — more efficient per token
    "latency": "C",   # parallel async chunks — fastest wall-clock time
    "balanced": "B",  # sequential batches — predictable, easier to debug
}


def physical_plan_to_executor_inputs(
    logical_plan: LogicalPlan,
    physical_plan: PhysicalPlan,
    source_registry: Optional[Dict[str, str]] = None,
    optimization_goal: str = "balanced",
    max_rows: Optional[int] = None,
) -> dict:
    """
    Returns a dict that can be unpacked directly into run_executor(**inputs).

    Raises ValueError if no SCAN node maps to a path in the source_registry.
    """
    registry = source_registry or DEFAULT_SOURCE_REGISTRY
    physical_by_logical_id = {n.logical_node_id: n for n in physical_plan.nodes}

    # --- csv_path: first SCAN node whose source is in the registry ---
    csv_path = None
    for node in logical_plan.nodes:
        if node.operation == "SCAN" and node.target_source in registry:
            csv_path = registry[node.target_source]
            break
    if csv_path is None:
        known = list(registry.keys())
        found = [n.target_source for n in logical_plan.nodes if n.operation == "SCAN"]
        raise ValueError(
            f"No SCAN node maps to a known source. "
            f"Registry: {known}, plan sources: {found}"
        )

    # --- filter_instruction: first FILTER node ---
    filter_logical = next(
        (n for n in logical_plan.nodes if n.operation == "FILTER"), None
    )
    filter_instruction = (
        filter_logical.instruction if filter_logical else "Keep all records."
    )

    # --- aggregation_instruction: AGGREGATE node ---
    agg_logical = next(
        (n for n in logical_plan.nodes if n.operation == "AGGREGATE"), None
    )
    aggregation_instruction = (
        agg_logical.instruction if agg_logical else "Summarise the results."
    )

    # --- model: use the physical node assigned to the FILTER step,
    #     since that's the highest-volume operation.
    #     Fall back to the first physical node if no FILTER exists. ---
    ref_physical = (
        physical_by_logical_id.get(filter_logical.node_id)
        if filter_logical
        else None
    ) or physical_plan.nodes[0]

    return dict(
        csv_path=csv_path,
        filter_instruction=filter_instruction,
        aggregation_instruction=aggregation_instruction,
        model_id=ref_physical.model.model_name,
        mode=_GOAL_TO_MODE.get(optimization_goal, "B"),
        model_input_price=ref_physical.model.input_cost_per_m,
        model_output_price=ref_physical.model.output_cost_per_m,
        max_rows=max_rows,
    )
