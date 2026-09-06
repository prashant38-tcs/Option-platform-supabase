"use client";

import { useState } from "react";
import Header from "@/components/Header";
import AgentReasoningFeed from "@/components/AgentReasoningFeed";
import OptionChainViewer from "@/components/OptionChainViewer";
import SignalsPanel from "@/components/SignalsPanel";
import OrdersPanel from "@/components/OrdersPanel";
import SentimentPanel from "@/components/SentimentPanel";
import { useCycleWebSocket } from "@/lib/useWebSocket";
import type { Underlying, TradingMode } from "@/lib/types";

export default function DashboardPage() {
  const [underlying, setUnderlying] = useState<Underlying>("NIFTY50");
  const [tradingMode, setTradingMode] = useState<TradingMode>("ADVISORY");
  const ws = useCycleWebSocket(underlying);

  return (
    <div className="flex min-h-screen flex-col">
      <Header selectedUnderlying={underlying} onSelectUnderlying={setUnderlying}
        currentMode={ws.schedulerStatus?.trading_mode ?? tradingMode} onModeChanged={setTradingMode}
        connectionStatus={ws.status} schedulerStatus={ws.schedulerStatus} />
      <main className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <OptionChainViewer data={ws.optionChain} />
          <AgentReasoningFeed logs={ws.logs} />
        </div>
        <div className="space-y-4">
          <SentimentPanel sentiment={ws.sentiment} />
          <SignalsPanel signals={ws.signals} />
          <OrdersPanel orders={ws.orders} />
        </div>
      </main>
      <footer className="border-t border-panelborder px-6 py-3 text-center text-[11px] text-gray-600">
        Educational/personal-use platform. Not investment advice. NSE index options only.
        Advisory and Paper modes place no real orders. Live mode requires full SEBI compliance setup on the backend.
      </footer>
    </div>
  );
}
