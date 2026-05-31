import type { Status } from "@/store/useQueryStore";

const COLORS: Record<Status, string> = {
  idle: "#9ca3af",
  pending: "#9ca3af",
  running: "#2563eb",
  done: "#16a34a",
  error: "#dc2626",
};

export function StatusDot({ status, className = "" }: { status: Status; className?: string }) {
  const color = COLORS[status];
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${status === "running" ? "pulse-dot" : ""} ${className}`}
      style={{ backgroundColor: color }}
    />
  );
}
