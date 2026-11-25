"""Đọc FAQ từ Excel và tạo FAISS cho chatbot điện thoại chạy local."""

import argparse
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "data1.xlsx"
DB_DIR = BASE_DIR / "vectorstores" / "db_faiss"
MODEL_DIR = BASE_DIR / "model"
EMBEDDING_MODEL = "all-MiniLM-L6-v2.gguf2.f16.gguf"


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_training(path=DATA_FILE):
    """Chỉ đọc sheet training; tìm cột theo tiêu đề, giữ số dòng Excel."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Đặt data1.xlsx trong thư mục data: {path}")

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "training" not in workbook.sheetnames:
            raise ValueError("File Excel cần có sheet tên training.")
        sheet = workbook["training"]
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, ())
        labels = [str(value or "").strip().casefold() for value in header]
        try:
            question_col = labels.index("câu hỏi")
            answer_col = labels.index("câu trả lời")
        except ValueError as error:
            raise ValueError("Dòng 1 cần có tiêu đề: câu hỏi, Câu trả lời.") from error
        source_col = labels.index("nguồn tham khảo") if "nguồn tham khảo" in labels else None

        records = []
        incomplete = []
        for excel_row, values in enumerate(rows, start=2):
            question = str(values[question_col] if question_col < len(values) and values[question_col] is not None else "").strip()
            answer = str(values[answer_col] if answer_col < len(values) and values[answer_col] is not None else "").strip()
            reference_url = str(values[source_col] if source_col is not None and source_col < len(values) and values[source_col] is not None else "").strip()
            if not question and not answer:
                continue
            if not question or not answer:
                incomplete.append({"row": excel_row, "question": question})
                continue
            records.append({
                "question": question,
                "answer": answer,
                "source": path.name,
                "sheet": "training",
                "row": excel_row,
                "reference_url": reference_url if reference_url.startswith("https://") else "",
            })
        if not records:
            raise ValueError("Sheet training chưa có cặp hỏi–đáp đầy đủ.")
        return records, incomplete
    finally:
        workbook.close()


def create_embeddings(allow_download):
    """Dùng cùng một model embedding ở bước lập chỉ mục và hỏi–đáp."""
    from langchain_community.embeddings import GPT4AllEmbeddings

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / EMBEDDING_MODEL
    if not model_path.is_file() and not allow_download:
        raise FileNotFoundError("Chưa có model embedding. Chạy prepare_vector_db.py trước.")
    return GPT4AllEmbeddings(
        model_name=EMBEDDING_MODEL,
        device="cpu",
        n_threads=4,
        gpt4all_kwargs={
            "model_path": str(MODEL_DIR),
            "allow_download": allow_download and not model_path.is_file(),
        },
    )


def print_summary(records, incomplete):
    print(f"Đọc được {len(records)} cặp hỏi–đáp đầy đủ từ sheet training.", flush=True)
    if incomplete:
        row_numbers = ", ".join(str(item["row"]) for item in incomplete)
        print(f"Bỏ qua {len(incomplete)} dòng thiếu dữ liệu: {row_numbers}", flush=True)
    print("Sheet test được giữ riêng, không đưa vào chỉ mục.", flush=True)


def build_index(offline=False):
    # Nhớ phiên bản đầu vào; nếu Excel bị sửa trong lúc lập chỉ mục thì chạy lại.
    source_digest = file_digest(DATA_FILE) if DATA_FILE.is_file() else None
    records, incomplete = read_training()
    print_summary(records, incomplete)

    from langchain_core.documents import Document
    from langchain_community.vectorstores import FAISS

    documents = [
        Document(
            page_content=f"Câu hỏi: {item['question']}\nCâu trả lời: {item['answer']}",
            metadata=item,
        )
        for item in records
    ]
    print("Đang nạp embedding; lần đầu cần mạng để tải model nhỏ...", flush=True)
    embeddings = create_embeddings(allow_download=not offline)
    print("Đang lập chỉ mục, tiến độ tính theo số cặp hỏi–đáp...", flush=True)

    # Xử lý từng nhóm để thấy tiến độ thay vì chờ toàn bộ file.
    batch_size = 32
    database = FAISS.from_documents(documents[:batch_size], embeddings)
    done = min(batch_size, len(documents))
    print(f"{done}/{len(documents)}", flush=True)
    for start in range(batch_size, len(documents), batch_size):
        database.add_documents(documents[start:start + batch_size])
        print(f"{min(start + batch_size, len(documents))}/{len(documents)}", flush=True)

    if file_digest(DATA_FILE) != source_digest:
        raise RuntimeError("Excel đã thay đổi trong lúc lập chỉ mục. Hãy chạy lại.")

    DB_DIR.mkdir(parents=True, exist_ok=True)
    # Chỉ tải lại các file FAISS do chính script này tạo trên máy của bạn.
    database.save_local(str(DB_DIR))
    manifest = {
        "source_sha256": source_digest,
        "embedding_model": EMBEDDING_MODEL,
        "document_count": len(documents),
        "incomplete": incomplete,
    }
    (DB_DIR / "source.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Xong! Đã lưu {len(documents)} cặp tại: {DB_DIR}", flush=True)
    print("Bước tiếp theo: chạy qabot.py", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Lập chỉ mục FAQ điện thoại từ data/data1.xlsx")
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra Excel, chưa tải model")
    parser.add_argument("--offline", action="store_true", help="Chỉ dùng model có sẵn; cấm kết nối mạng từ Python")
    args = parser.parse_args()
    if args.offline:
        import os
        import socket
        os.environ['LANGCHAIN_TRACING_V2'] = 'false'
        os.environ['LANGSMITH_TRACING'] = 'false'
        def deny_network(*args, **kwargs):
            raise RuntimeError('Offline indexing: outbound connections are disabled')
        socket.socket.connect = deny_network
        socket.socket.connect_ex = deny_network
        socket.create_connection = deny_network
    if args.check:
        records, incomplete = read_training()
        print_summary(records, incomplete)
    else:
        build_index(offline=args.offline)


if __name__ == "__main__":
    main()
