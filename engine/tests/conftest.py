"""pytest set-up for the engine's tests.

The tests are coroutines, and need nothing beyond pytest: an `async def
test_...` is run here on a fresh event loop of its own. Shared pieces live in
harness.py; a fixture used by one file is in that file.
"""

import asyncio
import inspect

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    if not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    args = {n: pyfuncitem.funcargs[n] for n in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(pyfuncitem.obj(**args))
    return True
