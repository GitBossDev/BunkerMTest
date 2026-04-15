"""Tests para el scope futuro broker.bridge_bundle."""
from __future__ import annotations

from models.orm import BrokerDesiredState
import services.broker_desired_state_service as desired_state_svc


class FakeSession:
    def __init__(self):
        self.state: BrokerDesiredState | None = None

    async def get(self, model, scope):
        if self.state is not None and self.state.scope == scope:
            return self.state
        return None

    def add(self, state):
        self.state = state

    async def commit(self):
        return None

    async def refresh(self, state):
        self.state = state
        return None


async def test_bridge_bundle_status_returns_unmanaged_without_desired_state():
    """El scope de bridges futuros existe en el modelo pero arranca como unmanaged."""
    session = FakeSession()
    status = await desired_state_svc.get_bridge_bundle_status(session)

    assert status["scope"] == desired_state_svc.BRIDGE_BUNDLE_SCOPE
    assert status["status"] == "unmanaged"
    assert status["activeInProductSurface"] is False


async def test_set_bridge_bundle_desired_persists_deferred_scope():
    """Guardar el placeholder bridge bundle deja estado auditable y explícitamente deferred."""
    session = FakeSession()
    state = await desired_state_svc.set_bridge_bundle_desired(
        session,
        {
            "requestedBy": "test",
            "bridges": [
                {
                    "name": "aws-outbound",
                    "provider": "aws",
                    "enabled": False,
                    "topics": ["site/1/#"],
                    "certRefs": ["bridge-ca.pem"],
                },
                {"name": "", "provider": "azure"},
            ],
        },
    )
    status = await desired_state_svc.get_bridge_bundle_status(session)

    assert state.scope == desired_state_svc.BRIDGE_BUNDLE_SCOPE
    assert status["status"] == "deferred"
    assert status["desired"]["requestedBy"] == "test"
    assert status["desired"]["bridges"] == [
        {
            "name": "aws-outbound",
            "provider": "aws",
            "enabled": False,
            "topics": ["site/1/#"],
            "certRefs": ["bridge-ca.pem"],
        }
    ]
    assert status["lastError"] == "bridge scope defined but not active in product surface"
    assert status["activeInProductSurface"] is False