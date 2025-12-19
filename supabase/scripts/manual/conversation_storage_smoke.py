"""
Manual smoke test for conversation persistence (API + Supabase).

This is intentionally NOT a unit test. It requires:
  1) The NORTH API server to be running
  2) Supabase credentials (service key) in environment variables

Environment:
  - NORTH_API_URL (optional, default: http://localhost:8000)
  - NORTH_SMOKE_EMAIL (required; must be authorized/whitelisted)
  - NORTH_SMOKE_PASSWORD (required)
  - SUPABASE_URL (required)
  - SUPABASE_SERVICE_KEY (required)
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

import requests
from supabase import create_client


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing required env var: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def main() -> int:
    api_url = os.getenv("NORTH_API_URL", "http://localhost:8000").rstrip("/")
    email = _require_env("NORTH_SMOKE_EMAIL")
    password = _require_env("NORTH_SMOKE_PASSWORD")
    supabase_url = _require_env("SUPABASE_URL")
    supabase_service_key = _require_env("SUPABASE_SERVICE_KEY")

    signin = requests.post(
        f"{api_url}/api/auth/signin",
        json={"email": email, "password": password},
        timeout=30,
    )
    if not signin.ok:
        print(f"Sign-in failed: {signin.status_code} {signin.text}")
        return 1

    auth_data: Dict[str, Any] = signin.json()
    token = auth_data["access_token"]
    user_id = auth_data["user"]["id"]

    chat = requests.post(
        f"{api_url}/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "Smoke test: store a conversation row"},
        timeout=120,
    )
    if not chat.ok:
        print(f"Chat request failed: {chat.status_code} {chat.text}")
        return 1

    supabase = create_client(supabase_url, supabase_service_key)
    rows = (
        supabase.table("conversations")
        .select("conversation_id,created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )

    count = len(rows.data or [])
    print(f"Recent conversation rows for user {user_id}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

