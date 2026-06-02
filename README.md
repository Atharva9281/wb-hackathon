# QueryMind

A multi-agent LLM system that automatically optimises how natural language queries are executed over large datasets.

Built at the **AGI House Hackathon, May 2026**, powered by [Weights & Biases](https://wandb.ai) inference and Weave tracing.

**Presentation:** https://gamma.app/docs/Stop-Overpaying-for-AI-Queries-dagsxclndmyx57y

---

## What it does

You type a question like *"Which banks have the most unresolved complaints?"*. The system:

1. **Plans** — breaks the question into a logical DAG of operations (SCAN → FILTER → AGGREGATE)
2. **Optimises** — a cost-based optimizer picks the cheapest model for each step (cheap flash model for bulk filtering, frontier model only for final aggregation)
3. **Executes** — runs filter → aggregate → report on the actual complaints dataset
4. **Streams** — sends live progress events to the frontend as each agent completes

The result is a markdown executive report with key findings, risk indicators, and recommendations — along with a full cost and token breakdown for every agent.

---

## Architecture

```
User query (natural language)
        │
        ▼
┌──────────────────┐
│  Planner Agent   │  LLM → Logical Execution Plan (DAG)
│  (LangGraph)     │  Operations: SCAN, FILTER, EXTRACT, JOIN, AGGREGATE
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Query Optimizer  │  Cost-based: enumerates candidate physical plans
│ (CostBased)      │  Selects best by weighted score (cost + latency + accuracy)
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────┐
│          Executor Agent              │
│  filter_node → aggregator_node → joiner_node  │
│  (LangGraph, 3 sequential nodes)     │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────┐
│  FastAPI Backend │  POST /query → Server-Sent Events stream
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  React Frontend  │  ExecutionGraph + AnswerPanel + Economics dashboard
│  (TanStack Start)│  History saved to localStorage
└──────────────────┘
```

---

## Execution modes

| Mode | Strategy | Cost | Latency |
|------|----------|------|---------|
| **A — Brute Force** | No filtering, every row sent to frontier model | ~$14.20 | Slowest |
| **B — Smart Filter** | Cheap model filters first (sequential batches of 20), frontier model aggregates only matching rows | ~$1.15 | Medium |
| **C — Parallel** | Same as B but splits into 4 concurrent async chunks | ~$2.30 | Fastest |

The optimizer selects the mode automatically based on your goal (Cheapest / Balanced / Fastest).

---

## Repo structure

```
.
├── run.py                        # CLI end-to-end runner
├── utils.py                      # Pretty-print helpers
│
├── planner_agent/
│   ├── agent.py                  # LangGraph: planner → optimizer → executor nodes
│   ├── models.py                 # LogicalPlan, PlanNode (Pydantic)
│   ├── executor_bridge.py        # Translates logical+physical plan → executor inputs
│   └── requirements.txt
│
├── query_optimizer/
│   └── query_optimizer.py        # CostBasedOptimizer, ModelProfile, PhysicalPlan
│
├── executor_agent/
│   ├── agent.py                  # LangGraph: filter_node → aggregator_node → joiner_node
│   ├── models.py                 # AggregationResult, JoinedResult (Pydantic)
│   └── requirements.txt
│
├── backend/
│   ├── main.py                   # FastAPI server — POST /query (SSE), GET /health
│   ├── complaints_clean.csv      # CFPB consumer complaints dataset (20k rows, 2018–2019)
│   └── requirements.txt
│
└── frontend/
    ├── vite.config.ts
    ├── src/
    │   ├── routes/
    │   │   ├── index.tsx         # Landing page
    │   │   ├── dashboard.tsx     # Main query interface
    │   │   └── economics.tsx     # Cost analytics dashboard
    │   ├── components/
    │   │   ├── ExecutionGraph.tsx # Live agent pipeline visualisation
    │   │   └── AnswerPanel.tsx   # Markdown result + PDF/DOCX export
    │   ├── store/
    │   │   └── useQueryStore.ts  # Zustand store (history persisted to localStorage)
    │   └── lib/
    │       ├── runQuery.ts       # SSE client + simulation fallback
    │       └── exportAnswer.ts   # PDF + DOCX export
    └── package.json
```

---

## Data

`backend/complaints_clean.csv` — a 20,000-row sample of the [CFPB Consumer Financial Protection Bureau](https://www.consumerfinance.gov/data-research/consumer-complaints/) complaints dataset, filtered to 2018–2019 rows where the narrative is not null.

---

## Running locally

### Prerequisites

- Python 3.10+
- Node.js / [Bun](https://bun.sh)
- A `.env` file at the project root:

```
WANDB_API_KEY=your_key_here
WANDB_MODEL=openai/gpt-oss-20b
```

### Backend

```bash
pip install -r backend/requirements.txt
python backend/main.py
# → http://localhost:8000
```

### Frontend

```bash
cd frontend
bun install
bun dev
# → http://localhost:3000
```

### CLI (no server needed)

```bash
pip install -r backend/requirements.txt
python run.py "Which companies have the most unresolved complaints?"
```

---

## API

### `POST /query`

Returns a Server-Sent Events stream.

**Request body:**
```json
{
  "question": "Which banks have the most unresolved complaints?",
  "mode": "B"
}
```

**SSE events:**
```
data: {"type": "agent_started",   "agent": "planner"}
data: {"type": "agent_completed", "agent": "planner",   "tokens": 520,  "cost": 0.031, "latency": 1.2}
data: {"type": "agent_started",   "agent": "sqlA"}
data: {"type": "agent_completed", "agent": "sqlA",      "tokens": 4100, "cost": 0.32,  "latency": 8.4}
data: {"type": "agent_started",   "agent": "sqlB"}
data: {"type": "agent_completed", "agent": "sqlB",      "tokens": 5800, "cost": 0.41,  "latency": 4.1}
data: {"type": "agent_started",   "agent": "reducer"}
data: {"type": "agent_completed", "agent": "reducer",   "tokens": 1900, "cost": 0.37,  "latency": 2.3}
data: {"type": "final_answer",    "text": "## Executive Summary\n..."}
```

### `GET /health`

```json
{"status": "ok"}
```

---

## Models used

| Role | Model | Notes |
|------|-------|-------|
| Logical planner | `openai/gpt-oss-20b` | Via W&B inference |
| Filter (cost-optimised) | `meta-llama/Llama-3.1-8B-Instruct` | Cheap flash — bulk YES/NO classification |
| Aggregation | `meta-llama/Llama-3.3-70B-Instruct` | Mid-tier — structured JSON grouping |
| Report (frontier) | `deepseek-ai/DeepSeek-V4-Pro` | Used when accuracy goal is highest |

All models served through the [W&B Inference API](https://api.inference.wandb.ai/v1). All calls traced with [Weave](https://wandb.ai/site/weave).

---

## Deployment

- **Frontend** — Vercel (TanStack Start + Nitro, Node.js 24 serverless)
- **Backend** — Railway / Render (FastAPI + uvicorn)

Frontend falls back to a built-in simulation if the backend is unreachable, so the demo works without a live backend.
