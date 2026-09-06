import clsx from "clsx";
import type { ConnectionStatus } from "@/lib/useWebSocket";

const LABELS: Record<ConnectionStatus, string> = {
  connecting: "Connecting…", open: "Live", reconnecting: "Reconnecting…", closed: "Disconnected",
};
const DOT_COLOR: Record<ConnectionStatus, string> = {
  connecting: "bg-yellow-400", open: "bg-accent", reconnecting: "bg-yellow-400 animate-pulse", closed: "bg-danger",
};

export default function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  return (
    <div className="flex items-center gap-2 text-xs text-gray-400">
      <span className={clsx("h-2 w-2 rounded-full", DOT_COLOR[status])} />
      {LABELS[status]}
    </div>
  );
}
