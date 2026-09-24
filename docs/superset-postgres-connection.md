# Kết nối Superset tới PostgreSQL

Tài liệu này ghi lại phase thiết lập database connection `NYC Taxi PostgreSQL` trong Superset và cách tự kiểm tra hoặc tạo connection bằng UI. Bảng kết quả ở cuối là snapshot của phase connection trước khi hoàn tất BI flow. Trạng thái hiện tại của Dataset, metrics, charts và dashboard được cập nhật trong [hướng dẫn NYC Taxi dashboard](superset-nyc-taxi-dashboard.md).

## Hai database và hai mục đích

Compose chạy PostgreSQL service `postgres` (image `postgres:16-alpine`) và Superset service `superset` (Apache Superset `6.1.0`). Cả hai cùng ở Compose network `ai_bi_network`; Docker đặt tên network thực tế là `ai-bi-assistant_ai_bi_network`.

| Kết nối | Database | Mục đích | Tài khoản hiện dùng |
| --- | --- | --- | --- |
| Superset metadata store | `superset` | Lưu cấu hình, người dùng và metadata của Superset | `ai_bi_user` qua `SQLALCHEMY_DATABASE_URI` hiện có |
| Superset analytics data source | `ai_bi` | Đọc dữ liệu NYC Taxi trong schema `raw` | `superset_reader` |

Hai database dùng chung PostgreSQL server nhưng là hai kết nối với mục đích khác nhau. Cấu hình `SQLALCHEMY_DATABASE_URI` trong `superset/superset_config.py` vẫn trỏ tới metadata database `superset`; database connection mới trong Superset trỏ tới `ai_bi`. Không thay thế hai cấu hình cho nhau.

## Địa chỉ kết nối

| Từ | Host | Port | Ghi chú |
| --- | --- | --- | --- |
| Máy host tới PostgreSQL | `localhost` | `55439` | Port mapping `127.0.0.1:55439:5432` |
| Superset container tới PostgreSQL | `postgres` | `5432` | Dùng Docker service DNS và port nội bộ |
| Máy host tới Superset UI | `localhost` | `58088` | Port mapping `127.0.0.1:58088:8088` |

Không dùng `localhost:55439` trong SQLAlchemy URI của Superset: bên trong container, `localhost` là chính container Superset. URI analytics có dạng:

```text
postgresql://superset_reader:***@postgres:5432/ai_bi
```

Mật khẩu reader được lưu cục bộ trong `.env.local` tại `SUPERSET_ANALYTICS_DB_PASSWORD`; file này đang được Git ignore. `.env.example` chỉ có giá trị mẫu. Mật khẩu được tạo cho tài khoản này chỉ dùng ký tự URL-safe, nên không cần URL-encode. Nếu tự đặt mật khẩu có ký tự như `@`, `:`, `/`, `#` hoặc `%`, hãy URL-encode phần mật khẩu trong URI.

## Luồng kết nối

```text
Browser
   ↓ HTTP tới localhost:58088
Superset UI
   ↓
Superset backend
   ↓ SQLAlchemy
psycopg2
   ↓ Docker DNS: postgres:5432
PostgreSQL database ai_bi
   ↓
schema raw
   ↓
yellow_taxi_trips / taxi_zone_lookup / ingestion_log
```

Superset lưu thông tin connection trong metadata database `superset`; Superset không sao chép các bảng analytics sang metadata database. Khi một thao tác Superset cần truy vấn dữ liệu, backend mở kết nối bằng SQLAlchemy và PostgreSQL driver, gửi SQL tới PostgreSQL, rồi nhận result set trả về cho Superset.

Apache Superset 6.1.0 yêu cầu DB-API driver và SQLAlchemy dialect cho mỗi loại database. Container hiện có `psycopg2` `2.9.13` (`psycopg2-binary`); không cần cài lại driver.

## Tài khoản analytics chỉ đọc

Repository ban đầu chỉ có PostgreSQL login `ai_bi_user`, tài khoản này có quyền superuser và đang được cấu hình cho metadata/app. Tài khoản đó không được dùng cho analytics connection. Phase này đã tạo riêng `superset_reader` với quyền:

- `CONNECT` tới database `ai_bi`.
- `USAGE` trên schema `raw`.
- `SELECT` trên các bảng hiện có trong `raw`.
- Quyền mặc định `SELECT` cho bảng mới trong `raw` do `ai_bi_user` tạo.

Role không có `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, hoặc quyền `CREATE` trên schema `raw`. Superset connection cũng lưu các lựa chọn `Expose in SQL Lab`, CTAS, CVAS, DML và file upload ở trạng thái tắt. Quyền PostgreSQL là lớp kiểm soát chính đối với dữ liệu.

## Xem connection hiện có trong UI

1. Mở <http://localhost:58088>.
2. Đăng nhập bằng tên người dùng trong `SUPERSET_ADMIN_USERNAME` ở `.env.local`.
3. Mở **Settings → Data: Database Connections**.
4. Chọn **NYC Taxi PostgreSQL** để xem thông tin connection.
5. Nếu cần kiểm tra lại, mở phần chỉnh sửa connection và bấm **Test Connection**. Kết quả mong đợi là kết nối thành công.

## Các bước UI tương đương để tạo connection

Superset 6.1.0 hướng dẫn flow **Settings → Data: Database Connections → + DATABASE → chọn database type hoặc SQLAlchemy URI → Test Connection → Connect**. Connection này được tạo qua API sau khi gọi Test Connection; các bước UI tương đương là:

1. Mở <http://localhost:58088> và đăng nhập bằng Superset admin.
2. Mở **Settings → Data: Database Connections** rồi chọn **+ DATABASE**.
3. Chọn **PostgreSQL**.
4. Đặt tên connection là `NYC Taxi PostgreSQL`.
5. Chọn cách nhập **SQLAlchemy URI** và nhập URI dưới đây. Thay `***` bằng giá trị `SUPERSET_ANALYTICS_DB_PASSWORD` trong `.env.local`:

   ```text
   postgresql://superset_reader:***@postgres:5432/ai_bi
   ```

6. Để **Expose in SQL Lab**, **Allow CTAS**, **Allow CVAS**, **Allow DML** và **Allow file uploads** tắt. Tài khoản PostgreSQL cũng không có quyền ghi vào `raw`.
7. Bấm **Test Connection**. Kết quả phải báo kết nối thành công.
8. Bấm **Connect** để lưu database connection.

Tên trường trong UI có thể được trình bày trong phần form connection của PostgreSQL; URI chứa cùng thông tin host `postgres`, port `5432`, database `ai_bi` và user `superset_reader`.

## Kết quả đã xác minh

| Kiểm tra | Kết quả |
| --- | --- |
| PostgreSQL | Healthy; service `postgres`; port trong container `5432`; host port `55439` |
| Superset | Healthy; version `6.1.0`; UI port `58088` |
| Docker DNS/network | `superset` phân giải được `postgres`; hai container cùng Compose network; TCP `postgres:5432` kết nối được |
| PostgreSQL driver | `psycopg2` `2.9.13` có trong Superset container |
| Database và dữ liệu | `current_database()` là `ai_bi`; `raw.yellow_taxi_trips` có `11,458,193` dòng |
| Superset Test Connection | Thành công: HTTP `200`, kết quả `OK` |
| Superset database connection | `NYC Taxi PostgreSQL`, database ID `1`; connection dùng `postgresql://superset_reader:***@postgres:5432/ai_bi` |
| Schema Superset khám phá được | `public`, `information_schema`, `raw` |
| Tables Superset khám phá được trong `raw` | `ingestion_log`, `taxi_zone_lookup`, `yellow_taxi_trips` |
| Read-only SELECT | Từ Superset container, `superset_reader` truy vấn được `raw.taxi_zone_lookup` với `LIMIT 5` |
| SQL Lab/write/upload options | Đều tắt trên connection |
| Dataset / chart / dashboard / SQL Lab tab | Không có object nào được tạo; API trả về count `0` cho từng loại |

Các truy vấn xác minh chỉ đọc; dữ liệu trong các bảng `raw` không bị thay đổi.

## Tài liệu Superset

- [Connecting to Databases — Superset 6.1.0](https://superset.apache.org/user-docs/6.1.0/databases/)
- [PostgreSQL — Superset 6.1.0](https://superset.apache.org/user-docs/6.1.0/databases/supported/postgresql/)
- [Database API — Superset 6.1.0](https://superset.apache.org/developer-docs/6.1.0/api/database/)
