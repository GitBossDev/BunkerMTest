"""Initial history/reporting schema.

Revision ID: 001_history_reporting_initial
Revises:
Create Date: 2026-04-16
"""

from __future__ import annotations

from alembic import op

from models.orm import (
    BrokerDailySummary,
    BrokerMetricTick,
    BrokerRuntimeState,
    ClientDailyDistinctTopic,
    ClientDailySummary,
    ClientRegistry,
    ClientSessionEvent,
    ClientSubscriptionState,
    ClientTopicEvent,
    TopicPublishBucket,
    TopicRegistry,
    TopicSubscribeBucket,
)


revision = "001_history_reporting_initial"
down_revision = None
branch_labels = None
depends_on = None


TABLES = [
    BrokerMetricTick.__table__,
    BrokerRuntimeState.__table__,
    BrokerDailySummary.__table__,
    TopicRegistry.__table__,
    TopicPublishBucket.__table__,
    TopicSubscribeBucket.__table__,
    ClientRegistry.__table__,
    ClientSessionEvent.__table__,
    ClientTopicEvent.__table__,
    ClientSubscriptionState.__table__,
    ClientDailySummary.__table__,
    ClientDailyDistinctTopic.__table__,
]


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind=bind, checkfirst=True)