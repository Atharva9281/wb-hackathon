import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Mode = "A" | "B" | "C";
export type Goal = "fastest" | "balanced" | "cheapest";
export type AgentKey = "planner" | "sqlA" | "sqlB" | "reducer";
export type Status = "idle" | "pending" | "running" | "done" | "error";

export interface AgentState {
  status: Status;
  tokens: number;
  cost: number;
  latency: number;
  startedAt?: number;
  endedAt?: number;
}

export interface HistoryItem {
  id: string;
  question: string;
  mode: Mode;
  cost: number;
  tokens: number;
  latency: number;
  timestamp: number;
  answer: string;
  agents: Record<AgentKey, AgentState>;
  modeReason?: string;
}

const emptyAgent = (): AgentState => ({
  status: "idle",
  tokens: 0,
  cost: 0,
  latency: 0,
});

const emptyAgents = (): Record<AgentKey, AgentState> => ({
  planner: emptyAgent(),
  sqlA: emptyAgent(),
  sqlB: emptyAgent(),
  reducer: emptyAgent(),
});

interface State {
  question: string;
  goal: Goal;
  mode: Mode;
  status: Status;
  answer: string;
  agents: Record<AgentKey, AgentState>;
  history: HistoryItem[];
  modeReason?: string;
  setQuestion: (q: string) => void;
  setGoal: (g: Goal) => void;
  setMode: (m: Mode) => void;
  setModeReason: (r: string) => void;
  startRun: () => void;
  agentStarted: (a: AgentKey) => void;
  agentCompleted: (a: AgentKey, tokens: number, cost: number, latency: number) => void;
  setAnswer: (text: string) => void;
  finishRun: () => void;
  errorRun: (msg: string) => void;
  resetAgents: () => void;
}

const now = Date.now();

const exampleHistory: HistoryItem[] = [
  {
    id: "demo-001",
    question: "Which bank has the most unresolved complaints?",
    mode: "B",
    cost: 1.15,
    tokens: 18432,
    latency: 12.3,
    timestamp: now - 300000,
    answer: "## Summary\n\nSmart filter narrowed the search space before invoking the analytical model.\n\n### Key findings\n\n- **Wells Fargo** leads with 4,210 unresolved complaints (12% of category).\n- Bank of America and Chase trail by less than 5%.\n- No data quality issues detected in the relevant slice.",
    modeReason: "Large dataset detected (20,000 rows). Filtering reduces token cost by 92%.",
    agents: {
      planner: { status: "done", tokens: 900, cost: 0.05, latency: 0.6 },
      sqlA: { status: "done", tokens: 4200, cost: 0.32, latency: 1.8 },
      sqlB: { status: "done", tokens: 5800, cost: 0.41, latency: 2.0 },
      reducer: { status: "done", tokens: 1900, cost: 0.37, latency: 0.9 },
    },
  },
  {
    id: "demo-002",
    question: "Find complaints threatening legal action",
    mode: "C",
    cost: 2.3,
    tokens: 22000,
    latency: 8.0,
    timestamp: now - 900000,
    answer: "## Summary\n\nTwo agents ran in parallel and a reducer merged the partial answers.\n\n### Key findings\n\n- 1,847 complaints reference 'lawyer', 'sue', or 'attorney general'.\n- 64% are mortgage-related disputes.\n- Median resolution time is 38 days.",
    modeReason: "Speed prioritized — parallelism cuts wall-clock by 60% with modest cost overhead.",
    agents: {
      planner: { status: "done", tokens: 1000, cost: 0.08, latency: 0.5 },
      sqlA: { status: "done", tokens: 6400, cost: 0.78, latency: 2.4 },
      sqlB: { status: "done", tokens: 6100, cost: 0.74, latency: 2.4 },
      reducer: { status: "done", tokens: 1800, cost: 0.7, latency: 0.7 },
    },
  },
  {
    id: "demo-003",
    question: "Find all fraud complaints filed in 2018",
    mode: "A",
    cost: 14.2,
    tokens: 80000,
    latency: 45.0,
    timestamp: now - 1800000,
    answer: "## Summary\n\nBrute force pass complete. The dataset was scanned end-to-end without filtering.\n\n### Key findings\n\n- 12,447 fraud complaints in 2018.\n- Peak month: August (1,420).\n- Top state: California (18%).",
    modeReason: "No filterable dimensions — full scan required.",
    agents: {
      planner: { status: "done", tokens: 1200, cost: 0.6, latency: 0.8 },
      sqlA: { status: "done", tokens: 48000, cost: 12.8, latency: 9.0 },
      sqlB: { status: "idle", tokens: 0, cost: 0, latency: 0 },
      reducer: { status: "done", tokens: 2200, cost: 0.8, latency: 1.2 },
    },
  },
];

export const useQueryStore = create<State>()(
  persist(
    (set, get) => ({
      question: "",
      goal: "balanced",
      mode: "B",
      status: "idle",
      answer: "",
      agents: emptyAgents(),
      history: exampleHistory,
      modeReason: undefined,
      setQuestion: (q) => set({ question: q }),
      setGoal: (g) => set({ goal: g }),
      setMode: (m) => set({ mode: m }),
      setModeReason: (r) => set({ modeReason: r }),
      resetAgents: () => set({ agents: emptyAgents(), answer: "", modeReason: undefined }),
      startRun: () =>
        set({
          status: "running",
          agents: emptyAgents(),
          answer: "",
          modeReason: undefined,
        }),
      agentStarted: (a) =>
        set((s) => ({
          agents: {
            ...s.agents,
            [a]: { ...s.agents[a], status: "running", startedAt: Date.now() },
          },
        })),
      agentCompleted: (a, tokens, cost, latency) =>
        set((s) => ({
          agents: {
            ...s.agents,
            [a]: {
              ...s.agents[a],
              status: "done",
              tokens,
              cost,
              latency,
              endedAt: Date.now(),
            },
          },
        })),
      setAnswer: (text) => set({ answer: text }),
      finishRun: () => {
        const s = get();
        const totalCost = Object.values(s.agents).reduce((sum, a) => sum + a.cost, 0);
        const totalTokens = Object.values(s.agents).reduce((sum, a) => sum + a.tokens, 0);
        const totalLatency = Math.max(
          ...Object.values(s.agents).map((a) => a.latency),
          0,
        );
        const item: HistoryItem = {
          id: crypto.randomUUID(),
          question: s.question,
          mode: s.mode,
          cost: totalCost,
          tokens: totalTokens,
          latency: totalLatency,
          timestamp: Date.now(),
          answer: s.answer,
          agents: s.agents,
          modeReason: s.modeReason,
        };
        set({ status: "done", history: [item, ...s.history].slice(0, 100) });
      },
      errorRun: () => set({ status: "error" }),
    }),
    {
      name: "querymind-store",
      partialize: (s) => ({ history: s.history }),
    },
  ),
);

export const MODE_META: Record<Mode, { key: Mode; name: string; short: string; color: string; bg: string }> = {
  A: { key: "A", name: "Brute Force", short: "Brute",    color: "#dc2626", bg: "#fef2f2" },
  B: { key: "B", name: "Smart Filter", short: "Smart",   color: "#16a34a", bg: "#f0fdf4" },
  C: { key: "C", name: "Parallel",     short: "Parallel",color: "#2563eb", bg: "#eff6ff" },
};

/**
 * Agent registry. Keys are kept as-is for back-compat with runQuery + history,
 * but visible labels follow the new Planner / Optimizer / Executor / Reducer model.
 */
export const AGENT_META: Record<AgentKey, { label: string; color: string }> = {
  planner:  { label: "Planner",   color: "#2563eb" },
  sqlA:     { label: "Optimizer", color: "#d97706" },
  sqlB:     { label: "Executor",  color: "#7c3aed" },
  reducer:  { label: "Reducer",   color: "#16a34a" },
};

export function pickModeFromGoal(goal: Goal): { mode: Mode; reason: string } {
  if (goal === "fastest") {
    return {
      mode: "C",
      reason: "Speed prioritized — parallel agents cut wall-clock by 60% with modest cost overhead.",
    };
  }
  if (goal === "cheapest") {
    return {
      mode: "B",
      reason: "Cost prioritized — filtering with a cheap model first cuts tokens by ~92%.",
    };
  }
  return {
    mode: "B",
    reason: "Large dataset detected (20,000 rows). Filtering reduces token cost by 92%.",
  };
}
