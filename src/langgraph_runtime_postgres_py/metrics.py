"""Runtime metrics."""

from __future__ import annotations

from langgraph_runtime_postgres_py.database import pool_stats


def get_metrics() -> dict[str, dict[str, int]]:
    from langgraph_api import config as api_config
    workers_max = api_config.N_JOBS_PER_WORKER
    db_stats = pool_stats()
    return {
        "workers": {
            "max": workers_max,
            "active": 0,  # Updated by queue heartbeat
            "available": workers_max,
        },
        **db_stats,
    }