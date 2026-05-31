"""
Integration tests: planner_agent -> query_optimizer pipeline.

These tests hit the real W&B inference endpoint and require WANDB_API_KEY
to be set (loaded from the project-root .env file).

Run with:
    pytest tests/test_integration.py -v -s
"""
from pathlib import Path
from typing import Set

import pytest
import weave
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
weave.init("query-optimizer-tests")

from planner_agent import run_planner, LogicalPlan, PlanningResult
from query_optimizer import PhysicalPlan
from utils import print_logical_plan, print_physical_plan

DATASET_STATS = {"total_docs": 1000, "avg_tokens_per_doc": 1500}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_topological_order(logical_plan: LogicalPlan, physical_plan: PhysicalPlan) -> None:
    """Each physical node must appear after all its declared dependencies."""
    logical_node_map = {n.node_id: n for n in logical_plan.nodes}
    seen: Set[str] = set()
    for p_node in physical_plan.nodes:
        logical_node = logical_node_map[p_node.logical_node_id]
        for dep_id in logical_node.depends_on:
            assert dep_id in seen, (
                f"Node '{p_node.logical_node_id}' appears before its dependency '{dep_id}'"
            )
        seen.add(p_node.logical_node_id)


def _assert_valid_physical_plan(physical_plan: PhysicalPlan) -> None:
    assert physical_plan is not None
    assert len(physical_plan.nodes) > 0
    assert physical_plan.estimated_cost_usd > 0
    assert physical_plan.estimated_latency_sec > 0
    assert 0.0 < physical_plan.estimated_accuracy <= 1.0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLinearPipeline:
    """Queries that produce a simple linear chain (no JOIN)."""

    def test_refund_query_produces_valid_physical_plan(self):
        query = "Find all cities where customers asked for a refund."
        result: PlanningResult = run_planner(query, DATASET_STATS)
        print_logical_plan(result["logical_plan"])
        print_physical_plan(result["physical_plan"])

        assert result["logical_plan"] is not None
        assert len(result["logical_plan"].nodes) >= 2
        _assert_valid_physical_plan(result["physical_plan"])
        _assert_topological_order(result["logical_plan"], result["physical_plan"])

    def test_churn_summary_query(self):
        query = "Summarize the top complaints from customers who churned last month."
        result: PlanningResult = run_planner(query, DATASET_STATS)
        print_logical_plan(result["logical_plan"])
        print_physical_plan(result["physical_plan"])

        _assert_valid_physical_plan(result["physical_plan"])
        _assert_topological_order(result["logical_plan"], result["physical_plan"])


class TestJoinPipeline:
    """Queries that should trigger a JOIN between transcripts and crm_database."""

    def test_bug_churn_join_query(self):
        query = (
            "Find customers who are churning due to bugs "
            "and look up their contract value from the CRM."
        )
        result: PlanningResult = run_planner(query, DATASET_STATS)
        print_logical_plan(result["logical_plan"])
        print_physical_plan(result["physical_plan"])

        assert len(result["logical_plan"].nodes) >= 3
        _assert_valid_physical_plan(result["physical_plan"])
        _assert_topological_order(result["logical_plan"], result["physical_plan"])


class TestOptimizationGoals:
    """The chosen goal should affect the selected plan's cost/latency trade-off."""

    @pytest.fixture(scope="class")
    def planning_result(self):
        return run_planner(
            "Find all customers who complained about billing errors.",
            DATASET_STATS,
        )

    def test_cost_goal_is_cheaper_than_latency_goal(self, planning_result):
        logical_plan = planning_result["logical_plan"]
        cost_result = run_planner(logical_plan.plan_id, DATASET_STATS, optimization_goal="cost")
        latency_result = run_planner(logical_plan.plan_id, DATASET_STATS, optimization_goal="latency")
        assert cost_result["physical_plan"].estimated_cost_usd <= latency_result["physical_plan"].estimated_cost_usd

    def test_latency_goal_is_faster_than_cost_goal(self, planning_result):
        logical_plan = planning_result["logical_plan"]
        cost_result = run_planner(logical_plan.plan_id, DATASET_STATS, optimization_goal="cost")
        latency_result = run_planner(logical_plan.plan_id, DATASET_STATS, optimization_goal="latency")
        assert latency_result["physical_plan"].estimated_latency_sec <= cost_result["physical_plan"].estimated_latency_sec

    def test_all_goals_produce_valid_plans(self, planning_result):
        print_logical_plan(planning_result["logical_plan"])
        for goal in ("cost", "latency", "balanced"):
            result = run_planner(
                "Find all customers who complained about billing errors.",
                DATASET_STATS,
                optimization_goal=goal,
            )
            print_physical_plan(result["physical_plan"])
            _assert_valid_physical_plan(result["physical_plan"])
            _assert_topological_order(result["logical_plan"], result["physical_plan"])
