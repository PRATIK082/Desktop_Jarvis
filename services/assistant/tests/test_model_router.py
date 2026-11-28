"""Privacy and ordering tests for the deterministic model router."""
from __future__ import annotations

import pytest

from jarvis.providers.router import (
    CloudApprovalRequired,
    CloudNotPermitted,
    DataClassification,
    ModelRouter,
    ProviderDescriptor,
    RoutingError,
    RoutingMode,
    RoutingRequest,
)


class FakeProvider:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy
        self.calls = 0

    async def health_check(self) -> bool:
        self.calls += 1
        return self.healthy


@pytest.mark.asyncio
async def test_healthy_local_is_preferred_even_when_cloud_is_allowed() -> None:
    local, cloud = FakeProvider(), FakeProvider()
    router = ModelRouter(
        {"ollama": local, "cloud": cloud},
        [
            ProviderDescriptor("ollama", True, frozenset({"chat"})),
            ProviderDescriptor("cloud", False, frozenset({"chat"})),
        ],
        mode=RoutingMode.CLOUD_ALLOWED,
        cloud_enabled=True,
    )
    decision = await router.select(RoutingRequest(cloud_consent=True))
    assert decision.provider_id == "ollama"
    assert decision.is_local
    assert cloud.calls == 0


@pytest.mark.asyncio
async def test_local_only_never_falls_back_to_cloud() -> None:
    cloud = FakeProvider()
    router = ModelRouter(
        {"cloud": cloud},
        [ProviderDescriptor("cloud", False, frozenset({"chat"}))],
        mode=RoutingMode.LOCAL_ONLY,
        cloud_enabled=True,
    )
    with pytest.raises(RoutingError):
        await router.select(RoutingRequest())
    assert cloud.calls == 0


@pytest.mark.asyncio
async def test_ask_before_cloud_requires_per_request_consent() -> None:
    cloud = FakeProvider()
    router = ModelRouter(
        {"cloud": cloud},
        [ProviderDescriptor("cloud", False, frozenset({"chat"}))],
        mode=RoutingMode.ASK_BEFORE_CLOUD,
        cloud_enabled=True,
    )
    with pytest.raises(CloudApprovalRequired):
        await router.select(RoutingRequest())
    assert cloud.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "classification",
    [DataClassification.SENSITIVE, DataClassification.RESTRICTED],
)
async def test_sensitive_data_never_uses_cloud(classification: DataClassification) -> None:
    cloud = FakeProvider()
    router = ModelRouter(
        {"cloud": cloud},
        [ProviderDescriptor("cloud", False, frozenset({"chat"}))],
        mode=RoutingMode.CLOUD_ALLOWED,
        cloud_enabled=True,
    )
    with pytest.raises(CloudNotPermitted):
        await router.select(RoutingRequest(classification=classification, cloud_consent=True))
    assert cloud.calls == 0


@pytest.mark.asyncio
async def test_cloud_allowed_requires_both_global_enablement_and_request_consent() -> None:
    cloud = FakeProvider()
    router = ModelRouter(
        {"cloud": cloud},
        [ProviderDescriptor("cloud", False, frozenset({"chat"}))],
        mode=RoutingMode.CLOUD_ALLOWED,
        cloud_enabled=False,
    )
    with pytest.raises(CloudNotPermitted):
        await router.select(RoutingRequest(cloud_consent=True))
    assert cloud.calls == 0


@pytest.mark.asyncio
async def test_cloud_route_requires_matching_capability() -> None:
    cloud = FakeProvider()
    router = ModelRouter(
        {"cloud": cloud},
        [ProviderDescriptor("cloud", False, frozenset({"chat"}))],
        mode=RoutingMode.CLOUD_ALLOWED,
        cloud_enabled=True,
    )
    with pytest.raises(RoutingError):
        await router.select(RoutingRequest(required_capabilities=frozenset({"vision"}), cloud_consent=True))
    assert cloud.calls == 0


@pytest.mark.asyncio
async def test_explicitly_approved_cloud_fallback_is_selectable() -> None:
    cloud = FakeProvider()
    router = ModelRouter(
        {"cloud": cloud},
        [ProviderDescriptor("cloud", False, frozenset({"chat"}))],
        mode=RoutingMode.CLOUD_ALLOWED,
        cloud_enabled=True,
    )
    decision = await router.select(RoutingRequest(cloud_consent=True))
    assert decision.provider_id == "cloud"
    assert not decision.is_local
