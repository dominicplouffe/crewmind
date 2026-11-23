"""Operations on secrets and variables themselves: add, replace, change, import, list, show
and delete (CON-1 to CON-3, CON-15, CON-16). Values go in; they never come out."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from crewmind.catalog.caller import Authority
from crewmind.catalog.define import PERSON_AND_MCP, operation
from crewmind.catalog.execute import Context
from crewmind.catalog.operation import Reversibility
from crewmind.catalog.refusal import Refusal, RefusalKind
from crewmind.domain.connections import attach, service
from crewmind.domain.connections.mcp import OAUTH_SECRETS, SERVER_MACHINE, ServerState
from crewmind.domain.connections.model import (
    ADDED,
    CHANGED,
    CON_1,
    CON_2,
    CON_3,
    CONNECTION_MACHINE,
    REPLACED,
    SECRET_NAME,
    SECRET_OWNER,
    STATE_CHANGED,
    ConnectionState,
    Delivery,
    HeaderKind,
    Kind,
    Scope,
    Shape,
    check_env_name,
    check_header_name,
    check_name,
    check_single_line,
    check_site,
    default_env_name,
)
from crewmind.domain.connections.views import ConnectionView, item_view
from crewmind.domain.projects.access import project_not_found, role_in
from crewmind.domain.secrets.store import SecretStore
from crewmind.domain.settings.registry import Scope as SettingScope
from crewmind.domain.settings.service import INSTALL_SUBJECT, Subject
from crewmind.services import services_of
from crewmind.storage.models import (
    Connection,
    ConnectionSecret,
    ConnectionVariable,
    Event,
    McpServer,
    Person,
    Project,
)


class Placement(BaseModel):
    scope: Scope = Field(
        default=Scope.PERSON,
        description="person (yours, for any project you chair), project, or install (admins).",
    )
    project_id: str | None = Field(
        default=None,
        description="The project it belongs to (project scope), or to attach it to at once.",
    )
    roles: list[str] | None = Field(
        default=None,
        description="With a project: the roles that may use it, or *. By default, the roles "
        "that need it.",
    )


class SecretUse(BaseModel):
    delivery: Delivery = Field(
        default=Delivery.SENT_FOR_YOU,
        description="sent_for_you (crewmind adds it to requests to the sites; agents never "
        "see it) or given (placed in the agent's sandbox, masked in everything it writes).",
    )
    sites: list[str] = Field(
        default_factory=list, description="Sent for you: the exact host names it is sent to."
    )
    header_kind: HeaderKind = Field(
        default=HeaderKind.BEARER,
        description="Sent for you: bearer, basic (with a user) or header.",
    )
    header_name: str | None = Field(default=None, description="The header, for header.")
    basic_user: str | None = Field(default=None, description="The user name, for basic.")
    shape: Shape = Field(default=Shape.TEXT, description="Given: text (a variable) or file.")
    env_name: str | None = Field(
        default=None, description="Given: the variable or file name. By default, from the name."
    )


class AddSecretInput(Placement, SecretUse):
    name: str = Field(description="What it is called, such as wordpress.")
    description: str = Field(
        min_length=1, max_length=300, description="What it is for, in one line. Agents read it."
    )
    value: SecretStr = Field(description="The value. It is encrypted and never shown again.")
    expires_on: date | None = Field(default=None, description="The day it stops working (UTC).")


class AddVariableInput(Placement):
    name: str = Field(description="What it is called.")
    description: str = Field(min_length=1, max_length=300, description="What it is for.")
    value: str = Field(description="The value. Variables are shown to members and agents.")
    env_name: str | None = Field(default=None, description="The environment variable name.")


class ConnectionRef(BaseModel):
    connection: str = Field(description="The connection's name or id.")
    project_id: str | None = Field(
        default=None, description="The project, to find a project connection by name."
    )


class ReplaceSecretInput(ConnectionRef):
    value: SecretStr = Field(description="The new value. The old one is gone.")


class ChangeSecretInput(ConnectionRef):
    description: str | None = Field(default=None, min_length=1, max_length=300)
    delivery: Delivery | None = None
    sites: list[str] | None = None
    header_kind: HeaderKind | None = None
    header_name: str | None = None
    basic_user: str | None = None
    shape: Shape | None = None
    env_name: str | None = None
    expires_on: date | None = Field(default=None, description="A new expiry day (UTC).")
    no_expiry: bool = Field(default=False, description="Remove the expiry date.")


class ChangeVariableInput(ConnectionRef):
    description: str | None = Field(default=None, min_length=1, max_length=300)
    value: str | None = None
    env_name: str | None = None


class ListInput(BaseModel):
    scope: Scope | None = Field(default=None, description="Only this scope.")
    project_id: str | None = Field(default=None, description="Include this project's own.")


class ItemList(BaseModel):
    items: list[ConnectionView]


class Usage(BaseModel):
    project_id: str
    project_name: str
    roles: list[str]
    env_name: str | None


class HistoryLine(BaseModel):
    at: datetime
    what: str
    by: str
    project_id: str | None


class ItemDetail(BaseModel):
    item: ConnectionView
    used_in: list[Usage] = Field(description="The projects you can see that use it.")
    hidden_uses: int = Field(description="Projects using it that you cannot see.")
    history: list[HistoryLine]


def _store(context: Context) -> SecretStore:
    return SecretStore(services_of(context).master_key_file)


def _use(use: SecretUse, name: str) -> ConnectionSecret:
    """CON-2, CON-6, CON-7: a secret's use, checked."""
    secret = ConnectionSecret(delivery=use.delivery, sites=[])
    if use.delivery == Delivery.SENT_FOR_YOU:
        sites = sorted({check_site(site) for site in use.sites})
        if not sites:
            raise Refusal(
                "sites_required",
                f"Name the sites {name} is sent to.",
                rule=CON_2.id,
                hint="Give the exact host, such as example.com, or give it to the agent instead.",
            )
        secret.sites, secret.header_kind = sites, use.header_kind
        if use.header_kind == HeaderKind.HEADER:
            secret.header_name = check_header_name(use.header_name or "")
        if use.header_kind == HeaderKind.BASIC:
            user = check_single_line(use.basic_user or "", "user_name")
            if not user or ":" in user:
                raise Refusal(
                    "basic_user_required",
                    "Basic sign-in needs a user name, without a colon.",
                    rule=CON_2.id,
                )
            secret.basic_user = user
    else:
        secret.shape = use.shape
    return secret


async def new_item(
    context: Context, kind: Kind, placement: Placement, name: str, description: str
) -> tuple[Connection, Project | None]:
    check_name(name)
    check_single_line(description, "description", CON_2.id)
    owner = await service.check_owner(
        context.session, context.caller, placement.scope, placement.project_id
    )
    await service.check_free(context.session, placement.scope, owner, name)
    project = None
    if placement.project_id is not None:
        project = await context.session.get(Project, placement.project_id)
        if (
            project is None
            or await role_in(context.session, context.caller.person_id, project.id) is None
        ):
            raise project_not_found()
        if not await service.chairs(context.session, context.caller, project.id):
            raise Refusal(
                "role_required",
                "Only the chairman or a co-chair attaches connections to a project.",
                kind=RefusalKind.FORBIDDEN,
                rule=CON_1.id,
            )
    CONNECTION_MACHINE.check("(new)", ConnectionState.ACTIVE)
    item = Connection(
        kind=kind,
        scope=placement.scope,
        owner_id=owner,
        name=name,
        name_key=name.lower(),
        description=description,
        state=ConnectionState.ACTIVE,
        created_by=context.caller.actor_id,
        created_at=context.now,
        changed_at=context.now,
        warned=[],
    )
    context.session.add(item)
    await context.session.flush()
    return item, project


def record_added(context: Context, item: Connection, extra: dict[str, object]) -> None:
    context.record(
        ADDED,
        subject=("connection", item.id),
        project_id=item.owner_id if item.scope == Scope.PROJECT else None,
        after={"name": item.name, "kind": item.kind, "scope": item.scope, **extra},
    )


@operation(
    "connections.add_secret",
    summary="Add a secret. Its value is encrypted and never shown again.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def add_secret(context: Context, payload: AddSecretInput) -> ConnectionView:
    """CON-1, CON-2, CON-4, CON-6, CON-7: a write-only value, used one way, owned by one
    scope; with a project, attached and granted at once."""
    await service.check_project(context.session, context.caller, payload.project_id)
    value = payload.value.get_secret_value()
    await service.check_value(context.session, services_of(context).settings, value, payload.name)
    item, project = await new_item(context, Kind.SECRET, payload, payload.name, payload.description)
    secret = _use(payload, payload.name)
    secret.connection_id = item.id
    if secret.delivery == Delivery.GIVEN:
        item.env_name = check_env_name(payload.env_name or default_env_name(payload.name))
    item.expires_on = payload.expires_on
    context.session.add(secret)
    await service.put_value(context.session, _store(context), item, value, context.now)
    await context.session.flush()
    record_added(context, item, {"delivery": secret.delivery, "sites": secret.sites})
    if project is not None:
        await attach.attach(context, project, item, payload.roles, None)
    return await item_view(context.session, context.caller, item)


@operation(
    "connections.add_variable",
    summary="Add a variable: a plain value members and agents can read.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def add_variable(context: Context, payload: AddVariableInput) -> ConnectionView:
    """CON-1, CON-3, CON-4: a plain value, placed in granted runs as an environment variable."""
    await service.check_project(context.session, context.caller, payload.project_id)
    await _check_variable_size(context, payload.value, payload.name)
    item, project = await new_item(
        context, Kind.VARIABLE, payload, payload.name, payload.description
    )
    item.env_name = check_env_name(payload.env_name or default_env_name(payload.name))
    context.session.add(ConnectionVariable(connection_id=item.id, value=payload.value))
    await context.session.flush()
    record_added(context, item, {"env_name": item.env_name})
    if project is not None:
        await attach.attach(context, project, item, payload.roles, None)
    return await item_view(context.session, context.caller, item)


async def _check_variable_size(context: Context, value: str, name: str) -> None:
    install = Subject(SettingScope.INSTALL, INSTALL_SUBJECT)
    largest = int(
        await services_of(context).settings.get(context.session, install, "secret.max_size")
    )
    if len(value.encode()) > largest:
        raise Refusal(
            "variable_too_large",
            f"The value of {name} is larger than {largest} bytes.",
            rule=CON_3.id,
        )


def _activate(context: Context, item: Connection) -> None:
    """CON-2, 7.18: a new value or expiry date brings an expired secret back."""
    if item.state == ConnectionState.EXPIRED:
        CONNECTION_MACHINE.check(item.state, ConnectionState.ACTIVE)
        context.record(
            STATE_CHANGED,
            subject=("connection", item.id),
            before={"state": item.state},
            after={"state": ConnectionState.ACTIVE, "name": item.name},
        )
        item.state = ConnectionState.ACTIVE


@operation(
    "connections.replace_secret",
    summary="Replace a secret's value. The old value is gone for good.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def replace_secret(context: Context, payload: ReplaceSecretInput) -> ConnectionView:
    """CON-2: replacing is the only change a value can have. It takes effect at each run's
    next request."""
    item = await service.manageable(
        context.session, context.caller, payload.connection, payload.project_id
    )
    if item.kind != Kind.SECRET:
        raise Refusal(
            "not_a_secret", f"{item.name} is not a secret.", rule=CON_2.id,
            hint="Change a variable with `connections change-variable`.",
        )  # fmt: skip
    value = payload.value.get_secret_value()
    await service.check_value(context.session, services_of(context).settings, value, item.name)
    await service.put_value(context.session, _store(context), item, value, context.now)
    item.changed_at = context.now
    context.record(REPLACED, subject=("connection", item.id), after={"name": item.name})
    _activate(context, item)
    await service.refresh_users(context.session, item, context.now, context.caller)
    return await item_view(context.session, context.caller, item)


@operation(
    "connections.change_secret",
    summary="Change what a secret is for, how it is used, or its expiry date.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def change_secret(context: Context, payload: ChangeSecretInput) -> ConnectionView:
    """CON-2, CON-4, CON-7: where a secret goes is the person's decision, so a model client
    cannot change it (IF-5.6). A change that would collide in a project is refused."""
    item = await service.manageable(
        context.session, context.caller, payload.connection, payload.project_id
    )
    secret = await context.session.get(ConnectionSecret, item.id)
    if item.kind != Kind.SECRET or secret is None:
        raise Refusal("not_a_secret", f"{item.name} is not a secret.", rule=CON_2.id)
    use = SecretUse(
        delivery=payload.delivery or Delivery(secret.delivery),
        sites=payload.sites if payload.sites is not None else list(secret.sites or []),
        header_kind=payload.header_kind or HeaderKind(secret.header_kind or HeaderKind.BEARER),
        header_name=payload.header_name if payload.header_name is not None else secret.header_name,
        basic_user=payload.basic_user if payload.basic_user is not None else secret.basic_user,
        shape=payload.shape or Shape(secret.shape or Shape.TEXT),
    )
    checked = _use(use, item.name)
    env = item.env_name
    if checked.delivery == Delivery.GIVEN:
        env = check_env_name(payload.env_name or item.env_name or default_env_name(item.name))
    else:
        env = None
    before = {"delivery": secret.delivery, "sites": secret.sites, "env_name": item.env_name}
    for link, project in await service.attachments(context.session, item.id):
        sites = (
            frozenset(str(site) for site in checked.sites or [])
            if checked.delivery == Delivery.SENT_FOR_YOU
            else frozenset[str]()
        )
        await service.check_collisions(
            context.session, project.id, item, list(link.roles or []),
            (link.env_name or env) if checked.delivery == Delivery.GIVEN else None, sites=sites,
        )  # fmt: skip
    secret.delivery, secret.sites, secret.header_kind = (
        checked.delivery,
        checked.sites,
        checked.header_kind,
    )
    secret.header_name, secret.basic_user, secret.shape = (
        checked.header_name,
        checked.basic_user,
        checked.shape,
    )
    item.env_name = env
    if payload.description is not None:
        item.description = check_single_line(payload.description, "description")
    if payload.no_expiry or payload.expires_on is not None:
        new_day = None if payload.no_expiry else payload.expires_on
        item.expires_on, item.warned = new_day, []
        if new_day is None or new_day >= context.now.date():
            _activate(context, item)
    item.changed_at = context.now
    context.record(
        CHANGED,
        subject=("connection", item.id),
        before=before,
        after={
            "name": item.name,
            "delivery": secret.delivery,
            "sites": secret.sites,
            "env_name": item.env_name,
            "expires_on": item.expires_on.isoformat() if item.expires_on else None,
        },
    )
    await service.refresh_users(context.session, item, context.now, context.caller)
    return await item_view(context.session, context.caller, item)


@operation(
    "connections.change_variable",
    summary="Change a variable's value, description or environment variable name.",
    authority=Authority.PERSON,
    reversibility=Reversibility.REVERSIBLE,
)
async def change_variable(context: Context, payload: ChangeVariableInput) -> ConnectionView:
    """CON-3, CON-4: a variable's change reaches each run at its next start."""
    item = await service.manageable(
        context.session, context.caller, payload.connection, payload.project_id
    )
    variable = await context.session.get(ConnectionVariable, item.id)
    if item.kind != Kind.VARIABLE or variable is None:
        raise Refusal("not_a_variable", f"{item.name} is not a variable.", rule=CON_3.id)
    before = {"env_name": item.env_name}
    if payload.env_name is not None and payload.env_name != item.env_name:
        env = check_env_name(payload.env_name)
        for link, project in await service.attachments(context.session, item.id):
            await service.check_collisions(
                context.session, project.id, item, list(link.roles or []), link.env_name or env
            )
        item.env_name = env
    if payload.value is not None:
        await _check_variable_size(context, payload.value, item.name)
        variable.value = payload.value
    if payload.description is not None:
        item.description = check_single_line(payload.description, "description", CON_3.id)
    item.changed_at = context.now
    context.record(
        CHANGED,
        subject=("connection", item.id),
        before=before,
        after={
            "name": item.name,
            "env_name": item.env_name,
            "value_changed": payload.value is not None,
        },
    )
    return await item_view(context.session, context.caller, item)


@operation(
    "connections.list",
    summary="List the secrets, variables and MCP servers you can use. Values are never shown.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def list_connections(context: Context, payload: ListInput) -> ItemList:
    """CON-1, CON-15: the install's, your own, and a project's you belong to."""
    await service.check_project(context.session, context.caller, payload.project_id)
    rows = await context.session.scalars(
        select(Connection)
        .where(Connection.state.in_(service.LIVE))
        .order_by(Connection.scope, Connection.name_key)
    )
    shown: list[ConnectionView] = []
    for row in rows:
        if payload.scope is not None and row.scope != payload.scope:
            continue
        if row.scope == Scope.PROJECT and row.owner_id != payload.project_id:
            continue
        if await service.can_see(context.session, context.caller, row):
            shown.append(await item_view(context.session, context.caller, row))
    return ItemList(items=shown)


_WHAT = {
    ADDED: "Added",
    REPLACED: "Value replaced",
    CHANGED: "Changed",
    STATE_CHANGED: "State changed",
}


@operation(
    "connections.show",
    summary="Show a connection: how it is used, where, and its history. Never its value.",
    authority=Authority.PERSON,
    reversibility=Reversibility.READ,
    principals=PERSON_AND_MCP,
    mcp_scope="read",
)
async def show_connection(context: Context, payload: ConnectionRef) -> ItemDetail:
    """CON-1, CON-15, CON-16: where it is used and its history, from the record."""
    item = await service.find(
        context.session, context.caller, payload.connection, payload.project_id
    )
    used: list[Usage] = []
    hidden = 0
    for link, project in await service.attachments(context.session, item.id):
        member = await role_in(context.session, context.caller.person_id, project.id)
        if member is None and not context.caller.is_admin:
            hidden += 1
            continue
        used.append(
            Usage(
                project_id=project.id,
                project_name=project.name,
                roles=[str(role) for role in link.roles or []],
                env_name=service.env_of(link, item),
            )
        )
    events = await context.session.scalars(
        select(Event)
        .where(Event.subject_kind == "connection", Event.subject_id == item.id)
        .order_by(Event.id.desc())
        .limit(50)
    )
    rows = list(events)
    people = await context.session.scalars(
        select(Person).where(Person.id.in_({event.actor_id for event in rows}))
    )
    names = {person.id: person.name or "someone" for person in people}
    history = [
        HistoryLine(
            at=event.at,
            what=_WHAT.get(event.type, event.type.split(".", 1)[1].replace("_", " ").capitalize()),
            by=names.get(
                event.actor_id, "the platform" if event.actor_kind != "person" else "someone"
            ),
            project_id=event.project_id,
        )
        for event in rows
    ]
    return ItemDetail(
        item=await item_view(context.session, context.caller, item),
        used_in=used,
        hidden_uses=hidden,
        history=history,
    )


@operation(
    "connections.delete",
    summary="Delete a connection: it is detached from every project and its value destroyed.",
    authority=Authority.PERSON,
    reversibility=Reversibility.IRREVERSIBLE,
)
async def delete_connection(context: Context, payload: ConnectionRef) -> ConnectionView:
    """CON-1, CON-2, CON-14: the value is destroyed, every attachment ends, and the seats
    that needed it are held. The row stays, without its value, for the record."""
    item = await service.manageable(
        context.session, context.caller, payload.connection, payload.project_id
    )
    for link, project in await service.attachments(context.session, item.id):
        await attach.detach(context, project, link, item)
    CONNECTION_MACHINE.check(item.state, ConnectionState.DELETED)
    context.record(
        STATE_CHANGED,
        subject=("connection", item.id),
        before={"state": item.state},
        after={"state": ConnectionState.DELETED, "name": item.name},
    )
    item.state, item.changed_at = ConnectionState.DELETED, context.now
    for secret_name in (SECRET_NAME, *OAUTH_SECRETS):
        await _store(context).delete(context.session, (SECRET_OWNER, item.id), secret_name)
    server = await context.session.get(McpServer, item.id)
    if server is not None and server.state != ServerState.DELETED:
        SERVER_MACHINE.check(server.state, ServerState.DELETED)
        server.state = ServerState.DELETED
    variable = await context.session.get(ConnectionVariable, item.id)
    if variable is not None:
        variable.value = ""
    await context.session.flush()
    return await item_view(context.session, context.caller, item)
