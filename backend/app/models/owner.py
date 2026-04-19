"""
Owner — the single value object flowing through every request.

Replaces raw `user_id` arguments across the service layer. Services read
`owner.plan` and `owner.metaapi_account_id` instead of branching on
authenticated vs. anonymous.
"""

from dataclasses import dataclass
from typing import Literal

OwnerKind = Literal["user", "anon"]
PlanTier = Literal["anon", "free", "pro", "premium"]


@dataclass(frozen=True)
class Owner:
    id: str
    kind: OwnerKind
    plan: PlanTier
    metaapi_account_id: str | None

    def __post_init__(self):
        if self.kind == "anon" and self.plan != "anon":
            raise ValueError("anon owners must have plan='anon'")
        if self.kind == "anon" and self.metaapi_account_id is not None:
            raise ValueError("anon owners cannot bind metaapi accounts")
