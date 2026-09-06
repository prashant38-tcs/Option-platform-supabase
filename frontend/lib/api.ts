import type { SchedulerStatus, CycleSummary, FyersSessionStatus, Underlying, TradingMode } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`API error ${resp.status} on ${path}: ${text}`);
  }
  return resp.json() as Promise<T>;
}

export function getUnderlyings(): Promise<Underlying[]> {
  return jsonFetch<Underlying[]>("/api/underlyings");
}

export function getSchedulerStatus(): Promise<SchedulerStatus> {
  return jsonFetch<SchedulerStatus>("/api/scheduler/status");
}

export function getRecentCycles(underlying: Underlying, limit = 20): Promise<CycleSummary[]> {
  return jsonFetch<CycleSummary[]>(`/api/scheduler/cycles/${underlying}?limit=${limit}`);
}

export function setTradingMode(underlying: Underlying, mode: TradingMode): Promise<{ underlying: string; mode: string }> {
  return jsonFetch(`/api/scheduler/mode/${underlying}`, { method: "POST", body: JSON.stringify({ mode }) });
}

export function runCycleNow(underlying: Underlying): Promise<CycleSummary> {
  return jsonFetch<CycleSummary>(`/api/scheduler/run-now/${underlying}`, { method: "POST" });
}

export function setCapital(capital: number): Promise<{ capital: number }> {
  return jsonFetch("/api/capital", { method: "POST", body: JSON.stringify({ capital }) });
}

export function getFyersSessionStatus(): Promise<FyersSessionStatus> {
  return jsonFetch<FyersSessionStatus>("/api/fyers/session-status");
}

export function getWebSocketUrl(underlying: Underlying): string {
  const wsBase = API_BASE.replace(/^http/, "ws");
  return `${wsBase}/ws/cycles/${underlying}`;
}
