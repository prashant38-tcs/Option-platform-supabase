#!/usr/bin/env python
"""Daily Fyers authentication CLI -- for LOCAL development only (writes
directly to the local backend process's disk). For a deployed backend
(Render, etc.), use GET /api/fyers/login-url + POST /api/fyers/exchange
instead -- see the deployment guide."""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings
from app.core.fyers_auth_helpers import extract_auth_code, AuthCodeParseError
from app.integrations.fyers_client import FyersClient, FyersAPIError

DEFAULT_SESSION_FILE = Path(__file__).resolve().parent.parent / ".fyers_session.json"


async def run_login_flow(session_file: Path = DEFAULT_SESSION_FILE) -> None:
    settings = get_settings()

    if not settings.fyers_credentials_present():
        print("ERROR: FYERS_APP_ID / FYERS_SECRET_ID / FYERS_REDIRECT_URI are not fully configured in your .env file.")
        sys.exit(1)

    client = FyersClient(settings)

    if client.load_session_from_file(session_file):
        print(f"A still-valid session already exists at {session_file} for today -- no login needed.")
        proceed = input("Log in again anyway and overwrite it? [y/N]: ").strip().lower()
        if proceed != "y":
            print("Keeping existing session. Done.")
            await client.aclose()
            return

    login_url = client.build_login_url()
    print()
    print("=" * 70)
    print("STEP 1: Open this URL in your browser and log in to Fyers:")
    print(f"    {login_url}")
    print("STEP 2: Copy the FULL redirected URL after completing login + 2FA.")
    print("=" * 70)
    print()

    user_input = input("Paste the full redirected URL (or just the auth_code) here: ")

    try:
        auth_code = extract_auth_code(user_input)
    except AuthCodeParseError as exc:
        print(f"ERROR: {exc}")
        await client.aclose()
        sys.exit(1)

    try:
        session = await client.exchange_auth_code_for_token(auth_code)
    except FyersAPIError as exc:
        print(f"ERROR: Fyers rejected the auth_code exchange -- {exc}")
        await client.aclose()
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Unexpected failure during token exchange -- {exc}")
        await client.aclose()
        sys.exit(1)

    client.save_session_to_file(session_file)

    print()
    print("SUCCESS -- session established and saved.")
    print(f"  App ID: {session.app_id} | Compliant App: {session.is_compliant_app} | "
          f"Static IP whitelisted: {session.static_ip_whitelisted}")
    print(f"  Valid until (IST): {session.expires_at_market_close}")
    print(f"  Saved to: {session_file}")

    await client.aclose()


def main() -> None:
    asyncio.run(run_login_flow())


if __name__ == "__main__":
    main()
