"use client";

import clsx from "clsx";
import type { SentimentPayload } from "@/lib/types";

const REGIME_COLOR: Record<string, string> = {
  BULLISH: "text-emerald-400", BEARISH: "text-red-400", NEUTRAL_RANGE_BOUND: "text-gray-300",
  HIGH_VOLATILITY: "text-amber-400", LOW_VOLATILITY: "text-sky-400",
};

export default function SentimentPanel({ sentiment }: { sentiment: SentimentPayload | null }) {
  if (!sentiment) {
    return <div className="rounded-lg border border-panelborder bg-panel p-4 text-xs text-gray-500">No sentiment data yet.</div>;
  }
  const scorePct = ((sentiment.sentiment_score + 1) / 2) * 100;
  return (
    <div className="rounded-lg border border-panelborder bg-panel p-4">
      <div className="mb-2 text-sm font-medium text-gray-200">Market Sentiment</div>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="text-gray-400">Score</span>
        <span className={clsx("font-semibold", sentiment.sentiment_score > 0.1 ? "text-emerald-400" : sentiment.sentiment_score < -0.1 ? "text-red-400" : "text-gray-300")}>
          {sentiment.sentiment_score >= 0 ? "+" : ""}{sentiment.sentiment_score.toFixed(2)}
        </span>
      </div>
      <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
        <div className={clsx("h-full", sentiment.sentiment_score > 0.1 ? "bg-emerald-500" : sentiment.sentiment_score < -0.1 ? "bg-red-500" : "bg-gray-500")}
          style={{ width: `${scorePct}%` }} />
      </div>
      <div className="mb-2 text-xs">Regime: <span className={clsx("font-semibold", REGIME_COLOR[sentiment.market_regime] ?? "text-gray-300")}>{sentiment.market_regime.replace(/_/g, " ")}</span></div>
      <div className="text-xs text-gray-400">{sentiment.rationale}</div>
      <div className="mt-2 text-[10px] text-gray-600">via {sentiment.llm_provider_used}</div>
    </div>
  );
}
