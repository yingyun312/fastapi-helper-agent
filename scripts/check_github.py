"""Read-only, unauthenticated GitHub smoke check. No .env file is read."""

import asyncio
import json

from app.config import Settings
from app.tools import ToolRegistry


async def main():
    tools = ToolRegistry(None, Settings(app_mode="live"))
    try:
        result = await tools.execute(
            "search_github_issues", '{"query":"dependencies yield","top_k":2}'
        )
        print(
            json.dumps(
                {
                    "error": result.error,
                    "warnings": result.warnings,
                    "sources": [
                        {"url": item.url, "retrieved_at": item.retrieved_at}
                        for item in result.evidence
                    ],
                },
                indent=2,
            )
        )
        if result.error:
            raise SystemExit(1)
    finally:
        await tools.close()


if __name__ == "__main__":
    asyncio.run(main())
