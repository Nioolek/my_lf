"""Validate our checkpointer against the conformance suite."""

import pytest
from langgraph.checkpoint.conformance import checkpointer_test, validate
from langgraph.checkpoint.conformance.report import ProgressCallbacks


@checkpointer_test(name="PostgresRuntimeSaver")
async def pg_runtime_checkpointer():
    from langgraph_runtime_postgres_py.database import start_pool
    from langgraph_runtime_postgres_py.checkpoint import start_checkpointer
    await start_pool()
    await start_checkpointer()
    from langgraph_runtime_postgres_py.checkpoint import Checkpointer
    yield Checkpointer()


@pytest.mark.asyncio
async def test_checkpoint_conformance():
    report = await validate(pg_runtime_checkpointer, progress=ProgressCallbacks.verbose())
    report.print_report()
    assert report.passed_all_base(), f"Base capability tests failed: {report.to_dict()}"
