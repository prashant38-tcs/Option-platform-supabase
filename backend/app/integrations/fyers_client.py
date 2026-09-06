from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import Settings
from app.core.market_calendar import now_ist_naive
from app.models.fyers_schemas import (
    FyersFundsResponse, FyersOptionChainResponse, FyersPlaceOrderRequest,
    FyersPlaceOrderResponse, FyersAuthSession, FyersMultiLegOrderRequest,
)

logger = logging.getLogger("fyers_client")

BASE_TXN_URL = "https://api-t1.fyers.in/api/v3"
BASE_DATA_URL = "https://api-t1.fyers.in/data"
AUTH_BASE_URL = "https://api-t1.fyers.in/api/v3"

_MAX_RETRIES = 3
_RETRYABLE_STATUS = {500, 502, 503, 504}
_SESSION_HARD_EXPIRY_IST = dtime(23, 59, 0)


class FyersSessionExpiredError(RuntimeError):
    pass


class FyersAPIError(RuntimeError):
    def __init__(self, endpoint: str, code: int, message: str):
        super().__init__(f"Fyers API error at {endpoint}: code={code} message={message}")
        self.endpoint = endpoint
        self.code = code
        self.message = message


class FyersClient:
    def __init__(self, settings: Settings, http_client: Optional[httpx.AsyncClient] = None):
        self._settings = settings
        if http_client is not None:
            self._client = http_client
        else:
            client_kwargs: dict = {"timeout": 15.0}
            if settings.outbound_proxy_url:
                client_kwargs["proxy"] = settings.outbound_proxy_url
                logger.info("FyersClient routing all outbound calls through configured proxy.")
            self._client = httpx.AsyncClient(**client_kwargs)
        self._session: Optional[FyersAuthSession] = None

    async def aclose(self) -> None:
        await self._client.aclose()

    def build_login_url(self, state: str = "state123") -> str:
        if not self._settings.fyers_credentials_present():
            raise ValueError("FYERS_APP_ID / FYERS_SECRET_ID / FYERS_REDIRECT_URI not configured in .env")
        return (
            f"{AUTH_BASE_URL}/generate-authcode"
            f"?client_id={self._settings.fyers_app_id}"
            f"&redirect_uri={self._settings.fyers_redirect_uri}"
            f"&response_type=code&state={state}"
        )

    async def exchange_auth_code_for_token(self, auth_code: str) -> FyersAuthSession:
        import hashlib
        app_id_hash = hashlib.sha256(
            f"{self._settings.fyers_app_id}:{self._settings.fyers_secret_id}".encode()
        ).hexdigest()
        payload = {"grant_type": "authorization_code", "appIdHash": app_id_hash, "code": auth_code}
        resp = await self._client.post(f"{AUTH_BASE_URL}/validate-authcode", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("s") != "ok":
            raise FyersAPIError("validate-authcode", data.get("code", -1), data.get("message", "unknown error"))

        access_token = data["access_token"]
        now = now_ist_naive()
        expiry = datetime.combine(now.date(), _SESSION_HARD_EXPIRY_IST)
        self._session = FyersAuthSession(
            app_id=self._settings.fyers_app_id, access_token=access_token,
            issued_at=now, expires_at_market_close=expiry,
            static_ip_whitelisted=bool(self._settings.fyers_static_ip),
            is_compliant_app=self._settings.fyers_app_id.endswith("200"),
        )
        logger.info("Fyers session established for %s, valid until %s", self._settings.fyers_app_id, expiry)
        return self._session

    def save_session_to_file(self, path: str | Path) -> None:
        if self._session is None:
            raise ValueError("No active session to save -- call exchange_auth_code_for_token() first.")
        path = Path(path)
        if path.is_dir():
            raise ValueError(
                f"Cannot save session: {path} exists but is a directory, not a file "
                f"(common Docker bind-mount artifact when the host file didn't exist "
                f"before `docker compose up` -- create an empty file at that host path first)."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._session.model_dump(mode="json")
        try:
            path.write_text(json.dumps(data, indent=2))
        except OSError as exc:
            raise ValueError(f"Could not write session file to {path}: {exc}") from exc
        try:
            path.chmod(0o600)
        except OSError:
            pass
        logger.info("Fyers session saved to %s", path)

    def load_session_from_file(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        if path.is_dir():
            logger.warning(
                "%s exists but is a directory, not a file (a common Docker "
                "bind-mount artifact when the host file didn't exist yet) -- "
                "treating as no session present.", path,
            )
            return False
        try:
            data = json.loads(path.read_text())
            session = FyersAuthSession(**data)
        except (json.JSONDecodeError, ValueError, TypeError, OSError) as exc:
            logger.warning("Could not parse saved Fyers session at %s (%s) -- ignoring.", path, exc)
            return False

        if not session.is_valid_now(now_ist_naive()):
            logger.info("Saved Fyers session at %s has expired -- daily re-login required.", path)
            return False

        self._session = session
        logger.info("Loaded valid Fyers session from %s (app_id=%s, valid until %s)",
                     path, session.app_id, session.expires_at_market_close)
        return True

    def has_valid_session(self) -> bool:
        return self._session is not None and self._session.is_valid_now(now_ist_naive())

    def _require_valid_session(self) -> FyersAuthSession:
        if self._session is None or not self._session.is_valid_now(now_ist_naive()):
            raise FyersSessionExpiredError(
                "No valid Fyers session for today. Run the daily auth-code flow "
                "(build_login_url -> user logs in -> exchange_auth_code_for_token) first."
            )
        return self._session

    def _auth_header(self) -> dict:
        session = self._require_valid_session()
        return {"Authorization": f"{session.app_id}:{session.access_token}"}

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        headers.update(self._auth_header())

        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.request(method, url, headers=headers, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("Fyers request to %s failed (attempt %d/%d): %s", url, attempt, _MAX_RETRIES, exc)
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if resp.status_code in (401, 403):
                raise FyersSessionExpiredError(
                    f"Fyers rejected token at {url} (status {resp.status_code}). Re-run daily auth flow."
                )
            if resp.status_code in _RETRYABLE_STATUS:
                last_exc = FyersAPIError(url, resp.status_code, resp.text[:300])
                logger.warning("Fyers %s returned %d (attempt %d/%d), retrying", url, resp.status_code, attempt, _MAX_RETRIES)
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            resp.raise_for_status()
            data = resp.json()
            if data.get("s") == "error":
                raise FyersAPIError(url, data.get("code", -1), data.get("message", "unknown error"))
            return data

        raise FyersAPIError(url, -1, f"Exhausted retries. Last error: {last_exc}")

    async def get_funds(self) -> FyersFundsResponse:
        data = await self._request("GET", f"{BASE_TXN_URL}/funds")
        return FyersFundsResponse(**data)

    async def get_option_chain(self, symbol: str, strike_count: int = 20, timestamp: Optional[str] = None) -> FyersOptionChainResponse:
        params = {"symbol": symbol, "strikecount": strike_count}
        if timestamp:
            params["timestamp"] = timestamp
        data = await self._request("GET", f"{BASE_DATA_URL}/options-chain-v3", params=params)
        return FyersOptionChainResponse(**data)

    async def get_history(self, symbol: str, resolution: str, range_from, range_to, date_format: str = "1", cont_flag: str = "1") -> dict:
        params = {"symbol": symbol, "resolution": resolution, "date_format": date_format,
                  "range_from": str(range_from), "range_to": str(range_to), "cont_flag": cont_flag}
        return await self._request("GET", f"{BASE_DATA_URL}/history", params=params)

    async def get_quotes(self, symbols: list[str]) -> dict:
        params = {"symbols": ",".join(symbols)}
        return await self._request("GET", f"{BASE_DATA_URL}/quotes", params=params)

    async def place_order(self, order: FyersPlaceOrderRequest, algo_id_tag: Optional[str] = None) -> FyersPlaceOrderResponse:
        payload = order.model_dump()
        if algo_id_tag:
            payload["orderTag"] = algo_id_tag
        data = await self._request("POST", f"{BASE_TXN_URL}/orders/sync", json=payload)
        return FyersPlaceOrderResponse(**data)

    async def place_multileg_order(self, order: FyersMultiLegOrderRequest) -> dict:
        payload = order.model_dump()
        return await self._request("POST", f"{BASE_TXN_URL}/multileg/orders/sync", json=payload)

    async def get_positions(self) -> dict:
        return await self._request("GET", f"{BASE_TXN_URL}/positions")

    async def exit_all_positions(self) -> dict:
        return await self._request("DELETE", f"{BASE_TXN_URL}/positions", json={"exit_all": 1})
