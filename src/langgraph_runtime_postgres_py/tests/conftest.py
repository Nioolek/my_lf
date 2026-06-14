"""Test fixtures using testcontainers for Postgres + Redis."""

import pytest


@pytest.fixture(scope="session")
def pg_uri():
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_uri():
    from testcontainers.redis import RedisContainer
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}"


@pytest.fixture(autouse=True)
def setup_env(pg_uri, redis_uri, monkeypatch):
    monkeypatch.setenv("LANGGRAPH_RUNTIME_EDITION", "postgres")
    monkeypatch.setenv("DATABASE_URI", pg_uri)
    monkeypatch.setenv("REDIS_URI", redis_uri)
