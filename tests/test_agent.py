import asyncio

import agent
from monitor import Fetchers


def test_make_fetchers_wires_cimb():
    async def go():
        async with agent.make_session() as session:
            fetchers = agent.make_fetchers(session)
            return fetchers, session.headers.get("User-Agent", "")

    fetchers, ua = asyncio.run(go())
    assert isinstance(fetchers, Fetchers) and callable(fetchers.cimb)
    assert ua.startswith("Mozilla/5.0")
