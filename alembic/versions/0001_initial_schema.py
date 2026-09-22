"""Initial schema + PostGIS enablement (T-30).

Creates the existing tables (observations, location_cache, flood_events,
scheduler_lock) and, on PostgreSQL only, enables PostGIS with a generated
geography column + GiST index for spatial queries. Downgrade rolls everything
back. On SQLite the PostGIS steps are skipped.
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    try:
        return op.get_bind().dialect.name == "postgresql"
    except Exception:
        return False


def upgrade() -> None:
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("date_time", sa.DateTime(), nullable=False),
        sa.Column("rainfall_1h_mm", sa.Float(), server_default="0"),
        sa.Column("rainfall_24h_mm", sa.Float(), server_default="0"),
        sa.Column("river_discharge_m3s", sa.Float(), server_default="0"),
        sa.Column("discharge_anomaly_ratio", sa.Float(), server_default="0"),
        sa.Column("flood_occurred", sa.Integer(), server_default="0"),
        sa.Column("inundation_depth_m", sa.Float(), server_default="0"),
    )
    op.create_index("ix_observations_lat", "observations", ["lat"])
    op.create_index("ix_observations_lon", "observations", ["lon"])
    op.create_index(
        "ix_obs_latlon_time", "observations", ["lat", "lon", "date_time"]
    )

    op.create_table(
        "location_cache",
        sa.Column("lat", sa.Float(), primary_key=True),
        sa.Column("lon", sa.Float(), primary_key=True),
        sa.Column("last_synced", sa.DateTime(), nullable=True),
        sa.Column("data_source", sa.String(50), server_default="open-meteo"),
        sa.Column("total_records", sa.Integer(), server_default="0"),
    )

    op.create_table(
        "flood_events",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("event_date", sa.DateTime(), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("inundation_depth_m", sa.Float(), server_default="0"),
        sa.Column("area_flooded_km2", sa.Float(), server_default="0"),
        sa.Column("duration_hours", sa.Float(), server_default="1"),
        sa.Column("source", sa.String(200), server_default="synthetic"),
        sa.Column("verified", sa.Boolean(), server_default="0"),
    )
    op.create_index("ix_flood_latlon", "flood_events", ["lat", "lon"])

    op.create_table(
        "scheduler_lock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("holder", sa.String(200), nullable=False),
        sa.Column("heartbeat", sa.DateTime(), nullable=False),
    )

    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute(
            "ALTER TABLE observations ADD COLUMN IF NOT EXISTS geom "
            "geography(Point, 4326) GENERATED ALWAYS AS "
            "(ST_SetSRID(ST_MakePoint(lon, lat), 4326))::geography STORED"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_observations_geom "
            "ON observations USING GIST (geom)"
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_observations_geom")
        op.execute("ALTER TABLE observations DROP COLUMN IF EXISTS geom")
    op.drop_table("scheduler_lock")
    op.drop_table("flood_events")
    op.drop_table("location_cache")
    op.drop_index("ix_obs_latlon_time", table_name="observations")
    op.drop_index("ix_observations_lat", table_name="observations")
    op.drop_index("ix_observations_lon", table_name="observations")
    op.drop_table("observations")
