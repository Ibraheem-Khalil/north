"""
Quick data profile for NORTH's Weaviate collections.

Usage:
    python scripts/data_profile.py

Outputs total object counts per collection so you can ground README claims
without exposing any document content.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv


def _connect() -> Optional["weaviate.WeaviateClient"]:
    """Connect to Weaviate using the same env-based logic as the app."""
    try:
        import weaviate
        import weaviate.auth as wvauth
    except ImportError:
        print("❌ weaviate-client not installed. Run `pip install weaviate-client`.")
        return None

    load_dotenv()

    url = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    api_key = os.getenv("WEAVIATE_API_KEY")

    # Optional headers (e.g., Voyage for reranking)
    headers: Dict[str, str] = {}
    voyage = os.getenv("VOYAGE_API_KEY")
    if voyage:
        headers["X-VoyageAI-Api-Key"] = voyage

    try:
        if url.startswith("https://") and api_key:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=url,
                auth_credentials=wvauth.AuthApiKey(api_key),
                headers=headers or None,
            )
        else:
            parsed = urlparse(url)
            client = weaviate.connect_to_local(
                host=parsed.hostname or "localhost",
                port=parsed.port or 8080,
                grpc_port=50051,
            )
    except Exception as exc:
        print(f"❌ Failed to connect to Weaviate at {url}: {exc}")
        return None

    return client


def _count_collection(collection) -> Optional[int]:
    """Return total object count for a collection, or None if it fails."""
    try:
        agg = collection.aggregate.over_all(total_count=True)
        return getattr(agg, "total_count", None)
    except Exception:
        return None


def main() -> None:
    client = _connect()
    if not client:
        return

    try:
        print(f"📊 Data profile as of {datetime.utcnow().isoformat()}Z")

        collections = client.collections.list_all()
        if not collections:
            print("No collections found.")
            return

        # Map names to collection objects
        col_map = {c.name: client.collections.get(c.name) for c in collections}

        # Preferred order for NORTH
        preferred = ["Company", "WorkLog", "Document", "DocumentChunk"]

        for name in preferred:
            if name in col_map:
                count = _count_collection(col_map[name])
                count_str = count if count is not None else "?"
                print(f"- {name}: {count_str} objects")

        # Show any other collections too
        other = [n for n in col_map if n not in preferred]
        if other:
            print("Other collections:")
            for name in sorted(other):
                count = _count_collection(col_map[name])
                count_str = count if count is not None else "?"
                print(f"  - {name}: {count_str} objects")
    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
