from __future__ import annotations
from urllib.parse import urlparse, parse_qs


class AuthCodeParseError(ValueError):
    pass


def extract_auth_code(user_input: str) -> str:
    user_input = user_input.strip()
    if not user_input:
        raise AuthCodeParseError("Empty input -- paste the redirect URL or the bare auth_code.")

    if "://" in user_input or user_input.startswith("?"):
        parsed = urlparse(user_input if "://" in user_input else f"http://x/{user_input}")
        query = parse_qs(parsed.query)
        codes = query.get("auth_code")
        if not codes:
            raise AuthCodeParseError(
                "Could not find an 'auth_code' query parameter in the URL you pasted. "
                "Make sure you copied the FULL redirected URL, including everything after '?'."
            )
        return codes[0]
    return user_input
