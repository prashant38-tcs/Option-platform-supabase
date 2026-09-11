from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

from .enums import FyersOrderSide, FyersOrderType, FyersProductType, FyersValidity


class FyersResponseEnvelope(BaseModel):
    s: Literal["ok", "error"]
    code: int
    message: str = ""


class FyersFundLimitItem(BaseModel):
    id: int
    title: str
    equityAmount: float = 0.0
    commodityAmount: float = 0.0

    @property
    def total_amount(self) -> float:
        return self.equityAmount + self.commodityAmount


class FyersFundsResponse(FyersResponseEnvelope):
    fund_limit: list[FyersFundLimitItem] = Field(default_factory=list)

    def available_balance(self) -> float:
        for item in self.fund_limit:
            if item.id == 10:
                return item.total_amount
        return 0.0

    def utilized_margin(self) -> float:
        for item in self.fund_limit:
            if item.id == 2:
                return item.total_amount
        return 0.0


class FyersOptionGreeksRaw(BaseModel):
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None


class FyersIndiaVixData(BaseModel):
    ltp: Optional[float] = None
    ch: Optional[float] = None
    chp: Optional[float] = None


class FyersOptionChainLeg(BaseModel):
    symbol: str
    strike_price: float
    option_type: str = ""
    ltp: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    oi: int = 0
    oich: float = 0.0
    oichp: float = 0.0
    volume: int = 0
    greeks: Optional[FyersOptionGreeksRaw] = None

    @field_validator("option_type")
    @classmethod
    def _normalize_option_type(cls, v: str) -> str:
        return (v or "").upper().strip()

    def is_underlying_row(self) -> bool:
        return self.option_type == ""

class FyersOptionChainData(BaseModel):
    optionsChain: list[FyersOptionChainLeg] = Field(default_factory=list)
    indiavixData: Optional[FyersIndiaVixData] = None
    expiryData: list[dict] = Field(default_factory=list)
    callOi: int = 0
    putOi: int = 0


class FyersOptionChainResponse(FyersResponseEnvelope):
    data: FyersOptionChainData = Field(default_factory=FyersOptionChainData)


class FyersPlaceOrderRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    symbol: str
    qty: int = Field(gt=0)
    type: FyersOrderType
    side: FyersOrderSide
    productType: FyersProductType
    limitPrice: float = 0.0
    stopPrice: float = 0.0
    validity: FyersValidity = FyersValidity.DAY
    disclosedQty: int = 0
    offlineOrder: bool = False
    stopLoss: float = 0.0
    takeProfit: float = 0.0
    orderTag: Optional[str] = None


class FyersMultiLegOrderLeg(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    symbol: str
    qty: int = Field(gt=0)
    side: FyersOrderSide
    type: FyersOrderType
    limitPrice: float = 0.0
    productType: FyersProductType = FyersProductType.MARGIN


class FyersMultiLegOrderRequest(BaseModel):
    orderTag: Optional[str] = None
    legs: list[FyersMultiLegOrderLeg] = Field(min_length=1, max_length=10)


class FyersPlaceOrderResponse(FyersResponseEnvelope):
    id: Optional[str] = None


class FyersAuthSession(BaseModel):
    app_id: str
    access_token: Optional[str] = None
    issued_at: Optional[datetime] = None
    expires_at_market_close: Optional[datetime] = None
    static_ip_whitelisted: bool = False
    is_compliant_app: bool = False

    def is_valid_now(self, now: datetime) -> bool:
        if not self.access_token or not self.expires_at_market_close:
            return False
        return now < self.expires_at_market_close
