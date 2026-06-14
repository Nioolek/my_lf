"""psycopg3 retry logic."""

from __future__ import annotations

import asyncio
import functools

from psycopg import OperationalError, InterfaceError

RETRIABLE_EXCEPTIONS = (OperationalError, InterfaceError, ConnectionError)
OVERLOADED_EXCEPTIONS = ()


def retry_db(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        for i in range(3):
            if i == 2:
                return await func(*args, **kwargs)
            try:
                return await func(*args, **kwargs)
            except RETRIABLE_EXCEPTIONS:
                await asyncio.sleep(0.1 * (2 ** i))
    return wrapper