import logging
from typing import Any

from sqlalchemy import text

from app.db.database import engine

logger = logging.getLogger(__name__)


class AnomalyService:
    """Detects analytical anomalies and manages enterprise system alerts."""

    @staticmethod
    def get_alerts(limit: int = 20, unread_only: bool = False) -> list[dict[str, Any]]:
        """Retrieve alerts from database."""
        try:
            with engine.connect() as conn:
                where_clause = "WHERE is_read = false" if unread_only else ""
                sql = f"""
                    SELECT id, dataset_id, alert_type, severity, title, message,
                           metric_name, change_percent, suggested_query, is_read, created_at
                    FROM public.system_alerts
                    {where_clause}
                    ORDER BY id DESC
                    LIMIT :lim;
                """
                rows = conn.execute(text(sql), {"lim": limit}).fetchall()
                alerts = []
                for r in rows:
                    alerts.append(
                        {
                            "id": r.id,
                            "dataset_id": r.dataset_id,
                            "alert_type": r.alert_type,
                            "severity": r.severity,
                            "title": r.title,
                            "message": r.message,
                            "metric_name": r.metric_name,
                            "change_percent": r.change_percent,
                            "suggested_query": r.suggested_query,
                            "is_read": r.is_read,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                        }
                    )
                return alerts
        except Exception as e:
            logger.exception("get_alerts_failed: %s", e)
            return []

    @staticmethod
    def mark_as_read(alert_id: int) -> bool:
        """Mark an alert as read."""
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE public.system_alerts SET is_read = true WHERE id = :aid;"),
                    {"aid": alert_id},
                )
                return True
        except Exception as e:
            logger.exception("mark_as_read_failed: %s", e)
            return False

    @staticmethod
    def mark_all_as_read() -> bool:
        """Mark all alerts as read."""
        try:
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE public.system_alerts SET is_read = true WHERE is_read = false;")
                )
                return True
        except Exception as e:
            logger.exception("mark_all_as_read_failed: %s", e)
            return False

    @classmethod
    def seed_initial_alerts_if_empty(cls) -> None:
        """Seeds representative enterprise alerts so UI is rich upon launch."""
        try:
            with engine.begin() as conn:
                count = (
                    conn.execute(text("SELECT COUNT(*) FROM public.system_alerts;")).scalar() or 0
                )
                if count == 0:
                    conn.execute(
                        text("""
                            INSERT INTO public.system_alerts
                                (dataset_id, alert_type, severity, title, message, metric_name, change_percent, suggested_query, is_read)
                            VALUES
                                (1, 'anomaly', 'warning',
                                 'Sụt giảm số chuyến bất thường vào Chủ nhật',
                                 'Số lượng chuyến taxi ngày Chủ nhật giảm 34.2% so với trung bình các ngày trong tuần. Cần kiểm tra nhu cầu và phân bổ tài xế.',
                                 'total_trips', -34.2,
                                 'So sánh số lượng chuyến đi theo từng ngày trong tuần',
                                 false),
                                (1, 'insight', 'info',
                                 'Doanh thu thanh toán thẻ tín dụng chiếm ưu thế',
                                 'Tỷ lệ thanh toán bằng Credit Card đạt 78.5% tổng doanh thu trong tháng, tăng 4.8% so với chu kỳ trước.',
                                 'gross_revenue', 4.8,
                                 'Cơ cấu doanh thu theo phương thức thanh toán',
                                 false),
                                (5, 'threshold', 'critical',
                                 'Độ tập trung dân số cao ở các Siêu đô thị',
                                 'Mặc dù chỉ chiếm 13% tổng số địa điểm, các siêu đô thị (megacities) chiếm tới 62.4% tổng dân số toàn cầu.',
                                 'total_population', 62.4,
                                 'Tỷ lệ dân số giữa siêu đô thị và đô thị thông thường',
                                 false);
                        """)
                    )
        except Exception as e:
            logger.warning(f"seed_initial_alerts_if_empty failed: {e}")

    @classmethod
    def scan_anomalies(cls, dataset_id: int = 1) -> list[dict[str, Any]]:
        """Scans dataset for anomalies and registers new alerts."""
        new_alerts = []
        try:
            with engine.begin() as conn:
                # Check for table existence
                if dataset_id in (1, 2):
                    res = conn.execute(
                        text("""
                            SELECT day_of_week, COUNT(*) as cnt
                            FROM raw.nyc_taxi_analysis
                            GROUP BY day_of_week
                            ORDER BY cnt ASC;
                        """)
                    ).fetchall()
                    if res and len(res) >= 2:
                        counts = [r.cnt for r in res]
                        avg_cnt = sum(counts) / len(counts)
                        lowest_day = res[0].day_of_week
                        lowest_cnt = res[0].cnt
                        diff_pct = round(((lowest_cnt - avg_cnt) / avg_cnt) * 100, 1)

                        if diff_pct < -25.0:
                            title = f"Biến động sụt giảm mạnh vào {lowest_day}"
                            msg = f"Số chuyến ngày {lowest_day} ({lowest_cnt:,}) sụt giảm {abs(diff_pct)}% so với trung bình ({int(avg_cnt):,})."
                            # Insert if not duplicate title
                            exists = conn.execute(
                                text("SELECT COUNT(*) FROM public.system_alerts WHERE title = :t;"),
                                {"t": title},
                            ).scalar()
                            if not exists:
                                ins = conn.execute(
                                    text("""
                                        INSERT INTO public.system_alerts
                                            (dataset_id, alert_type, severity, title, message, metric_name, change_percent, suggested_query)
                                        VALUES
                                            (:did, 'anomaly', 'warning', :t, :m, 'trip_count', :dp, 'Tổng số chuyến theo ngày trong tuần')
                                        RETURNING id, title, message, change_percent;
                                    """),
                                    {"did": dataset_id, "t": title, "m": msg, "dp": diff_pct},
                                ).fetchone()
                                if ins:
                                    new_alerts.append(
                                        {"id": ins.id, "title": ins.title, "message": ins.message}
                                    )
        except Exception as e:
            logger.warning(f"scan_anomalies failed: {e}")

        return new_alerts
