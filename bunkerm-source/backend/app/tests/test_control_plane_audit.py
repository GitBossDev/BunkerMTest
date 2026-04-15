from sqlalchemy import delete, select

from core.database import get_db
from main import app
from models.orm import BrokerDesiredState, BrokerDesiredStateAudit
import services.broker_desired_state_service as desired_state_svc


async def test_desired_state_changes_append_audit_rows(client):
    session_generator = app.dependency_overrides[get_db]()
    session = await anext(session_generator)
    try:
        await session.execute(
            delete(BrokerDesiredStateAudit).where(BrokerDesiredStateAudit.scope == desired_state_svc.DEFAULT_ACL_SCOPE)
        )
        await session.execute(
            delete(BrokerDesiredState).where(BrokerDesiredState.scope == desired_state_svc.DEFAULT_ACL_SCOPE)
        )
        await session.commit()

        await desired_state_svc.set_default_acl_desired(
            session,
            {
                "publishClientSend": True,
                "publishClientReceive": True,
                "subscribe": True,
                "unsubscribe": True,
            },
        )
        await desired_state_svc.set_default_acl_desired(
            session,
            {
                "publishClientSend": False,
                "publishClientReceive": True,
                "subscribe": False,
                "unsubscribe": True,
            },
        )

        audits = (
            await session.execute(
                select(BrokerDesiredStateAudit)
                .where(BrokerDesiredStateAudit.scope == desired_state_svc.DEFAULT_ACL_SCOPE)
                .order_by(BrokerDesiredStateAudit.version.asc(), BrokerDesiredStateAudit.id.asc())
            )
        ).scalars().all()

        assert [row.event_kind for row in audits] == ["desired_change", "desired_change"]
        assert [row.version for row in audits] == [1, 2]
        assert audits[-1].reconcile_status == "pending"
        assert '"publishClientSend": false' in (audits[-1].desired_payload_json or "")
    finally:
        await session_generator.aclose()