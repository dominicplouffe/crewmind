"""Every table. Import from here so the metadata is complete."""

from crewmind.storage.models.accounts import (
    BrowserSession,
    Link,
    LoginAttempts,
    Membership,
    Person,
    Token,
)
from crewmind.storage.models.base import Base, new_id
from crewmind.storage.models.conversation import Channel, Message, ReadPosition
from crewmind.storage.models.execution import (
    LedgerLine,
    Notice,
    Role,
    Run,
    RunRefusal,
    RunStep,
    Seat,
    Team,
    Wake,
)
from crewmind.storage.models.models import (
    Lineup,
    ModelCredential,
    ProjectCredential,
    ProviderCeiling,
)
from crewmind.storage.models.projects import HoldReason, Project
from crewmind.storage.models.record import Event, IdempotencyKey, SettingValue, StoredSecret

__all__ = [
    "Base",
    "BrowserSession",
    "Channel",
    "Event",
    "HoldReason",
    "IdempotencyKey",
    "LedgerLine",
    "Lineup",
    "Link",
    "LoginAttempts",
    "Membership",
    "Message",
    "ModelCredential",
    "Notice",
    "Person",
    "Project",
    "ProjectCredential",
    "ProviderCeiling",
    "ReadPosition",
    "Role",
    "Run",
    "RunRefusal",
    "RunStep",
    "Seat",
    "SettingValue",
    "StoredSecret",
    "Team",
    "Token",
    "Wake",
    "new_id",
]
