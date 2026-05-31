import os
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any, Tuple
from planner_agent import PlanNode, LogicalPlan


# --- Define Physical Execution Profiles ---
class ModelProfile(BaseModel):
    model_name: str
    input_cost_per_m: float   # USD per Million tokens
    output_cost_per_m: float  # USD per Million tokens
    estimated_tps: float      # Tokens per second throughput
    accuracy_heuristic: float # 0.0 to 1.0 accuracy rating


class PhysicalNode(BaseModel):
    logical_node_id: str
    operation: str
    model: ModelProfile
    estimated_selectivity: float = 1.0  # Fraction of tokens passed to next step


class PhysicalPlan(BaseModel):
    plan_name: str
    nodes: List[PhysicalNode]
    estimated_cost_usd: float = 0.0
    estimated_latency_sec: float = 0.0
    estimated_accuracy: float = 1.0


def _topological_sort(nodes: List[PlanNode]) -> List[PlanNode]:
    """Returns nodes sorted so every node appears after all its dependencies."""
    node_map = {n.node_id: n for n in nodes}
    visited: set = set()
    result: List[PlanNode] = []

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        for dep_id in node_map[node_id].depends_on:
            visit(dep_id)
        result.append(node_map[node_id])

    for node in nodes:
        visit(node.node_id)

    return result


# --- The Cost-Based Optimizer Engine ---
class CostBasedOptimizer:
    def __init__(
        self,
        dataset_stats: Dict[str, Any],
        optimization_goal: Literal["cost", "latency", "balanced"] = "balanced",
    ):
        self.dataset_stats = dataset_stats  # e.g., {"total_docs": 1000, "avg_tokens_per_doc": 1500}
        self.optimization_goal = optimization_goal

        self.models = {
            "cheap_flash": ModelProfile(
                model_name="meta-llama/Llama-3.1-8B-Instruct",
                input_cost_per_m=0.07,
                output_cost_per_m=0.31,
                estimated_tps=120.0,
                accuracy_heuristic=0.82,
            ),
            "powerful_mid": ModelProfile(
                model_name="meta-llama/Llama-3.3-70B-Instruct",
                input_cost_per_m=0.70,
                output_cost_per_m=0.90,
                estimated_tps=60.0,
                accuracy_heuristic=0.93,
            ),
            "frontier_reasoning": ModelProfile(
                model_name="deepseek-ai/DeepSeek-V4-Pro",
                input_cost_per_m=2.00,
                output_cost_per_m=8.00,
                estimated_tps=35.0,
                accuracy_heuristic=0.98,
            ),
        }

    def _get_optimization_weights(self) -> Tuple[float, float, float]:
        """Returns weights for (Financial Cost, Latency, Accuracy Penalty)"""
        if self.optimization_goal == "cost":
            return (0.8, 0.1, 0.1)
        elif self.optimization_goal == "latency":
            return (0.1, 0.8, 0.1)
        else:  # balanced
            return (0.4, 0.3, 0.3)

    def enumerate_physical_plans(self, logical_plan: LogicalPlan) -> List[PhysicalPlan]:
        """
        Generates candidate physical strategies for the logical steps.
        Nodes within each plan are ordered by their DAG dependencies.
        """
        sorted_nodes = _topological_sort(logical_plan.nodes)
        plans = []

        # Plan 1: Naive (Route everything to the Frontier Model)
        naive_nodes = [
            PhysicalNode(
                logical_node_id=node.node_id,
                operation=node.operation,
                model=self.models["frontier_reasoning"],
                estimated_selectivity=1.0 if node.operation != "AGGREGATE" else 0.05,
            )
            for node in sorted_nodes
        ]
        plans.append(PhysicalPlan(plan_name="Naive (All-Frontier)", nodes=naive_nodes))

        # Plan 2: Push-down Optimization (cheap model for Scan/Filter, frontier for Aggregation)
        optimized_nodes = []
        for node in sorted_nodes:
            if node.operation in ["SCAN", "FILTER"]:
                chosen_model = self.models["cheap_flash"]
                selectivity = 0.05 if node.operation == "FILTER" else 1.0
            elif node.operation in ["EXTRACT", "JOIN"]:
                chosen_model = self.models["powerful_mid"]
                selectivity = 1.0
            else:  # AGGREGATE
                chosen_model = self.models["frontier_reasoning"]
                selectivity = 0.05

            optimized_nodes.append(
                PhysicalNode(
                    logical_node_id=node.node_id,
                    operation=node.operation,
                    model=chosen_model,
                    estimated_selectivity=selectivity,
                )
            )
        plans.append(PhysicalPlan(plan_name="Cost-Optimized Push-Down", nodes=optimized_nodes))

        return plans

    def evaluate_and_select(self, logical_plan: LogicalPlan) -> PhysicalPlan:
        candidate_plans = self.enumerate_physical_plans(logical_plan)
        w_cost, w_latency, w_accuracy = self._get_optimization_weights()

        # Build a lookup so we can resolve each physical node's logical dependencies.
        logical_node_map = {n.node_id: n for n in logical_plan.nodes}

        best_plan = None
        lowest_global_score = float("inf")

        for plan in candidate_plans:
            total_usd = 0.0
            total_seconds = 0.0
            accumulated_accuracy = 1.0

            # Track how many docs flow out of each node so downstream nodes use
            # the right input volume instead of a single shared counter.
            node_output_docs: Dict[str, int] = {}
            tokens_per_doc = self.dataset_stats["avg_tokens_per_doc"]

            for p_node in plan.nodes:
                logical_node = logical_node_map[p_node.logical_node_id]

                # Determine input volume from actual upstream dependencies.
                if not logical_node.depends_on:
                    input_docs = self.dataset_stats["total_docs"]
                else:
                    # JOIN-like nodes receive data from all parents; others from one.
                    # Sum for JOIN (processing both streams), max otherwise.
                    if p_node.operation == "JOIN":
                        input_docs = sum(
                            node_output_docs[dep_id] for dep_id in logical_node.depends_on
                        )
                    else:
                        input_docs = max(
                            node_output_docs[dep_id] for dep_id in logical_node.depends_on
                        )

                input_tokens = input_docs * tokens_per_doc

                # Financial cost
                input_usd = (input_tokens / 1_000_000) * p_node.model.input_cost_per_m
                output_tokens = input_docs * (50 if p_node.operation != "AGGREGATE" else 500)
                output_usd = (output_tokens / 1_000_000) * p_node.model.output_cost_per_m
                total_usd += input_usd + output_usd

                # Latency (SCAN/FILTER assumed parallelisable across a thread pool of 10)
                node_latency = (input_tokens + output_tokens) / p_node.model.estimated_tps
                if p_node.operation in ["SCAN", "FILTER"]:
                    node_latency /= 10
                total_seconds += node_latency

                # Accuracy compounds across the chain
                accumulated_accuracy *= p_node.model.accuracy_heuristic

                # Record this node's output volume for its dependents
                node_output_docs[p_node.logical_node_id] = max(
                    1, int(input_docs * p_node.estimated_selectivity)
                )

            plan.estimated_cost_usd = round(total_usd, 4)
            plan.estimated_latency_sec = round(total_seconds, 2)
            plan.estimated_accuracy = round(accumulated_accuracy, 3)

            accuracy_penalty = (1.0 - plan.estimated_accuracy) * 100
            plan_score = (
                (w_cost * plan.estimated_cost_usd * 10)
                + (w_latency * plan.estimated_latency_sec)
                + (w_accuracy * accuracy_penalty)
            )

            if plan_score < lowest_global_score:
                lowest_global_score = plan_score
                best_plan = plan

        return best_plan
