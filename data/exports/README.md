# AI BI analytics data export

`ai_bi_raw_20260924.dump` is a PostgreSQL custom-format archive for the
`raw` analytics schema only. It is already gzip-compressed internally; do not
unzip it. Restore it with `pg_restore`.

## Contents

| Table | Rows at export |
| --- | ---: |
| `raw.yellow_taxi_trips` | 30,000 |
| `raw.taxi_zone_lookup` | 265 |
| `raw.ingestion_log` | 4 |

SHA-256:

```text
0754200D806D837C282F77C639392EF1CB326443985E4B3803EA06E44FEA4BB7
```

The archive includes the `raw` schema, its tables, data, primary key, and
indexes. It does not include PostgreSQL users/passwords, the `superset`
metadata database, Docker volumes, or `.env.local` / `.env.prod` secrets.

## Restore on a server

Install PostgreSQL client tools (version 16 or newer is recommended), create
an empty destination database, then run:

```bash
createdb --host SERVER_HOST --port 5432 --username SERVER_USER ai_bi
pg_restore --host SERVER_HOST --port 5432 --username SERVER_USER \
  --dbname ai_bi --no-owner --no-privileges --verbose \
  ai_bi_raw_20260924.dump
```

To replace an existing `raw` schema, first take a server backup, then add
`--clean --if-exists` to the `pg_restore` command. Those options delete the
existing restored objects before recreating them.

Verify the import:

```sql
SELECT COUNT(*) FROM raw.yellow_taxi_trips;
SELECT COUNT(*) FROM raw.taxi_zone_lookup;
SELECT COUNT(*) FROM raw.ingestion_log;
```

The expected counts are 30,000, 265, and 4 respectively.
