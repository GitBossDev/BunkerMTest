from __future__ import annotations

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.database_migrations import upgrade_control_plane_database
from core.database_url import get_async_engine_connect_args
from models.orm import BrokerDesiredState, BrokerDesiredStateAudit
import services.broker_desired_state_service as desired_state_svc
from tests.postgres_integration_support import require_real_postgres


@pytest.mark.asyncio
@pytest.mark.integration
async def test_control_plane_persists_desired_state_and_audit_in_real_postgres():
    database_url = require_real_postgres()
    await upgrade_control_plane_database(database_url)
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args=get_async_engine_connect_args(database_url),
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            await session.execute(
                delete(BrokerDesiredStateAudit).where(
                    BrokerDesiredStateAudit.scope == desired_state_svc.DEFAULT_ACL_SCOPE
                )
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

            state = await session.get(BrokerDesiredState, desired_state_svc.DEFAULT_ACL_SCOPE)
            audits = (
                await session.execute(
                    select(BrokerDesiredStateAudit)
                    .where(BrokerDesiredStateAudit.scope == desired_state_svc.DEFAULT_ACL_SCOPE)
                    .order_by(BrokerDesiredStateAudit.version.asc(), BrokerDesiredStateAudit.id.asc())
                )
            ).scalars().all()

            assert state is not None
            assert state.version == 2
            assert state.reconcile_status == "pending"
            assert len(audits) == 2
            assert [row.version for row in audits] == [1, 2]
            assert audits[-1].event_kind == "desired_change"
            assert '"publishClientSend": false' in (audits[-1].desired_payload_json or "")
    finally:
        await engine.dispose()