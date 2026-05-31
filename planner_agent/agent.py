import os
from pathlib import Path
from typing import TypedDict, Optional

from dotenv import load_dotenv
import weave

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END

from .models import LogicalPlan

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

# This class contains the overall state of the optimizer. It acts as a global dict between
# multiple agents where each agent is doing its own task. 
class PlannerState(TypedDict):
    user_query: str
    logical_plan: Optional[LogicalPlan]


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


# This will create the base graph for the multi-agent orchestration framework.
def build_graph() -> StateGraph:
    builder = StateGraph(PlannerState)

    # This builds the simple graph START->LOGICAL_QUERY_PLANNER->END
    builder.add_node("logical-query-planner", planner_node)
    builder.add_edge(START, "logical-query-planner")
    builder.add_edge("logical-query-planner", END)
    return builder.compile()


# Compiled graph — import this to embed the planner inside a larger multi-agent graph.
optimizer_demo_graph = build_graph()

# 
@weave.op()
def run_planner(user_query: str) -> LogicalPlan:
    result = optimizer_demo_graph.invoke({"user_query": user_query, "logical_plan": None})
    return result["logical_plan"]


if __name__ == "__main__":
    weave.init("query-optimizer-demo")

    query = "Find all the cities where customers want a refund."
    plan = run_planner(query)

    print(f"Plan ID : {plan.plan_id}")
    print(f"Nodes   : {len(plan.nodes)}")
    print(plan)
    for node in plan.nodes:
        deps = f" (depends on: {node.depends_on})" if node.depends_on else ""
        src = f" [{node.target_source}]" if node.target_source else ""
        print(f"  {node.node_id}  {node.operation}{src}: {node.instruction}{deps}")
