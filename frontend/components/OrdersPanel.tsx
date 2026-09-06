"use client";

import clsx from "clsx";
import type { OrderPayload, OrderStatus } from "@/lib/types";

const STATUS_COLOR: Record<OrderStatus, string> = {
  PENDING_RISK_CHECK: "text-gray-400", REJECTED_BY_RISK: "text-amber-400", ADVISORY_ONLY: "text-sky-400",
  SIMULATED_OPEN: "text-emerald-400", SIMULATED_CLOSED: "text-gray-400", SENT_TO_BROKER: "text-emerald-400",
  ACKNOWLEDGED: "text-emerald-400", FILLED: "text-emerald-400", PARTIALLY_FILLED: "text-amber-400",
  CANCELLED: "text-gray-400", BROKER_REJECTED: "text-red-400", ERRORED: "text-red-400",
};

export default function OrdersPanel({ orders }: { orders: OrderPayload[] }) {
  return (
    <div className="rounded-lg border border-panelborder bg-panel">
      <div className="border-b border-panelborder px-4 py-2 text-sm font-medium text-gray-200">Orders / Positions This Cycle</div>
      <div className="max-h-64 overflow-y-auto p-3 text-xs">
        {orders.length === 0 && <div className="p-3 text-center text-gray-500">No orders yet this cycle.</div>}
        <table className="w-full">
          <tbody>
            {orders.map((o) => (
              <tr key={o.order_id} className="border-b border-panelborder/50">
                <td className="py-1.5 pr-2 text-gray-400">{o.symbol}</td>
                <td className="py-1.5 pr-2 text-gray-400">{o.quantity}</td>
                <td className={clsx("py-1.5 pr-2 font-medium", STATUS_COLOR[o.status])}>{o.status}</td>
                <td className="py-1.5 text-gray-500">{o.error_message ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
