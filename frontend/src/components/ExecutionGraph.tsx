import { AGENT_META, useQueryStore, type AgentKey } from "@/store/useQueryStore";

const STATUS_COLORS: Record<string, string> = {
  idle: "#d1d5db",
  pending: "#d1d5db",
  running: "#2563eb",
  done: "#16a34a",
  error: "#dc2626",
};

function StatusDot({ status }: { status: string }) {
  return (
    <span
      className={`inline-block h-2.5 w-2.5 rounded-full ${status === "running" ? "pulse-dot" : ""}`}
      style={{ backgroundColor: STATUS_COLORS[status] || "#d1d5db" }}
    />
  );
}

function AgentNode({ agentKey }: { agentKey: AgentKey }) {
  const a = useQueryStore((s) => s.agents[agentKey]);
  const meta = AGENT_META[agentKey];
  const running = a.status === "running";
  const done = a.status === "done";

  return (
    <div
      className="relative w-[220px] rounded-[10px] border bg-white px-4 py-3 transition"
      style={{
        borderColor: running ? "#2563eb" : "#e5e7eb",
        backgroundColor: running ? "#eff6ff" : "#ffffff",
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[14px] font-semibold text-charcoal">{meta.label}</span>
        <StatusDot status={a.status} />
      </div>
      {done && (
        <div className="mt-1 font-mono text-[11px] text-muted-foreground">
          {a.tokens.toLocaleString()} tok · ${a.cost.toFixed(2)} · {a.latency.toFixed(1)}s
        </div>
      )}
      {running && (
        <div className="mt-1 font-mono text-[11px] text-primary">running…</div>
      )}
      {a.status === "idle" && (
        <div className="mt-1 font-mono text-[11px] text-muted-foreground">pending</div>
      )}
    </div>
  );
}

function Connector({ active }: { active: boolean }) {
  return (
    <div
      className="w-px"
      style={{ height: 28, backgroundColor: active ? "#2563eb" : "#e5e7eb" }}
    />
  );
}

const TOOLS = ["Filter", "Aggregator", "Joiner"];

export function ExecutionGraph() {
  const agents = useQueryStore((s) => s.agents);
  const executorActive = agents.sqlB.status !== "idle";

  const totalLatency = Math.max(
    1,
    Object.values(agents).reduce((s, a) => s + (a.latency || 0), 0),
  );

  return (
    <div className="flex flex-col">
      <div className="flex flex-col items-center py-6">
        <AgentNode agentKey="planner" />
        <Connector active={agents.planner.status === "done"} />
        <AgentNode agentKey="sqlA" />
        <Connector active={agents.sqlA.status === "done"} />
        <AgentNode agentKey="sqlB" />
        <div className="mt-3 flex gap-2">
          {TOOLS.map((t) => {
            const lit = executorActive && agents.sqlB.status !== "idle";
            return (
              <span
                key={t}
                className="rounded-full border px-2.5 py-0.5 text-[11px]"
                style={{
                  borderColor: lit ? "#2563eb" : "#e5e7eb",
                  color: lit ? "#2563eb" : "#6b7280",
                  backgroundColor: lit ? "#eff6ff" : "#ffffff",
                }}
              >
                {t}
              </span>
            );
          })}
        </div>
        <Connector active={agents.sqlB.status === "done"} />
        <AgentNode agentKey="reducer" />
      </div>

      <div className="mt-6 rounded-[10px] border border-border bg-white p-4">
        <div className="label-eyebrow mb-3">Execution Timeline</div>
        <div className="space-y-2.5">
          {(Object.keys(AGENT_META) as AgentKey[]).map((k) => {
            const a = agents[k];
            const width = a.latency ? Math.max(4, (a.latency / totalLatency) * 100) : 0;
            return (
              <div key={k} className="flex items-center gap-3">
                <div className="w-24 text-[12px] text-body">{AGENT_META[k].label}</div>
                <div className="relative h-2.5 flex-1 rounded-sm bg-[#f3f4f6]">
                  <div
                    className="absolute left-0 top-0 h-2.5 rounded-sm transition-all"
                    style={{
                      width: `${width}%`,
                      backgroundColor: AGENT_META[k].color,
                      opacity: a.status === "done" ? 0.85 : a.status === "running" ? 0.5 : 0.15,
                    }}
                  />
                </div>
                <div className="w-14 text-right font-mono text-[11px] text-muted-foreground">
                  {a.latency ? `${a.latency.toFixed(1)}s` : "—"}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
