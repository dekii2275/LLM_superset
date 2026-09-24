import os
import sys
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:password@localhost:5432/ai_bi")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.query_service import QueryService, SQLValidationError


class QueryServiceValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = QueryService(default_limit=100, max_limit=500)

    def test_allows_select_and_adds_default_limit(self) -> None:
        sql = self.service.prepare_sql("SELECT COUNT(*) FROM raw.yellow_taxi_trips")
        self.assertEqual(sql, "SELECT COUNT(*) FROM raw.yellow_taxi_trips\nLIMIT 100")

    def test_allows_cte_select(self) -> None:
        sql = self.service.prepare_sql(
            """WITH monthly AS (
                SELECT DATE_TRUNC('month', tpep_pickup_datetime) AS month,
                       COUNT(*) AS trips
                FROM raw.yellow_taxi_trips
                GROUP BY 1
            )
            SELECT * FROM monthly"""
        )
        self.assertTrue(sql.endswith("LIMIT 100"))

    def test_blocks_dangerous_and_multiple_statements(self) -> None:
        for sql in (
            "DROP TABLE raw.yellow_taxi_trips",
            "DELETE FROM raw.yellow_taxi_trips",
            "SELECT * FROM raw.yellow_taxi_trips; DROP TABLE users;",
            "UPDATE raw.yellow_taxi_trips SET fare_amount = 0",
            "SELECT * INTO copied_trips FROM raw.yellow_taxi_trips",
        ):
            with self.subTest(sql=sql), self.assertRaises(SQLValidationError):
                self.service.prepare_sql(sql)

    def test_clamps_existing_limit(self) -> None:
        sql = self.service.prepare_sql("SELECT * FROM raw.taxi_zone_lookup LIMIT 9999")
        self.assertEqual(sql, "SELECT * FROM raw.taxi_zone_lookup LIMIT 500")


if __name__ == "__main__":
    unittest.main()
