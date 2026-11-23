"""Which MCP scope reaches which operation (IF-5.2), and which verbs need the person
themselves (IF-5.6). This is the one table; an operation does not state its own scope
unless it is a read.

Four scopes; `read` is implied by every other one.
"""

from __future__ import annotations

READ, STEER, CREATE, CONFIGURE = "read", "steer", "create", "configure"
SCOPES = (READ, STEER, CREATE, CONFIGURE)

HUMAN_ONLY: dict[str, str] = {
    "credentials.add": "creating a credential value",
    "connections.add_secret": "creating a credential value",
    "connections.replace_secret": "creating a credential value",
    "connections.import_env": "creating a credential value",
    "connections.review_env": "reading pasted secret values",
    "connections.change_secret": "choosing where a secret is sent (CON-15)",
    "connections.delete": "deleting a connection (CON-15)",
    "connections.add_mcp_server": "adding an MCP server (CON-15)",
    "connections.test_mcp_server": "creating a credential value",
    "connections.allow_tool": "allowing a tool (IF-5.6)",
    "connections.sign_in": "signing in to an MCP server (CON-10)",
    "connections.finish_sign_in": "signing in to an MCP server (CON-10)",
    "members.add": "changing project membership",
    "members.remove": "changing project membership",
    "members.set_role": "changing project membership",
    "members.hand_on_chair": "handing on the chair",
    "members.break_glass_hand_on": "handing on the chair",
    "projects.delete": "deleting a project",
    "projects.confirm_delete": "deleting a project",
    "projects.cancel_delete": "deleting a project",
    "mcp_clients.mint": "giving a model client access (7.10)",
    "tokens.mint": "creating a credential value",
    "oauth.approve": "giving a model client access (7.10)",
}
"""IF-5.6: verbs that require the person, not their model client."""

NOT_FOR_CLIENTS: dict[str, str] = {
    "auth.login": "signing in is the person's own",
    "auth.logout": "signing out is the person's own",
    "auth.change_password": "the password is the person's own",
    "auth.set_name": "the name is the person's own",
    "auth.use_link": "a one-time link is the person's own",
    "people.invite": "instance administration",
    "people.deactivate": "instance administration",
    "people.reactivate": "instance administration",
    "people.reset_link": "instance administration",
    "people.set_role": "instance administration",
    "people.list": "instance administration",
    "settings.change_install": "instance administration",
    "settings.show_install": "instance administration",
    "library.reload": "instance administration",
    "record.list_install": "instance administration",
    "push.public_key": "a browser's own subscription",
    "push.subscribe": "a browser's own subscription",
    "push.unsubscribe": "a browser's own subscription",
    "tokens.list": "the person's own credentials",
    "tokens.revoke": "the person's own credentials",
    "mcp_clients.list": "the person's own credentials",
    "mcp_clients.revoke": "the person's own credentials",
    "oauth.register": "a step of the OAuth protocol itself",
    "oauth.token": "a step of the OAuth protocol itself",
    "oauth.clients": "the person's own credentials",
    "oauth.revoke": "the person's own credentials",
}
"""Operations no model client needs: the person's own account and the install's admin."""

_READ = (
    "chat.help",
    "credentials.list",
    "memory.preferences",
    "models.providers",
    "settings.show_mine",
    "uploads.status",
)
_CREATE = (
    "projects.create",
    "projects.promote",
    "projects.import_spec",
    "projects.clone",
    "founder.start",
    "founder.quick",
    "founder.say",
    "founder.answer",
    "founder.accept_rest",
    "founder.create",
    "founder.discard",
)
_CONFIGURE_GROUPS = (
    "roster",
    "settings",
    "models",
    "credentials",
    "roles",
    "crews",
    "connections",
)
_STEER_GROUPS = (
    "artifacts",
    "audits",
    "bets",
    "budget",
    "cards",
    "chat",
    "commitments",
    "corrections",
    "cycles",
    "decisions",
    "directives",
    "examples",
    "gaps",
    "grill",
    "items",
    "launches",
    "memory",
    "orders",
    "plan",
    "projects",
    "raises",
    "requirements",
    "reserve",
    "reviews",
    "runs",
    "uploads",
)


def scope_of(name: str) -> str | None:
    """The MCP scope that reaches a person's operation, or None when no client may call
    it. Reads that state their own scope do not come through here."""
    if name in HUMAN_ONLY or name in NOT_FOR_CLIENTS:
        return None
    if name in _READ:
        return READ
    if name in _CREATE:
        return CREATE
    group = name.split(".", 1)[0]
    if group in _CONFIGURE_GROUPS:
        return CONFIGURE
    if group in _STEER_GROUPS:
        return STEER
    return None


def granted(scopes: frozenset[str]) -> frozenset[str]:
    """`read` is implied by every other scope."""
    return scopes | {READ} if scopes else scopes
