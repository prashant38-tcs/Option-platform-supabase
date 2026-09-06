"use client";

import { useEffect, useRef } from "react";
import clsx from "clsx";
import type { AgentLogEntry } from "@/lib/types";
import { formatTime } from "@/lib/format";

const LEVEL_COLOR: Record<AgentLogEntry["level"], string> = {
  info: "text-gray-300", warning: "text-amber-400", error: "text-red-400", decision: "text-emerald-400",
};
const AGENT_COLOR: Record<string, string> = {
  DataIngestionAgent: "text-sky-400", SentimentAgent: "text-purple-400", QuantAnalyticsAgent: "text-cyan-400",
  RiskManagerAgent: "text-orange-400", ExecutionAgent: "text-pink-400", Scheduler: "text-gray-400",
};

export default function AgentReasoningFeed({ logs }: { logs: AgentLogEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs.length]);

  return (
    <div className="flex h-full flex-col rounded-lg border border-panelborder bg-panel">
      <div className="border-b border-panelborder px-4 py-2 text-sm font-medium text-gray-200">Live Agent Reasoning</div>
      <div className="mono flex-1 overflow-y-auto px-4 py-2 text-xs leading-relaxed" style={{ maxHeight: 420 }}>
        {logs.length === 0 && <div className="text-gray-500">Waiting for the next cycle…</div>}
        {logs.map((entry, i) => (
          <div key={i} className="mb-0.5 flex gap-2">
            <span className="shrink-0 text-gray-600">{formatTime(entry.timestamp)}</span>
            <span className={clsx("shrink-0 font-semibold", AGENT_COLOR[entry.agent_name] ?? "text-gray-400")}>[{entry.agent_name}]</span>
            <span className={LEVEL_COLOR[entry.level]}>{entry.message}</span>
            {entry.llm_provider_used && <span className="shrink-0 rounded bg-gray-800 px-1 text-[10px] text-gray-400">{entry.llm_provider_used}</span>}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
