"""Standardized tests for adapters based on the Post model.

Tests come from the relationship document & operations laid out there
https://www.notion.so/osohq/Relationships-621b884edbc6423f93d29e6066e58d16.
"""
import pytest
import pytest_asyncio

from sqlalchemy.future import select
from sqlalchemy_oso.auth import authorize_model
from sqlalchemy_oso.compat import USING_SQLAlchemy_v1_3

from .models import Post, Tag, User, Category
from .conftest import print_query


def assert_query_equals(query, expected_str):
    assert " ".join(str(query).split()) == " ".join(expected_str.split())

@pytest.mark.asyncio
async def test_authorize_model_basic(async_sessionmaker, oso, fixture_data):
    """Test that a simple policy with checks on non-relationship attributes is correct."""
    oso.load_str(
        """allow("user", "read", post: Post) if
             post.access_level = "public";

           allow("user", "write", post: Post) if
             post.access_level = "private";

           allow("admin", "read", _: Post);

           allow("moderator", "read", post: Post) if
             (post.access_level = "private" or post.access_level = "public") and
             post.needs_moderation = true;"""
    )


    async with async_sessionmaker() as session:
        filter_authorize = authorize_model(oso, "user", "read", session, Post)
        print (f"filter_authorize: {filter_authorize}")
        statement = select(Post).filter(filter_authorize

        )
        print_query(statement)
        results = await session.execute(statement)
        posts = results.scalars().all()
        print (f"posts: {posts}")
        print (f"posts len = {len(posts)}")
        assert len(posts) == 5
        assert posts[0].contents == "foo public post"
        assert posts[0].id == 0

        statement = select(Post).filter(
            authorize_model(oso, "user", "write", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()

        assert len(posts) == 4
        assert posts[0].contents == "foo private post"
        assert posts[1].contents == "foo private post 2"

        statement = select(Post).filter(
            authorize_model(oso, "admin", "read", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()
        assert len(posts) == 9

        statement = select(Post).filter(
            authorize_model(oso, "moderator", "read", session, Post)
        )
        print_query(statement)
        results = await session.execute(statement)
        posts = results.scalars().all()

        assert posts[0].contents == "private for moderation"
        assert posts[1].contents == "public for moderation"

        statement = select(Post).filter(
            authorize_model(oso, "guest", "read", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()
        assert len(posts) == 0

@pytest.mark.asyncio
async def test_authorize_scalar_attribute_eq(async_sessionmaker, oso, fixture_data):
    """Test authorization rules on a relationship with one object equaling another."""
    # Object equals another object
    oso.load_str(
        """allow(actor: User, "read", post: Post) if
             post.created_by = actor and
             post.access_level = "private";

           allow(_: User, "read", post: Post) if
             post.access_level = "public";

           allow(_: User{is_moderator: true}, "read", post: Post) if
             post.access_level = "public";"""
    )

    async with async_sessionmaker() as session:

        statement = select(User).filter(User.username == "foo")
        results = await session.execute(statement)
        foo = results.scalars().first()

        statement = select(Post).filter(authorize_model(oso, foo, "read", session, Post))
        print_query(statement)
        results = await session.execute(statement)
        posts = results.scalars().all()

        def allowed(post):
            return (
                post.access_level == "public"
                or post.access_level == "private"
                and post.created_by == foo
            )

        assert len(posts) == 8
        assert all(allowed(post) for post in posts)

@pytest.mark.asyncio
async def test_authorize_scalar_attribute_condition(async_sessionmaker, oso, fixture_data):
    """Scalar attribute condition checks."""
    # Object equals another object

    oso.load_str(
        """allow(actor: User, "read", post: Post) if
             post.created_by.is_banned = false and
             post.created_by.username = actor.username and
             post.access_level = "private";

           allow(_: User, "read", post: Post) if
             post.created_by.is_banned = false and
             post.access_level = "public";

           # moderator can see posts made by banned users.
           allow(actor: User, "read", post: Post) if
             actor.is_moderator = true and
             post.created_by.is_banned = true;"""
    )

    async with async_sessionmaker() as session:

        statement = select(User).filter(User.username == "foo")
        results = await session.execute(statement)
        foo = results.scalars().first()

        statement = select(Post).filter(authorize_model(oso, foo, "read", session, Post))
        results = await session.execute(statement)
        posts = results.scalars().all()

        def allowed(post, user):
            return (
                (post.access_level == "public" and not post.created_by.is_banned)
                or post.access_level == "private"
                and post.created_by == user
            )

        assert len(posts) == 7
        assert all(allowed(post, foo) for post in posts)

        admin_statement = select(User).filter(User.username == "admin_user")
        admin_results = await session.execute(admin_statement)
        admin = admin_results.scalars().first()
        posts_statement = select(Post).filter(
            authorize_model(oso, admin, "read", session, Post)
        )
        posts_results = await session.execute (posts_statement)
        posts = posts_results.scalars().all()

        def allowed_admin(post):
            return post.created_by.is_banned

        assert len(posts) == 6
        for post in posts:
            assert allowed(post, admin) or allowed_admin(post)


@pytest_asyncio.fixture
async def tag_test_fixture(async_sessionmaker):
    """Test data for tests with tags."""
    user = User(username="user")
    other_user = User(username="other_user")
    moderator = User(username="moderator", is_moderator=True)

    eng = Tag(name="eng")
    foo = Tag(name="foo")
    random = Tag(name="random", is_public=True)

    user_public_post = Post(
        contents="public post", created_by=user, access_level="public"
    )
    user_private_post = Post(
        contents="private user post", created_by=user, access_level="private"
    )

    other_user_public_post = Post(
        contents="other user public", created_by=other_user, access_level="public"
    )
    other_user_private_post = Post(
        contents="other user private", created_by=other_user, access_level="private"
    )
    other_user_random_post = Post(
        contents="other user random",
        created_by=other_user,
        access_level="private",
        tags=[random],
    )
    other_user_foo_post = Post(
        contents="other user foo",
        created_by=other_user,
        access_level="private",
        tags=[foo],
    )

    # HACK!
    async with async_sessionmaker() as session:
        objects = {}
        for (name, local) in locals().items():
            if name not in ["async_sessionmaker", "objects", "session"]:
                session.add(local)

            objects[name] = local

        session.commit()

    return objects

@pytest.mark.asyncio
async def test_in_multiple_attribute_relationship(async_sessionmaker, oso, tag_test_fixture):
    oso.load_str(
        """
        allow(_user, "read", post: Post) if post.access_level = "public";
        allow(user, "read", post: Post) if post.access_level = "private" and post.created_by = user;
        allow(_user, "read", post: Post) if
            tag in post.tags and
            0 < post.id and
            (tag.is_public = true or tag.name = "foo");
    """
    )


    async with async_sessionmaker() as session:

        statement = select(Post).filter(
            authorize_model(oso, tag_test_fixture["user"], "read", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()

        assert tag_test_fixture["user_public_post"] in posts
        assert tag_test_fixture["user_private_post"] in posts
        assert tag_test_fixture["other_user_public_post"] in posts
        assert not tag_test_fixture["other_user_private_post"] in posts
        assert tag_test_fixture["other_user_random_post"] in posts
        assert tag_test_fixture["other_user_foo_post"] in posts
        assert len(posts) == 5


@pytest_asyncio.fixture
async def tag_nested_test_fixture(async_sessionmaker):
    user = User(username="user")
    other_user = User(username="other_user")
    moderator = User(username="moderator", is_moderator=True)

    eng = Tag(name="eng", created_by=user)
    user_posts = Tag(name="user_posts", created_by=user)
    random = Tag(name="random", is_public=True, created_by=other_user)

    user_eng_post = Post(
        contents="user eng post", access_level="public", created_by=user, tags=[eng]
    )
    user_user_post = Post(
        contents="user eng post",
        access_level="public",
        created_by=user,
        tags=[user_posts],
    )

    random_post = Post(
        contents="other random post",
        access_level="public",
        created_by=other_user,
        tags=[random],
    )

    not_tagged_post = Post(
        contents="not tagged post", access_level="public", created_by=user, tags=[]
    )

    all_tagged_post = Post(
        contents="not tagged post",
        access_level="public",
        created_by=user,
        tags=[eng, user_posts, random],
    )

    async with async_sessionmaker() as session:
        # HACK!
        objects = {}
        for (name, local) in locals().items():
            if name not in ["async_sessionmaker", "objects", "session"]:
                session.add(local)

            objects[name] = local

    session.commit()

    return objects


# TODO (dhatch): This doesn't actually exercise nested attribute code, because
# the nested piece is in a sub expression.
@pytest.mark.asyncio
async def test_nested_relationship_many_single(async_sessionmaker, oso, tag_nested_test_fixture):
    """Test that nested relationships work.

    post - (many) -> tags - (single) -> User

    A user can read a post with a tag if the tag's creator is the user.
    """
    oso.load_str(
        """
        allow(user, "read", post: Post) if tag in post.tags and tag.created_by = user;
    """
    )

    async with async_sessionmaker() as session:
        statement = select(Post).filter(
            authorize_model(oso, tag_nested_test_fixture["user"], "read", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()
        assert tag_nested_test_fixture["user_eng_post"] in posts
        assert tag_nested_test_fixture["user_user_post"] in posts
        assert not tag_nested_test_fixture["random_post"] in posts
        assert not tag_nested_test_fixture["not_tagged_post"] in posts
        assert tag_nested_test_fixture["all_tagged_post"] in posts
        assert len(posts) == 3

        statement = select(Post).filter(
            authorize_model(
                oso, tag_nested_test_fixture["other_user"], "read", session, Post
            )
        )
        results = await session.execute()
        posts = results.scalars().all()
        assert not tag_nested_test_fixture["user_eng_post"] in posts
        assert not tag_nested_test_fixture["user_user_post"] in posts
        assert tag_nested_test_fixture["random_post"] in posts
        assert not tag_nested_test_fixture["not_tagged_post"] in posts
        assert tag_nested_test_fixture["all_tagged_post"] in posts
        assert len(posts) == 2


@pytest_asyncio.fixture
async def tag_nested_many_many_test_fixture(async_sessionmaker):
    eng = Tag(name="eng")
    user_posts = Tag(name="user_posts")
    random = Tag(name="random", is_public=True)
    other = Tag(name="other")
    unused = Tag(name="unused")

    user = User(username="user", tags=[eng, user_posts], tag=random)
    other_user = User(username="other_user", tags=[random])
    moderator = User(username="moderator", tags=[random, user_posts, eng])

    user_eng_post = Post(
        contents="user eng post", access_level="public", created_by=user, tags=[eng]
    )
    user_user_post = Post(
        contents="user eng post",
        access_level="public",
        created_by=user,
        tags=[user_posts],
    )

    random_post = Post(
        contents="other random post",
        access_level="public",
        created_by=other_user,
        tags=[random],
    )

    not_tagged_post = Post(
        contents="not tagged post", access_level="public", created_by=user, tags=[]
    )

    all_tagged_post = Post(
        contents="not tagged post",
        access_level="public",
        created_by=user,
        tags=[eng, user_posts, random],
    )

    other_tagged_post = Post(
        contents="other tagged post",
        access_level="public",
        created_by=user,
        tags=[other],
    )

    async with async_sessionmaker() as session:
        # HACK!
        objects = {}
        for (name, local) in locals().items():
            if name not in ["async_sessionmaker", "objects", "session"]:
                session.add(local)

            objects[name] = local

    user.posts += [
        user_eng_post,
        user_user_post,
        not_tagged_post,
        all_tagged_post,
        other_tagged_post,
    ]
    other_user.posts += [random_post]

    session.commit()

    return objects
@pytest.mark.asyncio
async def test_nested_relationship_many_many(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    """Test that nested relationships work.

    post - (many) -> tags - (many) -> User

    A user can read a post with a tag if the tag's creator is the user.
    """
    # TODO This direction doesn't work, because tag in user.tags is a concrete object.
    # allow(user, "read", post: Post) if tag in post.tags and tag in user.tags;
    oso.load_str(
        """
    allow(user, "read", post: Post) if tag in post.tags and user in tag.users;
    """
    )

    async with async_sessionmaker() as session:

        results = await session.execute(select(Post).filter(
            authorize_model(
                oso, tag_nested_many_many_test_fixture["user"], "read", session, Post
            )
        ))
        posts = results.scalars().all()
        assert tag_nested_many_many_test_fixture["user_eng_post"] in posts
        assert tag_nested_many_many_test_fixture["user_user_post"] in posts
        assert not tag_nested_many_many_test_fixture["random_post"] in posts
        assert not tag_nested_many_many_test_fixture["not_tagged_post"] in posts
        assert tag_nested_many_many_test_fixture["all_tagged_post"] in posts

        results = await session.execute(select(Post).filter(
            authorize_model(
                oso, tag_nested_many_many_test_fixture["other_user"], "read", session, Post
            )
        ))
        posts = results.scalars().all()
        assert not tag_nested_many_many_test_fixture["user_eng_post"] in posts
        assert not tag_nested_many_many_test_fixture["user_user_post"] in posts
        assert tag_nested_many_many_test_fixture["random_post"] in posts
        assert not tag_nested_many_many_test_fixture["not_tagged_post"] in posts
        assert tag_nested_many_many_test_fixture["all_tagged_post"] in posts

@pytest.mark.asyncio
async def test_nested_relationship_many_many_constrained(
    async_sessionmaker, oso, tag_nested_many_many_test_fixture
):
    """Test that nested relationships work.

    post - (many) -> tags - (many) -> User

    A user can read a post with a tag if the tag's creator is the user.
    """
    oso.load_str(
        """
    allow(_, "read", post: Post) if tag in post.tags and user in tag.users and
        user.username = "user";
    """
    )

    async with async_sessionmaker() as session:
        statement = select(Post).filter(
            authorize_model(
                oso, tag_nested_many_many_test_fixture["user"], "read", session, Post
            )
        )
        results = await session.execute(statement)
        posts = results.scalars().all()
        assert tag_nested_many_many_test_fixture["user_eng_post"] in posts
        assert tag_nested_many_many_test_fixture["user_user_post"] in posts
        assert not tag_nested_many_many_test_fixture["random_post"] in posts
        assert not tag_nested_many_many_test_fixture["not_tagged_post"] in posts
        assert tag_nested_many_many_test_fixture["all_tagged_post"] in posts

@pytest.mark.asyncio
async def test_nested_relationship_many_many_many_constrained(async_sessionmaker, engine, oso):
    """Test that nested relationships work.

    post - (many) -> tags - (many) -> category - (many) -> User
    """
    foo = User(username="foo")
    bar = User(username="bar")

    foo_category = Category(name="foo_category", users=[foo])
    bar_category = Category(name="bar_category", users=[bar])
    both_category = Category(name="both_category", users=[foo, bar])
    public_category = Category(name="public", users=[foo, bar])

    foo_tag = Tag(name="foo", categories=[foo_category])
    bar_tag = Tag(name="bar", categories=[bar_category])
    both_tag = Tag(
        name="both",
        categories=[foo_category, bar_category, public_category],
        is_public=True,
    )

    foo_post = Post(contents="foo_post", tags=[foo_tag])
    bar_post = Post(contents="bar_post", tags=[bar_tag])
    both_post = Post(contents="both_post", tags=[both_tag])
    none_post = Post(contents="none_post", tags=[])
    foo_post_2 = Post(contents="foo_post_2", tags=[foo_tag])
    public_post = Post(contents="public_post", tags=[both_tag], access_level="public")

    async with async_sessionmaker() as session:
        session.add_all(
            [
                foo,
                bar,
                foo_category,
                bar_category,
                both_category,
                foo_tag,
                bar_tag,
                both_tag,
                foo_post,
                bar_post,
                both_post,
                none_post,
                foo_post_2,
                public_category,
                public_post,
            ]
        )
        await session.commit()

    # A user can read a post that they are the moderator of the category of.
        policy = """allow(user, "read", post: Post) if
                    tag in post.tags and
                    category in tag.categories and
                    moderator in category.users
                    and moderator = user;"""
        oso.load_str(policy)

        results = await session.execute(select(Post).filter(authorize_model(oso, foo, "read", session, Post)))
        posts = results.scalars().all()

        assert foo_post in posts
        assert both_post in posts
        assert public_post in posts
        assert foo_post_2 in posts
        assert bar_post not in posts
        assert len(posts) == 4

        results = await session.execute(select(Post).filter(authorize_model(oso, bar, "read", session, Post)))
        posts = results.scalars().all()

        assert bar_post in posts
        assert both_post in posts
        assert public_post in posts
        assert foo_post not in posts
        assert foo_post_2 not in posts
        assert len(posts) == 3

        oso.clear_rules()

        # A user can read a post that they are the moderator of the category of if the
        # tag is public.
        policy += """allow(user, "read_2", post: Post) if
                    tag in post.tags and
                    tag.is_public = true and
                    category in tag.categories and
                    moderator in category.users
                    and moderator = user;"""
        oso.load_str(policy)

        results = await session.execute(select(Post).filter(
            authorize_model(oso, bar, "read_2", session, Post)
        ))

        posts = results.scalars().all()

        # Only the both tag is public.
        assert both_post in posts
        assert public_post in posts
        assert bar_post not in posts
        assert foo_post not in posts
        assert foo_post_2 not in posts
        assert len(posts) == 2

        oso.clear_rules()

        # A user can read a post that they are the moderator of the category of if the
        # tag is public and the category name is public.
        policy += """allow(user, "read_3", post: Post) if
                    post.access_level = "public" and
                    tag in post.tags and
                    tag.is_public = true and
                    category in tag.categories and
                    category.name = "public" and
                    moderator in category.users and
                    moderator = user;"""
        oso.load_str(policy)

        statement = select(Post).filter(
            authorize_model(oso, bar, "read_3", session, Post)
        )
        print_query(statement)
        results = await session.execute(statement)

        posts = results.scalars().all()

        # Only the both tag is public but the category name is not correct.
        assert len(posts) == 1

@pytest.mark.asyncio
async def test_partial_in_collection(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str(
        """
        allow(user, "read", post: Post) if post in user.posts;
    """
    )

    user = tag_nested_many_many_test_fixture["user"]
    async with async_sessionmaker() as session:
        statement = select(Post).filter(
            authorize_model(oso, user, "read", session, Post)
        )
        print_query(statement)
        results = await session.execute(statement)
        posts = results.scalars().all()

    assert tag_nested_many_many_test_fixture["user_eng_post"] in posts
    assert tag_nested_many_many_test_fixture["user_user_post"] in posts
    assert tag_nested_many_many_test_fixture["random_post"] not in posts
    assert tag_nested_many_many_test_fixture["not_tagged_post"] in posts
    assert tag_nested_many_many_test_fixture["all_tagged_post"] in posts
    assert tag_nested_many_many_test_fixture["other_tagged_post"] in posts
    assert len(posts) == 5

    user = tag_nested_many_many_test_fixture["other_user"]
    posts = (
        await session.execute(select(Post)
        .filter(authorize_model(oso, user, "read", session, Post))
        .all()
    ))
    assert tag_nested_many_many_test_fixture["user_eng_post"] not in posts
    assert tag_nested_many_many_test_fixture["user_user_post"] not in posts
    assert tag_nested_many_many_test_fixture["random_post"] in posts
    assert tag_nested_many_many_test_fixture["not_tagged_post"] not in posts
    assert tag_nested_many_many_test_fixture["all_tagged_post"] not in posts
    assert len(posts) == 1

@pytest.mark.asyncio
async def test_empty_constraints_in(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str("""allow(_, "read", post: Post) if _tag in post.tags;""")
    user = tag_nested_many_many_test_fixture["user"]
    async with async_sessionmaker() as session:
        results = await session.execute(select(Post).filter(
            authorize_model(oso, user, "read", session, Post)
        ))
        posts = results.scalars().all()

        if USING_SQLAlchemy_v1_3:
            true_clause = ""
        else:
            # NOTE(gj): The trivial TRUE constraint is not compiled away in
            # SQLAlchemy 1.4.
            true_clause = " AND 1 = 1"

        assert str(posts) == (
            "SELECT posts.id AS posts_id, posts.contents AS posts_contents, posts.title AS"
            + " posts_title, posts.access_level AS posts_access_level,"
            + " posts.created_by_id AS posts_created_by_id, posts.needs_moderation AS posts_needs_moderation"
            + " \nFROM posts"
            + " \nWHERE EXISTS (SELECT 1"
            + " \nFROM post_tags, tags"
            + f" \nWHERE posts.id = post_tags.post_id AND tags.name = post_tags.tag_id{true_clause})"
        )
        posts = posts.all()
        assert len(posts) == 5
        assert tag_nested_many_many_test_fixture["not_tagged_post"] not in posts

@pytest.mark.asyncio
async def test_in_with_constraints_but_no_matching_objects(
    async_sessionmaker, oso, tag_nested_many_many_test_fixture
):
    oso.load_str(
        """
        allow(_, "read", post: Post) if
            tag in post.tags and
            tag.name = "bloop";
    """
    )
    user = tag_nested_many_many_test_fixture["user"]
    async with async_sessionmaker() as session:
        results = await session.execute(select(Post).filter(
            authorize_model(oso, user, "read", session, Post)
        ))
        posts = results.scalars().all()
        assert str(posts) == (
            "SELECT posts.id AS posts_id, posts.contents AS posts_contents, posts.title AS posts_title,"
            + " posts.access_level AS posts_access_level,"
            + " posts.created_by_id AS posts_created_by_id, posts.needs_moderation AS posts_needs_moderation"
            + " \nFROM posts"
            + " \nWHERE EXISTS (SELECT 1"
            + " \nFROM post_tags, tags"
            + " \nWHERE posts.id = post_tags.post_id AND tags.name = post_tags.tag_id AND tags.name = ?)"
        )
        posts = posts.all()
        assert len(posts) == 0

@pytest.mark.asyncio
async def test_redundant_in_on_same_field(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str(
        """
        allow(_, "read", post: Post) if
            tag in post.tags and tag2 in post.tags
            and tag.name = "random" and tag2.is_public = true;
        """
    )
    async with async_sessionmaker() as session:
        posts = await session.execute(select(Post).filter(
            authorize_model(oso, "user", "read", session, Post)
        ))

        posts = posts.all()
        assert len(posts) == 2

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Unification between fields of partials not supported.")
async def test_unify_ins(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str(
        """
        allow(_, _, post) if
            tag1 in post.tags and
            tag2 in post.tags and
            tag1.name = tag2.name and
            tag1.name > "a" and
            tag2.name <= "z";
        """
    )
    async with async_sessionmaker() as session:
        statement = select(Post).filter(
            authorize_model(oso, "user", "read", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()

        assert len(posts) == 1

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Cannot compare item in subquery to outer item.")
async def test_deeply_nested_in(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str(
        """
        allow(_, _, post: Post) if
            foo in post.created_by.posts and foo.id > 1 and
            bar in foo.created_by.posts and bar.id > 2 and
            baz in bar.created_by.posts and baz.id > 3 and
            post in baz.created_by.posts and post.id > 4;
    """
    )
    async with async_sessionmaker() as session:
        statement = select(Post).filter(
            authorize_model(oso, "user", "read", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()

        query_str = """
            SELECT posts.id AS posts_id, posts.contents AS posts_contents, posts.title AS posts_title, posts.access_level AS
            posts_access_level, posts.created_by_id AS posts_created_by_id, posts.needs_moderation AS
            posts_needs_moderation
            FROM posts
            WHERE (EXISTS (SELECT 1
            FROM users
            WHERE users.id = posts.created_by_id AND (EXISTS (SELECT 1
            FROM posts
            WHERE users.id = posts.created_by_id AND posts.id > ? AND (EXISTS (SELECT 1
            FROM users
            WHERE users.id = posts.created_by_id AND (EXISTS (SELECT 1
            FROM posts
            WHERE users.id = posts.created_by_id AND posts.id > ? AND (EXISTS (SELECT 1
            FROM users
            WHERE users.id = posts.created_by_id AND (EXISTS (SELECT 1
            FROM posts
            WHERE users.id = posts.created_by_id AND posts.id > ?)))))))))))) AND (EXISTS (SELECT 1
            FROM users
            WHERE users.id = posts.created_by_id AND (EXISTS (SELECT 1
            FROM posts
            WHERE users.id = posts.created_by_id)))) AND posts.id > ? AND posts.id =
        """

        assert_query_equals(statement, query_str)
        assert len(posts) == 1

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Intersection doesn't work in sqlalchemy")
async def test_in_intersection(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str(
        """
        allow(_, _, post: Post) if
            u in post.users and
            t in post.tags and
            u in t.users;
    """
    )

    async with async_sessionmaker() as session:
        statement = select(Post).filter(
            authorize_model(oso, "user", "read", session, Post)
        )
        results = await session.execute(statement)
        posts = results.scalars().all()

        # TODO (dhatch): Add query in here when this works.
        assert_query_equals(statement, "")

        assert len(posts) == 4


# TODO combine with test in test_django_oso.
@pytest.mark.asyncio
async def test_partial_isa_with_path(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str(
        """
            allow(user, _, post: Post) if
                check(user, post.created_by);


            allow(user, _, tag: Tag) if
                post in tag.posts and
                check(user, post);

            check(user: User, post: Post) if post.created_by = user;
            check(_: User, tag: Tag)      if tag.is_public;
            check(_: User, user: User)    if user.username = "user";
        """
    )

    user = tag_nested_many_many_test_fixture["user"]
    async with async_sessionmaker() as session:
        results = await session.execute(select(Post).filter(
            authorize_model(oso, user, "read", session, Post)
        ))
        # Should only get posts created by user.
        posts = results.scalars().all()
        for post in posts:
            assert post.created_by.username == "user"

        assert len(posts) == 5

        statement = select(Tag).filter(authorize_model(oso, user, "read", session, Tag))
        results = await session.execute(statement)
        tags = results.scalars().all

        print_query(statement)
        for tag in tags:
            assert any(post.created_by.username == "user" for post in tag.posts)

        assert len(tags) == 4

@pytest.mark.asyncio
async def test_two_level_isa_with_path(async_sessionmaker, oso, tag_nested_many_many_test_fixture):
    oso.load_str(
        """
            allow(user, _, post: Post) if
                check(user, post) and user.username == "user";

            check(user: User, post: Post) if
                post.created_by = u and
                check(user, u.tag);
            check(_: User, tag: Tag)      if tag.is_public;
        """
    )

    user = tag_nested_many_many_test_fixture["user"]
    async with async_sessionmaker() as session:
        statement = select(Post).filter(
            authorize_model(oso, user, "read", session, Post)
        )
        print_query(statement)
        results = await session.execute(statement)

        # Should only get posts created by user.
        posts = results.scalars().all()
        for post in posts:
            assert post.created_by.username == "user"

        assert len(posts) == 5


# TODO test_nested_relationship_single_many
# TODO test_nested_relationship_single_single
# TODO test_nested_relationship_single_single_single ... etc

# TODO test non Eq conditions
# TODO test f(x) if not x.boolean_attr;
# TODO test this = ? with multiple pks
