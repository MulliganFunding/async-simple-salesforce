"""Root conftest.py for pytest configuration."""
import asyncio
import sys

# On Windows, the default ProactorEventLoop has known incompatibilities with
# some async libraries. Switch to SelectorEventLoop for test compatibility.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
