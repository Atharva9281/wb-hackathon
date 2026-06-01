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


export const useQueryStore = create<State>()(
  persist(
    (set, get) => ({
      question: "",
      goal: "balanced",
      mode: "B",
      status: "idle",
      answer: "",
      agents: emptyAgents(),
      history: [],
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
