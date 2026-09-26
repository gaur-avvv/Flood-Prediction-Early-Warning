"""
Database setup using SQLAlchemy async (SQLite for local/Railway, PostgreSQL for production).
"""

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./flood_data.db",
)

# Railway injects PostgreSQL URL as postgres:// — convert to postgresql+asyncpg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    **({} if "sqlite" in DATABASE_URL else {"pool_size": 5, "max_overflow": 10}),
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables on startup and seed historical events if empty."""
    from database.models import ObservationRecord, LocationCache, FloodEvent  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed historical flood events from CSV if table is empty
    csv_candidates = [
        os.path.join(os.path.dirname(__file__), "..", "data", "historical_flood_events.csv"),
        os.path.join(os.path.dirname(__file__), "historical_flood_events.csv"),
    ]
    csv_file = next((p for p in csv_candidates if os.path.exists(p)), None)
    if csv_file:
        from sqlalchemy import select, func
        import pandas as pd
        from datetime import datetime
        async with get_session() as session:
            count = (await session.execute(select(func.count(FloodEvent.id)))).scalar_one_or_none() or 0
            if count == 0:
                df_events = pd.read_csv(csv_file)
                records = []
                for _, row in df_events.iterrows():
                    records.append(
                        FloodEvent(
                            lat=float(row["lat"]),
                            lon=float(row["lon"]),
                            event_date=datetime.strptime(str(row["date"]).strip(), "%Y-%m-%d"),
                            ward_id=str(row["ward_code"]),
                            inundation_depth_m=float(row["inundation_depth_m"]),
                            area_flooded_km2=float(row.get("area_flooded_km2", 1.0)),
                            duration_hours=float(row.get("duration_hours", 12.0)),
                            source=str(row.get("source", "historical_record")),
                            verified=bool(row.get("verified", True)),
                        )
                    )
                session.add_all(records)
                await session.commit()



@asynccontextmanager
async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
