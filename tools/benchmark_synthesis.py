"""Bounded local-only smoke benchmark; does not import the web app or its DB."""
from pathlib import Path
import subprocess
import sys


CHILD = r'''
import json, sys, time
from ctransformers import AutoModelForCausalLM
start = time.monotonic()
model = AutoModelForCausalLM.from_pretrained(
    sys.argv[1], model_type='llama', threads=4, gpu_layers=0,
    context_length=2048, max_new_tokens=48, temperature=0.1,
)
print(json.dumps({'loaded_seconds': round(time.monotonic()-start, 3)}), flush=True)
prompt = '<|im_start|>system\nChỉ dùng dữ liệu sau để tư vấn điện thoại. Trả lời tiếng Việt ngắn gọn, không thêm thông số.\n<|im_end|>\n<|im_start|>user\nNgân sách 15 triệu, muốn chơi game. Samsung A55 5G giá tham khảo 8,5-9,9 triệu, phù hợp gaming tầm trung. Không có dữ liệu FPS. Tóm tắt trong 2 câu.\n<|im_end|>\n<|im_start|>assistant\n'
start = time.monotonic()
chunks = []
for piece in model(prompt, stream=True, stop=['<|im_end|>','<|im_start|>']):
    if not chunks:
        print(json.dumps({'first_output_seconds': round(time.monotonic()-start, 3)}), flush=True)
    chunks.append(piece)
print(json.dumps({'generation_seconds': round(time.monotonic()-start, 3), 'answer': ''.join(chunks)}, ensure_ascii=False), flush=True)
'''

if __name__ == '__main__':
    model = Path(__file__).resolve().parents[1] / 'model' / 'vinallama-7b-chat_q5_0.gguf'
    try:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', CHILD, str(model)],
                                capture_output=True, text=True, encoding='utf-8', timeout=45)
        print(result.stdout)
        print(result.stderr[-1500:])
        raise SystemExit(result.returncode)
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b''
        print(output.decode('utf-8', errors='replace') if isinstance(output, bytes) else output)
        errors = error.stderr or b''
        print(errors[-1500:].decode('utf-8', errors='replace') if isinstance(errors, bytes) else errors[-1500:])
        print('Benchmark stopped at 45 seconds; model process terminated.')
