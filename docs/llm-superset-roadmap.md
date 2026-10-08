# Kế hoạch phát triển: LLM Superset Enterprise Platform

Tài liệu này định hình lộ trình chuyển đổi dự án **AI BI Assistant** từ phiên bản hiện tại (PoC hoạt động trên tập dữ liệu NYC Taxi) thành một nền tảng **LLM Superset (Generative BI)** toàn diện, đa nguồn dữ liệu, sẵn sàng phục vụ môi trường doanh nghiệp.

---

## 1. Tầm nhìn & Kiến trúc đích

Mục tiêu là xây dựng một nền tảng **Conversational Business Intelligence** cho phép bất kỳ người dùng nghiệp vụ nào cũng có thể:
1. Kết nối hoặc chọn bất kỳ cơ sở dữ liệu / tập dữ liệu nào trong Apache Superset.
2. Đặt câu hỏi bằng ngôn ngữ tự nhiên (tiếng Việt/tiếng Anh) và nhận kết quả truy vấn chính xác nhờ tầng ngữ nghĩa (Semantic Layer).
3. Đàm thoại phân tích đa chiều (Drill-down, so sánh kỳ, phân tích nguyên nhân gốc rễ).
4. Tự động sinh biểu đồ phù hợp và dựng bảng điều khiển (Dashboard) thông minh, có bộ lọc chéo (Cross-filters).
5. Đảm bảo an toàn dữ liệu doanh nghiệp với phân quyền theo dòng (Row-Level Security) và tối ưu chi phí với Semantic Cache.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                FRONTEND (Next.js 15)                            │
│  - Trò chuyện đa phiên (Chat Sessions)        - Dataset / Database Selector     │
│  - Dynamic Visualizations (Recharts/Superset) - Embedded Interactive Dashboard  │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │ REST / WebSocket
┌────────────────────────────────────────▼────────────────────────────────────────┐
│                                BACKEND (FastAPI)                                │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────────────┐  │
│  │   Intent & Router     │  │  Semantic Layer & RAG │  │  Guardrails & RLS   │  │
│  └──────────┬────────────┘  └───────────┬───────────┘  └──────────┬──────────┘  │
│             │                           │                         │             │
│             ▼                           ▼                         ▼             │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────────────┐  │
│  │  Gemini Engine (SQL)  │  │  Semantic Cache       │  │ Superset Automation │  │
│  │  & Self-Repair Loop   │  │  (Redis)              │  │ (REST / FastMCP)    │  │
│  └───────────────────────┘  └───────────────────────┘  └─────────────────────┘  │
└───────────────────────┬───────────────────────────────────────────┬─────────────┘
                        │                                           │
                        ▼                                           ▼
┌───────────────────────────────────────┐   ┌─────────────────────────────────────┐
│          APACHE SUPERSET 6.1          │   │         ANALYTICS DATABASES         │
│  - Metadata Catalog & Virtual Datasets│   │  - PostgreSQL, ClickHouse, MySQL    │
│  - Dashboards, Slices, Native Filters │   │  - BigQuery, Snowflake, etc.        │
│  - Guest Token Embedded Engine        │   │                                     │
└───────────────────────────────────────┘   └─────────────────────────────────────┘
```

---

## 2. Lộ trình triển khai chi tiết qua 4 giai đoạn

---

### GIAI ĐOẠN 1: Độc lập nguồn dữ liệu (Dynamic Data & Schema Engine)
> **Mục tiêu:** Xóa bỏ hoàn toàn ràng buộc cứng vào bộ dữ liệu NYC Taxi (`NYC_TAXI_SCHEMA`, `superset_taxi_dataset_id = 1`), cho phép ứng dụng làm việc với bất kỳ bảng/dataset nào trên Superset.

#### 1.1. Backend
* **API khám phá Datasets (`GET /api/v1/datasets`):**
  * Tích hợp với Superset REST API (`/api/v1/dataset/`) để lấy danh sách các physical & virtual datasets đã cấu hình.
  * Trả về thông tin: ID, tên hiển thị, database connection, schema, danh sách cột, metrics đã định nghĩa sẵn.
* **Service trích xuất Schema động (`SchemaService`):**
  * Tự động đọc danh sách cột, kiểu dữ liệu (numeric, temporal, string, boolean).
  * Lấy mẫu 3–5 giá trị đại diện cho các cột phân loại (categorical values) để LLM hiểu dữ liệu thực tế (ví dụ: trạng thái đơn hàng: `COMPLETED`, `PENDING`, `CANCELLED`).
* **Tái cấu trúc Prompt Builder trong `GeminiService`:**
  * Thay thế hằng số `NYC_TAXI_SCHEMA` bằng hàm `build_dynamic_schema_prompt(dataset_metadata)`.
  * Hỗ trợ chỉ định Dataset ID mục tiêu trong request chat: `AIChatRequest(message=..., dataset_id=...)`.
* **Dynamic Query Executor:**
  * Thay thế việc query cố định vào database `ai_bi` bằng cách định tuyến truy vấn tới database tương ứng của dataset được chọn thông qua SQLAlchemy engine động hoặc Superset SQL Lab execution API.

#### 1.2. Frontend
* **Dataset Selector Component:**
  * Thêm bộ chọn nguồn dữ liệu (Dropdown selector) ở Header hoặc Sidebar.
  * Hiển thị trạng thái kết nối và số lượng cột/chỉ số của dataset đang chọn.
* **Context State Management:**
  * Lưu trữ `activeDatasetId` trong ứng dụng.
  * Khi chuyển dataset, tự động thông báo và khởi tạo phiên phân tích tương ứng.

#### 1.3. Tiêu chí hoàn thành (Definition of Done - DoD)
- [ ] Chọn một dataset mới (không phải taxi) trên giao diện.
- [ ] Hỏi câu hỏi phân tích bằng tiếng Việt trên dataset đó.
- [ ] Hệ thống tự sinh SQL chính xác theo schema mới, thực thi và vẽ biểu đồ kết quả thành công.

---

### GIAI ĐOẠN 2: Tầng ngữ nghĩa & Đàm thoại sâu (Semantic Layer & Conversational Intelligence)
> **Mục tiêu:** Giúp AI hiểu đúng thuật ngữ nghiệp vụ (Doanh thu thuần, Khách hàng hoạt động, v.v.) và hỗ trợ chuỗi hội thoại phân tích chuyên sâu nhiều bước.

#### 2.1. Tầng ngữ nghĩa nghiệp vụ (Semantic Layer & Business Glossary)
* **Metadata & Glossary Database:**
  * Tạo bảng lưu trữ từ điển nghiệp vụ trong cơ sở dữ liệu quản trị:
    * `business_glossary`: Lưu từ đồng nghĩa (ví dụ: `doanh số`, `tiền thu về`, `revenue` -> `metric: gross_revenue`).
    * `verified_metrics`: Lưu công thức SQL chuẩn đã được Data Analyst kiểm duyệt (Golden SQL).
* **Semantic Layer Injection vào Prompt:**
  * Khi người dùng hỏi, AI kiểm tra glossary và verified metrics trước. Nếu câu hỏi khớp với metric chuẩn, bắt buộc sử dụng công thức đã định nghĩa, loại bỏ 100% rủi ro LLM tự "chế" công thức sai.
* **Metadata Management UI:**
  * Bổ sung trang quản trị trong ứng dụng: cho phép thêm mô tả tiếng Việt cho từng cột, gắn nhãn từ đồng nghĩa và cấu hình công thức chỉ số.

#### 2.2. Đàm thoại phân tích đa bước (Stateful Multi-Turn & Context Continuity)
* **Tích lũy điều kiện lọc (Filter Accumulation):**
  * Cho phép người dùng ra lệnh kế thừa ngữ cảnh:
    * *Bước 1:* "Cho tôi xem doanh thu năm 2025" -> Tạo SQL có `WHERE year = 2025`.
    * *Bước 2:* "Lọc riêng khu vực miền Bắc" -> Giữ nguyên bộ lọc 2025, bổ sung `AND region = 'Mien Bac'`.
    * *Bước 3:* "Chia nhỏ theo từng quý" -> Đổi `GROUP BY` sang `quarter`.
* **Phân tích nguyên nhân gốc rễ (Root Cause & Decomposition Analysis):**
  * Hỗ trợ các câu hỏi "Tại sao" (*Why questions*): AI tự động phân tích độ biến động của các thành phần con cấu thành nên chỉ số (ví dụ: Doanh thu giảm do lượng đơn giảm hay do giá trị đơn giảm? Giảm mạnh nhất ở kênh phân phối nào?).
* **Lưu trữ phiên hội thoại (Chat Sessions Persistence):**
  * Tạo các bảng `chat_sessions` và `chat_messages` trong database.
  * Hỗ trợ lưu trữ, đặt tên hội thoại, tạo mới và mở lại các phiên phân tích cũ trên sidebar.

#### 2.3. Tiêu chí hoàn thành (DoD)
- [x] Người dùng hỏi bằng tiếng lóng/từ đồng nghĩa nghiệp vụ, AI vẫn map đúng vào metric chuẩn.
- [x] Thực hiện chuỗi hội thoại 4 bước liên tiếp với các lệnh lọc dồn dập mà không bị mất ngữ cảnh trước đó.
- [x] Lịch sử chat được lưu trữ bền vững sau khi tải lại trang web.

---

### GIAI ĐOẠN 3: Trực quan hóa mở rộng & Bố cục Dashboard thông minh
> **Mục tiêu:** Mở rộng từ 4 biểu đồ cơ bản sang thư viện đồ thị đa dạng của Superset và tự động bố cục dashboard theo chuẩn trực quan hóa dữ liệu hiện đại.

#### 3.1. Thư viện biểu đồ mở rộng (Advanced Chart Types)
* **KPI Card kèm Sparkline (Thẻ chỉ số có xu hướng thu nhỏ):**
  * Hiển thị số tổng hợp lớn kèm biểu đồ đường mini thể hiện xu hướng tăng/giảm so với kỳ trước (% thay đổi).
* **Pivot Table (Bảng tổng hợp chéo nhiều chiều):**
  * Dành cho nhu cầu xem số liệu chi tiết theo dạng bảng ma trận (Hàng x Cột x Giá trị).
* **Heatmap & Scatter Plot (Biểu đồ nhiệt & Biểu đồ phân tán):**
  * Trực quan hóa mật độ hoạt động (theo giờ trong ngày / ngày trong tuần) hoặc tương quan giữa 2 biến liên tục.
* **Geographic Map (Bản đồ địa lý):**
  * Tích hợp bản đồ nhiệt hoặc polygon theo quận/tỉnh thành nếu dataset có tọa độ hoặc mã vùng.

#### 3.2. Bố cục Dashboard thông minh (Smart Layout Engine)
* **Quy chuẩn bố cục điều hành (Executive Layout Hierarchy):**
  * Thay thế lưới 2×2 cố định bằng bố cục chuẩn BI:
    * **Hàng 1 (Top Row):** 3–4 thẻ KPI Card (Doanh thu, Đơn hàng, Khách hàng, Tăng trưởng).
    * **Hàng 2 (Main Trend):** 1–2 biểu đồ xu hướng thời gian (Line/Area Chart full width).
    * **Hàng 3 (Breakdown):** 2 biểu đồ cơ cấu tỷ trọng (Bar/Pie/Donut).
    * **Hàng 4 (Details):** Bảng dữ liệu chi tiết hoặc bản đồ (nếu có).
* **Tự động cấu hình Native Filters & Bộ lọc chéo (Cross-Filtering):**
  * Khi tạo Dashboard, AI tự động thêm thanh bộ lọc phạm vi thời gian (Time Range Picker) và bộ lọc danh mục (Dropdown Filters).
  * Kích hoạt tính năng Cross-filtering: bấm vào một nhóm trên biểu đồ A sẽ tự động lọc dữ liệu cho các biểu đồ còn lại trên Dashboard.

#### 3.3. Tiêu chí hoàn thành (DoD)
- [x] AI sinh thành công dashboard có cấu trúc phân cấp: KPI Cards hàng trên + Biểu đồ xu hướng ở giữa + Cơ cấu ở dưới.
- [x] Dashboard nhúng hỗ trợ bộ lọc chéo mượt mà.

---

### GIAI ĐOẠN 4: Chuẩn hóa Enterprise (Bảo mật, Caching & Tự động hóa)
> **Mục tiêu:** Đưa hệ thống vào môi trường doanh nghiệp thực tế: bảo mật dữ liệu theo người dùng, tốc độ phản hồi tức thì và chủ động thông báo biến động.

#### 4.1. Xác thực & Phân quyền theo dòng dữ liệu (Authentication & Row-Level Security)
* **Xác thực người dùng (User Authentication):**
  * Tích hợp NextAuth / JWT OAuth2 với hệ thống SSO nội bộ (Google Workspace, Microsoft Entra ID).
* **Dynamic Row-Level Security (RLS) Injection:**
  * Cơ chế viết lại câu lệnh SQL an toàn (SQL Rewriter):
  * Dựa trên danh tính người dùng hiện tại, tự động tiêm điều kiện lọc vào mệnh đề `WHERE` của SQL do LLM sinh ra:
    ```sql
    -- Query ban đầu:
    SELECT SUM(sales) FROM orders;
    -- Query sau khi tiêm RLS của user chi nhánh Hà Nội:
    SELECT SUM(sales) FROM orders WHERE branch_id = 'HN';
    ```
  * Đảm bảo LLM dù có bị prompt injection cũng không thể vượt qua hàng rào RLS của hệ thống.

#### 4.2. Tối ưu chi phí & Tốc độ phản hồi (Semantic Caching)
* **Kiến trúc Caching bằng Redis & Vector Similarity:**
  * Lưu trữ các câu hỏi, câu SQL tương ứng và kết quả truy vấn vào Redis.
  * Khi có câu hỏi mới, thực hiện so khớp ngữ nghĩa (Embedding Cosine Similarity > 0.95).
  * Nếu tìm thấy câu hỏi tương đương và dữ liệu trong bảng chưa thay đổi: trả về ngay kết quả trong vòng **< 100ms**, tiết kiệm **100% token LLM**.

#### 4.3. Báo cáo định kỳ & Cảnh báo thông minh (Scheduled Insights & Alerts)
* **Lên lịch báo cáo điều hành tự động:**
  * Chạy Background Worker định kỳ (ví dụ: 08:00 sáng thứ Hai đầu tuần).
  * Tự động quét Dashboard, chụp ảnh các chỉ số, gọi AI phân tích biến động và gửi bản tin tổng kết qua Email hoặc Telegram/Slack webhook.
* **Phát hiện bất thường (Anomaly Detection Alerts):**
  * So sánh chỉ số theo chu kỳ (WoW, MoM). Khi phát hiện chỉ số sụt giảm hoặc tăng đột biến ngoài ngưỡng dung sai (ví dụ: ±35%), hệ thống tự động kích hoạt cảnh báo kèm phân tích nguyên nhân sơ bộ.

#### 4.4. Tiêu chí hoàn thành (DoD)
- [x] Người dùng A chỉ xem được dữ liệu của phòng ban A dù hỏi câu hỏi toàn công ty (Dynamic RLS SQL Rewriter).
- [x] Câu hỏi trùng lặp được trả về ngay lập tức từ Semantic Cache (< 50ms, tiết kiệm 100% token).
- [x] Báo cáo tóm tắt định kỳ và cảnh báo bất thường được gửi tự động qua chuông thông báo Header.

---

## 3. Ma trận ưu tiên & Ước lượng thời gian

| Giai đoạn | Tính năng chính | Độ phức tạp | Ước lượng | Mức độ ưu tiên |
| :--- | :--- | :---: | :---: | :---: |
| **Giai đoạn 1** | Dynamic Dataset API & Schema Prompt Builder | Trung bình | 1 – 2 tuần | **P0 (Bắt buộc làm ngay)** |
| **Giai đoạn 2** | Semantic Layer (Glossary, Golden SQL) & Multi-turn | Cao | 2 – 3 tuần | **P0 (Lõi sản phẩm)** |
| **Giai đoạn 3** | Smart Layout & KPI Sparkline / Native Filters | Trung bình | 1 – 2 tuần | **P1 (Nâng cao trải nghiệm)** |
| **Giai đoạn 4** | User Auth + RLS, Semantic Cache, Alerts | Cao | 2 – 3 tuần | **P1 (Sẵn sàng thương mại)** |

---

## 4. Kế hoạch hành động cụ thể cho Bước 1 (Bắt đầu ngay)

Để triển khai ngay **Giai đoạn 1**, các file cần tác động trong mã nguồn bao gồm:

1. **`backend/app/services/superset.py`**:
   * Thêm hàm `get_datasets()` để lấy danh sách datasets kèm columns/metrics từ Superset REST API.
2. **`backend/app/services/gemini_service.py`**:
   * Chuyển `generate_sql(self, question, schema_context)` thành hàm nhận schema động thay vì dùng cố định `NYC_TAXI_SCHEMA`.
3. **`backend/app/api/ai.py`**:
   * Bổ sung `dataset_id` vào schema request `AIChatRequest`.
   * Endpoint `GET /api/v1/ai/datasets` để frontend nạp danh sách dữ liệu.
4. **`frontend/components/layout/AppHeader.tsx`**:
   * Thêm `DatasetSelect` component để người dùng đổi nguồn dữ liệu tức thì.
