"""
Manual smoke test for NORTH authentication.

This is intentionally NOT a unit test. It requires the API server to be running.
Credentials are provided via environment variables to avoid hardcoding secrets.

Environment:
  - NORTH_API_URL (optional, default: http://localhost:8000)
  - NORTH_SMOKE_EMAIL (required; must be authorized/whitelisted)
  - NORTH_SMOKE_PASSWORD (required)
  - NORTH_SMOKE_FULL_NAME (optional)
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

import requests


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing required env var: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def _mask(value: str, keep: int = 12) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "..."


def _post_json(url: str, payload: Dict[str, Any], timeout_s: int = 30) -> requests.Response:
    return requests.post(url, json=payload, timeout=timeout_s)


def main() -> int:
    api_url = os.getenv("NORTH_API_URL", "http://localhost:8000").rstrip("/")
    email = _require_env("NORTH_SMOKE_EMAIL")
    password = _require_env("NORTH_SMOKE_PASSWORD")
    full_name = os.getenv("NORTH_SMOKE_FULL_NAME") or None

    print(f"API: {api_url}")
    print("Checking whitelist...")
    try:
        whitelist_res = requests.post(
            f"{api_url}/api/auth/check-email",
            params={"email": email},
            timeout=10,
        )
        if whitelist_res.ok:
            authorized = whitelist_res.json().get("authorized")
            print(f"Authorized: {authorized}")
            if not authorized:
                print("Email is not authorized; update `config/authorized_users.json` and retry.")
                return 1
        else:
            print(f"Whitelist check failed: {whitelist_res.status_code} {whitelist_res.text}")
    except requests.RequestException as e:
        print(f"Whitelist check request failed: {e}", file=sys.stderr)
        return 1

    print("Attempting sign-in...")
    signin_res = _post_json(
        f"{api_url}/api/auth/signin",
        {"email": email, "password": password},
    )

    token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None

    if signin_res.ok:
        signin_data = signin_res.json()
        token = signin_data.get("access_token") or None
        user = signin_data.get("user") or None
        print("Sign-in: OK")
    else:
        print(f"Sign-in failed: {signin_res.status_code} {signin_res.text}")
        print("Attempting sign-up (may require email verification)...")
        signup_payload: Dict[str, Any] = {"email": email, "password": password}
        if full_name:
            signup_payload["full_name"] = full_name
        signup_res = _post_json(f"{api_url}/api/auth/signup", signup_payload)
        if not signup_res.ok:
            print(f"Sign-up failed: {signup_res.status_code} {signup_res.text}")
            return 1

        signup_data = signup_res.json()
        token = signup_data.get("access_token") or None
        user = signup_data.get("user") or None
        print("Sign-up: OK")
        if not token:
            print("No access token returned (likely email verification required).")
            return 0

    if token:
        print(f"Access token: {_mask(token)}")

    if token:
        print("Calling /api/auth/me...")
        me_res = requests.get(
            f"{api_url}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        print(f"/api/auth/me: {me_res.status_code}")
        if me_res.ok:
            print("OK")
        else:
            print(me_res.text)

    if user:
        print(f"User: {user.get('email')} ({user.get('id')})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

