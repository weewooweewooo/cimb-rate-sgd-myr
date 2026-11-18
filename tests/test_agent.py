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
    assert callable(fetchers.wise_live) and callable(fetchers.wise_fee)
    assert ua.startswith("Mozilla/5.0")


def test_initial_state_uses_saved_wise_fee():
    from db import Database
    from models import WiseFee

    db = Database(":memory:")
    assert agent.initial_state(db).wise_fee == WiseFee(0.53, 0.0025)
    db.save_wise_fee(WiseFee(0.6, 0.003), __import__("datetime").datetime(2026, 11, 18))
    assert agent.initial_state(db).wise_fee == WiseFee(0.6, 0.003)


def test_make_history_fetcher_is_callable():
    async def go():
        async with agent.make_session() as session:
            return agent.make_history_fetcher(session)

    assert callable(asyncio.run(go()))
