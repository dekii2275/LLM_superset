import io
import logging
import re
from typing import Any

import pandas as pd
from sqlalchemy import text

from app.db.database import engine
from app.services.superset import SupersetClient

logger = logging.getLogger(__name__)


def init_data_tables() -> None:
    """Initialize metadata tables and views for dataset settings if not exist."""
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw;"))
            conn.execute(
                text("""
                CREATE TABLE IF NOT EXISTS public.dataset_dashboard_settings (
                    dataset_id INT PRIMARY KEY,
                    dashboard_id INT NULL,
                    is_enabled BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.business_glossary (
                    id SERIAL PRIMARY KEY,
                    dataset_id INT NOT NULL,
                    term VARCHAR(255) NOT NULL,
                    target_type VARCHAR(50) NOT NULL,
                    target_name VARCHAR(255) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.verified_metrics (
                    id SERIAL PRIMARY KEY,
                    dataset_id INT NOT NULL,
                    metric_name VARCHAR(255) NOT NULL,
                    display_name VARCHAR(255) NOT NULL,
                    sql_expression TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.chat_sessions (
                    id VARCHAR(64) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    dataset_id INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(64) REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
                    sender VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    display_name VARCHAR(100) NOT NULL,
                    role VARCHAR(20) NOT NULL DEFAULT 'viewer',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.user_dataset_rls (
                    id SERIAL PRIMARY KEY,
                    user_id INT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    dataset_id INT NOT NULL,
                    filter_clause TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS public.system_alerts (
                    id SERIAL PRIMARY KEY,
                    dataset_id INT,
                    alert_type VARCHAR(50) NOT NULL,
                    severity VARCHAR(20) NOT NULL DEFAULT 'warning',
                    title VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    metric_name VARCHAR(100),
                    change_percent FLOAT,
                    suggested_query TEXT,
                    is_read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            )

            # Seed default glossary and verified metrics if empty
            glossary_count = (
                conn.execute(text("SELECT COUNT(*) FROM public.business_glossary")).scalar() or 0
            )
            if glossary_count == 0:
                conn.execute(
                    text("""
                    INSERT INTO public.business_glossary (dataset_id, term, target_type, target_name, description) VALUES
                    (1, 'doanh thu', 'column', 'total_amount', 'Tổng doanh thu tiền cước taxi'),
                    (1, 'tiền thu về', 'column', 'total_amount', 'Tổng tiền thu từ chuyến đi'),
                    (1, 'quãng đường', 'column', 'trip_distance', 'Khoảng cách di chuyển của chuyến đi'),
                    (1, 'khoảng cách', 'column', 'trip_distance', 'Khoảng cách di chuyển của chuyến đi'),
                    (1, 'tiền tip', 'column', 'tip_amount', 'Tiền tip của khách'),
                    (1, 'hành khách', 'column', 'passenger_count', 'Số lượng hành khách'),
                    (1, 'số chuyến', 'metric', 'total_trips', 'Tổng số lượt chuyến đi'),
                    (2, 'doanh thu', 'column', 'total_amount', 'Tổng doanh thu tiền cước taxi'),
                    (2, 'tiền thu về', 'column', 'total_amount', 'Tổng tiền thu từ chuyến đi'),
                    (5, 'dân số', 'column', 'population_max', 'Dân số tối đa của địa điểm'),
                    (5, 'số dân', 'column', 'population_max', 'Dân số tối đa của địa điểm'),
                    (5, 'thủ đô', 'column', 'is_capital', 'Có phải thủ đô hay không (1 hoặc 0)'),
                    (5, 'quốc gia', 'column', 'country', 'Tên quốc gia');
                """)
                )

            metrics_count = (
                conn.execute(text("SELECT COUNT(*) FROM public.verified_metrics")).scalar() or 0
            )
            if metrics_count == 0:
                conn.execute(
                    text("""
                    INSERT INTO public.verified_metrics (dataset_id, metric_name, display_name, sql_expression, description) VALUES
                    (1, 'total_trips', 'Tổng số chuyến đi', 'COUNT(*)', 'Số lượng lượt chuyến đi'),
                    (1, 'gross_revenue', 'Tổng doanh thu', 'SUM(total_amount)', 'Tổng doanh thu thu về từ cước taxi'),
                    (1, 'avg_trip_distance', 'Quãng đường trung bình', 'AVG(trip_distance)', 'Quãng đường di chuyển trung bình'),
                    (1, 'avg_fare', 'Cước phí trung bình', 'AVG(fare_amount)', 'Giá cước cơ bản trung bình'),
                    (2, 'total_trips', 'Tổng số chuyến đi', 'COUNT(*)', 'Số lượng lượt chuyến đi'),
                    (2, 'gross_revenue', 'Tổng doanh thu', 'SUM(total_amount)', 'Tổng doanh thu thu về từ cước taxi'),
                    (5, 'total_places', 'Tổng số địa điểm', 'COUNT(*)', 'Tổng số địa điểm/thành phố'),
                    (5, 'total_population', 'Tổng dân số', 'SUM(population_max)', 'Tổng dân số cộng dồn của các địa điểm'),
                    (5, 'avg_population', 'Dân số trung bình', 'AVG(population_max)', 'Dân số trung bình trên mỗi thành phố');
                """)
                )
            # Ensure virtual view raw.nyc_taxi_analysis exists
            conn.execute(
                text("""
                CREATE OR REPLACE VIEW raw.nyc_taxi_analysis AS
                SELECT
                    trips.*,
                    pickup.borough AS pickup_borough,
                    pickup.zone AS pickup_zone,
                    dropoff.borough AS dropoff_borough,
                    dropoff.zone AS dropoff_zone,
                    CASE trips.vendor_id
                        WHEN 1 THEN 'Creative Mobile Technologies'
                        WHEN 2 THEN 'Curb Mobility'
                        WHEN 6 THEN 'Myle Technologies'
                        WHEN 7 THEN 'Helix'
                        ELSE 'Vendor ' || COALESCE(trips.vendor_id::text, 'Unknown')
                    END AS vendor_name,
                    CASE trips.payment_type
                        WHEN 1 THEN 'Credit Card'
                        WHEN 2 THEN 'Cash'
                        WHEN 3 THEN 'No Charge'
                        WHEN 4 THEN 'Dispute'
                        WHEN 5 THEN 'Unknown'
                        WHEN 6 THEN 'Voided Trip'
                        ELSE 'Other'
                    END AS payment_type_name,
                    TRIM(TO_CHAR(trips.tpep_pickup_datetime, 'FMDay')) AS day_of_week,
                    CASE
                        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 5 AND 6 THEN 'Early Morning'
                        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 7 AND 11 THEN 'Morning'
                        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 12 AND 16 THEN 'Afternoon'
                        WHEN EXTRACT(HOUR FROM trips.tpep_pickup_datetime) BETWEEN 17 AND 20 THEN 'Evening'
                        ELSE 'Night'
                    END AS time_of_day
                FROM raw.yellow_taxi_trips AS trips
                LEFT JOIN raw.taxi_zone_lookup AS pickup ON trips.pu_location_id = pickup.location_id
                LEFT JOIN raw.taxi_zone_lookup AS dropoff ON trips.do_location_id = dropoff.location_id;
            """)
            )

            # Seed default users & RLS rules
            from app.services.auth_service import AuthService

            AuthService.seed_default_users()
    except Exception as e:
        logger.warning(f"Failed to initialize dataset_dashboard_settings or views: {e}")


class DataService:
    def __init__(self, superset_client: SupersetClient | None = None) -> None:
        self.superset = superset_client
        init_data_tables()

    @staticmethod
    def sanitize_identifier(name: str) -> str:
        """Sanitize table or column name into a safe snake_case SQL identifier."""
        name = name.strip().lower()
        name = re.sub(r"[^\w\s-]", "", name)
        name = re.sub(r"[\s-]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        if not name or name[0].isdigit():
            name = f"col_{name}"
        return name[:60]

    def read_file_to_df(self, filename: str, content: bytes) -> pd.DataFrame:
        """Parse uploaded file (CSV or Parquet) into a pandas DataFrame."""
        lower_name = filename.lower()
        if lower_name.endswith(".parquet") or lower_name.endswith(".pq"):
            return pd.read_parquet(io.BytesIO(content))
        elif lower_name.endswith(".csv") or lower_name.endswith(".txt"):
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    return pd.read_csv(io.BytesIO(content), encoding=encoding)
                except UnicodeDecodeError:
                    continue
            return pd.read_csv(io.BytesIO(content))
        else:
            raise ValueError(
                "Định dạng tệp không được hỗ trợ. Vui lòng tải lên tệp .csv hoặc .parquet."
            )

    def upload_dataset(
        self,
        filename: str,
        content: bytes,
        table_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Ingests CSV or Parquet into PostgreSQL raw schema and registers in Superset."""
        df = self.read_file_to_df(filename, content)
        if df.empty:
            raise ValueError("Tệp dữ liệu trống hoặc không có dòng nào.")

        # Sanitize table name
        raw_table_name = table_name or filename.rsplit(".", 1)[0]
        sanitized_table = self.sanitize_identifier(raw_table_name)
        if not sanitized_table:
            sanitized_table = f"dataset_{int(pd.Timestamp.now().timestamp())}"

        # Sanitize columns
        original_cols = list(df.columns)
        new_cols = []
        seen = set()
        for col in original_cols:
            clean = self.sanitize_identifier(str(col))
            candidate = clean
            counter = 1
            while candidate in seen:
                candidate = f"{clean}_{counter}"
                counter += 1
            seen.add(candidate)
            new_cols.append(candidate)
        df.columns = new_cols

        # Save to PostgreSQL
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw;"))

        df.to_sql(sanitized_table, schema="raw", con=engine, if_exists="replace", index=False)

        # Register in Superset
        superset_dataset_id: int | None = None
        if self.superset:
            try:
                # Find database ID (default 1)
                dbs = self.superset.request("GET", "/api/v1/database/").get("result", [])
                db_id = dbs[0].get("id") if dbs else 1

                # Check if dataset already exists in Superset
                existing_list = self.superset.list_datasets()
                found = next(
                    (
                        d
                        for d in existing_list
                        if d.get("table_name") == sanitized_table and d.get("schema") == "raw"
                    ),
                    None,
                )
                if found:
                    superset_dataset_id = found.get("id")
                else:
                    create_res = self.superset.request(
                        "POST",
                        "/api/v1/dataset/",
                        {
                            "database": db_id,
                            "schema": "raw",
                            "table_name": sanitized_table,
                        },
                    )
                    superset_dataset_id = create_res.get("id")
            except Exception as e:
                logger.warning(f"Could not register dataset in Superset: {e}")

        # Build column metadata
        columns_meta = []
        for col in df.columns:
            dtype_str = str(df[col].dtype)
            columns_meta.append(
                {
                    "name": col,
                    "type": dtype_str,
                    "sample": [str(x) for x in df[col].dropna().head(3).tolist()],
                }
            )

        # Sample rows (first 10)
        sample_rows = df.head(10).fillna("").to_dict(orient="records")

        return {
            "dataset_id": superset_dataset_id,
            "table_name": sanitized_table,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": columns_meta,
            "sample_rows": sample_rows,
            "description": description or f"Bảng dữ liệu {sanitized_table} tải lên từ {filename}",
        }

    def preview_dataset(self, table_name: str, limit: int = 20) -> dict[str, Any]:
        """Fetch column info and first N rows from raw.<table_name>."""
        sanitized = self.sanitize_identifier(table_name)
        with engine.connect() as conn:
            # Check row count
            count_res = conn.execute(text(f"SELECT COUNT(*) FROM raw.{sanitized}"))
            total_rows = count_res.scalar() or 0

            # Fetch rows
            rows_res = conn.execute(text(f"SELECT * FROM raw.{sanitized} LIMIT {limit}"))
            cols = list(rows_res.keys())
            raw_rows = rows_res.fetchall()
            rows_data = [
                dict(zip(cols, [str(v) if v is not None else "" for v in row])) for row in raw_rows
            ]

            # Fetch column types from information_schema
            type_res = conn.execute(
                text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'raw' AND table_name = :tbl
                ORDER BY ordinal_position
            """),
                {"tbl": sanitized},
            )
            col_types = {r[0]: r[1] for r in type_res.fetchall()}

        return {
            "table_name": sanitized,
            "total_rows": total_rows,
            "column_count": len(cols),
            "columns": [{"name": c, "type": col_types.get(c, "unknown")} for c in cols],
            "rows": rows_data,
        }

    def list_all_dashboards(self) -> list[dict[str, Any]]:
        """List all Superset dashboards available for linking."""
        if not self.superset:
            return []
        try:
            dashboards = self.superset.request("GET", "/api/v1/dashboard/?q=(page_size:100)").get(
                "result", []
            )
            output = []
            for d in dashboards:
                output.append(
                    {
                        "id": d.get("id"),
                        "title": d.get("dashboard_title") or f"Dashboard {d.get('id')}",
                        "slug": d.get("slug") or "",
                    }
                )
            return output
        except Exception as e:
            logger.warning(f"Error fetching dashboards: {e}")
            return []

    def get_dashboard_setting(self, dataset_id: int) -> dict[str, Any]:
        """Get custom dashboard toggle and link for a dataset."""
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                SELECT dashboard_id, is_enabled FROM public.dataset_dashboard_settings
                WHERE dataset_id = :did
            """),
                {"did": dataset_id},
            ).fetchone()
            if row:
                return {"dashboard_id": row[0], "is_enabled": bool(row[1])}
            return {"dashboard_id": None, "is_enabled": True}

    def update_dashboard_setting(
        self, dataset_id: int, dashboard_id: int | None, is_enabled: bool
    ) -> dict[str, Any]:
        """Save toggle state and assigned dashboard for a dataset."""
        with engine.begin() as conn:
            conn.execute(
                text("""
                INSERT INTO public.dataset_dashboard_settings (dataset_id, dashboard_id, is_enabled, updated_at)
                VALUES (:did, :dash_id, :enabled, CURRENT_TIMESTAMP)
                ON CONFLICT (dataset_id) DO UPDATE
                SET dashboard_id = EXCLUDED.dashboard_id,
                    is_enabled = EXCLUDED.is_enabled,
                    updated_at = CURRENT_TIMESTAMP;
            """),
                {"did": dataset_id, "dash_id": dashboard_id, "enabled": is_enabled},
            )
        return {"dataset_id": dataset_id, "dashboard_id": dashboard_id, "is_enabled": is_enabled}
