# Phân quyền dashboard nhúng

Dashboard dùng tài khoản đăng nhập của ứng dụng để cấp guest token Superset.
Admin xem toàn bộ dữ liệu. Tài khoản khác phải có quy tắc trong
`public.user_dataset_rls` cho **mọi dataset thực tế được dùng bởi các chart**
trên dashboard. Thiếu quy tắc trả `403`, không tự cấp quyền toàn bộ.

Quy tắc áp dụng theo dataset ID, không theo tên tài khoản. Một tài khoản có
role `admin` luôn xem toàn bộ, kể cả khi tên tài khoản chứa Manhattan/Queens.
Các tài khoản demo giới hạn vùng là `user_manhattan`, `user_queens` (role
`manager`). Không sửa role của tài khoản khác tự động.

Với dataset taxi gốc `raw.yellow_taxi_trips`, quy tắc `pickup_borough = '...'`
được chuyển thành điều kiện `pu_location_id` đối chiếu `raw.taxi_zone_lookup`.
Dataset ảo có cột `pickup_borough` dùng điều kiện trực tiếp. Không giả định
dashboard ID bằng dataset ID.

## Hành vi

- Các API trong `/api/v1/superset/` yêu cầu Bearer token hợp lệ và tài khoản active.
- Guest token chứa username thật và các điều kiện RLS theo dataset.
- Chuyển tài khoản hủy iframe cũ, bỏ kết quả giải thích/báo cáo cũ và tải lại dashboard.
- Giải thích chart và dữ liệu báo cáo của manager chạy bằng guest token;
  các request này không mang cookie hoặc access token của Superset Admin.
- Ảnh báo cáo của manager được render trong trình duyệt riêng bằng guest token.
  Backend từ chối ảnh nếu Superset chưa hỗ trợ chế độ RLS này.
- Xuất báo cáo sử dụng dashboard đang mở, tab và bộ lọc đang chọn, cộng với
  giới hạn RLS bắt buộc. Bộ lọc giao diện không thể bỏ giới hạn RLS.

Thay đổi này bảo vệ luồng dashboard nhúng và các API giải thích/xuất báo cáo
liên quan. Các API chat, upload, preview dữ liệu và lịch sử hội thoại cần được
nghiệm thu phân quyền riêng; không suy ra rằng toàn bộ ứng dụng đã có phân quyền hoàn chỉnh.

## Triển khai

Cần phát hành **cả backend, frontend và Superset image mới**. Chỉ đổi `.env.prod`
hoặc restart image cũ không cập nhật mã nguồn. Frontend/Superset production
không mount mã nguồn từ server. Dùng CI/CD của dự án để build/publish/deploy
phiên bản mới; giữ mapping `.images.prod` khi thao tác Compose thủ công.
CD đã làm mới gateway sau khi các container ứng dụng thay đổi.

Nếu server có dataset ID khác local, kiểm tra quy tắc đang lưu và datasource
thực tế của chart. Cấp quy tắc cho đúng dataset đã được duyệt; không mặc định
cấp quyền cho tất cả dataset có tên tương tự.

## Kiểm thử

1. Cùng dashboard taxi, cùng tab và bộ lọc: ghi Total Trips bằng Admin,
   Manhattan, Queens. Đối chiếu với COUNT trong PostgreSQL theo vùng đón khách.
2. Manhattan chọn bộ lọc Queens: không nhận dữ liệu Queens.
3. Chuyển trực tiếp Admin → Manhattan → Queens: iframe tải lại và không giữ
   số liệu hoặc cửa sổ giải thích của tài khoản trước.
4. Giải thích cùng chart ở mỗi tài khoản: số liệu khớp phạm vi tài khoản.
5. Xuất PDF/DOCX bằng manager: cả nhận xét, số liệu và ảnh chart đều nằm trong
   phạm vi RLS. Không có ảnh toàn bộ dữ liệu bên cạnh số liệu đã giới hạn.
6. Gọi guest-token, charts, explain, report khi thiếu/sai Bearer token: `401`.
7. Tài khoản không có quy tắc hoặc dashboard trộn dataset chưa được cấp quyền: `403`.

Tiền kiểm `scripts/demo_preflight.py` vẫn chỉ gọi GET. Truyền token ứng dụng
qua biến môi trường `APP_PREFLIGHT_TOKEN` để kiểm tra các API dashboard.
Không đưa token vào Git hoặc gửi token trong log kiểm thử.

## Kết quả kiểm tra local ngày 09/10/2026

- Bộ backend: 132 ca đạt, gồm 13 ca hồi quy cho phân quyền dashboard.
- Frontend: kiểm tra kiểu, kiểm thử DOCX, định dạng và production build đạt.
- Cùng chart Total Trips: Admin 30.000, Manhattan 26.184, Queens 2.653;
  số liệu Manhattan/Queens khớp truy vấn PostgreSQL theo vùng đón khách.
- Cả dataset taxi gốc và dataset phân tích trả 26.184 cho Manhattan.
- API thật cấp guest token theo từng username/RLS; Asia mở dashboard taxi trả
  `403`, request không đăng nhập trả `401`.
- Giải thích KPI thật và ảnh báo cáo Manhattan đều hiển thị 26.184.
- Superset tạo được bộ ảnh của báo cáo theo RLS. Phần sinh nhận xét Gemini
  đã kiểm thử bằng mock, chưa xác minh được với provider thật trong phiên này.
- Chưa thực hiện kiểm thử chuyển tài khoản qua trình duyệt do phiên làm việc
  không có trình duyệt được kết nối. Cần chạy lại ca 3 sau khi deploy.
