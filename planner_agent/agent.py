import os
from pathlib import Path
from typing import TypedDict, Optional, Dict, Any, Literal

from dotenv import load_dotenv
import weave

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from .models import LogicalPlan
from .executor_bridge import physical_plan_to_executor_inputs
from query_optimizer.query_optimizer import CostBasedOptimizer, PhysicalPlan
from executor_agent.agent import run_executor

DEFAULT_DATASET_STATS = {"total_docs": 1000, "avg_tokens_per_doc": 1500}

SYSTEM_PROMPT ='''
GOAL:
You are a Logical Query Planner. Break the user request into a DAG of operations. 
Each node represents a single operation (SCAN, FILTER, EXTRACT, JOIN, or AGGREGATE). 
Assign unique node IDs (e.g. '1', '2') and specify dependencies between nodes.
Your job is to translate a user's natural language request into a Logical Execution Plan
represented as a Directed Acyclic Graph (DAG) of discrete operations.

BACKGROUND:
You have access to the following Data Sources:
1. "transcripts" (Unstructured Text: contains customer service chat logs)
2. "crm_database" (Structured SQL: contains customer_id, arr, renewal_date)

Available Logical Operations:
- SCAN: Read from a data source.
- FILTER: Isolate records based on a condition (e.g., "threatened to cancel").
- EXTRACT: Pull specific structured fields from unstructured text.
- JOIN: Combine streams of data based on a common key.
- AGGREGATE/SUMMARIZE: Reduce the final dataset into a final answer.

RULES:
1. Break the user's request down into the smallest logical steps.
2. Nodes must reference their upstream dependencies using `depends_on`.
3. Output strictly in the provided JSON schema format. Do not execute the tasks.

EXPECTED OUTPUT:
The returned JSON plan should correspond to the following JSON schema:

```
{
  "type": "object",
  "properties": {
    "plan_id": { "type": "string" },
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "node_id": { "type": "string" },
          "operation": { 
            "type": "string", 
            "enum": ["SCAN", "FILTER", "EXTRACT", "JOIN", "AGGREGATE"] 
          },
          "target_source": { "type": "string", "description": "e.g., support_transcripts" },
          "instruction": { "type": "string", "description": "The specific task for this node" },
          "depends_on": { 
            "type": "array", 
            "items": { "type": "string" },
            "description": "node_ids that must complete before this node starts"
          }
        },
        "required": ["node_id", "operation", "instruction", "depends_on"]
      }
    }
  },
  "required": ["plan_id", "nodes"]
}
```
i.e. the json plan should be a DAG nodes where eech node has the following properties:
- node_id: (required field)
- operation: can be one of SCAN, FILTER, EXTRACT, AGGREGATE, JOIN (reuired field)
- target_source: The source data for input to the node. This is an optional field
- depends_on: This field lists the node ids that this node would depend on.
  These node_ids must complete before this agent starts

EXAMPLE: 

Given the following user query:

" Find all the consumer complaints that involve a techincal bug and identify the 
  billing accounts of all those customers "

Expacted output:

{
  "plan_id": "req_88a9f2",
  "nodes": [
    {
      "node_id": "1",
      "operation": "SCAN",
      "target_source": "transcripts",
      "instruction": "Load all consumer complaints.",
      "depends_on": []
    },
    {
      "node_id": "2",
      "operation": "SCAN",
      "target_source": "crm_database",
      "instruction": "Load all consumer billing accounts.",
      "depends_on": []
    },
    {
      "node_id": "3",
      "operation": "FILTER",
      "target_source": null,
      "instruction": "Identify transcripts where the consumer is complaining about a technical bug.",
      "depends_on": ["1"]
    },
    {
      "node_id": "4",
      "operation": "EXTRACT",
      "target_source": null,
      "instruction": "Extract the 'account_id' and 'core_issue' from filtered transcripts.",
      "depends_on": ["3"]
    },
    {
      "node_id": "5",
      "operation": "JOIN",
      "target_source": null,
      "instruction": "Join the data for accounts with filtered transcripts with the account_id information.",
      "depends_on": ["4", "2"]
    },
    {
      "node_id": "6",
      "operation": "AGGREGATE",
      "target_source": null,
      "instruction": "Compile the data and write a concise, high-level summary.",
      "depends_on": ["4"]
    }
  ]
}

'''

# Shared state dict passed between all nodes in the graph.
class PlannerState(TypedDict):
    user_query: str
    dataset_stats: Dict[str, Any]
    optimization_goal: str
    source_registry: Optional[Dict[str, str]]   # None → skip execution
    max_rows: Optional[int]                      # cap CSV rows for testing
    logical_plan: Optional[LogicalPlan]
    physical_plan: Optional[PhysicalPlan]
    execution_result: Optional[dict]


class PlanningResult(TypedDict):
    logical_plan: LogicalPlan
    physical_plan: PhysicalPlan
    execution_result: Optional[dict]    # None when no source_registry supplied


# This creates the LLM client.
def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ.get("WANDB_MODEL", "openai/gpt-oss-20b"),
        api_key=os.environ["WANDB_API_KEY"],
        base_url="https://api.inference.wandb.ai/v1",
    ).with_structured_output(LogicalPlan)


# This represents the 'logical-query-planner' node in the the LangGraph.
# This node in the 'LangGraph' represents a 'logical-query-planner' task.
@weave.op()
def planner_node(state: PlannerState) -> dict:
    llm = _build_llm()
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=state["user_query"]),
    ]
    plan: LogicalPlan = llm.invoke(messages)
    return {"logical_plan": plan}


@weave.op()
def optimizer_node(state: PlannerState) -> dict:
    optimizer = CostBasedOptimizer(
        dataset_stats=state["dataset_stats"],
        optimization_goal=state["optimization_goal"],
    )
    physical_plan = optimizer.evaluate_and_select(state["logical_plan"])
    return {"physical_plan": physical_plan}


@weave.op()
def executor_node(state: PlannerState) -> dict:
    inputs = physical_plan_to_executor_inputs(
        state["logical_plan"],
        state["physical_plan"],
        state["source_registry"],
        state["optimization_goal"],
        state.get("max_rows"),
    )
    result = run_executor(**inputs)
    return {"execution_result": result}


def _route_after_optimizer(state: PlannerState) -> str:
    """Run the executor only when a source_registry was supplied."""
    registry = state.get("source_registry") or {}
    return "executor" if registry else END


# This will create the base graph for the multi-agent orchestration framework.
def build_graph() -> StateGraph:
    builder = StateGraph(PlannerState)

    # START -> logical-query-planner -> query-optimizer -> (executor)? -> END
    builder.add_node("logical-query-planner", planner_node)
    builder.add_node("query-optimizer", optimizer_node)
    builder.add_node("executor", executor_node)
    builder.add_edge(START, "logical-query-planner")
    builder.add_edge("logical-query-planner", "query-optimizer")
    builder.add_conditional_edges(
        "query-optimizer",
        _route_after_optimizer,
        {"executor": "executor", END: END},
    )
    builder.add_edge("executor", END)
    return builder.compile()


# Compiled graph — import this to embed the planner inside a larger multi-agent graph.
optimizer_demo_graph = build_graph()

# 
@weave.op()
def run_planner(
    user_query: str,
    dataset_stats: Optional[Dict[str, Any]] = None,
    optimization_goal: Literal["cost", "latency", "balanced"] = "balanced",
    source_registry: Optional[Dict[str, str]] = None,
    max_rows: Optional[int] = None,
) -> PlanningResult:
    result = optimizer_demo_graph.invoke({
        "user_query": user_query,
        "dataset_stats": dataset_stats or DEFAULT_DATASET_STATS,
        "optimization_goal": optimization_goal,
        "source_registry": source_registry,
        "max_rows": max_rows,
        "logical_plan": None,
        "physical_plan": None,
        "execution_result": None,
    })
    return PlanningResult(
        logical_plan=result["logical_plan"],
        physical_plan=result["physical_plan"],
        execution_result=result.get("execution_result"),
    )


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from utils import print_logical_plan, print_physical_plan

    weave.init("query-optimizer-demo")

    query = "Find all the cities where customers want a refund."

    # Pass a source_registry to also run the executor.
    # Remove / set to None to skip execution and only plan + optimise.
    registry = {
        "transcripts": str(Path(__file__).resolve().parents[1] / "backend" / "complaints_clean.csv")
    }

    result = run_planner(query, source_registry=registry)

    print_logical_plan(result["logical_plan"])
    print_physical_plan(result["physical_plan"])

    if result["execution_result"]:
        print("\n=== Execution Result ===")
        print("Filter stats :", result["execution_result"].get("filter_stats"))
        print("Aggregation  :", result["execution_result"].get("aggregation_result"))
        print("Final report :", result["execution_result"].get("joined_result"))
