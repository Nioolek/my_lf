"""Start LangGraph API server with postgres_py runtime.

Usage:
    cd demo
    python start_server.py

Then test with Postman or:
    python test_api.py
"""

import asyncio
import os
import selectors
import sys

from dotenv import load_dotenv

# Load .env from demo directory
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import uvicorn
from uvicorn import Config, Server


async def serve():
    """Run uvicorn server."""
    config = Config(
        "langgraph_api.server:app",
        host="127.0.0.1",
        port=2024,
        reload=False,
        access_log=False,
        log_level="info",
    )
    server = Server(config)
    await server.serve()


def loop_factory():
    """SelectorEventLoop for psycopg3 async on Windows."""
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


if __name__ == "__main__":
    print()
    print("  LangGraph API Server (postgres_py Runtime)")
    print("  " + "-" * 40)
    print("  API:       http://127.0.0.1:2024")
    print("  Docs:      http://127.0.0.1:2024/docs")
    print("  Graph:     counter")
    print()
    print("  Press Ctrl+C to stop")
    print()

    asyncio.run(serve(), loop_factory=loop_factory)