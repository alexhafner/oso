import pytest

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session

from sqlalchemy_oso.async_session import async_authorized_sessionmaker

from .models import Post, Tag

@pytest.fixture
def oso_async_authorized_sessionmaker(oso, engine):
    return async_authorized_sessionmaker(
        get_oso=lambda: oso,
        get_user=lambda: "u",
        get_checked_permissions=lambda: {Post: "a"},
        class_=AsyncSession,
    )


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Not supported yet.")
async def test_field_comparison(oso_async_authorized_sessionmaker, async_sessionmaker, oso, engine):
    post0 = Post(id=0, contents="private post", title="not private post")
    post1 = Post(id=1, contents="private post", title="private post")
    post2 = Post(id=2, contents="post", title="post")

    async with async_sessionmaker() as session:
        session.add_all([post0, post1, post2])
        session.commit()

    oso.load_str(
        """
        allow(_, _, post: Post) if
            post.title = post.contents;
    """
    )

    async with oso_async_authorized_sessionmaker() as authz_session:
        results = await authz_session.execute(select(Post))
        posts = results.scalars().all()
        post_ids = [p.id for p in posts]

        assert len(posts) == 2
        assert 1 in post_ids
        assert 2 in post_ids

@pytest.mark.asyncio
async def test_scalar_in_list(oso_async_authorized_sessionmaker, async_sessionmaker, oso, engine):
    post0 = Post(id=0, contents="private post", title="not private post")
    post1 = Post(id=1, contents="allowed posts", title="private post")
    post2 = Post(id=2, contents="post", title="post")

    async with async_sessionmaker() as session:
        session.add_all([post0, post1, post2])
        session.commit()

    oso.load_str(
        """
        allow(_, _, post: Post) if
            post.contents in ["post", "allowed posts"];
    """
    )

    async with oso_async_authorized_sessionmaker() as authz_session:
        results = await authz_session.execute(select(Post))
        posts = results.scalars().all()
        post_ids = [p.id for p in posts]

        assert len(posts) == 2
        assert 1 in post_ids
        assert 2 in post_ids

@pytest.mark.asyncio
async def test_ground_object_in_collection(oso_async_authorized_sessionmaker, async_sessionmaker, oso, engine):
    tag = Tag(name="tag")
    post0 = Post(id=0, contents="tag post", tags=[tag])
    post1 = Post(id=1, contents="no tag post", tags=[])
    post2 = Post(id=2, contents="tag 2 post", tags=[tag])

    async with async_sessionmaker() as session:
        session.add_all([tag, post0, post1, post2])
        session.commit()

    oso.register_constant(tag, "allowed_tag")
    oso.load_str(
        """
        allow(_, _, post: Post) if
            allowed_tag in post.tags;
    """
    )

    async with oso_async_authorized_sessionmaker() as authz_session:
        results = await authz_session.execute(select(Post))
        posts = results.scalars().all()
        post_ids = [p.id for p in posts]

    assert len(posts) == 2
    assert 0 in post_ids
    assert 2 in post_ids

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Negate in not supported yet.")
async def test_all_objects_collection_condition(oso_async_authorized_sessionmaker, async_sessionmaker, oso, engine):
    public_tag = Tag(name="public", is_public=True)
    private_tag = Tag(name="private", is_public=False)

    post0 = Post(id=0, contents="public tag", tags=[public_tag])
    post1 = Post(id=1, contents="no tags", tags=[])
    post2 = Post(id=2, contents="both tags", tags=[public_tag, private_tag])
    post3 = Post(id=3, contents="public tag 2", tags=[public_tag])
    post4 = Post(id=4, contents="private tag", tags=[private_tag])

    async with async_sessionmaker() as session:
        session.add_all([public_tag, private_tag, post0, post1, post2, post3, post4])
        session.commit()

    oso.load_str(
        """
        allow(_, _, post: Post) if
            forall(tag in post.tags, tag.is_public = true);
    """
    )

    async with oso_async_authorized_sessionmaker() as authz_session:
        results = await authz_session.execute(select(Post))
        posts = results.scalars().all()
        post_ids = [p.id for p in posts]

    assert len(posts) == 2
    assert 0 in post_ids
    assert 3 in post_ids

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Negate in not supported yet.")
async def test_no_objects_collection_condition(oso_async_authorized_sessionmaker, async_sessionmaker, oso, engine):
    public_tag = Tag(name="public", is_public=True)
    private_tag = Tag(name="private", is_public=False)

    post0 = Post(id=0, contents="public tag", tags=[public_tag])
    post1 = Post(id=1, contents="no tags", tags=[])
    post2 = Post(id=2, contents="both tags", tags=[public_tag, private_tag])
    post3 = Post(id=3, contents="public tag 2", tags=[public_tag])
    post4 = Post(id=4, contents="private tag", tags=[private_tag])

    async with async_sessionmaker() as session:
        session.add_all([public_tag, private_tag, post0, post1, post2, post3, post4])
        session.commit()

    oso.load_str(
        """
        allow(_, _, post: Post) if
            not (tag in post.tags and tag.is_public = true);
    """
    )

    async with oso_async_authorized_sessionmaker() as authz_session:
        results = await authz_session.execute(select(Post))
        posts = results.scalars().all()
        post_ids = [p.id for p in posts]

    assert len(posts) == 2
    assert 1 in post_ids
    assert 4 in post_ids
