"""Policy engine (Agent.md §11).

Decides whether a proposed tool call is allowed, denied, or requires approval.

Risk levels:
  Level 0 — conversational response / local read-only calculations; no approval.
  Level 1 — reads from explicitly approved resources; approval may be remembered
            per category.
  Level 2 — creates or changes local data; opens applications or URLs; always
            show a clear preview unless a narrow remembered rule exists.
  Level 3 — destructive, security-sensitive, financial, credential-related, or
            privacy-sensitive; deny by default in this version.

Remembered permissions are scoped, editable, revocable, recorded, and denied if
a request exceeds the stored scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Any


class RiskLevel(int, Enum):
    LEVEL_0 = 0  # conversational / read-only calc; no approval
    LEVEL_1 = 1  # read approved resources; rememberable per category
    LEVEL_2 = 2  # create/change data, open apps/URLs; preview unless remembered
    LEVEL_3 = 3  # destructive/security/financial/credential/privacy; deny by default


class PolicyDecision(StrEnum):
    ALLOW = "allow"          # execute without further user interaction
    DENY = "deny"            # reject; do not execute
    REQUIRE_APPROVAL = "require_approval"  # show approval card to user


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    risk_level: RiskLevel
    reason: str
    requires_approval: bool = False
    remembered_permission_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class RememberedPermission:
    id: str
    tool_id: str
    permission_category: str
    scope: dict[str, Any]  # narrowed scope the user approved
    created_at: str
    updated_at: str
    revoked: bool = False

    def covers(self, tool_id: str, category: str, args: dict[str, Any]) -> bool:
        """Return True if this remembered permission covers the request."""
        if self.revoked:
            return False
        if self.tool_id != tool_id:
            return False
        if self.permission_category != category:
            return False
        # Scope narrowing: every key/value in scope must match args.
        for key, value in self.scope.items():
            if args.get(key) != value:
                return False
        return True


@dataclass
class PolicyEngine:
    """Evaluates tool proposals against risk levels and remembered permissions."""

    def __init__(self) -> None:
        self._remembered: dict[str, RememberedPermission] = {}
        self._decisions: list[dict[str, object]] = []  # audit trail

    # ── public API -------------------------------------------------------

    def evaluate(
        self,
        tool_id: str,
        args: dict[str, Any],
        risk_level: RiskLevel,
        permission_category: str,
    ) -> PolicyResult:
        """Decide allow / deny / require_approval for a tool proposal."""

        # Level 3: deny by default in this version.
        if risk_level == RiskLevel.LEVEL_3:
            result = PolicyResult(
                decision=PolicyDecision.DENY,
                risk_level=risk_level,
                reason="level 3 actions are denied by default",
                error_code="level3_denied_by_default",
            )
            self._record(tool_id, args, risk_level, result)
            return result

        # Check remembered (narrow) permission first.
        remembered = self._find_remembered(tool_id, permission_category, args)
        if remembered is not None:
            result = PolicyResult(
                decision=PolicyDecision.ALLOW,
                risk_level=risk_level,
                reason=f"covered by remembered permission {remembered.id}",
                remembered_permission_id=remembered.id,
            )
            self._record(tool_id, args, risk_level, result)
            return result

        # Level 0: no approval needed.
        if risk_level == RiskLevel.LEVEL_0:
            result = PolicyResult(
                decision=PolicyDecision.ALLOW,
                risk_level=risk_level,
                reason="level 0 read-only action; no approval required",
            )
            self._record(tool_id, args, risk_level, result)
            return result

        # Level 1: reads from approved resources; approval may be remembered.
        if risk_level == RiskLevel.LEVEL_1:
            result = PolicyResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                risk_level=risk_level,
                reason="level 1 read action requires approval (may be remembered per category)",
                requires_approval=True,
            )
            self._record(tool_id, args, risk_level, result)
            return result

        # Level 2: creates/changes data, opens apps/URLs; always preview unless
        # a narrow remembered rule exists (none matched above).
        if risk_level == RiskLevel.LEVEL_2:
            result = PolicyResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                risk_level=risk_level,
                reason="level 2 state-changing action requires approval and a clear preview",
                requires_approval=True,
            )
            self._record(tool_id, args, risk_level, result)
            return result

        # Fallback: deny unknown risk levels.
        result = PolicyResult(
            decision=PolicyDecision.DENY,
            risk_level=risk_level,
            reason="unknown risk level; denied by default",
            error_code="unknown_risk_level",
        )
        self._record(tool_id, args, risk_level, result)
        return result

    def remember_permission(
        self,
        permission_id: str,
        tool_id: str,
        permission_category: str,
        scope: dict[str, Any],
    ) -> RememberedPermission:
        """Record a user-approved narrow permission (scoped, editable, revocable)."""
        now = datetime.now(UTC).isoformat()
        perm = RememberedPermission(
            id=permission_id,
            tool_id=tool_id,
            permission_category=permission_category,
            scope=dict(scope),
            created_at=now,
            updated_at=now,
            revoked=False,
        )
        self._remembered[permission_id] = perm
        return perm

    def revoke_permission(self, permission_id: str) -> bool:
        """Revoke a remembered permission."""
        perm = self._remembered.get(permission_id)
        if perm is None:
            return False
        # Dataclass is frozen; replace with revoked copy.
        revoked = RememberedPermission(
            id=perm.id,
            tool_id=perm.tool_id,
            permission_category=perm.permission_category,
            scope=dict(perm.scope),
            created_at=perm.created_at,
            updated_at=datetime.now(UTC).isoformat(),
            revoked=True,
        )
        self._remembered[permission_id] = revoked
        return True

    def list_remembered(self, include_revoked: bool = False) -> list[RememberedPermission]:
        return [
            p for p in self._remembered.values() if include_revoked or not p.revoked
        ]

    def get_decision_audit(self) -> list[dict[str, object]]:
        """Return a copy of the policy decision audit trail."""
        return list(self._decisions)

    # ── internal ---------------------------------------------------------

    def _find_remembered(
        self,
        tool_id: str,
        category: str,
        args: dict[str, Any],
    ) -> RememberedPermission | None:
        for perm in self._remembered.values():
            if perm.covers(tool_id, category, args):
                return perm
        return None

    def _record(
        self,
        tool_id: str,
        args: dict[str, Any],
        risk_level: RiskLevel,
        result: PolicyResult,
    ) -> None:
        self._decisions.append(
            {
                "tool_id": tool_id,
                "args": args,
                "risk_level": int(risk_level),
                "decision": result.decision.value,
                "reason": result.reason,
                "requires_approval": result.requires_approval,
                "remembered_permission_id": result.remembered_permission_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
