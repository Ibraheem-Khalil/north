"""
Manual helper to upsert a user profile row via Supabase service role key.

This is intentionally NOT a unit test.

Environment:
  - SUPABASE_URL (required)
  - SUPABASE_SERVICE_KEY (required)
  - NORTH_USER_ID (required)
  - NORTH_USER_EMAIL (required)
  - NORTH_USER_FULL_NAME (optional)
  - NORTH_USER_COMPANY (optional)
"""

from __future__ import annotations

import os
import sys

from supabase import create_client


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"Missing required env var: {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def main() -> int:
    supabase_url = _require_env("SUPABASE_URL")
    supabase_service_key = _require_env("SUPABASE_SERVICE_KEY")
    user_id = _require_env("NORTH_USER_ID")
    email = _require_env("NORTH_USER_EMAIL")
    full_name = os.getenv("NORTH_USER_FULL_NAME") or "Test User"
    company = os.getenv("NORTH_USER_COMPANY") or "Example Company"

    supabase = create_client(supabase_url, supabase_service_key)
    result = (
        supabase.table("user_profiles")
        .upsert(
            {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "company": company,
            }
        )
        .execute()
    )

    print(f"Upserted user_profiles row for {email}: {result.data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

