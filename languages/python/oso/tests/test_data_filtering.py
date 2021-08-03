import pytest

from typing import Any, ClassVar
from dataclasses import dataclass
from oso import Oso, OsoError
from polar import Relationship


@pytest.fixture
def oso():
    oso = Oso()
    return oso


def test_data_filtering(oso):
    # Register some types and callbacks
    @dataclass
    class Bar:
        id: str
        is_cool: bool
        is_still_cool: bool

    @dataclass
    class Foo:
        id: str
        bar_id: str
        is_fooey: bool

    hello_bar = Bar(id="hello", is_cool=True, is_still_cool=True)
    goodbye_bar = Bar(id="goodbye", is_cool=False, is_still_cool=True)
    something_foo = Foo(id="something", bar_id="hello", is_fooey=False)
    another_foo = Foo(id="another", bar_id="hello", is_fooey=True)
    third_foo = Foo(id="third", bar_id="hello", is_fooey=True)
    forth_foo = Foo(id="fourth", bar_id="goodbye", is_fooey=True)

    bars = [hello_bar, goodbye_bar]
    foos = [something_foo, another_foo, third_foo, forth_foo]

    def matches_fields(fields, obj):
        for k, v in fields.items():
            if getattr(obj, k) != v:
                return False
            return True

    def field_matcher(fields):
        def matcher(obj):
            return matches_fields(fields, obj)

        return matcher

    def get_bars(constraints):
        results = []
        for bar in bars:
            matches = True
            for constraint in constraints:
                val = getattr(bar, constraint.field)
                if constraint.kind == "Eq":
                    if val != constraint.value:
                        matches = False
                        break
                if constraint.kind == "In":
                    if val not in constraint.value:
                        matches = False
                        break
            if matches:
                results.append(bar)
        return results

    def get_foos(constraints):
        results = []
        for foo in foos:
            matches = True
            for constraint in constraints:
                val = getattr(foo, constraint.field)
                if constraint.kind == "Eq":
                    if val != constraint.value:
                        matches = False
                        break
                if constraint.kind == "In":
                    if val not in constraint.value:
                        matches = False
                        break
            if matches:
                results.append(foo)
        return results

    oso.register_class(Bar, types={"id": str, "is_cool": bool}, fetcher=get_bars)
    oso.register_class(
        Foo,
        types={
            "id": str,
            "bar_id": str,
            "bar": Relationship(
                kind="parent", other_type="Bar", my_field="bar_id", other_field="id"
            ),
        },
        fetcher=get_foos,
    )

    # Write a policy
    policy = """
    allow("steve", "get", resource: Foo) if
        resource.is_fooey = true;
    """
    oso.load_str(policy)
    assert oso.is_allowed("steve", "get", another_foo)

    results = list(oso.get_allowed_resources("steve", "get", Foo))
    assert len(results) == 3

    oso.clear_rules()
    #
    policy = """
    allow("steve", "get", resource: Foo) if
        resource.bar = bar and
        bar.is_cool = true and
        resource.is_fooey = true;
    """
    oso.load_str(policy)
    assert oso.is_allowed("steve", "get", another_foo)

    results = list(oso.get_allowed_resources("steve", "get", Foo))
    assert len(results) == 2

    oso.clear_rules()
    #
    policy = """
    allow("steve", "get", resource: Foo) if
        resource.bar = bar and
        bar.is_cool in [true, false];
    """
    oso.load_str(policy)
    assert oso.is_allowed("steve", "get", another_foo)

    results = list(oso.get_allowed_resources("steve", "get", Foo))
    assert len(results) == 4


def test_roles_data_filtering(oso):
    # Register some types and callbacks
    @dataclass
    class User:
        name: str

    @dataclass
    class Org:
        name: str

    @dataclass
    class Repo:
        name: str
        org_name: str

    @dataclass
    class Issue:
        name: str
        repo_name: str

    @dataclass
    class Role:
        user_name: str
        resource_name: str
        role: str

    apple = Org(name="apple")
    osohq = Org(name="osohq")

    ios = Repo(name="ios", org_name="apple")
    oso_repo = Repo(name="oso", org_name="osohq")
    demo_repo = Repo(name="demo", org_name="osohq")

    ios_laggy = Issue(name="laggy", repo_name="ios")
    oso_bug = Issue(name="bug", repo_name="oso")

    leina = User(name="leina")
    steve = User(name="steve")
    gabe = User(name="gabe")

    users = [leina, steve, gabe]
    orgs = [apple, osohq]
    repos = [ios, oso_repo, demo_repo]
    issues = [ios_laggy, oso_bug]

    roles = [
        Role(user_name="leina", resource_name="osohq", role="owner"),
        Role(user_name="steve", resource_name="osohq", role="member"),
        Role(user_name="gabe", resource_name="oso", role="writer"),
    ]

    def filter_array(array, constraints):
        results = []
        for elem in array:
            matches = True
            for constraint in constraints:
                val = getattr(elem, constraint.field)
                if constraint.kind == "Eq":
                    if val != constraint.value:
                        matches = False
                        break
                if constraint.kind == "In":
                    if val not in constraint.value:
                        matches = False
                        break
            if matches:
                results.append(elem)
        return results

    def get_orgs(constraints):
        return filter_array(orgs, constraints)

    def get_repos(constraints):
        return filter_array(repos, constraints)

    def get_issues(constraints):
        return filter_array(issues, constraints)

    def get_roles(constraints):
        return filter_array(roles, constraints)

    def get_users(constraints):
        return filter_array(users, constraints)

    oso.register_class(Org, types={"name": str}, fetcher=get_orgs)
    oso.register_class(
        Repo,
        types={
            "name": str,
            "org_name": str,
            "org": Relationship(
                kind="parent", other_type="Org", my_field="org_name", other_field="name"
            ),
        },
        fetcher=get_repos,
    )
    oso.register_class(
        Issue,
        types={
            "name": str,
            "repo_name": str,
            "repo": Relationship(
                kind="parent",
                other_type="Repo",
                my_field="repo_name",
                other_field="name",
            ),
        },
        fetcher=get_issues,
    )
    oso.register_class(
        Role,
        types={
            "user_name": str,
            "resource_name": str,
            "role": str,
        },
        fetcher=get_roles,
    )
    oso.register_class(
        User,
        types={
            "name": str,
            "roles": Relationship(
                kind="children",
                other_type="Role",
                my_field="name",
                other_field="user_name",
            ),
        },
        fetcher=get_users,
    )

    policy = """
    resource(_type: Org, "org", actions, roles) if
        actions = [
            "invite",
            "create_repo"
        ] and
        roles = {
            member: {
                permissions: ["create_repo"],
                implies: ["repo:reader"]
            },
            owner: {
                permissions: ["invite"],
                implies: ["repo:writer", "member"]
            }
        };

    resource(_type: Repo, "repo", actions, roles) if
        actions = [
            "push",
            "pull"
        ] and
        roles = {
            writer: {
                permissions: ["push", "issue:edit"],
                implies: ["reader"]
            },
            reader: {
                permissions: ["pull"]
            }
        };

    resource(_type: Issue, "issue", actions, {}) if
        actions = [
            "edit"
        ];

    parent_child(parent_org, repo: Repo) if
        repo.org = parent_org and
        parent_org matches Org;

    parent_child(parent_repo, issue: Issue) if
        issue.repo = parent_repo and
        parent_repo matches Repo;

    actor_has_role_for_resource(actor, role_name: String, resource) if
        role in actor.roles and
        role.resource_name = resource.name and
        role.role = role_name;

    allow(actor, action, resource) if
        role_allows(actor, action, resource);
    """

    oso.load_str(policy)
    oso.enable_roles()

    assert oso.is_allowed(leina, "invite", osohq)
    assert oso.is_allowed(leina, "create_repo", osohq)
    assert oso.is_allowed(leina, "push", oso_repo)
    assert oso.is_allowed(leina, "pull", oso_repo)
    assert oso.is_allowed(leina, "edit", oso_bug)

    assert not oso.is_allowed(steve, "invite", osohq)
    assert oso.is_allowed(steve, "create_repo", osohq)
    assert not oso.is_allowed(steve, "push", oso_repo)
    assert oso.is_allowed(steve, "pull", oso_repo)
    assert not oso.is_allowed(steve, "edit", oso_bug)

    assert not oso.is_allowed(leina, "edit", ios_laggy)
    assert not oso.is_allowed(steve, "edit", ios_laggy)

    results = list(oso.get_allowed_resources(leina, "pull", Repo))
    assert len(results) == 2

    # Well, it seems like this does an infinite loop or something. Not good.
    # results = list(oso.get_allowed_resources(leina, "edit", Issue))
    # assert results == [oso_bug]

    results = list(oso.get_allowed_resources(leina, "invite", Org))
    assert results == [osohq]
