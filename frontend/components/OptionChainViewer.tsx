"use client";

import clsx from "clsx";
import type { OptionChainPayload } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

export default function OptionChainViewer({ data }: { data: OptionChainPayload | null }) {
  if (!data) {
    return <div className="rounded-lg border border-panelborder bg-panel p-6 text-center text-sm text-gray-500">
      No option chain data yet -- waiting for the first cycle to complete.</div>;
  }
  return (
    <div className="rounded-lg border border-panelborder bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-panelborder px-4 py-2">
        <div className="text-sm font-medium text-gray-200">Live Option Chain</div>
        <div className="flex flex-wrap gap-4 text-xs text-gray-400">
          <span>Spot: <span className="font-semibold text-gray-100">{data.spot.toFixed(2)}</span></span>
          <span>ATM: <span className="font-semibold text-gray-100">{data.atm_strike ?? "--"}</span></span>
          {data.india_vix !== null && <span>India VIX: <span className="font-semibold text-gray-100">{data.india_vix.toFixed(2)}</span></span>}
          {data.put_call_ratio_oi !== null && <span>PCR (OI): <span className="font-semibold text-gray-100">{data.put_call_ratio_oi.toFixed(2)}</span></span>}
          <span>Expiry: {formatDateTime(data.expiry)}</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-panel text-gray-400">
            <tr className="border-b border-panelborder">
              <th className="px-2 py-2 text-right">OI</th><th className="px-2 py-2 text-right">IV%</th>
              <th className="px-2 py-2 text-right">Delta</th><th className="px-2 py-2 text-right">LTP</th>
              <th className="bg-gray-900/60 px-3 py-2 text-center font-semibold">Strike</th>
              <th className="px-2 py-2 text-right">LTP</th><th className="px-2 py-2 text-right">Delta</th>
              <th className="px-2 py-2 text-right">IV%</th><th className="px-2 py-2 text-right">OI</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => {
              const isAtm = row.strike === data.atm_strike;
              return (
                <tr key={row.strike} className={clsx("border-b border-panelborder/50", isAtm && "bg-emerald-500/5")}>
                  <td className="px-2 py-1 text-right text-gray-400">{row.call ? formatOI(row.call.oi) : "--"}</td>
                  <td className="px-2 py-1 text-right text-gray-400">{row.call ? (row.call.iv * 100).toFixed(1) : "--"}</td>
                  <td className="px-2 py-1 text-right text-gray-400">{row.call ? row.call.delta.toFixed(2) : "--"}</td>
                  <td className="px-2 py-1 text-right font-medium text-emerald-400">{row.call ? row.call.ltp.toFixed(2) : "--"}</td>
                  <td className={clsx("bg-gray-900/60 px-3 py-1 text-center font-semibold", isAtm && "text-accent")}>{row.strike}</td>
                  <td className="px-2 py-1 text-right font-medium text-red-400">{row.put ? row.put.ltp.toFixed(2) : "--"}</td>
                  <td className="px-2 py-1 text-right text-gray-400">{row.put ? row.put.delta.toFixed(2) : "--"}</td>
                  <td className="px-2 py-1 text-right text-gray-400">{row.put ? (row.put.iv * 100).toFixed(1) : "--"}</td>
                  <td className="px-2 py-1 text-right text-gray-400">{row.put ? formatOI(row.put.oi) : "--"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatOI(oi: number): string {
  if (oi >= 100000) return `${(oi / 100000).toFixed(1)}L`;
  if (oi >= 1000) return `${(oi / 1000).toFixed(1)}K`;
  return String(oi);
}
