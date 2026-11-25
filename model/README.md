# Thư mục model local

Hai tệp mô hình GGUF được loại khỏi Git vì `vinallama-7b-chat_q5_0.gguf` (~4,74 GB) vượt giới hạn dung lượng tệp của GitHub:

- `all-MiniLM-L6-v2.gguf2.f16.gguf` (~45,9 MB) — model embedding
- `vinallama-7b-chat_q5_0.gguf` (~4,74 GB) — mô hình ngôn ngữ VinaLLaMA 7B Q5

Trước khi chạy ứng dụng hoặc dựng lại chỉ mục offline (`prepare_vector_db.py --offline`), hãy đặt hai tệp GGUF này vào thư mục `model/`.
