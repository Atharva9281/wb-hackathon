import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Navbar } from "@/components/Navbar";
import {
  AGENT_META,
  MODE_META,
  useQueryStore,
  type AgentKey,
  type HistoryItem,
  type Mode,
} from "@/store/useQueryStore";

export const Route = createFileRoute("/economics")({
  head: () => ({
    meta: [
      { title: "Economics — QueryMind" },
      { name: "description", content: "Cost analytics across query modes and agents." },
    ],
  }),
  component: Economics,
});

type ModeFilter = "all" | Mode;

function Economics() {
  const history = useQueryStore((s) => s.history);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all");
  const [tab, setTab] = useState<"breakdown" | "logs">("breakdown");

  const selected: HistoryItem | undefined =
    history.find((h) => h.id === selectedId) ?? history[0];

  const filtered = useMemo(
    () => history.filter((h) => modeFilter === "all" || h.mode === modeFilter),
    [history, modeFilter],
  );

  const totals = useMemo(() => {
    const totalQueries = history.length;
    const totalTokens = history.reduce((s, h) => s + h.tokens, 0);
    const totalCost = history.reduce((s, h) => s + h.cost, 0);
    const avg = totalQueries ? totalCost / totalQueries : 0;
    return { totalQueries, totalTokens, totalCost, avg };
  }, [history]);

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <Navbar />
      <div className="grid flex-1 grid-cols-12">
        {/* LEFT */}
        <aside className="col-span-12 border-r border-border bg-panel p-5 lg:col-span-3 lg:max-h-[calc(100vh-56px)] lg:overflow-y-auto">
          <h1 className="text-[20px] font-bold tracking-tight text-charcoal">Economics</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Cost analytics across all queries. Select to drill in.
          </p>

          <div className="mt-5 space-y-2">
            <StatCard label="Total Queries" value={totals.totalQueries.toString()} />
            <StatCard label="Total Tokens"  value={totals.totalTokens.toLocaleString()} />
            <StatCard label="Total Cost"    value={`$${totals.totalCost.toFixed(2)}`} />
            <StatCard label="Avg Cost / Query" value={`$${totals.avg.toFixed(2)}`} />
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            {([
              ["all", "All"],
              ["A", "Brute"],
              ["B", "Smart"],
              ["C", "Parallel"],
            ] as [ModeFilter, string][]).map(([k, label]) => {
              const active = modeFilter === k;
              return (
                <button
                  key={k}
                  onClick={() => setModeFilter(k)}
                  className="rounded-full border px-3 py-1 text-[12px] font-medium transition"
                  style={{
                    borderColor: active ? "#2563eb" : "#e5e7eb",
                    backgroundColor: active ? "#2563eb" : "#ffffff",
                    color: active ? "#ffffff" : "#6b7280",
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>

          <div className="mt-4 rounded-lg border border-border bg-white">
            {filtered.length === 0 ? (
              <div className="px-3 py-6 text-center text-[12px] text-muted-foreground">
                No queries match
              </div>
            ) : (
              filtered.map((h) => (
                <QueryRow
                  key={h.id}
                  item={h}
                  active={h.id === selected?.id}
                  onClick={() => setSelectedId(h.id)}
                />
              ))
            )}
          </div>
        </aside>

        {/* RIGHT */}
        <section className="col-span-12 bg-white p-6 lg:col-span-9 lg:max-h-[calc(100vh-56px)] lg:overflow-y-auto">
          {!selected ? (
            <div className="rounded-lg border border-border p-10 text-center text-sm text-muted-foreground">
              Run a query from the dashboard to see economics.
            </div>
          ) : (
            <>
              <DetailHeader item={selected} />

              <div className="mt-6 flex gap-6 border-b border-border">
                <TabBtn active={tab === "breakdown"} onClick={() => setTab("breakdown")}>
                  Cost Breakdown
                </TabBtn>
                <TabBtn active={tab === "logs"} onClick={() => setTab("logs")}>
                  Raw Logs
                </TabBtn>
              </div>

              {tab === "breakdown" ? (
                <Breakdown selected={selected} />
              ) : (
                <Logs selected={selected} />
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-white px-3.5 py-3">
      <div className="text-[10px] font-medium uppercase tracking-wider text-[#9ca3af]">
        {label}
      </div>
      <div className="mt-1 font-mono text-[22px] font-semibold text-charcoal">{value}</div>
    </div>
  );
}

function QueryRow({
  item,
  active,
  onClick,
}: {
  item: HistoryItem;
  active: boolean;
  onClick: () => void;
}) {
  const meta = MODE_META[item.mode];
  return (
    <button
      onClick={onClick}
      className="relative flex w-full items-center gap-3 border-b border-[#f3f4f6] px-3 py-2.5 text-left transition last:border-b-0 hover:bg-[#f8f9fa]"
      style={{ backgroundColor: active ? "#ffffff" : undefined }}
    >
      {active && <span className="absolute inset-y-0 left-0 w-[3px] bg-primary" />}
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

function DetailHeader({ item }: { item: HistoryItem }) {
  const meta = MODE_META[item.mode];
  return (
    <div>
      <div className="text-[16px] font-bold leading-snug text-charcoal">
        {item.question}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[12px] text-muted-foreground">
        <span
          className="rounded-sm px-2 py-0.5 text-[11px] font-medium"
          style={{ backgroundColor: meta.bg, color: meta.color }}
        >
          {meta.name}
        </span>
        <span>{new Date(item.timestamp).toLocaleString()}</span>
        <span className="text-[#d1d5db]">·</span>
        <span className="font-mono">
          COST ${item.cost.toFixed(2)} · TOKENS {item.tokens.toLocaleString()} ·{" "}
          {item.latency.toFixed(1)}s
        </span>
      </div>
    </div>
  );
}

function TabBtn({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="relative -mb-px py-2.5 text-[13px] font-medium transition"
      style={{
        color: active ? "#2563eb" : "#6b7280",
        borderBottom: active ? "2px solid #2563eb" : "2px solid transparent",
      }}
    >
      {children}
    </button>
  );
}

function Breakdown({ selected }: { selected: HistoryItem }) {
  const base = selected.cost;
  const isBrute = selected.mode === "A";

  const modeCompare: Record<Mode, { cost: number; latency: number; tokens: number; accuracy: number }> = (() => {
    const real = {
      cost: selected.cost,
      latency: selected.latency,
      tokens: selected.tokens,
      accuracy: selected.mode === "A" ? 0.92 : selected.mode === "B" ? 0.96 : 0.95,
    };
    if (selected.mode === "A") {
      return {
        A: real,
        B: { cost: base / 12, latency: selected.latency / 4, tokens: Math.round(selected.tokens / 4), accuracy: 0.96 },
        C: { cost: base / 6, latency: selected.latency / 2.5, tokens: Math.round(selected.tokens / 3), accuracy: 0.95 },
      };
    }
    if (selected.mode === "B") {
      return {
        A: { cost: base * 12, latency: selected.latency * 4, tokens: selected.tokens * 4, accuracy: 0.92 },
        B: real,
        C: { cost: base * 2, latency: selected.latency * 0.65, tokens: Math.round(selected.tokens * 1.2), accuracy: 0.95 },
      };
    }
    return {
      A: { cost: base * 6, latency: selected.latency * 5, tokens: selected.tokens * 3, accuracy: 0.92 },
      B: { cost: base / 2, latency: selected.latency * 1.5, tokens: Math.round(selected.tokens / 1.2), accuracy: 0.96 },
      C: real,
    };
  })();

  const savings = modeCompare.A.cost - modeCompare[selected.mode].cost;

  const chartData = (Object.keys(AGENT_META) as AgentKey[]).map((k) => ({
    name: AGENT_META[k].label,
    cost: Number(selected.agents[k].cost.toFixed(2)),
    color: AGENT_META[k].color,
  }));

  return (
    <div className="mt-6 space-y-6 pb-10">
      {!isBrute && savings > 0 && (
        <div
          className="rounded-lg border px-4 py-2.5 text-[13px] font-medium"
          style={{ backgroundColor: "#f0fdf4", borderColor: "#bbf7d0", color: "#15803d" }}
        >
          You saved <span className="font-mono">${savings.toFixed(2)}</span> with{" "}
          {MODE_META[selected.mode].name} vs Brute Force
        </div>
      )}

      {/* Comparison table */}
      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="bg-panel text-left text-[11px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-3 font-medium">Metric</th>
              <ColHead label="Brute Force" winner={selected.mode === "A"} />
              <ColHead label="Smart Filter" winner={selected.mode === "B"} check />
              <ColHead label="Parallel" winner={selected.mode === "C"} />
            </tr>
          </thead>
          <tbody>
            <CompareRow
              label="Cost"
              a={`$${modeCompare.A.cost.toFixed(2)}`}
              b={`$${modeCompare.B.cost.toFixed(2)}`}
              c={`$${modeCompare.C.cost.toFixed(2)}`}
              winner={selected.mode}
              alt
            />
            <CompareRow
              label="Latency"
              a={`${modeCompare.A.latency.toFixed(1)}s`}
              b={`${modeCompare.B.latency.toFixed(1)}s`}
              c={`${modeCompare.C.latency.toFixed(1)}s`}
              winner={selected.mode}
            />
            <CompareRow
              label="Tokens"
              a={modeCompare.A.tokens.toLocaleString()}
              b={modeCompare.B.tokens.toLocaleString()}
              c={modeCompare.C.tokens.toLocaleString()}
              winner={selected.mode}
              alt
            />
            <CompareRow
              label="Accuracy"
              a={`${(modeCompare.A.accuracy * 100).toFixed(0)}%`}
              b={`${(modeCompare.B.accuracy * 100).toFixed(0)}%`}
              c={`${(modeCompare.C.accuracy * 100).toFixed(0)}%`}
              winner={selected.mode}
            />
          </tbody>
        </table>
      </div>

      {/* Chart */}
      <div className="rounded-lg border border-border bg-white p-4">
        <div className="mb-3 text-[14px] font-bold text-charcoal">Cost per Agent</div>
        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#f3f4f6" vertical={false} />
              <XAxis dataKey="name" stroke="#9ca3af" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis
                stroke="#9ca3af"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => `$${v}`}
                style={{ fontFamily: "IBM Plex Mono, monospace" }}
              />
              <Tooltip
                cursor={{ fill: "#f8f9fa" }}
                contentStyle={{
                  background: "#fff",
                  border: "1px solid #e5e7eb",
                  borderRadius: 6,
                  fontSize: 12,
                  fontFamily: "IBM Plex Mono, monospace",
                }}
                formatter={(v: any) => [`$${Number(v).toFixed(2)}`, "Cost"]}
              />
              <Bar dataKey="cost" radius={[3, 3, 0, 0]}>
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Agent breakdown */}
      <div className="rounded-lg border border-border bg-white">
        <div className="border-b border-border px-4 py-2 text-[11px] uppercase tracking-wider text-muted-foreground">
          <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr] gap-2">
            <span>Agent</span>
            <span className="text-right">Tokens</span>
            <span className="text-right">Cost</span>
            <span className="text-right">Latency</span>
          </div>
        </div>
        {(Object.keys(AGENT_META) as AgentKey[]).map((k) => {
          const a = selected.agents[k];
          return (
            <div
              key={k}
              className="grid grid-cols-[1.5fr_1fr_1fr_1fr] items-center gap-2 border-b border-[#f3f4f6] px-4 py-2.5 text-[13px] last:border-b-0"
            >
              <span className="flex items-center gap-2 text-charcoal">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: AGENT_META[k].color }} />
                {AGENT_META[k].label}
              </span>
              <span className="text-right font-mono text-charcoal">{a.tokens.toLocaleString()}</span>
              <span className="text-right font-mono text-charcoal">${a.cost.toFixed(2)}</span>
              <span className="text-right font-mono text-charcoal">{a.latency.toFixed(1)}s</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ColHead({ label, winner, check }: { label: string; winner: boolean; check?: boolean }) {
  return (
    <th
      className="px-4 py-3 font-medium"
      style={{
        backgroundColor: winner ? "#eff6ff" : undefined,
        color: winner ? "#2563eb" : undefined,
      }}
    >
      {label} {winner && check && "✓"}
    </th>
  );
}

function CompareRow({
  label,
  a,
  b,
  c,
  winner,
  alt,
}: {
  label: string;
  a: string;
  b: string;
  c: string;
  winner: Mode;
  alt?: boolean;
}) {
  const bg = alt ? "#fafafa" : "#ffffff";
  const cell = (val: string, mode: Mode) => (
    <td
      className="px-4 py-2.5 font-mono"
      style={{
        backgroundColor: winner === mode ? "#eff6ff" : bg,
        color: winner === mode ? "#2563eb" : "#111827",
        fontWeight: winner === mode ? 600 : 400,
      }}
    >
      {val}
    </td>
  );
  return (
    <tr>
      <td className="px-4 py-2.5 text-charcoal" style={{ backgroundColor: bg }}>
        {label}
      </td>
      {cell(a, "A")}
      {cell(b, "B")}
      {cell(c, "C")}
    </tr>
  );
}

function Logs({ selected }: { selected: HistoryItem }) {
  return (
    <div className="mt-6 space-y-2 pb-10">
      {(Object.keys(AGENT_META) as AgentKey[]).map((k) => (
        <LogRow key={k} agentKey={k} state={selected.agents[k]} question={selected.question} />
      ))}
    </div>
  );
}

function LogRow({
  agentKey,
  state,
  question,
}: {
  agentKey: AgentKey;
  state: HistoryItem["agents"][AgentKey];
  question: string;
}) {
  const [open, setOpen] = useState(false);
  const meta = AGENT_META[agentKey];

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-white">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-panel"
      >
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: meta.color }} />
        <span className="text-[13px] font-semibold text-charcoal">{meta.label}</span>
        <span className="font-mono text-[11px] text-[#9ca3af]">
          {state.startedAt ? new Date(state.startedAt).toLocaleTimeString() : "—"}
        </span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">
          {state.tokens.toLocaleString()} tok · ${state.cost.toFixed(2)} · {state.latency.toFixed(1)}s
        </span>
        <ChevronDown
          className="h-4 w-4 text-muted-foreground transition"
          style={{ transform: open ? "rotate(180deg)" : "none" }}
        />
      </button>

      {open && (
        <div className="border-t border-border px-4 py-4">
          <div className="text-[10px] font-medium uppercase tracking-wider text-[#9ca3af]">
            Prompt
          </div>
          <pre className="mt-1.5 whitespace-pre-wrap rounded-md border border-border bg-panel p-3 font-mono text-[12px] text-[#374151]">
{`[system] You are ${meta.label} Agent. Be concise.
[user] ${question}`}
          </pre>

          <div className="mt-3 text-[10px] font-medium uppercase tracking-wider text-[#9ca3af]">
            Response
          </div>
          <pre className="mt-1.5 whitespace-pre-wrap rounded-md border border-border bg-white p-3 font-mono text-[12px] text-[#374151]">
{exampleResponse(agentKey)}
          </pre>

          <div className="mt-2 font-mono text-[11px] text-[#9ca3af]">
            {state.tokens.toLocaleString()} tokens · ${state.cost.toFixed(2)} · {state.latency.toFixed(1)}s
          </div>
        </div>
      )}
    </div>
  );
}

function exampleResponse(k: AgentKey) {
  switch (k) {
    case "planner":
      return "Plan: 1) identify entity column 2) filter unresolved status 3) group + count 4) sort desc 5) limit 5.";
    case "sqlA":
      return "Selected strategy: smart-filter. Estimated reduction: ~92%.\nFilter expression: status='unresolved'";
    case "sqlB":
      return "SELECT company, COUNT(*) FROM complaints WHERE status='unresolved' GROUP BY company ORDER BY 2 DESC LIMIT 5;";
    case "reducer":
      return "Top result: Wells Fargo (4,210). Confidence: high. No anomalies detected.";
  }
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
