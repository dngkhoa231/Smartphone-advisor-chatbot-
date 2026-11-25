# PhoneGPT — Đồ án chatbot tư vấn điện thoại

Ứng dụng hỗ trợ tra cứu thông số, so sánh và gợi ý điện thoại từ bộ dữ liệu Excel. Giao diện tiếng Việt có đăng ký, đăng nhập, lịch sử cá nhân, xóa từng mục và xem nguồn tham khảo.

## Môi trường và khởi chạy

Python 3.11 trên Windows. Thử nghiệm thực hiện trên máy có 16 GB RAM. Mô hình ngôn ngữ chiếm khoảng 4,74 GB trên đĩa. Hai tệp GGUF được đặt trong `model/` của bản đầy đủ.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe app.py
```

Mở http://127.0.0.1:5000. Đăng ký tài khoản riêng với mật khẩu ít nhất 12 ký tự. SQLite được tạo tự động khi chạy. Cài thư viện lần đầu cần internet. Model và dữ liệu dùng tại máy.

Bản `PhoneGPT_source_20261126.zip` chứa mã nguồn, dữ liệu, chỉ mục, kiểm thử và tài liệu. Khi dùng bản ZIP này, cần bổ sung hai tệp `all-MiniLM-L6-v2.gguf2.f16.gguf` và `vinallama-7b-chat_q5_0.gguf` vào thư mục `model/`.

## Cấu trúc

| Thành phần | Trách nhiệm |
| --- | --- |
| app.py | HTTP API, xác thực, lưu lịch sử, điều phối trả lời |
| answer_engine.py | Đối chiếu FAQ, nhận diện phiên bản máy, giới hạn tác vụ suy luận |
| recommendations.py | Lọc tư vấn theo điều kiện trong dữ liệu |
| conversation_context.py | Bổ sung ngữ cảnh từ các câu hỏi trước |
| security_controls.py | CSRF, giới hạn yêu cầu, phiên đăng nhập và HTTP headers |
| prepare_vector_db.py | Đọc Excel, tạo embedding và chỉ mục FAISS |
| templates/index.html | Giao diện trình duyệt |
| test_*.py | Kiểm thử đơn vị và tích hợp API |
| docs/ | Đặc tả và đánh giá kỹ thuật |
| evaluation/ | Kết quả đo và danh sách vấn đề dữ liệu |

## Chạy kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
.\.venv\Scripts\python.exe tools/audit_data_quality.py --out evaluation
.\.venv\Scripts\python.exe tools/evaluate_project.py --out evaluation
```

Sau khi thay đổi Excel, tạo lại chỉ mục bằng `python prepare_vector_db.py --offline`, sau đó khởi động lại ứng dụng. Chỉ mục hiện tại khớp dữ liệu kèm theo.

Kết quả và giới hạn được trình bày trong `docs/DANH_GIA.md`. Phạm vi triển khai của phiên bản này là demo trên localhost.
