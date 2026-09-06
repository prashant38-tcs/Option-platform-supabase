"use client";

import clsx from "clsx";
import type { SignalPayload } from "@/lib/types";
import { formatCurrency } from "@/lib/format";

export default function SignalsPanel({ signals }: { signals: SignalPayload[] }) {
  return (
    <div className="rounded-lg border border-panelborder bg-panel">
      <div className="border-b border-panelborder px-4 py-2 text-sm font-medium text-gray-200">Candidate Strategies This Cycle</div>
      <div className="max-h-80 overflow-y-auto p-3">
        {signals.length === 0 && <div className="p-3 text-center text-xs text-gray-500">No candidates yet.</div>}
        <div className="space-y-2">
          {signals.map((sig) => (
            <div key={sig.signal_id} className="rounded-md border border-panelborder bg-background p-3 text-xs">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-semibold text-gray-100">{sig.strategy_type.replace(/_/g, " ")}</span>
                <span className={clsx("rounded px-1.5 py-0.5 text-[10px] font-medium",
                  sig.risk_category === "DEFINED_RISK" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400")}>
                  {sig.risk_category === "DEFINED_RISK" ? "Defined Risk" : "Undefined Risk (Naked)"}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-gray-400">
                <span>Net premium: <span className="text-gray-200">{formatCurrency(sig.net_premium)}</span></span>
                <span>Max loss: <span className="text-gray-200">{sig.max_loss_estimate !== null ? formatCurrency(sig.max_loss_estimate) : "Unlimited"}</span></span>
                <span>Max profit: <span className="text-gray-200">{sig.max_profit_estimate !== null ? formatCurrency(sig.max_profit_estimate) : "Unlimited"}</span></span>
              </div>
              {sig.confidence_score !== null && <div className="mt-1 text-gray-400">Confidence score: <span className="text-gray-200">{sig.confidence_score.toFixed(2)}</span></div>}
              {sig.performance_note && <div className="mt-1 italic text-gray-500">{sig.performance_note}</div>}
              <div className="mt-1 text-gray-500">{sig.rationale}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
