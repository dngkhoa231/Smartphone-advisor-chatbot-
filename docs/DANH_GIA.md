# Đánh giá kỹ thuật PhoneGPT

Ngày đánh giá 26/11/2026. Kết quả áp dụng cho mã và dữ liệu trong bản này.

## Kết luận

Phiên bản có chức năng demo và bộ kiểm thử hồi quy chạy thành công. Chưa đạt điều kiện khẳng định dữ liệu đầy đủ, toàn bộ thông tin đúng hoặc ứng dụng đủ an toàn để triển khai công khai.

## Dữ liệu

| Chỉ tiêu đo | Kết quả |
| --- | ---: |
| Cặp hỏi–đáp đầy đủ | 781 |
| Câu thiếu đáp án | 0 |
| Cặp có URL tham khảo | 168 |
| Cặp chưa có URL tham khảo | 613 |
| Phiên bản điện thoại được bộ nhận diện tìm thấy | 85 |
| Phiên bản thiếu ít nhất một trong 7 thuộc tính cốt lõi | 30 |
| Nhóm câu trùng chuẩn hóa có đáp án xung đột | 0 |

Bảy thuộc tính được đối chiếu gồm giá, chip, RAM, bộ nhớ, màn hình, camera và pin. Bộ đếm căn cứ nội dung câu hỏi và quy tắc nhận diện, cần rà soát thủ công những trường hợp diễn đạt khác. Có URL chưa chứng minh nội dung đã được kiểm chứng. Giá cần gắn phiên bản dung lượng, tình trạng máy, nơi bán và ngày ghi nhận.

`evaluation/data_issues.csv` liệt kê từng dòng thiếu đáp án hoặc thiếu nguồn. `evaluation/phone_coverage.csv` liệt kê các thuộc tính thiếu theo phiên bản máy. Dữ liệu chưa có quy trình xác nhận đầy đủ nguồn, ngày kiểm chứng và người rà soát. Các con số trên là hiện trạng dữ liệu, không phải tỷ lệ chính xác.

14 đáp án giá được ghi nhận từ từng trang sản phẩm CellphoneS ngày 26/11/2026, khu vực Hồ Chí Minh, kèm RAM và dung lượng. Chi tiết: `data/price_sources_20261126.json`. Số cặp có URL là số đếm liên kết, chưa phải số cặp đã kiểm chứng đầy đủ. Không dùng trang chủ CellphoneS để chứng minh chung cho các câu chưa có nguồn.

## Kiểm thử phần mềm

Chưa xác định được công thức và quy ước tính theo tài liệu môn học. Phần này chỉ báo cáo kết quả thực thi. Không quy đổi số bài chạy qua thành độ bao phủ mã, độ chính xác chatbot hoặc mức hoàn thành yêu cầu môn học.

87 bài kiểm thử tự động đã chạy qua. Các nhóm gồm xác thực, phiên, CSRF, giới hạn dữ liệu, lịch sử theo tài khoản, đối chiếu sản phẩm, ngữ cảnh, tư vấn và sao lưu. Kết quả từng bài nằm trong `evaluation/unit_tests.txt`.

Bộ 33 câu hồi quy chạy không phát sinh ngoại lệ. Có 33 câu trả dòng nguồn nội bộ, 18 câu có URL ngoài và 21 câu khớp văn bản đáp án kỳ vọng sau chuẩn hóa. Cả 33 câu đều đi qua các nhánh có sẵn, số câu gọi model là 0. Bộ này đã được dùng trong quá trình phát triển nên chưa đủ để đo chất lượng tổng quát trên câu hỏi mới.

Chưa đo tỷ lệ bao phủ dòng/nhánh. Chưa có đánh giá độc lập bởi người dùng, kiểm thử tải dài hạn hoặc kiểm thử trình duyệt hoàn chỉnh. Truy cập localhost qua công cụ trình duyệt bị timeout trong môi trường đánh giá. API đã được kiểm tra bằng Flask test client.

## Thử model và thư viện

VinaLLaMA nạp được trong 4,625 giây. Trong phép thử riêng 48 token, ký tự đầu xuất hiện sau 26,234 giây tính từ lúc bắt đầu sinh. Tiến trình bị dừng tại giới hạn tổng 45 giây trước khi hoàn tất câu trả lời. Đây là một lần đo trên máy hiện tại, chưa phải thống kê hiệu năng. Nhánh trả lời web có ngân sách mặc định 20 giây và cơ chế dự phòng.

`pip check` báo không có phụ thuộc bị hỏng. Chưa thực hiện được quét CVE tự động vì kết nối pypi.org bị lỗi DNS khi cài công cụ pip-audit. Kiểm tra tương thích phụ thuộc chưa đủ để kết luận thư viện không có lỗ hổng.

## Các sửa đổi đã kiểm chứng

- Từ chối CSRF token Unicode sai bằng HTTP 403 thay vì phát sinh lỗi máy chủ.
- Nhận đúng địa chỉ loopback IPv6 khi kiểm tra Host.
- Báo HTTP 503 khi cơ sở dữ liệu phiên hoặc đọc lịch sử không sẵn sàng.
- Báo history_saved=false khi lưu chat lỗi, hiển thị cảnh báo trên giao diện.
- Khi MongoDB đang hoạt động, lỗi lịch sử được trả về thay vì ghi sang kho khác.
- Từ chối đăng nhập với bản băm mật khẩu hỏng mà không gây lỗi 500.
- Đóng kết nối lịch sử SQLite cả khi thao tác lỗi và thêm chỉ mục truy vấn theo tài khoản.
- Hiển thị URL nguồn bằng DOM text và giới hạn đường dẫn HTTPS.
- Bổ sung đủ 14 dòng giá tham khảo còn thiếu từ nguồn CellphoneS (26/11/2026), bổ sung 28 URL nguồn Apple chính thức và dựng lại chỉ mục FAISS offline (781/781 cặp).
- Chuyển `/api/chat_stream` sang stream token thật qua SSE kèm sự kiện `replace` khi hết giờ/cắt cụt; cache `csrf_token` trên giao diện (tự làm mới khi nhận 403); tự chọn số luồng CPU (`min(8, max(4, os.cpu_count()))`) và hỗ trợ cấu hình `PHONEGPT_MODEL_FILE`.

## Điều kiện hoàn thiện

1. Bổ sung và đối chiếu các dòng trong data_issues.csv với nguồn chính thức hoặc nhà bán lẻ có ngày ghi nhận. Xác định phạm vi mẫu máy đủ dữ liệu cho bản nghiệm thu.
2. Rà soát đầy đủ bộ 33 đáp án kỳ vọng, bổ sung bộ câu hỏi đánh giá mới được giữ riêng khỏi quá trình sửa luật.
3. Hoàn tất kiểm thử giao diện trên trình duyệt và quét lỗ hổng thư viện khi kết nối cho phép.
4. Đo nhiều lần nhánh model thật, đánh giá chất lượng câu sinh và điều chỉnh model/cấu hình theo giới hạn máy.

Đánh giá hiện tại phù hợp với một bản đồ án đang hoàn thiện có bằng chứng kiểm thử. Các điều kiện trên còn mở.
