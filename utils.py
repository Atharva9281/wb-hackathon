from typing import Dict, Any

from planner_agent import LogicalPlan
from query_optimizer import PhysicalPlan, CostBasedOptimizer

_WIDTH = 72


def print_logical_plan(plan: LogicalPlan) -> None:
    print(f"\n┌─ LogicalPlan [{plan.plan_id}] {'─' * max(0, _WIDTH - 16 - len(plan.plan_id))}")
    for node in plan.nodes:
        src = f"  [{node.target_source}]" if node.target_source else ""
        deps = f"  (depends on: {', '.join(node.depends_on)})" if node.depends_on else ""
        print(f"│  [{node.node_id}] {node.operation}{src}{deps}")
        print(f"│       \"{node.instruction}\"")
        print("│")
    print(f"└{'─' * _WIDTH}\n")


def print_physical_plan(plan: PhysicalPlan) -> None:
    header = f"PhysicalPlan [{plan.plan_name}]"
    print(f"\n┌─ {header} {'─' * max(0, _WIDTH - 4 - len(header))}")
    print(f"│  Cost: ${plan.estimated_cost_usd:.4f}   "
          f"Latency: {plan.estimated_latency_sec:.2f}s   "
          f"Accuracy: {plan.estimated_accuracy:.3f}")
    print("│")
    for node in plan.nodes:
        op = node.operation.ljust(10)
        model = node.model.model_name
        sel = node.estimated_selectivity
        print(f"│  [{node.logical_node_id}] {op} → {model}  (selectivity: {sel:.2f})")
    print(f"└{'─' * _WIDTH}\n")


def print_optimizer_comparison(
    logical_plan: LogicalPlan,
    dataset_stats: Dict[str, Any],
    optimization_goal: str,
    selected_plan: PhysicalPlan,
) -> None:
    """Enumerate all candidate plans, evaluate each, and print a comparison table."""
    optimizer = CostBasedOptimizer(dataset_stats, optimization_goal)
    candidates = optimizer.enumerate_physical_plans(logical_plan)

    # evaluate_and_select already scored and populated the fields on the
    # winning plan; re-score the others so every candidate has metrics.
    w_cost, w_latency, w_accuracy = optimizer._get_optimization_weights()
    logical_node_map = {n.node_id: n for n in logical_plan.nodes}

    scored = []
    for plan in candidates:
        if plan.estimated_cost_usd == 0.0:
            # not yet evaluated — run the cost model
            node_output_docs: Dict[str, int] = {}
            total_usd = total_sec = 0.0
            acc = 1.0
            tpd = dataset_stats["avg_tokens_per_doc"]
            for p_node in plan.nodes:
                ln = logical_node_map[p_node.logical_node_id]
                if not ln.depends_on:
                    docs = dataset_stats["total_docs"]
                elif p_node.operation == "JOIN":
                    docs = sum(node_output_docs[d] for d in ln.depends_on)
                else:
                    docs = max(node_output_docs[d] for d in ln.depends_on)
                toks_in = docs * tpd
                toks_out = docs * (50 if p_node.operation != "AGGREGATE" else 500)
                total_usd += (toks_in / 1e6) * p_node.model.input_cost_per_m
                total_usd += (toks_out / 1e6) * p_node.model.output_cost_per_m
                lat = (toks_in + toks_out) / p_node.model.estimated_tps
                if p_node.operation in ("SCAN", "FILTER"):
                    lat /= 10
                total_sec += lat
                acc *= p_node.model.accuracy_heuristic
                node_output_docs[p_node.logical_node_id] = max(1, int(docs * p_node.estimated_selectivity))
            plan.estimated_cost_usd = round(total_usd, 4)
            plan.estimated_latency_sec = round(total_sec, 2)
            plan.estimated_accuracy = round(acc, 3)

        accuracy_penalty = (1.0 - plan.estimated_accuracy) * 100
        score = (
            w_cost * plan.estimated_cost_usd * 10
            + w_latency * plan.estimated_latency_sec
            + w_accuracy * accuracy_penalty
        )
        scored.append((plan, score))

    print(f"\n┌─ Optimizer Comparison  (goal: {optimization_goal}) {'─' * max(0, _WIDTH - 38 - len(optimization_goal))}")
    print(f"│  {'Plan':<30}  {'Cost (USD)':>10}  {'Latency (s)':>11}  {'Accuracy':>8}  {'Score':>8}")
    print(f"│  {'─'*30}  {'─'*10}  {'─'*11}  {'─'*8}  {'─'*8}")
    for plan, score in scored:
        marker = " ◀ selected" if plan.plan_name == selected_plan.plan_name else ""
        print(
            f"│  {plan.plan_name:<30}  "
            f"${plan.estimated_cost_usd:>9.4f}  "
            f"{plan.estimated_latency_sec:>11.2f}  "
            f"{plan.estimated_accuracy:>8.3f}  "
            f"{score:>8.2f}"
            f"{marker}"
        )
    print(f"└{'─' * _WIDTH}\n")
