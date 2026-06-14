"""Test the LangGraph API server with real HTTP requests.

Run this AFTER start_server.py is running in another terminal.

Usage:
    cd G:\code\my_lf\demo
    python test_api.py
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import httpx

BASE = "http://127.0.0.1:2024"


def log(label, data):
    """Pretty print a labeled response."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    else:
        print(data)


def main():
    with httpx.Client(timeout=30.0) as c:
        # ── 0. Health check ─────────────────────────────────────────────
        r = c.get(f"{BASE}/ok")
        log("Health Check", r.json())

        # ── 1. List assistants (auto-created from graph registration) ───
        r = c.post(f"{BASE}/assistants/search", json={})
        assistants = r.json()
        log("Assistants", assistants)

        if not assistants:
            print("No assistants found. Graph may not be registered.")
            return

        assistant_id = assistants[0]["assistant_id"]
        log(f"Using Assistant ID: {assistant_id}", assistant_id)

        # ── 2. Get graph schemas ────────────────────────────────────────
        r = c.get(f"{BASE}/assistants/{assistant_id}/schemas")
        schemas = r.json()
        log("Graph Schemas", schemas)

        # ── 3. Stateless run (one-shot, no thread) ──────────────────────
        print("\n--- Stateless Run ---")
        r = c.post(
            f"{BASE}/runs/stream",
            json={
                "assistant_id": assistant_id,
                "input": {"count": 0, "messages": ["Hello!"]},
                "stream_mode": ["values"],
            },
            headers={"Accept": "text/event-stream"},
        )
        print("Status:", r.status_code)
        # Parse SSE events
        final_state = None
        for line in r.text.split("\n"):
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if isinstance(data, dict) and "count" in data:
                        final_state = data
                except json.JSONDecodeError:
                    pass
        log("Final State (Stateless)", final_state)

        # ── 4. Create a thread (stateful conversation) ──────────────────
        r = c.post(
            f"{BASE}/threads",
            json={"metadata": {"user": "demo"}},
        )
        thread = r.json()
        thread_id = thread["thread_id"]
        log(f"Created Thread: {thread_id}", thread)

        # ── 5. Run on thread (streaming) ────────────────────────────────
        print("\n--- Stateful Run 1 ---")
        r = c.post(
            f"{BASE}/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": assistant_id,
                "input": {"count": 0, "messages": ["Run 1"]},
                "stream_mode": ["values"],
            },
            headers={"Accept": "text/event-stream"},
        )
        final_state = None
        for line in r.text.split("\n"):
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if isinstance(data, dict) and "count" in data:
                        final_state = data
                except json.JSONDecodeError:
                    pass
        log("Thread State After Run 1", final_state)

        # ── 6. Get thread state ─────────────────────────────────────────
        r = c.get(f"{BASE}/threads/{thread_id}/state")
        state = r.json()
        log("Thread State (via API)", state)

        # ── 7. Second run on same thread ────────────────────────────────
        print("\n--- Stateful Run 2 (accumulates) ---")
        r = c.post(
            f"{BASE}/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": assistant_id,
                "input": {"count": 0, "messages": ["Run 2"]},
                "stream_mode": ["values"],
            },
            headers={"Accept": "text/event-stream"},
        )
        final_state = None
        for line in r.text.split("\n"):
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    if isinstance(data, dict) and "count" in data:
                        final_state = data
                except json.JSONDecodeError:
                    pass
        log("Thread State After Run 2", final_state)

        # ── 8. Thread history ───────────────────────────────────────────
        r = c.get(f"{BASE}/threads/{thread_id}/history")
        history = r.json()
        log("Thread History (checkpoint count)", len(history))

        # ── 9. Delete thread ────────────────────────────────────────────
        r = c.delete(f"{BASE}/threads/{thread_id}")
        log("Thread Deleted", r.status_code)

    print("\n" + "=" * 60)
    print("  All API tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()