import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import toast from "react-hot-toast";
import { ChevronRight, Sparkles, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Navbar } from "@/components/Navbar";
import { ExecutionGraph } from "@/components/ExecutionGraph";
import { MODE_META, useQueryStore, type Goal, type HistoryItem } from "@/store/useQueryStore";
import { runQuery } from "@/lib/runQuery";

export const Route = createFileRoute("/dashboard")({
  head: () => ({
    meta: [
      { title: "Dashboard — QueryMind" },
      { name: "description", content: "Run multi-agent SQL queries and watch the execution graph in real time." },
    ],
  }),
  component: Dashboard,
});

const GOALS: { key: Goal; label: string }[] = [
  { key: "fastest",  label: "⚡ Fastest" },
  { key: "balanced", label: "⚖️ Balanced" },
  { key: "cheapest", label: "💰 Cheapest" },
];

function Dashboard() {
  const question = useQueryStore((s) => s.question);
  const goal = useQueryStore((s) => s.goal);
  const status = useQueryStore((s) => s.status);
  const mode = useQueryStore((s) => s.mode);
  const modeReason = useQueryStore((s) => s.modeReason);
  const answer = useQueryStore((s) => s.answer);
  const agents = useQueryStore((s) => s.agents);
  const history = useQueryStore((s) => s.history);
  const setQuestion = useQueryStore((s) => s.setQuestion);
  const setGoal = useQueryStore((s) => s.setGoal);

  const [local, setLocal] = useState(question);

  const handleRun = async () => {
    const q = local.trim();
    if (!q) {
      toast.error("Enter a question first");
      return;
    }
    try {
      await runQuery(q, goal);
    } catch (e: any) {
      toast.error(e?.message || "Query failed");
    }
  };

  const totalTokens = Object.values(agents).reduce((s, a) => s + a.tokens, 0);
  const totalCost = Object.values(agents).reduce((s, a) => s + a.cost, 0);
  const totalLatency = Math.max(...Object.values(agents).map((a) => a.latency), 0);
  const isDone = status === "done";

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <Navbar />
      <div className="grid flex-1 grid-cols-12">
        {/* LEFT */}
        <aside className="col-span-12 border-r border-border bg-panel p-5 lg:col-span-3 lg:max-h-[calc(100vh-56px)] lg:overflow-y-auto">
          <div className="label-eyebrow">Query</div>
          <textarea
            value={local}
            onChange={(e) => {
              setLocal(e.target.value);
              setQuestion(e.target.value);
            }}
            placeholder="Ask anything about your data..."
            rows={5}
            className="mt-2 w-full resize-y rounded-lg border border-border bg-white p-3 text-[14px] text-charcoal placeholder:text-[#9ca3af] focus:border-primary focus:outline-none"
            style={{ minHeight: 100 }}
          />

          <div className="label-eyebrow mt-5">Optimization Goal</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {GOALS.map((g) => {
              const active = goal === g.key;
              return (
                <button
                  key={g.key}
                  onClick={() => setGoal(g.key)}
                  className="rounded-full border px-3 py-1 text-[12px] font-medium transition"
                  style={{
                    borderColor: active ? "#2563eb" : "#e5e7eb",
                    backgroundColor: active ? "#2563eb" : "#ffffff",
                    color: active ? "#ffffff" : "#6b7280",
                  }}
                >
                  {g.label}
                </button>
              );
            })}
          </div>

          <button
            onClick={handleRun}
            disabled={status === "running"}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-[14px] font-medium text-primary-foreground transition hover:bg-[#1d4ed8] disabled:opacity-60"
          >
            {status === "running" ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Agents working…
              </>
            ) : (
              "Run Query"
            )}
          </button>

          <div className="my-5 border-t border-border" />

          <div className="label-eyebrow">Recent Queries</div>
          <div className="mt-2">
            {history.length === 0 && (
              <div className="text-xs text-muted-foreground">No queries yet</div>
            )}
            {history.slice(0, 8).map((h) => (
              <HistoryRow
                key={h.id}
                item={h}
                onClick={() => {
                  setLocal(h.question);
                  setQuestion(h.question);
                }}
              />
            ))}
          </div>
        </aside>

        {/* MIDDLE */}
        <section className="col-span-12 border-r border-border bg-white p-6 lg:col-span-6 lg:max-h-[calc(100vh-56px)] lg:overflow-y-auto">
          <div className="label-eyebrow">Execution Graph</div>
          <ExecutionGraph />

          {isDone && (
            <div
              className="mt-5 rounded-lg border border-border bg-white p-4"
              style={{ borderLeftWidth: 3, borderLeftColor: "#2563eb" }}
            >
              <div className="text-[13px] font-bold text-charcoal">
                Agent selected: {MODE_META[mode].name}
              </div>
              {modeReason && (
                <div className="mt-1 text-[13px] text-muted-foreground">{modeReason}</div>
              )}
            </div>
          )}
        </section>

        {/* RIGHT */}
        <aside className="col-span-12 bg-panel p-5 lg:col-span-3 lg:max-h-[calc(100vh-56px)] lg:overflow-y-auto">
          <div className="label-eyebrow">Answer</div>

          {!answer ? (
            <div className="mt-6 flex flex-col items-center justify-center rounded-lg border border-border bg-white py-12 text-center">
              <Sparkles className="h-5 w-5 text-muted-foreground" />
              <div className="mt-2 text-[13px] text-muted-foreground">
                Run a query to see results
              </div>
            </div>
          ) : (
            <div className="md-answer mt-3 rounded-lg border border-border bg-white p-4 text-[13.5px] leading-relaxed text-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
            </div>
          )}

          {isDone && (
            <div className="mt-4 rounded-lg border border-border bg-white p-4">
              <CostRow label="Agent chose"  value={MODE_META[mode].name} />
              <CostRow label="Model"        value="DeepSeek-V3.1" />
              <CostRow label="Tokens"       value={totalTokens.toLocaleString()} />
              <CostRow label="Cost"         value={`$${totalCost.toFixed(4)}`} />
              <CostRow label="Latency"      value={`${totalLatency.toFixed(1)}s`} last />
            </div>
          )}

          <Link
            to="/economics"
            className="mt-4 inline-block text-[13px] font-medium text-primary hover:underline"
          >
            View full breakdown →
          </Link>
        </aside>
      </div>
    </div>
  );
}

function CostRow({ label, value, last }: { label: string; value: string; last?: boolean }) {
  return (
    <div
      className="flex items-center justify-between py-1.5 font-mono text-[12px]"
      style={{ borderBottom: last ? "none" : "1px solid #f3f4f6" }}
    >
      <span className="text-[#9ca3af]">{label}</span>
      <span className="text-charcoal">{value}</span>
    </div>
  );
}

function HistoryRow({ item, onClick }: { item: HistoryItem; onClick: () => void }) {
  const meta = MODE_META[item.mode];
  return (
    <button
      onClick={onClick}
      className="group flex w-full items-center gap-3 border-b border-[#f3f4f6] px-3 py-2.5 text-left transition hover:bg-[#f1f5f9]"
    >
      <span
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-charcoal">
          {item.question}
        </div>
        <div className="mt-0.5 truncate font-mono text-[11px] text-[#9ca3af]">
          ${item.cost.toFixed(2)} · {item.latency.toFixed(1)}s · {meta.short} · {relTime(item.timestamp)}
        </div>
      </div>
      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#9ca3af]" />
    </button>
  );
}

function relTime(ts: number) {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
