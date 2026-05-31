import json
import time
import asyncio
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from planner_agent import run_planner
from executor_agent.agent import filter_node, aggregator_node, joiner_node

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_CSV_PATH = str(Path(__file__).resolve().parent / "complaints_clean.csv")
_MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
_MODEL_INPUT_PRICE = 0.06
_MODEL_OUTPUT_PRICE = 0.06


class QueryRequest(BaseModel):
    question: str
    mode: str = "B"  # "A" | "B" | "C"


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _stream(question: str, mode: str):
    # ── Planner ────────────────────────────────────────────────────────────────
    yield _sse({"type": "agent_started", "agent": "planner"})

    t0 = time.time()
    plan = await asyncio.to_thread(run_planner, question)
    planner_latency = round(time.time() - t0, 2)

    # Extract instructions from the planner's DAG
    filter_instruction = question       # fallback: use raw question
    aggregation_instruction = question  # fallback

    for node in plan.nodes:
        if node.operation == "FILTER" and filter_instruction == question:
            filter_instruction = node.instruction
        if node.operation in ("AGGREGATE", "SUMMARIZE") and aggregation_instruction == question:
            aggregation_instruction = node.instruction

    # Estimate planner cost from plan size (planner doesn't expose token usage)
    plan_text_len = sum(len(n.instruction) for n in plan.nodes)
    est_tokens = 500 + plan_text_len // 4
    est_cost = round((est_tokens / 1_000_000) * _MODEL_INPUT_PRICE, 6)

    yield _sse({
        "type": "agent_completed",
        "agent": "planner",
        "tokens": est_tokens,
        "cost": est_cost,
        "latency": planner_latency,
    })

    # Shared state passed between executor nodes
    state = {
        "csv_path": _CSV_PATH,
        "filter_instruction": filter_instruction,
        "aggregation_instruction": aggregation_instruction,
        "model_id": _MODEL_ID,
        "mode": mode,
        "model_input_price": _MODEL_INPUT_PRICE,
        "model_output_price": _MODEL_OUTPUT_PRICE,
        "filtered_df": None,
        "filter_stats": None,
        "aggregation_result": None,
        "aggregation_stats": None,
        "joined_result": None,
        "joiner_stats": None,
    }

    # ── Filter node (sqlA) ─────────────────────────────────────────────────────
    yield _sse({"type": "agent_started", "agent": "sqlA"})

    result = await asyncio.to_thread(filter_node, state)
    state.update(result)
    s = state["filter_stats"]

    yield _sse({
        "type": "agent_completed",
        "agent": "sqlA",
        "tokens": s["tokens_in"] + s["tokens_out"],
        "cost": s["cost_usd"] or s["hypothetical_cost_usd"] or 0,
        "latency": s["latency_seconds"],
    })

    # ── Aggregator node (sqlB) ─────────────────────────────────────────────────
    yield _sse({"type": "agent_started", "agent": "sqlB"})

    result = await asyncio.to_thread(aggregator_node, state)
    state.update(result)
    s = state["aggregation_stats"]

    yield _sse({
        "type": "agent_completed",
        "agent": "sqlB",
        "tokens": s["tokens_in"] + s["tokens_out"],
        "cost": s["cost_usd"],
        "latency": s["latency_seconds"],
    })

    # ── Joiner node (reducer) ──────────────────────────────────────────────────
    yield _sse({"type": "agent_started", "agent": "reducer"})

    result = await asyncio.to_thread(joiner_node, state)
    state.update(result)
    s = state["joiner_stats"]
    joined = state["joined_result"]

    yield _sse({
        "type": "agent_completed",
        "agent": "reducer",
        "tokens": s["tokens_in"] + s["tokens_out"],
        "cost": s["cost_usd"],
        "latency": s["latency_seconds"],
    })

    # ── Final answer as markdown ───────────────────────────────────────────────
    md = f"## Executive Summary\n{joined.get('executive_summary', '')}\n\n"

    if joined.get("key_findings"):
        md += "## Key Findings\n"
        md += "\n".join(f"- {f}" for f in joined["key_findings"])
        md += "\n\n"

    if joined.get("real_examples"):
        md += "## Real Examples\n"
        md += "\n".join(f"> {e}" for e in joined["real_examples"])
        md += "\n\n"

    if joined.get("risk_indicators"):
        md += "## Risk Indicators\n"
        md += "\n".join(f"- {r}" for r in joined["risk_indicators"])
        md += "\n\n"

    if joined.get("recommendations"):
        md += "## Recommended Actions\n"
        md += "\n".join(f"- {r}" for r in joined["recommendations"])

    yield _sse({"type": "final_answer", "text": md})


@app.post("/query")
async def query(req: QueryRequest):
    return StreamingResponse(
        _stream(req.question, req.mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
