import pytest
import pytest_asyncio

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm.session import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from oso import Oso
from sqlalchemy_oso.auth import register_models
from sqlalchemy_oso.compat import USING_SQLAlchemy_v1_3


from .models import ModelBase, Post, User

if USING_SQLAlchemy_v1_3:
    collect_ignore = ["test_advanced_queries_14.py"]


def print_query(query):
    print(query.compile(), query.compile().params)


@pytest.fixture
def post_fixtures():

    foo = User(id=0, username="foo")
    admin_user = User(id=1, username="admin_user", is_moderator=True)
    bad_user = User(id=2, username="bad_user", is_banned=True)
    users = [foo, admin_user, bad_user]

    posts = [
        Post(
            id=0, contents="foo public post", access_level="public", created_by=foo
        ),
        Post(
            id=1,
            contents="foo public post 2",
            access_level="public",
            created_by=foo,
        ),
        Post(
            id=3,
            contents="foo private post",
            access_level="private",
            created_by=foo,
        ),
        Post(
            id=4,
            contents="foo private post 2",
            access_level="private",
            created_by=foo,
        ),
        Post(
            id=5,
            contents="private for moderation",
            access_level="private",
            needs_moderation=True,
            created_by=foo,
        ),
        Post(
            id=6,
            contents="public for moderation",
            access_level="public",
            needs_moderation=True,
            created_by=foo,
        ),
        Post(
            id=7,
            contents="admin post",
            access_level="public",
            needs_moderation=True,
            created_by=admin_user,
        ),
        Post(
            id=8,
            contents="admin post",
            access_level="private",
            needs_moderation=True,
            created_by=admin_user,
        ),
        Post(
            id=9, contents="banned post", access_level="public", created_by=bad_user
        ),
    ]


    def create(session: Session):

        for p in posts:
            session.add(p)

        for u in users:
            session.add(u)

    return create


@pytest_asyncio.fixture
async def fixture_data(async_sessionmaker, post_fixtures):

    async with async_sessionmaker() as session:
        async with session.begin():
            post_fixtures(session)
            await session.commit()


@pytest.fixture
def db_uri():
    return "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine(db_uri):
    # TODO: run async tests only if SQLAlchemy 1.4 is installed
    engine = create_async_engine(db_uri)
    async with engine.begin() as conn:
        await conn.run_sync(ModelBase.metadata.create_all)
    return engine


@pytest.fixture
def async_sessionmaker(engine):
    return sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )


@pytest.fixture
def oso():
    oso = Oso()
    register_models(oso, ModelBase)
    return oso

