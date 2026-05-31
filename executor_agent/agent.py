import os
import time
import json
import asyncio
import concurrent.futures
from pathlib import Path
from typing import TypedDict, Optional, Any

from dotenv import load_dotenv
import weave
import pandas as pd
from openai import OpenAI, AsyncOpenAI
from langgraph.graph import StateGraph, START, END

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

_WB_BASE_URL = "https://api.inference.wandb.ai/v1"


# ── This class contains the overall state of the executor.
# It acts as a global dict between the 3 nodes where each node
# does its own task and writes its results back into state.
class ExecutorState(TypedDict):
    # ── Inputs (set at invocation by the optimizer agent upstream) ──
    csv_path: str
    filter_instruction: str
    aggregation_instruction: str
    model_id: str          # decided upstream — nodes never change this
    mode: str              # "A", "B", or "C" — decided upstream
    model_input_price: float
    model_output_price: float
    max_rows: Optional[int]  # cap rows loaded from CSV; None = load all
    # ── Intermediate results (filled by each node) ──
    filtered_df: Optional[Any]       # pandas DataFrame
    filter_stats: Optional[dict]
    aggregation_result: Optional[dict]
    aggregation_stats: Optional[dict]
    joined_result: Optional[dict]
    joiner_stats: Optional[dict]


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("WANDB_API_KEY"), base_url=_WB_BASE_URL)


def _get_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=os.getenv("WANDB_API_KEY"), base_url=_WB_BASE_URL)


def _calc_cost(tokens_in: int, tokens_out: int, state: ExecutorState) -> float:
    return (tokens_in / 1_000_000 * state["model_input_price"]) + \
           (tokens_out / 1_000_000 * state["model_output_price"])


def _estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars per token."""
    return max(1, len(str(text)) // 4)


def _extract_json(raw: str) -> dict:
    """Strip markdown fences and extract the first JSON object."""
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1:
        raise ValueError("No JSON object in response")
    return json.loads(raw[start:end])


def _run_async(coro):
    """Run an async coroutine safely whether or not a loop is already running."""
    try:
        asyncio.get_running_loop()
        # Already inside a running loop — offload to a thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


# ── Filter helpers ─────────────────────────────────────────────────────────────

def _filter_messages(filter_instruction: str, narrative: str) -> list:
    return [
        {
            "role": "system",
            "content": (
                "You are a complaint classifier. "
                "Reply YES or NO only. No explanation whatsoever."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Instruction: {filter_instruction}\n\n"
                f"Complaint: {narrative}\n\n"
                "Does this complaint match?\n"
                "Answer YES or NO only."
            ),
        },
    ]


def _classify_sync(client, model_id, filter_instruction, narrative):
    resp = client.chat.completions.create(
        model=model_id,
        messages=_filter_messages(filter_instruction, narrative),
        max_tokens=5,
        temperature=0,
    )
    match = resp.choices[0].message.content.strip().upper().startswith("YES")
    return match, resp.usage


async def _classify_async(async_client, model_id, filter_instruction, narrative):
    resp = await async_client.chat.completions.create(
        model=model_id,
        messages=_filter_messages(filter_instruction, narrative),
        max_tokens=5,
        temperature=0,
    )
    match = resp.choices[0].message.content.strip().upper().startswith("YES")
    return match, resp.usage


async def _process_chunk(async_client, model_id, filter_instruction, chunk_df):
    tasks, indices = [], []
    for idx, row in chunk_df.iterrows():
        narrative = row["Consumer complaint narrative"]
        if pd.isna(narrative) or str(narrative).strip() == "":
            continue
        tasks.append(
            _classify_async(async_client, model_id, filter_instruction, str(narrative))
        )
        indices.append(idx)
    results = await asyncio.gather(*tasks)
    return list(zip(indices, results))


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 1 — filter_node   (was: filter_tool)
# ═══════════════════════════════════════════════════════════════════════════════

# This represents the 'filter' node in the LangGraph.
# It reads complaints from csv_path, applies LLM-based filtering,
# and writes filtered_df + filter_stats back into state.
@weave.op()
def filter_node(state: ExecutorState) -> dict:
    max_rows = state.get("max_rows")
    print(
        f"\n[executor] FILTER  — loading {state['csv_path']}"
        + (f"  (limit: {max_rows} rows)" if max_rows else ""),
        flush=True,
    )
    complaints_df = pd.read_csv(state["csv_path"], nrows=max_rows)

    model_id = state["model_id"]
    mode = state["mode"]
    filter_instruction = state["filter_instruction"]

    t0 = time.time()
    rows_in = len(complaints_df)
    tokens_in_total = 0
    tokens_out_total = 0

    # ── Mode A: skip filtering, compute hypothetical cost ──────────────────────
    if mode == "A":
        sys_text = (
            "You are a complaint classifier. "
            "Reply YES or NO only. No explanation whatsoever."
        )
        prefix = f"Instruction: {filter_instruction}\n\nComplaint: "
        suffix = "\n\nDoes this complaint match?\nAnswer YES or NO only."

        hyp_in, hyp_out = 0, 0
        for _, row in complaints_df.iterrows():
            narrative = row["Consumer complaint narrative"]
            if pd.isna(narrative) or str(narrative).strip() == "":
                continue
            hyp_in += _estimate_tokens(sys_text + prefix + str(narrative) + suffix)
            hyp_out += 1

        return {
            "filtered_df": complaints_df,
            "filter_stats": {
                "rows_in": rows_in,
                "rows_out": rows_in,
                "filter_rate": 0.0,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost_usd": 0.0,
                "hypothetical_cost_usd": round(_calc_cost(hyp_in, hyp_out, state), 6),
                "latency_seconds": round(time.time() - t0, 2),
            },
        }

    # ── Mode B: sequential batches of 20 ──────────────────────────────────────
    if mode == "B":
        client = _get_client()
        keep_indices = []
        processed = 0

        for batch_start in range(0, rows_in, 20):
            batch = complaints_df.iloc[batch_start : batch_start + 20]
            for idx, row in batch.iterrows():
                narrative = row["Consumer complaint narrative"]
                if pd.isna(narrative) or str(narrative).strip() == "":
                    processed += 1
                    continue
                match, usage = _classify_sync(
                    client, model_id, filter_instruction, str(narrative)
                )
                tokens_in_total += usage.prompt_tokens
                tokens_out_total += usage.completion_tokens
                if match:
                    keep_indices.append(idx)
                processed += 1
                print(
                    f"  [filter] {processed}/{rows_in} rows "
                    f"({len(keep_indices)} matched)",
                    end="\r",
                    flush=True,
                )
        print()  # newline after the \r progress line

    # ── Mode C: 4 concurrent chunks via asyncio ────────────────────────────────
    elif mode == "C":
        async_client = _get_async_client()
        chunk_size = max(1, -(-rows_in // 4))  # ceiling division → 4 chunks
        chunks = [
            complaints_df.iloc[i : i + chunk_size]
            for i in range(0, rows_in, chunk_size)
        ]
        print(f"  [filter] running {len(chunks)} parallel chunks of ~{chunk_size} rows each...", flush=True)

        async def _run_all():
            tasks = [
                _process_chunk(async_client, model_id, filter_instruction, chunk)
                for chunk in chunks
            ]
            return await asyncio.gather(*tasks)

        keep_indices = []
        for chunk_result in _run_async(_run_all()):
            for idx, (match, usage) in chunk_result:
                tokens_in_total += usage.prompt_tokens
                tokens_out_total += usage.completion_tokens
                if match:
                    keep_indices.append(idx)
        print(f"  [filter] done — {len(keep_indices)}/{rows_in} rows matched", flush=True)

    filtered = (
        complaints_df.loc[keep_indices]
        if keep_indices
        else complaints_df.iloc[0:0]
    )
    rows_out = len(filtered)
    filter_rate = round(1 - rows_out / rows_in, 4) if rows_in > 0 else 0.0

    return {
        "filtered_df": filtered,
        "filter_stats": {
            "rows_in": rows_in,
            "rows_out": rows_out,
            "filter_rate": filter_rate,
            "tokens_in": tokens_in_total,
            "tokens_out": tokens_out_total,
            "cost_usd": round(_calc_cost(tokens_in_total, tokens_out_total, state), 6),
            "hypothetical_cost_usd": None,
            "latency_seconds": round(time.time() - t0, 2),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 2 — aggregator_node   (was: aggregator_tool)
# ═══════════════════════════════════════════════════════════════════════════════

# This represents the 'aggregator' node in the LangGraph.
# It samples up to 500 rows from filtered_df, asks the LLM to
# group and summarise, and writes aggregation_result + aggregation_stats
# back into state.
@weave.op()
def aggregator_node(state: ExecutorState) -> dict:
    print(f"\n[executor] AGGREGATE — summarising {len(state['filtered_df'])} matched rows", flush=True)
    model_id = state["model_id"]
    filtered_df = state["filtered_df"]
    aggregation_instruction = state["aggregation_instruction"]

    t0 = time.time()
    client = _get_client()

    # Sample max 500 rows to avoid token overflow
    n = min(500, len(filtered_df))
    sample_df = (
        filtered_df.sample(n=n, random_state=42)
        if len(filtered_df) > 500
        else filtered_df
    )

    columns = filtered_df.columns.tolist()
    data_str = sample_df.to_csv(index=False)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a data analyst. "
                "Return JSON only. No markdown. No explanation. Raw JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Task: {aggregation_instruction}\n\n"
                f"Columns available: {columns}\n\n"
                f"Data sample:\n{data_str}\n\n"
                "Return JSON:\n"
                "{\n"
                '  "summary": "one sentence",\n'
                '  "top_groups": [\n'
                '    {"label": "...", "count": 0, "percentage": 0.0}\n'
                "  ],\n"
                '  "total_matches": 0,\n'
                '  "key_insight": "string"\n'
                "}"
            ),
        },
    ]

    tokens_in_total = 0
    tokens_out_total = 0

    def _call_and_parse() -> dict:
        nonlocal tokens_in_total, tokens_out_total
        resp = client.chat.completions.create(
            model=model_id, messages=messages, temperature=0
        )
        tokens_in_total += resp.usage.prompt_tokens
        tokens_out_total += resp.usage.completion_tokens
        return _extract_json(resp.choices[0].message.content.strip())

    try:
        result = _call_and_parse()
    except (json.JSONDecodeError, ValueError):
        result = _call_and_parse()  # retry once

    return {
        "aggregation_result": result,
        "aggregation_stats": {
            "tokens_in": tokens_in_total,
            "tokens_out": tokens_out_total,
            "cost_usd": round(_calc_cost(tokens_in_total, tokens_out_total, state), 6),
            "latency_seconds": round(time.time() - t0, 2),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 3 — joiner_node   (was: joiner_tool)
# ═══════════════════════════════════════════════════════════════════════════════

# This represents the 'joiner' node in the LangGraph.
# It joins aggregation_result with 3 real narrative examples
# and generates an executive report, writing joined_result +
# joiner_stats back into state.
@weave.op()
def joiner_node(state: ExecutorState) -> dict:
    print(f"\n[executor] JOIN    — generating executive report", flush=True)
    model_id = state["model_id"]
    filtered_df = state["filtered_df"]
    aggregation_result = state["aggregation_result"]

    t0 = time.time()
    client = _get_client()

    # 3 real narrative examples from filtered_df
    narratives = filtered_df["Consumer complaint narrative"].dropna()
    examples = narratives.sample(min(3, len(narratives)), random_state=42).tolist()
    examples_str = "\n\n".join(f"[{i + 1}] {ex}" for i, ex in enumerate(examples))

    columns = filtered_df.columns.tolist()

    messages = [
        {
            "role": "system",
            "content": "You are writing an executive report. Be concise and factual.",
        },
        {
            "role": "user",
            "content": (
                f"Analysis:\n{json.dumps(aggregation_result, indent=2)}\n\n"
                f"Real examples:\n{examples_str}\n\n"
                f"Available fields:\n{columns}\n\n"
                "Write report with:\n"
                "- Executive summary (2-3 sentences)\n"
                "- Key findings with real examples\n"
                "- Risk indicators\n"
                "- Recommended actions\n\n"
                "Return as JSON:\n"
                "{\n"
                '  "executive_summary": "2-3 sentences",\n'
                '  "key_findings": ["finding1", "finding2"],\n'
                '  "real_examples": ["verbatim example1", "verbatim example2"],\n'
                '  "risk_indicators": ["risk1", "risk2"],\n'
                '  "recommendations": ["action1", "action2"]\n'
                "}"
            ),
        },
    ]

    resp = client.chat.completions.create(
        model=model_id, messages=messages, temperature=0
    )
    tokens_in = resp.usage.prompt_tokens
    tokens_out = resp.usage.completion_tokens
    raw = resp.choices[0].message.content.strip()

    try:
        result = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        result = {
            "executive_summary": raw[:600],
            "key_findings": [],
            "real_examples": examples,
            "risk_indicators": [],
            "recommendations": [],
        }

    return {
        "joined_result": result,
        "joiner_stats": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": round(_calc_cost(tokens_in, tokens_out, state), 6),
            "latency_seconds": round(time.time() - t0, 2),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Graph — START → filter → aggregator → joiner → END
# ═══════════════════════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    builder = StateGraph(ExecutorState)

    builder.add_node("filter", filter_node)
    builder.add_node("aggregator", aggregator_node)
    builder.add_node("joiner", joiner_node)

    builder.add_edge(START, "filter")
    builder.add_edge("filter", "aggregator")
    builder.add_edge("aggregator", "joiner")
    builder.add_edge("joiner", END)

    return builder.compile()


# Compiled graph — import this to embed the executor inside a larger multi-agent graph.
executor_graph = build_graph()


@weave.op()
def run_executor(
    csv_path: str,
    filter_instruction: str,
    aggregation_instruction: str,
    model_id: str,
    mode: str,
    model_input_price: float,
    model_output_price: float,
    max_rows: Optional[int] = None,
) -> dict:
    return executor_graph.invoke(
        {
            "csv_path": csv_path,
            "filter_instruction": filter_instruction,
            "aggregation_instruction": aggregation_instruction,
            "model_id": model_id,
            "mode": mode,
            "model_input_price": model_input_price,
            "model_output_price": model_output_price,
            "max_rows": max_rows,
            "filtered_df": None,
            "filter_stats": None,
            "aggregation_result": None,
            "aggregation_stats": None,
            "joined_result": None,
            "joiner_stats": None,
        }
    )


if __name__ == "__main__":
    weave.init("wb-hackathon")
    _csv = str(Path(__file__).resolve().parents[1] / "backend" / "complaints_clean.csv")

    result = run_executor(
        csv_path=_csv,
        filter_instruction="complaints mentioning legal threats",
        aggregation_instruction="group by company and count",
        model_id="meta-llama/Llama-3.1-8B-Instruct",
        mode="B",
        model_input_price=0.06,
        model_output_price=0.06,
    )

    print("Filter stats    :", result["filter_stats"])
    print("Aggregation     :", result["aggregation_result"])
    print("Final report    :", result["joined_result"])
