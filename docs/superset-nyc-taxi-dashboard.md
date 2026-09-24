# NYC Yellow Taxi dashboard trong Superset

Tài liệu này mô tả BI flow đang chạy trên dữ liệu thật trong PostgreSQL:

```text
PostgreSQL
    ↓
Superset Database Connection
    ↓
Superset Dataset
    ↓
Metric
    ↓
Chart
    ↓
Dashboard
```

Phase này kết thúc trong Apache Superset. Chưa có Superset Embed, Guest Token, tích hợp FastAPI/Next.js, LLM hay NL2SQL.

## Runtime và nguồn dữ liệu

| Thành phần | Giá trị đã kiểm tra |
| --- | --- |
| Superset service | `superset` trong Docker Compose |
| Superset version | `6.1.0` |
| Superset URL | <http://localhost:58088> |
| Database connection | `NYC Taxi PostgreSQL`, ID `1` |
| PostgreSQL database | `ai_bi` |
| Schema/table | `raw.yellow_taxi_trips` |
| Dataset ID | `1` |

Health check trong lần triển khai: Superset, FastAPI `/health`, `/health/db`, `/health/superset` và Next.js đều trả HTTP 200; PostgreSQL port `55439` và Redis port `56379` nhận TCP connection.

Kết nối `NYC Taxi PostgreSQL` đã tồn tại và được tái sử dụng. Không tạo kết nối PostgreSQL thứ hai.

Superset tạo tên vật lý cho Dataset từ schema và table: `raw.yellow_taxi_trips`. Brief gọi Dataset này là **NYC Yellow Taxi Trips**; nhãn thân thiện đó được lưu trong mô tả Dataset vì physical Dataset của Superset 6.1.0 lấy tên hiển thị từ relation thật.

Dataset là metadata trong Superset; nó không sao chép 11 triệu dòng sang Superset. Mỗi chart gửi câu truy vấn aggregate qua PostgreSQL connection.

## Dataset và metrics

Dataset trỏ trực tiếp tới `ai_bi.raw.yellow_taxi_trips`. Superset nhận diện 25 cột. `tpep_pickup_datetime` và `tpep_dropoff_datetime` được đánh dấu là temporal; các trường số như `trip_distance`, `passenger_count`, `fare_amount`, `tip_amount` và `total_amount` được nhận diện numeric. Không cần đổi kiểu ở PostgreSQL.

Dataset chứa các metrics sau:

| Metric | SQL | Format |
| --- | --- | --- |
| Total Trips | `COUNT(*)` | Số nguyên có dấu phân nhóm |
| Gross Trip Amount | `SUM(total_amount)` | USD, 2 chữ số thập phân |
| Average Trip Amount | `AVG(total_amount)` | USD, 2 chữ số thập phân |
| Average Trip Distance | `AVG(trip_distance)` | 2 chữ số thập phân, miles |

`Gross Trip Amount` là tổng `total_amount` được ghi nhận trong các bản ghi taxi. Nó không được gọi là accounting revenue.

## Quy tắc lọc dữ liệu demo

Các chart tổng hợp dùng điều kiện ở BI layer:

```sql
source_year = 2026
AND source_month IN (5, 6, 7)
```

Chart `Trips Over Time` dùng thêm cột `tpep_pickup_datetime` và khoảng thời gian từ `2026-05-01` tới trước `2026-08-01`. Mốc kết thúc loại trừ cho phép bao gồm toàn bộ ngày 31/7 và tránh timestamp anomaly cũ kéo dài trục thời gian.

Các phép kiểm tra chỉ chạy `SELECT` aggregate trên PostgreSQL; raw data không bị sửa, xóa hay làm sạch.

## Charts

Dashboard dùng bốn chart chính:

| ID | Chart | Visualization | Cấu hình |
| --- | --- | --- | --- |
| 1 | NYC Taxi — Total Trips | Big Number | Total Trips; lọc source year/month |
| 2 | NYC Taxi — Gross Trip Amount | Big Number | Gross Trip Amount; lọc source year/month; USD |
| 3 | NYC Taxi — Trips Over Time | Time-series Line Chart | pickup datetime theo ngày; 1/5/2026–31/7/2026; lọc source year/month |
| 4 | NYC Taxi — Trips by Payment Type | Donut Chart | `payment_type` và Total Trips; sắp xếp giảm dần |

Chart thanh toán giữ nguyên các mã numeric từ `payment_type`; phase này không thêm mapping ngữ nghĩa.

## Dashboard

Tên: **NYC Yellow Taxi Overview**. Layout đặt hai Big Number cạnh nhau, Trips Over Time bên dưới và phân bố Payment Type ở hàng cuối. Dashboard được publish trong Superset cục bộ để mở trực tiếp sau khi đăng nhập.

URL: <http://localhost:58088/superset/dashboard/1/>

## Chạy lại setup

Sau khi Docker Compose đang chạy và `.env.local` có Superset admin credentials:

```powershell
python superset/scripts/setup_nyc_taxi_demo.py
```

Mặc định script gọi Superset trên host tại `http://localhost:58088`. Có thể đổi địa chỉ bằng `--base-url`. Script đọc credential từ biến môi trường hoặc `.env.local` (hoặc `.env.prod` nếu file local không có), không ghi password/secret vào output, tái sử dụng database connection và tìm object theo tên trước khi tạo hoặc cập nhật.

Script dùng Python standard library và Superset REST API của version đang chạy. Nó kiểm tra metadata Dataset, cập nhật metrics, upsert bốn chart, chạy query cho mỗi chart, tạo/cập nhật dashboard và in ID cùng URL.

## Tự thao tác bằng UI

1. Mở <http://localhost:58088> và đăng nhập Superset.
2. Vào **Data → Datasets**. Dataset vật lý nằm dưới connection `NYC Taxi PostgreSQL`, schema `raw`, table `yellow_taxi_trips`.
3. Chọn **Explore**, chọn visualization tương ứng, metric, dimension hoặc temporal column và filters ở trên.
4. Bấm **Run** rồi **Save** với tên chart trong bảng.
5. Vào **Dashboards → NYC Yellow Taxi Overview**, kiểm tra chart tiles và lưu nếu chỉnh layout thủ công.

## Native filter

Native filter `Source Month` chưa được cấu hình. Payload filter qua REST API không được lưu trong Superset 6.1.0 khi kiểm tra, nên bỏ qua phần optional để giữ dashboard ổn định; có thể thêm bằng UI theo bước bên dưới.

Để thêm filter trong UI: mở dashboard, chọn **⋮ → Edit dashboard**, mở **Filter Bar → + Add/Edit Filters → Add filter**, chọn Dataset vật lý `raw.yellow_taxi_trips`, column `source_month`, bật multi-select, đặt scope cho bốn chart rồi bấm **Save**. Filter chỉ bổ sung điều kiện dashboard; các chart vẫn giữ điều kiện source year/month demo. Superset mô tả cùng flow trong [Creating Your First Dashboard](https://superset.apache.org/user-docs/using-superset/creating-your-first-dashboard/).

## Kết quả truy vấn đã kiểm tra

Các truy vấn aggregate qua Superset API đã chạy thành công:

| Kiểm tra | Kết quả |
| --- | ---: |
| Sample query giới hạn 5 dòng trên các source columns | 5 dòng, thành công |
| Trips trong source months 5–7/2026 | 11,458,193 |
| Gross Trip Amount trong cùng phạm vi | $347,859,833.11 |
| Average Trip Amount trong cùng phạm vi | $30.36 |
| Average Trip Distance trong cùng phạm vi | 5.22 miles |
| Trips trong khoảng pickup datetime 1/5–31/7/2026 | 11,337,261 |
| Số nhóm ngày của time-series | 92 |
| Số mã payment type | 6 |

REST API trả `success` cho cả bốn chart; kết quả có lần lượt 1, 1, 92 và 6 hàng aggregate. Dashboard API trả bốn chart definition, và sau đăng nhập `GET /superset/dashboard/1/` trả HTTP 200 cùng đúng dashboard title. Browser automation không có browser khả dụng trong phiên triển khai này, nên chưa có kiểm tra trực quan bằng screenshot.

## Dataset → Metric → Chart → Dashboard

- **Dataset** chứa metadata cho bảng PostgreSQL thật.
- **Metric** khai báo cách PostgreSQL aggregate như `COUNT(*)` và `SUM(total_amount)`.
- **Chart** lưu kiểu trực quan và cấu hình query như metric, dimension, bộ lọc và time grain.
- **Dashboard** lưu layout của các chart đã lưu và các filter áp dụng trong dashboard.

## Tài liệu API

- [Charts — Superset 6.1.0](https://superset.apache.org/developer-docs/6.1.0/api/charts/)
- [Datasets — Superset 6.1.0](https://superset.apache.org/developer-docs/6.1.0/api/datasets/)
- [Dashboards — Superset 6.1.0](https://superset.apache.org/developer-docs/6.1.0/api/dashboards/)
