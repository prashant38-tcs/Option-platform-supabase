"use client";

import { useState, type FormEvent, type ChangeEvent } from "react";
import clsx from "clsx";
import { AlertTriangle } from "lucide-react";
import type { Underlying, TradingMode, UnderlyingScheduleStatus } from "@/lib/types";
import { UNDERLYING_LABELS } from "@/lib/types";
import { setTradingMode, runCycleNow, setCapital } from "@/lib/api";
import ConnectionBadge from "./ConnectionBadge";
import type { ConnectionStatus } from "@/lib/useWebSocket";

const UNDERLYINGS: Underlying[] = ["NIFTY50", "NIFTYBANK", "FINNIFTY", "SENSEX"];
const MODES: TradingMode[] = ["ADVISORY", "PAPER", "LIVE"];
const MODE_STYLES: Record<TradingMode, string> = {
  ADVISORY: "bg-blue-600 hover:bg-blue-500", PAPER: "bg-amber-600 hover:bg-amber-500", LIVE: "bg-red-600 hover:bg-red-500",
};

interface HeaderProps {
  selectedUnderlying: Underlying;
  onSelectUnderlying: (u: Underlying) => void;
  currentMode: TradingMode;
  onModeChanged: (mode: TradingMode) => void;
  connectionStatus: ConnectionStatus;
  schedulerStatus: UnderlyingScheduleStatus | null;
}

export default function Header({ selectedUnderlying, onSelectUnderlying, currentMode, onModeChanged, connectionStatus, schedulerStatus }: HeaderProps) {
  const [capitalInput, setCapitalInput] = useState("");
  const [capitalSaved, setCapitalSaved] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleModeClick(mode: TradingMode) {
    if (mode === "LIVE" && currentMode !== "LIVE") {
      const confirmed = window.confirm(
        "Arming LIVE trading requires the full SEBI compliance checklist to be satisfied on the backend, or every order will be blocked. Continue?",
      );
      if (!confirmed) return;
    }
    setBusy(true);
    try { await setTradingMode(selectedUnderlying, mode); onModeChanged(mode); } finally { setBusy(false); }
  }

  async function handleRunNow() {
    setBusy(true);
    try { await runCycleNow(selectedUnderlying); } finally { setBusy(false); }
  }

  async function handleCapitalSubmit(e: FormEvent) {
    e.preventDefault();
    const value = parseFloat(capitalInput);
    if (!value || value <= 0) return;
    await setCapital(value);
    setCapitalSaved(value);
  }

  return (
    <header className="border-b border-panelborder bg-panel px-6 py-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-gray-100">Options Trading Platform</h1>
          <ConnectionBadge status={connectionStatus} />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <select value={selectedUnderlying} onChange={(e: ChangeEvent<HTMLSelectElement>) => onSelectUnderlying(e.target.value as Underlying)}
            className="rounded-md border border-panelborder bg-background px-3 py-1.5 text-sm text-gray-200">
            {UNDERLYINGS.map((u) => (<option key={u} value={u}>{UNDERLYING_LABELS[u]}</option>))}
          </select>
          <div className="flex overflow-hidden rounded-md border border-panelborder">
            {MODES.map((mode) => (
              <button key={mode} disabled={busy} onClick={() => handleModeClick(mode)}
                className={clsx("px-3 py-1.5 text-xs font-medium text-white transition-colors disabled:opacity-50",
                  currentMode === mode ? MODE_STYLES[mode] : "bg-gray-800 hover:bg-gray-700")}>
                {mode}
              </button>
            ))}
          </div>
          <button onClick={handleRunNow} disabled={busy}
            className="rounded-md border border-panelborder bg-background px-3 py-1.5 text-xs font-medium text-gray-200 hover:bg-gray-800 disabled:opacity-50">
            Run Now
          </button>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-400">
        <span>Market: <span className={schedulerStatus?.is_market_open ? "text-accent" : "text-gray-500"}>
          {schedulerStatus?.is_market_open ? "OPEN" : "CLOSED"}</span>
          {!schedulerStatus?.is_market_open && schedulerStatus?.next_market_open_at && (
            <> · next open {new Date(schedulerStatus.next_market_open_at).toLocaleString("en-IN")}</>)}
        </span>
        <span>Cycles run: {schedulerStatus?.total_cycles_run ?? 0}</span>
        <span className={schedulerStatus && schedulerStatus.total_errors > 0 ? "text-warn" : ""}>
          Errors: {schedulerStatus?.total_errors ?? 0}
        </span>
        <form onSubmit={handleCapitalSubmit} className="ml-auto flex items-center gap-2">
          <label className="text-gray-400">Capital (₹):</label>
          <input type="number" min={1} value={capitalInput} onChange={(e: ChangeEvent<HTMLInputElement>) => setCapitalInput(e.target.value)}
            placeholder="e.g. 500000" className="w-32 rounded-md border border-panelborder bg-background px-2 py-1 text-gray-200" />
          <button type="submit" className="rounded-md bg-accent px-2 py-1 text-black hover:bg-green-400">Set</button>
          {capitalSaved !== null && <span className="text-accent">Saved ₹{capitalSaved.toLocaleString("en-IN")}</span>}
        </form>
      </div>
      {currentMode === "LIVE" && (
        <div className="mt-2 flex items-center gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-xs text-red-300">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          LIVE mode selected -- real orders will only be sent if the backend's SEBI compliance checklist is fully satisfied.
        </div>
      )}
    </header>
  );
}
