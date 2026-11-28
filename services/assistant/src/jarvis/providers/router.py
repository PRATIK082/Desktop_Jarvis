"""Explicit local-first model routing with privacy and consent gates.

Routing is deterministic policy code. It never sends a request itself and
never treats model output as permission to use a cloud provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class RoutingMode(StrEnum):
    LOCAL_ONLY = "local_only"
    ASK_BEFORE_CLOUD = "ask_before_cloud"
    CLOUD_ALLOWED = "cloud_allowed"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    is_local: bool
    capabilities: frozenset[str]
    enabled: bool = True


@dataclass(frozen=True)
class RoutingRequest:
    required_capabilities: frozenset[str] = frozenset({"chat"})
    classification: DataClassification = DataClassification.INTERNAL
    cloud_consent: bool = False


@dataclass(frozen=True)
class RouteDecision:
    provider_id: str
    is_local: bool
    reason: str


class ProviderHealth(Protocol):
    async def health_check(self) -> bool: ...


class RoutingError(RuntimeError):
    """No eligible provider can safely satisfy a routing request."""


class CloudApprovalRequired(RoutingError):
    """A cloud route may work, but explicit per-request approval is missing."""


class CloudNotPermitted(RoutingError):
    """Privacy classification or policy forbids cloud processing."""


class ModelRouter:
    """Select a healthy local provider first; cloud is strictly opt-in."""

    def __init__(
        self,
        providers: dict[str, ProviderHealth],
        descriptors: list[ProviderDescriptor],
        mode: RoutingMode = RoutingMode.LOCAL_ONLY,
        cloud_enabled: bool = False,
    ) -> None:
        self._providers = providers
        self._descriptors = {item.provider_id: item for item in descriptors}
        self.mode = mode
        self.cloud_enabled = cloud_enabled

    async def select(self, request: RoutingRequest) -> RouteDecision:
        eligible = [
            item
            for item in self._descriptors.values()
            if item.enabled and request.required_capabilities.issubset(item.capabilities)
        ]

        # Always prefer a healthy local provider, regardless of cloud mode.
        for item in eligible:
            if item.is_local:
                provider = self._providers.get(item.provider_id)
                if provider is not None and await provider.health_check():
                    return RouteDecision(item.provider_id, True, "healthy local provider preferred")

        if self.mode is RoutingMode.LOCAL_ONLY:
            raise RoutingError("No healthy local provider satisfies the requested capabilities")

        if request.classification in {
            DataClassification.SENSITIVE,
            DataClassification.RESTRICTED,
        }:
            raise CloudNotPermitted("Sensitive or restricted data cannot be routed to cloud")

        cloud_candidates = [item for item in eligible if not item.is_local]
        if not cloud_candidates:
            raise RoutingError("No enabled cloud provider supports the requested capabilities")

        if self.mode is RoutingMode.ASK_BEFORE_CLOUD and not request.cloud_consent:
            raise CloudApprovalRequired("Cloud processing requires explicit approval for this request")

        if self.mode is not RoutingMode.CLOUD_ALLOWED and not request.cloud_consent:
            raise CloudApprovalRequired("Cloud processing has not been approved")

        if not self.cloud_enabled:
            raise CloudNotPermitted("Cloud providers are disabled in JARVIS settings")

        for item in cloud_candidates:
            provider = self._providers.get(item.provider_id)
            if provider is not None and await provider.health_check():
                return RouteDecision(item.provider_id, False, "explicitly permitted cloud fallback")

        raise RoutingError("No healthy cloud provider is available")
