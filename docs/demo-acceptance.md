# Kiểm thử và demo LLM Superset

Tài liệu này tách hai việc: **tiền kiểm hệ thống** trước buổi trình diễn và **nghiệm thu tính năng** sau mỗi lần thay đổi lớn. Không coi một phản hồi `200` hay bộ unit test xanh là bằng chứng rằng toàn bộ luồng người dùng đã hoạt động.

## 1. Cổng vào demo

Chạy từ thư mục gốc dự án, sau khi các container và frontend đã khởi động:

```powershell
python scripts/demo_preflight.py
```

Lệnh này chỉ gọi các endpoint `GET`. Nó kiểm tra 11 điều kiện: API, PostgreSQL, Superset qua API và trực tiếp, Gemini/MCP, trạng thái bật AI, dataset taxi, biểu đồ, cấu hình nhúng, guest token và trang frontend. Mã thoát `0` nghĩa là đạt hết; mã `1` nghĩa là phải xử lý dòng `[FAIL]`. Token chỉ được kiểm tra sự hiện diện và không được in ra.

Các API dashboard hiện yêu cầu đăng nhập. Trước khi chạy tiền kiểm, đặt
`APP_PREFLIGHT_TOKEN` bằng token ứng dụng của tài khoản kiểm thử; công cụ
chỉ gửi token đến các API Superset của ứng dụng, không in token. Xem
[hướng dẫn phân quyền dashboard](dashboard-rls.md) để kiểm tra theo vai trò.

Nếu dùng cổng hoặc dataset khác:

```powershell
python scripts/demo_preflight.py --api http://127.0.0.1:48123 --frontend http://127.0.0.1:43117 --superset http://127.0.0.1:59088 --dataset-id 1
```

Lệnh này chưa xác nhận dữ liệu bên trong chart đã render đúng, Gemini trả lời đúng mọi câu hỏi, hoặc quyền truy cập đã được bảo vệ. Các mục đó cần kiểm tra theo bảng dưới đây. Trước khi demo, mở trang web và thử chính xác các câu hỏi định trình bày.

Lần kiểm tra ngày 06/10/2026: tiền kiểm đạt **11/11**, năm route frontend trả `200`, **107/107 backend tests** đạt khi database/Redis không khả dụng và Gemini dùng key giả, frontend production build thành công. Chat thật với tài khoản Admin trả **30.000 chuyến**, khớp `COUNT(*)` trong PostgreSQL. Đây là ảnh chụp trạng thái tại thời điểm kiểm tra; chạy lại tiền kiểm trước mỗi buổi demo.

## 2. Kịch bản demo 6–8 phút

Chỉ dùng dataset **NYC Yellow Taxi** và dashboard mặc định của dataset đó. Trong dữ liệu demo hiện tại, dataset ID là `1`, dashboard có 4 chart và bảng `raw.yellow_taxi_trips` có 30.000 dòng (đối chiếu ngày 06/10/2026). Nếu nhập thêm dữ liệu, không đọc thuộc lòng con số 30.000; kiểm tra lại bằng `SELECT COUNT(*)`.

| Phút | Thao tác | Dấu hiệu đạt | Nếu không đạt |
| --- | --- | --- | --- |
| 0 | Chạy `python scripts/demo_preflight.py` | `11/11 checks passed` | Dừng demo, xử lý dòng `[FAIL]` rồi chạy lại. |
| 1 | Mở `http://localhost:43117`, đăng nhập Admin, chọn NYC Yellow Taxi | Trang phân tích và tên dataset hiện đúng | Kiểm tra frontend container, API `/api/v1/auth/users` và đăng nhập. |
| 2 | Mở **Bảng điều khiển** | Dashboard nhúng hiển thị chart, không có màn hình trắng hay lỗi guest token | Kiểm tra `embed-config`, guest token, Superset health và origin trong cấu hình. |
| 4 | Mở **Phân tích mới**, hỏi: **“Tổng cộng có bao nhiêu chuyến taxi?”** | Câu trả lời có số chuyến, bảng kết quả có 1 dòng, không có `query.error` | Kiểm tra Gemini, MCP, SQL và số dòng thật trong PostgreSQL. |
| 6 | Mở lại dashboard và chọn một bộ lọc có dữ liệu | Chart cập nhật; số liệu không bị rỗng ngoài dự kiến | Chuyển về bộ lọc mặc định và giữ phần demo đã xác nhận. |

Không đưa thao tác tạo/xóa dataset, tạo dashboard bằng AI, xuất PDF/DOCX, cache hay chuyển vai trò RLS vào luồng chính cho đến khi từng thao tác được thử trên đúng môi trường trình diễn. Các thao tác ghi có thể tạo dữ liệu rác hoặc phụ thuộc kết quả ngẫu nhiên của mô hình.

**Phương án dự phòng:** Nếu Gemini gặp quota hoặc mạng chậm giữa buổi, chuyển sang dashboard đã có và giải thích số liệu từ chart hiện hữu. Tiền kiểm chỉ xác nhận khóa API và MCP có sẵn, nên lần hỏi AI thật trước buổi demo là bắt buộc.

## 3. Ma trận nghiệm thu

Đánh dấu từng mục bằng bằng chứng cụ thể: ảnh màn hình, mã trạng thái, câu SQL, số dòng, hoặc ID chart/dashboard tạo ra. Dùng dataset thử riêng cho thao tác ghi và ghi lại ID để dọn sau kiểm thử. Không chạy bộ test thay đổi dữ liệu trên database trình diễn.

| Nhóm | Ca cần thử | Kết quả mong đợi |
| --- | --- | --- |
| Khởi động | Refresh `/`, `/dashboard`, `/datasets` | Không 404/500; chuyển trang không mất trạng thái ngoài dự kiến. |
| AI dữ liệu | Câu đếm chuyến, câu nhóm theo tháng, câu không có dữ liệu | SQL chỉ đọc, đúng dataset, số liệu khớp query gốc; trường hợp rỗng được diễn đạt rõ. |
| Chart | Bar/line/pie, tooltip, chart rỗng, giải thích chart | Trục và đơn vị đúng; giải thích dựa trên chính dữ liệu đang hiển thị. |
| Hội thoại | Hỏi tiếp, tạo phiên mới, mở lại sau F5, xóa phiên | Ngữ cảnh và chart lưu đúng; không lẫn giữa hai phiên hoặc hai dataset. |
| Hành động ghi | Đề xuất chart/dashboard, Hủy, Đồng ý, thêm/sửa chart | Hủy không ghi; Đồng ý chỉ tạo đúng một lần; chart lưu xem được trên Superset. |
| Superset | Nhúng dashboard, guest token, filter, reload | Chart hiển thị; filter tác động đúng; không lỗi quyền hoặc origin. |
| Dataset | Đổi dataset, preview, upload CSV nhỏ, xóa bản thử | Schema, câu hỏi, dashboard và phiên chat thuộc đúng dataset; dữ liệu thử được dọn. |
| Semantic/cache | Thêm thuật ngữ thử, hỏi biến thể, xóa cache | Metric đúng; cache hit cùng dataset và quyền; không tái dùng kết quả sai phạm vi. |
| Quyền | Admin, Manhattan, Queens; gọi API trực tiếp khi không có token | Kết quả chỉ nằm trong phạm vi được phép, kể cả SQL lồng/UNION và các endpoint ngoài chat. |
| Lỗi | Tắt Gemini/MCP/Redis trong môi trường thử; input sai; double click | Có thông báo dễ hiểu; không tạo đối tượng trùng; hệ thống phục hồi sau khi bật lại. |

### Các điểm cần ưu tiên sửa trước khi công bố rộng

1. Nhiều endpoint backend hiện chưa bắt buộc Bearer token, gồm chat và các thao tác ghi. Màn hình đăng nhập ở frontend không đủ để bảo vệ API. Trong chat, thiếu token khiến `current_user=None` và không có RLS. **Không trình bày đây là phân quyền bảo mật hoàn chỉnh** trước khi áp dụng kiểm tra quyền ở backend.
2. `RLSService.rewrite_sql` dùng regex tìm `WHERE` đầu tiên. SQL có CTE/subquery/`UNION` có thể bị chèn filter sai vị trí hoặc không giới hạn toàn bộ dữ liệu. Cần parser SQL đáng tin cậy hoặc chính sách RLS ngay trong PostgreSQL, cùng test truy vấn lồng và truy cập trực tiếp API.
3. Tài khoản demo và JWT secret mặc định đang có trong mã. Chỉ dùng trên máy demo nội bộ; cấu hình secret và tài khoản riêng trước khi mở mạng.

## 4. Chạy kiểm thử mã nguồn

Trên môi trường Python **3.12** đã cài `backend/requirements.txt` và trỏ vào database thử riêng:

```powershell
$env:PYTHONPATH = "backend"
python -m unittest discover -s backend/tests -v
```

Nhóm `test_phase4_enterprise.py` đã được cô lập bằng mock, nên không xóa users/alerts hay Redis thật nữa. Vẫn cần rà các test mới trước khi chạy chung với database demo. Trên frontend:

```powershell
Set-Location frontend
& .\node_modules\.bin\tsc.cmd --noEmit --incremental false
npm.cmd run build
```

Chạy build khi frontend dev đang chạy cùng thư mục có thể tranh chấp thư mục `.next`. Dừng tiến trình dev hoặc dùng môi trường build tách riêng. `tsc` chỉ kiểm tra kiểu; build và kiểm tra trên trình duyệt vẫn cần thiết.
