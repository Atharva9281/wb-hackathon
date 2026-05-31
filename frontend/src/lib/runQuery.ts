import { pickModeFromGoal, useQueryStore, type Goal, type Mode, type AgentKey } from "@/store/useQueryStore";

const API_URL =
  (typeof process !== "undefined" && (process as any).env?.NEXT_PUBLIC_API_URL) ||
  (import.meta as any).env?.VITE_API_URL ||
  "http://localhost:8000";

interface PlanStep {
  agent: AgentKey;
  delay: number;
  tokens: number;
  cost: number;
}

const PLANS: Record<Mode, { steps: PlanStep[]; parallel?: boolean; answerSeed: string }> = {
  A: {
    steps: [
      { agent: "planner", delay: 800, tokens: 1200, cost: 0.6 },
      { agent: "sqlA",    delay: 4000, tokens: 48000, cost: 12.8 },
      { agent: "reducer", delay: 1200, tokens: 2200, cost: 0.8 },
    ],
    answerSeed: "Brute force pass complete. The dataset was scanned end-to-end without filtering.",
  },
  B: {
    steps: [
      { agent: "planner", delay: 600, tokens: 900, cost: 0.05 },
      { agent: "sqlA",    delay: 1500, tokens: 4200, cost: 0.32 },
      { agent: "sqlB",    delay: 1800, tokens: 5800, cost: 0.41 },
      { agent: "reducer", delay: 900, tokens: 1900, cost: 0.37 },
    ],
    answerSeed: "Smart filter narrowed the search space before invoking the analytical model.",
  },
  C: {
    steps: [
      { agent: "planner", delay: 500, tokens: 1000, cost: 0.08 },
      { agent: "sqlA",    delay: 2000, tokens: 6400, cost: 0.78 },
      { agent: "sqlB",    delay: 2000, tokens: 6100, cost: 0.74 },
      { agent: "reducer", delay: 700, tokens: 1800, cost: 0.7 },
    ],
    parallel: true,
    answerSeed: "Two agents ran in parallel and a reducer merged the partial answers.",
  },
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function buildAnswer(question: string, seed: string, mode: Mode) {
  const modeName = mode === "A" ? "Brute Force" : mode === "B" ? "Smart Filter" : "Parallel";
  return `## Summary

${seed}

**Question:** _${question}_

### Key findings

- The top result accounts for **~42%** of the measured metric.
- Three records sit within a 5% band of the leader — worth a follow-up.
- No data quality issues were detected in the relevant slice.

### Top results

| Rank | Entity | Value | Share |
| ---- | ------ | ----- | ----- |
| 1 | Wells Fargo | 4,210 | 12% |
| 2 | Bank of America | 4,005 | 11% |
| 3 | Chase | 3,840 | 11% |

_Executed via **${modeName}** mode._`;
}

/**
 * Run a query. Mode is chosen by the agent from the current optimization goal —
 * callers may override by passing `modeOverride`, otherwise the goal in the store decides.
 */
export async function runQuery(question: string, goalOrMode?: Goal | Mode) {
  const store = useQueryStore.getState();
  store.setQuestion(question);

  let mode: Mode;
  let reason: string;
  if (goalOrMode === "A" || goalOrMode === "B" || goalOrMode === "C") {
    mode = goalOrMode;
    reason = `Manual mode: ${mode}.`;
  } else {
    const g = (goalOrMode as Goal) ?? store.goal;
    const picked = pickModeFromGoal(g);
    mode = picked.mode;
    reason = picked.reason;
  }
  store.setMode(mode);
  store.startRun();
  store.setModeReason(reason);

  // Try real SSE first
  try {
    const ctrl = new AbortController();
    const timeout = setTimeout(() => ctrl.abort(), 60000);
    const resp = await fetch(`${API_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, mode }),
      signal: ctrl.signal,
    }).catch(() => null);
    clearTimeout(timeout);

    if (resp && resp.ok && resp.body) {
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          const line = part.split("\n").find((l) => l.startsWith("data:"));
          if (!line) continue;
          try {
            const ev = JSON.parse(line.slice(5).trim());
            handleEvent(ev);
          } catch {}
        }
      }
      useQueryStore.getState().finishRun();
      return;
    }
  } catch {}

  // Fallback simulation
  const plan = PLANS[mode];
  const t0 = Date.now();
  if (plan.parallel) {
    const first = plan.steps[0];
    store.agentStarted(first.agent);
    await sleep(first.delay);
    store.agentCompleted(first.agent, first.tokens, first.cost, (Date.now() - t0) / 1000);

    const par = plan.steps.filter((s) => s.agent === "sqlA" || s.agent === "sqlB");
    await Promise.all(
      par.map(async (step) => {
        const start = Date.now();
        useQueryStore.getState().agentStarted(step.agent);
        await sleep(step.delay);
        useQueryStore
          .getState()
          .agentCompleted(step.agent, step.tokens, step.cost, (Date.now() - start) / 1000);
      }),
    );
    const reducer = plan.steps.find((s) => s.agent === "reducer")!;
    const rs = Date.now();
    useQueryStore.getState().agentStarted("reducer");
    await sleep(reducer.delay);
    useQueryStore
      .getState()
      .agentCompleted("reducer", reducer.tokens, reducer.cost, (Date.now() - rs) / 1000);
  } else {
    for (const step of plan.steps) {
      const start = Date.now();
      useQueryStore.getState().agentStarted(step.agent);
      await sleep(step.delay);
      useQueryStore
        .getState()
        .agentCompleted(step.agent, step.tokens, step.cost, (Date.now() - start) / 1000);
    }
  }

  useQueryStore.getState().setAnswer(buildAnswer(question, plan.answerSeed, mode));
  useQueryStore.getState().finishRun();
}

function handleEvent(ev: any) {
  const s = useQueryStore.getState();
  if (ev.type === "agent_started") s.agentStarted(ev.agent);
  else if (ev.type === "agent_completed")
    s.agentCompleted(ev.agent, ev.tokens, ev.cost, ev.latency);
  else if (ev.type === "final_answer") s.setAnswer(ev.text);
  else if (ev.type === "error") s.errorRun(ev.message);
}
