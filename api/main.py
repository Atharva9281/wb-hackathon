"""
FastAPI backend for the WnB Hack Query Optimizer.

Streams SSE events as each pipeline stage completes so the frontend
can animate the agent graph in real time.

SSE event shapes (match the frontend's handleEvent in runQuery.ts):
  {"type": "agent_started",   "agent": "planner"|"sqlA"|"sqlB"|"reducer"}
  {"type": "agent_completed", "agent": ..., "tokens": int, "cost": float, "latency": float}
  {"type": "final_answer",    "text": str}
  {"type": "error",           "message": str}

Agent key mapping:
  planner  → logical-query-planner
  sqlA     → query-optimizer
  sqlB     → executor (filter + aggregate)
  reducer  → joiner   (executive report)
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

import weave
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Query Optimizer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your Vercel domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    weave.init("query-optimizer-api")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]
_CSV_PATH = str(_ROOT / "backend" / "complaints_clean.csv")
_SOURCE_REGISTRY = {"transcripts": _CSV_PATH}
_DATASET_STATS = {"total_docs": 1000, "avg_tokens_per_doc": 1500}
_MAX_ROWS = 200  # cap rows per request to keep latency acceptable

_MODE_TO_GOAL = {"A": "cost", "B": "balanced", "C": "latency"}


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str
    mode: str = "B"  # "A" | "B" | "C"


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _estimate_tokens(plan) -> int:
    """Rough token count for a logical plan based on instruction lengths."""
    if plan is None:
        return 0
    return sum(len(n.instruction) // 4 for n in plan.nodes) * 3


# ---------------------------------------------------------------------------
# Streaming endpoint
# ---------------------------------------------------------------------------

@app.post("/query")
async def query_endpoint(req: QueryRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream(req.question, req.mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream(question: str, mode: str) -> AsyncGenerator[str, None]:
    loop = asyncio.get_event_loop()
    optimization_goal = _MODE_TO_GOAL.get(mode, "balanced")

    # Lazy imports keep module-load time fast
    from planner_agent.agent import planner_node, optimizer_node, PlannerState
    from planner_agent.executor_bridge import physical_plan_to_executor_inputs
    from executor_agent.agent import run_executor

    state: PlannerState = {
        "user_query": question,
        "dataset_stats": _DATASET_STATS,
        "optimization_goal": optimization_goal,
        "source_registry": _SOURCE_REGISTRY if mode != "A" else None,
        "max_rows": _MAX_ROWS,
        "logical_plan": None,
        "physical_plan": None,
        "execution_result": None,
    }

    try:
        # ── 1. PLANNER ───────────────────────────────────────────────────────
        yield _sse({"type": "agent_started", "agent": "planner"})
        t0 = time.time()

        result = await loop.run_in_executor(None, planner_node, state)
        state.update(result)

        plan_tokens = _estimate_tokens(state["logical_plan"])
        yield _sse({
            "type": "agent_completed",
            "agent": "planner",
            "tokens": plan_tokens,
            "cost": round(plan_tokens / 1_000_000 * 2.0, 4),
            "latency": round(time.time() - t0, 2),
        })

        # ── 2. OPTIMIZER ─────────────────────────────────────────────────────
        yield _sse({"type": "agent_started", "agent": "sqlA"})
        t0 = time.time()

        result = await loop.run_in_executor(None, optimizer_node, state)
        state.update(result)

        physical_plan = state["physical_plan"]
        yield _sse({
            "type": "agent_completed",
            "agent": "sqlA",
            "tokens": 0,
            "cost": physical_plan.estimated_cost_usd if physical_plan else 0,
            "latency": round(time.time() - t0, 2),
        })

        # ── 3. EXECUTOR ──────────────────────────────────────────────────────
        exec_result: Optional[dict] = None
        if mode != "A":
            yield _sse({"type": "agent_started", "agent": "sqlB"})
            t0 = time.time()
            try:
                inputs = physical_plan_to_executor_inputs(
                    state["logical_plan"],
                    state["physical_plan"],
                    _SOURCE_REGISTRY,
                    optimization_goal,
                    max_rows=_MAX_ROWS,
                )
                inputs["mode"] = mode  # honour the exact mode requested
                exec_result = await loop.run_in_executor(
                    None, lambda: run_executor(**inputs)
                )
                state["execution_result"] = exec_result
            except Exception as exc:
                # executor failure is non-fatal — report cost as 0
                exec_result = None

            fs = (exec_result or {}).get("filter_stats") or {}
            yield _sse({
                "type": "agent_completed",
                "agent": "sqlB",
                "tokens": (fs.get("tokens_in") or 0) + (fs.get("tokens_out") or 0),
                "cost": fs.get("cost_usd") or 0,
                "latency": round(time.time() - t0, 2),
            })

        # ── 4. REDUCER (joiner → executive report) ───────────────────────────
        yield _sse({"type": "agent_started", "agent": "reducer"})
        t0 = time.time()

        agg_stats = (exec_result or {}).get("aggregation_stats") or {}
        join_stats = (exec_result or {}).get("joiner_stats") or {}
        reducer_tokens = (
            (agg_stats.get("tokens_in") or 0) + (agg_stats.get("tokens_out") or 0) +
            (join_stats.get("tokens_in") or 0) + (join_stats.get("tokens_out") or 0)
        )
        reducer_cost = (agg_stats.get("cost_usd") or 0) + (join_stats.get("cost_usd") or 0)

        yield _sse({
            "type": "agent_completed",
            "agent": "reducer",
            "tokens": reducer_tokens,
            "cost": round(reducer_cost, 4),
            "latency": round(time.time() - t0, 2),
        })

        # ── 5. FINAL ANSWER ──────────────────────────────────────────────────
        yield _sse({
            "type": "final_answer",
            "text": _build_answer(question, mode, state),
        })

    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# Answer formatter
# ---------------------------------------------------------------------------

def _build_answer(question: str, mode: str, state: dict) -> str:
    exec_result = state.get("execution_result") or {}
    report = exec_result.get("joined_result") or {}
    agg = exec_result.get("aggregation_result") or {}
    physical_plan = state.get("physical_plan")
    logical_plan = state.get("logical_plan")

    lines = ["## Summary\n"]

    summary = report.get("executive_summary") or agg.get("summary")
    if summary:
        lines.append(summary + "\n")
    elif physical_plan:
        lines.append(f"Query processed via **{physical_plan.plan_name}** plan.\n")

    lines.append(f"\n**Question:** _{question}_\n")

    if report.get("key_findings"):
        lines.append("\n### Key findings\n")
        for f in report["key_findings"]:
            lines.append(f"- {f}")

    if agg.get("top_groups"):
        lines.append("\n### Top groups\n")
        lines.append("| Group | Count | Share |")
        lines.append("| ----- | ----- | ----- |")
        for g in (agg["top_groups"] or [])[:5]:
            lines.append(f"| {g.get('label','')} | {g.get('count','')} | {g.get('percentage','')}% |")

    if report.get("recommendations"):
        lines.append("\n### Recommended actions\n")
        for r in report["recommendations"]:
            lines.append(f"- {r}")

    if physical_plan:
        lines.append("\n### Optimizer comparison\n")
        lines.append(f"**Selected plan:** {physical_plan.plan_name}  ")
        lines.append(
            f"Estimated cost: **${physical_plan.estimated_cost_usd:.4f}** | "
            f"Latency: **{physical_plan.estimated_latency_sec:.1f}s** | "
            f"Accuracy: **{physical_plan.estimated_accuracy:.2f}**"
        )

    if logical_plan:
        lines.append(f"\n### Logical plan ({len(logical_plan.nodes)} nodes)\n")
        for node in logical_plan.nodes:
            src = f" [{node.target_source}]" if node.target_source else ""
            deps = f" ← {', '.join(node.depends_on)}" if node.depends_on else ""
            lines.append(f"- **[{node.node_id}] {node.operation}{src}**{deps}: {node.instruction}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
