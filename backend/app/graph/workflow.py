from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional, Any

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from app.core.llm_router import LLMRouter
from app.core.volatility_analytics import IVHistoryBuffer
from app.core.position_store import PositionStore
from app.integrations.fyers_client import FyersClient
from app.integrations.moneycontrol_rss import MoneycontrolRSSClient
from app.agents.data_ingestion_agent import DataIngestionAgent, data_ingestion_node
from app.agents.sentiment_agent import SentimentAgent, sentiment_node
from app.agents.quant_analytics_agent import QuantAnalyticsAgent, quant_analytics_node
from app.agents.risk_manager_agent import RiskManagerAgent, risk_manager_node
from app.agents.execution_agent import ExecutionAgent, execution_node
from app.agents.performance_tracker import PerformanceTracker
from app.models.agent_state import TradingWorkflowState
from app.models.quant_config import QuantAgentConfig
from app.models.risk_schemas import RiskAgentConfig, LiveComplianceChecklist

logger = logging.getLogger("workflow_graph")


@dataclass
class WorkflowAgents:
    data_ingestion: DataIngestionAgent
    sentiment: SentimentAgent
    quant: QuantAnalyticsAgent
    risk: RiskManagerAgent
    execution: ExecutionAgent
    iv_history: IVHistoryBuffer
    position_store: PositionStore


def build_graph():
    graph = StateGraph(TradingWorkflowState)

    async def _data_ingestion(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await data_ingestion_node(state, agents.data_ingestion)

    async def _sentiment(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await sentiment_node(state, agents.sentiment)

    async def _quant(state: TradingWorkflowState, config: RunnableConfig) -> TradingWorkflowState:
        agents: WorkflowAgents = config["configurable"]["agents"]
        return await quant_analytics_node(state, agents.
