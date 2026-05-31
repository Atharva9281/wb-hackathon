"""
End-to-end runner:
  natural language query
    → LogicalPlan  (planner_agent)
    → PhysicalPlan (query_optimizer)
    → execution    (executor_agent)

Usage:
    python run.py
    python run.py "your custom query here"
"""
import sys
from pathlib import Path

import weave
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
weave.init("query-optimizer-demo")

from planner_agent import run_planner
from utils import print_logical_plan, print_physical_plan

CSV_PATH = str(Path(__file__).parent / "backend" / "complaints_clean.csv")

SOURCE_REGISTRY = {
    "transcripts": CSV_PATH,
}

DATASET_STATS = {"total_docs": 20, "avg_tokens_per_doc": 300}

DEFAULT_QUERY = (
    "Find all customer complaints that mention a technical bug or software error "
    "and summarise the key issues by company."
)


def main(query: str) -> None:
    print(f"\nQuery: {query}\n")

    result = run_planner(
        user_query=query,
        dataset_stats=DATASET_STATS,
        optimization_goal="balanced",
        source_registry=SOURCE_REGISTRY,
    )

    print_logical_plan(result["logical_plan"])
    print_physical_plan(result["physical_plan"])

    exec_result = result["execution_result"]
    if exec_result is None:
        print("(Execution skipped — no source_registry provided)")
        return

    print("\n" + "═" * 72)
    print("EXECUTION RESULT")
    print("═" * 72)

    fs = exec_result.get("filter_stats", {})
    print(f"\nFilter stats:")
    print(f"  Rows in        : {fs.get('rows_in')}")
    print(f"  Rows matched   : {fs.get('rows_out')}")
    print(f"  Filter rate    : {fs.get('filter_rate')}")
    print(f"  Cost           : ${fs.get('cost_usd')}")
    print(f"  Latency        : {fs.get('latency_seconds')}s")

    agg = exec_result.get("aggregation_result", {})
    if agg:
        print(f"\nAggregation:")
        print(f"  Summary        : {agg.get('summary')}")
        print(f"  Total matches  : {agg.get('total_matches')}")
        print(f"  Key insight    : {agg.get('key_insight')}")
        print(f"  Top groups:")
        for g in agg.get("top_groups", []):
            print(f"    - {g.get('label')}: {g.get('count')} ({g.get('percentage')}%)")

    report = exec_result.get("joined_result", {})
    if report:
        print(f"\nExecutive Report:")
        print(f"  {report.get('executive_summary')}")
        print(f"\n  Key findings:")
        for f in report.get("key_findings", []):
            print(f"    • {f}")
        print(f"\n  Recommendations:")
        for r in report.get("recommendations", []):
            print(f"    • {r}")

    print("\n" + "═" * 72)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_QUERY
    main(query)
