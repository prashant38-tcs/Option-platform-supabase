"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { getWebSocketUrl } from "./api";
import type {
  Underlying, WSMessage, AgentLogEntry, OptionChainPayload, SentimentPayload,
  SignalPayload, OrderPayload, UnderlyingScheduleStatus,
} from "./types";

const MAX_LOG_ENTRIES = 300;
const MAX_RECONNECT_DELAY_MS = 15_000;
const BASE_RECONNECT_DELAY_MS = 1_000;

export type ConnectionStatus = "connecting" | "open" | "closed" | "reconnecting";

export interface CycleWebSocketState {
  status: ConnectionStatus;
  logs: AgentLogEntry[];
  optionChain: OptionChainPayload | null;
  sentiment: SentimentPayload | null;
  signals: SignalPayload[];
  orders: OrderPayload[];
  schedulerStatus: UnderlyingScheduleStatus | null;
  lastCycleStatus: string | null;
}

export function useCycleWebSocket(underlying: Underlying): CycleWebSocketState {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [optionChain, setOptionChain] = useState<OptionChainPayload | null>(null);
  const [sentiment, setSentiment] = useState<SentimentPayload | null>(null);
  const [signals, setSignals] = useState<SignalPayload[]>([]);
  const [orders, setOrders] = useState<OrderPayload[]>([]);
  const [schedulerStatus, setSchedulerStatus] = useState<UnderlyingScheduleStatus | null>(null);
  const [lastCycleStatus, setLastCycleStatus] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedByEffectRef = useRef(false);

  const handleMessage = useCallback((raw: MessageEvent) => {
    let msg: WSMessage;
    try { msg = JSON.parse(raw.data); } catch { return; }

    switch (msg.type) {
      case "connected": setSchedulerStatus(msg.scheduler_status); break;
      case "cycle_started": setLogs([]); setSignals([]); setOrders([]); break;
      case "log":
        setLogs((prev) => {
          const next = [...prev, msg.data];
          return next.length > MAX_LOG_ENTRIES ? next.slice(next.length - MAX_LOG_ENTRIES) : next;
        });
        break;
      case "option_chain": setOptionChain(msg.data); break;
      case "sentiment": setSentiment(msg.data); break;
      case "signals": setSignals(msg.data); break;
      case "orders": setOrders(msg.data); break;
      case "cycle_finished": setLastCycleStatus(msg.cycle_status); break;
      case "cycle_summary": setLastCycleStatus(msg.data.cycle_status); break;
      case "cycle_error":
        setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), agent_name: "Scheduler",
          message: `Cycle error: ${msg.message}`, level: "error", llm_provider_used: null }]);
        break;
    }
  }, []);

  useEffect(() => {
    closedByEffectRef.current = false;
    reconnectAttemptRef.current = 0;

    function connect() {
      if (closedByEffectRef.current) return;
      setStatus(reconnectAttemptRef.current === 0 ? "connecting" : "reconnecting");

      const ws = new WebSocket(getWebSocketUrl(underlying));
      wsRef.current = ws;

      ws.onopen = () => { reconnectAttemptRef.current = 0; setStatus("open"); };
      ws.onmessage = handleMessage;
      ws.onclose = () => {
        if (closedByEffectRef.current) { setStatus("closed"); return; }
        setStatus("reconnecting");
        const delay = Math.min(BASE_RECONNECT_DELAY_MS * 2 ** reconnectAttemptRef.current, MAX_RECONNECT_DELAY_MS);
        reconnectAttemptRef.current += 1;
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
      ws.onerror = () => { ws.close(); };
    }

    connect();

    return () => {
      closedByEffectRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [underlying, handleMessage]);

  return { status, logs, optionChain, sentiment, signals, orders, schedulerStatus, lastCycleStatus };
}
