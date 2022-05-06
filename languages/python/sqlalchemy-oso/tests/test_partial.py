import pytest

from polar import Variable
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from sqlalchemy_oso.partial import partial_to_filter
from .models import User


@pytest.mark.asyncio
async def test_partial_to_query_filter(oso, async_sessionmaker):
    oso.load_str('ok(_: User{username:"gwen"});')
    async with async_sessionmaker() as session:
        gwen = User(username="gwen")
        session.add(gwen)
        steve = User(username="steve")
        session.add(steve)
        result = oso.query_rule("ok", Variable("actor"), accept_expression=True)

        partial = next(result)["bindings"]["actor"]
        filter = partial_to_filter(partial, session, User, oso.get_class)
        result = await session.execute(select(User).filter(filter))
        q = list(result.scalars().all())
    assert q == [gwen]
