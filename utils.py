from planner_agent import LogicalPlan
from query_optimizer import PhysicalPlan

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
