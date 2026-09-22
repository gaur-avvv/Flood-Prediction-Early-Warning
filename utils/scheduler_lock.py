"""DB-backed leader election for the APScheduler instance (Sprint 0 / T-31).

Prevents duplicate nightly retrains / hourly syncs when more than one app
instance shares the same DATABASE_URL. The leader writes a heartbeat row;
a standby whose heartbeat is stale (>180 s) takes over. Single-instance
SQLite deployments always acquire the lock immediately.
"""

import logging
import os
import socket
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.db import get_session
from database.models import SchedulerLockRecord

logger = logging.getLogger(__name__)

LOCK_ID = 1


class SchedulerLock:
    def __init__(self, stale_after_seconds: int = 180):
        self.holder = f"{socket.gethostname()}:{os.getpid()}"
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.is_leader = False

    async def acquire(self) -> bool:
        now = datetime.utcnow()
        try:
            async with get_session() as session:
                record = (
                    await session.execute(
                        select(SchedulerLockRecord).where(SchedulerLockRecord.id == LOCK_ID)
                    )
                ).scalar_one_or_none()
                if record is None:
                    session.add(
                        SchedulerLockRecord(id=LOCK_ID, holder=self.holder, heartbeat=now)
                    )
                    try:
                        await session.commit()
                        self.is_leader = True
                    except IntegrityError:
                        await session.rollback()
                        self.is_leader = False
                elif record.holder == self.holder or record.heartbeat < now - self.stale_after:
                    record.holder = self.holder
                    record.heartbeat = now
                    await session.commit()
                    self.is_leader = True
                else:
                    self.is_leader = False
        except Exception as exc:
            logger.warning("Scheduler lock acquisition failed (%s) – running as leader", exc)
            self.is_leader = True  # fail-open: a broken DB must not silence retraining
        logger.info(
            "Scheduler lock %s (holder=%s)",
            "acquired" if self.is_leader else "held by another instance – standby",
            self.holder,
        )
        return self.is_leader

    async def renew(self):
        if not self.is_leader:
            return
        try:
            async with get_session() as session:
                record = await session.get(SchedulerLockRecord, LOCK_ID)
                if record and record.holder == self.holder:
                    record.heartbeat = datetime.utcnow()
                    await session.commit()
                else:
                    self.is_leader = False
        except Exception as exc:
            logger.warning("Scheduler lock renewal failed: %s", exc)

    async def release(self):
        if not self.is_leader:
            return
        try:
            async with get_session() as session:
                record = await session.get(SchedulerLockRecord, LOCK_ID)
                if record and record.holder == self.holder:
                    await session.delete(record)
                    await session.commit()
        except Exception as exc:
            logger.warning("Scheduler lock release failed: %s", exc)
        self.is_leader = False
