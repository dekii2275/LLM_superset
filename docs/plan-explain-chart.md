# Kế hoạch tính năng giải thích biểu đồ

## Mục tiêu

Cho phép người dùng xem giải thích ngắn gọn, dựa trên dữ liệu thực tế của biểu đồ được tạo trong cuộc trò chuyện. Giải thích nêu xu hướng hoặc điểm nổi bật, kèm số liệu làm bằng chứng và giới hạn của kết luận.

## Phạm vi V1

- Thêm nút **Giải thích biểu đồ** cho chart được tạo và hiển thị trong chat.
- Hỗ trợ các loại chart hiện có trong chat: bar, line, pie và area.
- Phân tích kết quả truy vấn đang dùng cho chart.
- Trả về tóm tắt, các điểm nổi bật và lưu ý về phạm vi dữ liệu.
- Không bao gồm chart nằm trong dashboard Superset được nhúng. Phần đó cần một luồng riêng để đọc dữ liệu chart và các bộ lọc dashboard đang áp dụng.
- Không đưa ra khẳng định nhân quả nếu dữ liệu chỉ thể hiện mối liên hệ hoặc xu hướng.

## Trải nghiệm người dùng

1. Người dùng bấm **Giải thích biểu đồ** bên dưới chart.
2. Nút hiển thị trạng thái đang phân tích.
3. Kết quả xuất hiện ngay dưới chart, gồm:
   - **Tóm tắt:** chỉ số, nhóm hoặc khoảng thời gian được biểu diễn.
   - **Điểm nổi bật:** giá trị cao nhất/thấp nhất, xu hướng hoặc biến động đáng chú ý.
   - **Lưu ý:** phạm vi các dòng/nhóm đã phân tích và giới hạn của kết luận.
4. Nếu yêu cầu thất bại, giao diện hiển thị lỗi ngắn gọn và cho phép thử lại.

## Luồng kỹ thuật đề xuất

1. Frontend gửi SQL của truy vấn đã tạo chart cùng thông tin biểu đồ (`VisualizationSpec`) tới API giải thích.
2. Backend kiểm tra lại SQL theo chính sách chỉ đọc và chạy lại truy vấn bằng `QueryService`.
3. Backend tính các số liệu tổng hợp cần thiết từ kết quả truy vấn.
4. Backend gửi metadata biểu đồ và các số liệu đã tính cho Gemini để diễn đạt thành lời giải thích ngắn bằng tiếng Việt.
5. Backend trả response có cấu trúc để frontend hiển thị tóm tắt, điểm nổi bật và lưu ý.

Tính toán số liệu ở backend giúp lời giải thích dựa trên giá trị cụ thể. Không cần gửi toàn bộ dữ liệu thô cho mô hình nếu có thể tính trước các thống kê cần thiết.

## Các bước triển khai

### 1. Thiết kế API và schema

- Tạo endpoint riêng, ví dụ `POST /api/v1/ai/explain-chart`.
- Request nhận SQL và thông tin biểu đồ cần giải thích.
- Response có các trường tách biệt cho tóm tắt, điểm nổi bật và lưu ý.
- Giữ thao tác giải thích độc lập với luồng chat phân loại intent và các thao tác tạo/chỉnh sửa chart.

### 2. Tính thống kê từ dữ liệu

- Với chart phân loại: tìm nhóm cao nhất/thấp nhất và chênh lệch giữa chúng.
- Với chuỗi thời gian: tìm chiều hướng chung, thay đổi giữa đầu/cuối chuỗi và biến động lớn nếu dữ liệu đủ điểm.
- Chỉ tính tỷ lệ phần trăm khi mẫu số hợp lệ và nêu rõ mẫu dữ liệu dùng để tính.
- Với dữ liệu rỗng, thiếu giá trị số hoặc không đủ điểm, trả về giải thích giới hạn thay vì suy đoán.
- Khi truy vấn chỉ trả về một phần nhóm (ví dụ top N), ghi rõ kết quả chỉ phản ánh các nhóm đang hiển thị.

### 3. Tạo lời giải thích

- Mở rộng `GeminiService` với phương thức tạo giải thích chart.
- Prompt yêu cầu mô tả chính xác các số liệu được cung cấp, không tự thêm số hoặc kết luận nguyên nhân.
- Giới hạn độ dài để kết quả dễ đọc ngay dưới biểu đồ.
- Xử lý lỗi dịch vụ AI rõ ràng; có thể cung cấp câu giải thích mẫu từ thống kê đã tính nếu Gemini không khả dụng.

### 4. Tích hợp giao diện

- Thêm nút và panel giải thích vào chart trong chat.
- Bổ sung trạng thái loading, lỗi và kết quả; tránh gửi lặp yêu cầu khi request đang chạy.
- Thêm hàm gọi API và kiểu TypeScript cho request/response.
- Giữ giải thích gắn với đúng tin nhắn/chart để người dùng có thể yêu cầu giải thích nhiều chart độc lập.

### 5. Kiểm tra và hoàn thiện

- Kiểm tra chart cột, đường, tròn và vùng.
- Kiểm tra dữ liệu rỗng, dữ liệu không đủ điểm và giá trị thiếu.
- Kiểm tra SQL không hợp lệ/bị từ chối và lỗi từ dịch vụ AI.
- Kiểm tra trạng thái loading, thử lại và nhiều chart trong cùng cuộc trò chuyện.
- Đối chiếu các con số được nêu trong lời giải thích với kết quả truy vấn thực tế.

## Tiêu chí hoàn thành

- Nút giải thích chỉ xuất hiện khi tin nhắn có chart hợp lệ và dữ liệu truy vấn tương ứng.
- Các con số trong giải thích khớp với kết quả truy vấn.
- Phạm vi phân tích được nêu rõ khi chart chỉ hiển thị một phần kết quả.
- Không có khẳng định nhân quả nếu dữ liệu không chứng minh được quan hệ nhân quả.
- Lỗi API không làm giao diện bị kẹt ở trạng thái loading và người dùng có thể thử lại.
- Các luồng hỏi dữ liệu, tạo chart và chỉnh sửa dashboard hiện tại tiếp tục hoạt động.

## Rủi ro và cách xử lý

| Rủi ro | Cách xử lý |
| --- | --- |
| Truy vấn có giới hạn dòng hoặc chỉ trả về top N | Chỉ mô tả phần dữ liệu thực sự được phân tích và thể hiện rõ phạm vi đó. |
| Mô hình diễn giải quá mức hoặc tự thêm nguyên nhân | Tính số liệu ở backend, chỉ đưa bằng chứng cần thiết vào prompt và yêu cầu mô hình nêu giới hạn. |
| Cùng một chart được giải thích nhiều lần gây tăng thời gian/chi phí | Chỉ gọi API khi người dùng bấm nút; cân nhắc lưu kết quả trong state của tin nhắn trong phiên hiện tại. |
| SQL từ frontend bị sửa đổi | Backend xác thực SQL theo chính sách chỉ đọc trước khi thực thi. |
| Dashboard Superset không cung cấp ngữ cảnh lọc cho ứng dụng | Để giải thích dashboard nhúng ở giai đoạn sau, sau khi thiết kế được cách lấy dữ liệu và filter context an toàn. |

## Ước lượng

Ước lượng sơ bộ cho một lập trình viên: **2–4 ngày công** để hoàn thành V1 gồm backend, giao diện và kiểm tra các trường hợp chính. Phạm vi chart trong dashboard Superset được tách sang giai đoạn tiếp theo.

## Mở rộng sau V1

- Giải thích chart trong dashboard Superset với bộ lọc hiện hành.
- Gợi ý câu hỏi tiếp theo dựa trên điểm nổi bật vừa phát hiện.
- Phát hiện biến động bất thường và so sánh giữa các nhóm hoặc giai đoạn.
- Tải giải thích thành ghi chú hoặc đưa vào phần mô tả chart.
