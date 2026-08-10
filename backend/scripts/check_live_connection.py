"""
Quick standalone check that DATAHUB_GMS_URL + DATAHUB_TOKEN actually work,
before flipping the whole app to DATAHUB_MODE=live.

Usage:
    cd backend
    DATAHUB_GMS_URL=http://localhost:8080 DATAHUB_TOKEN=<your-pat> python3 scripts/check_live_connection.py

Note the GMS API is usually on a different port than the DataHub UI you
browse to (UI is commonly 9002; GMS is commonly 8080). Get a Personal
Access Token from the DataHub UI: Settings -> Access Tokens -> Generate
New Token.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402


async def main():
    base_url = os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").rstrip("/")
    token = os.getenv("DATAHUB_TOKEN", "")

    query = """
    query search($input: SearchInput!) {
      search(input: $input) {
        total
        searchResults { entity { urn type ... on Dataset { properties { name } } } }
      }
    }
    """
    variables = {"input": {"type": "DATASET", "query": "*", "start": 0, "count": 5}}
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"Checking {base_url}/api/graphql ...")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{base_url}/api/graphql", json={"query": query, "variables": variables}, headers=headers
            )
        except httpx.ConnectError as e:
            print(f"❌ Could not connect: {e}")
            print("   Is this the GMS port (often 8080), not the UI port (often 9002)?")
            return

    if resp.status_code != 200:
        print(f"❌ HTTP {resp.status_code}: {resp.text[:500]}")
        return

    data = resp.json()
    if data.get("errors"):
        print(f"❌ GraphQL errors: {data['errors']}")
        if not token:
            print("   No DATAHUB_TOKEN was set — many instances require one even for reads.")
        return

    results = data["data"]["search"]["searchResults"]
    total = data["data"]["search"]["total"]
    print(f"✅ Connected. {total} datasets visible to this token.")
    for r in results[:5]:
        name = (r["entity"].get("properties") or {}).get("name") or r["entity"]["urn"]
        print(f"   - {name}")


if __name__ == "__main__":
    asyncio.run(main())
