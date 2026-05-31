"""
Integration tests: planner_agent -> query_optimizer pipeline.

These tests hit the real W&B inference endpoint and require WANDB_API_KEY
to be set (loaded from the project-root .env file).

Run with:
    pytest tests/test_integration.py -v
"""
from pathlib import Path
from typing import Set

import pytest
import weave
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
weave.init("query-optimizer-tests")

from planner_agent import run_planner, LogicalPlan
from query_optimizer import CostBasedOptimizer, PhysicalPlan
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
        logical_plan = run_planner(query)
        print_logical_plan(logical_plan)

        assert logical_plan is not None
        assert len(logical_plan.nodes) >= 2

        optimizer = CostBasedOptimizer(DATASET_STATS, optimization_goal="balanced")
        physical_plan = optimizer.evaluate_and_select(logical_plan)
        print_physical_plan(physical_plan)

        _assert_valid_physical_plan(physical_plan)
        _assert_topological_order(logical_plan, physical_plan)

    def test_churn_summary_query(self):
        query = "Summarize the top complaints from customers who churned last month."
        logical_plan = run_planner(query)
        print_logical_plan(logical_plan)

        optimizer = CostBasedOptimizer(DATASET_STATS, optimization_goal="balanced")
        physical_plan = optimizer.evaluate_and_select(logical_plan)
        print_physical_plan(physical_plan)

        _assert_valid_physical_plan(physical_plan)
        _assert_topological_order(logical_plan, physical_plan)


class TestJoinPipeline:
    """Queries that should trigger a JOIN between transcripts and crm_database."""

    def test_bug_churn_join_query(self):
        query = (
            "Find customers who are churning due to bugs "
            "and look up their contract value from the CRM."
        )
        logical_plan = run_planner(query)
        print_logical_plan(logical_plan)

        # A JOIN query should have at least two root SCAN nodes plus downstream ops
        assert len(logical_plan.nodes) >= 3

        optimizer = CostBasedOptimizer(DATASET_STATS, optimization_goal="balanced")
        physical_plan = optimizer.evaluate_and_select(logical_plan)
        print_physical_plan(physical_plan)

        _assert_valid_physical_plan(physical_plan)
        _assert_topological_order(logical_plan, physical_plan)


class TestOptimizationGoals:
    """The chosen goal should affect the selected plan's cost/latency trade-off."""

    @pytest.fixture(scope="class")
    def logical_plan(self):
        return run_planner("Find all customers who complained about billing errors.")

    def test_cost_goal_is_cheaper_than_latency_goal(self, logical_plan):
        cost_plan = CostBasedOptimizer(DATASET_STATS, "cost").evaluate_and_select(logical_plan)
        latency_plan = CostBasedOptimizer(DATASET_STATS, "latency").evaluate_and_select(logical_plan)

        # Cost-optimized plan should have lower or equal USD cost
        assert cost_plan.estimated_cost_usd <= latency_plan.estimated_cost_usd

    def test_latency_goal_is_faster_than_cost_goal(self, logical_plan):
        cost_plan = CostBasedOptimizer(DATASET_STATS, "cost").evaluate_and_select(logical_plan)
        latency_plan = CostBasedOptimizer(DATASET_STATS, "latency").evaluate_and_select(logical_plan)

        # Latency-optimized plan should have lower or equal latency
        assert latency_plan.estimated_latency_sec <= cost_plan.estimated_latency_sec

    def test_all_goals_produce_valid_plans(self, logical_plan):
        print_logical_plan(logical_plan)
        for goal in ("cost", "latency", "balanced"):
            plan = CostBasedOptimizer(DATASET_STATS, goal).evaluate_and_select(logical_plan)
            print_physical_plan(plan)
            _assert_valid_physical_plan(plan)
            _assert_topological_order(logical_plan, plan)
