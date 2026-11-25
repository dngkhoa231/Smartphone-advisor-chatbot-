"""Ground FAQ answers in exact phone variants and requested attributes."""
import queue
import logging
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher


def normalize(text):
    text = unicodedata.normalize('NFKD', text.casefold().replace('đ', 'd'))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^\w+]', ' ', text).split())


PHONE_PATTERN = re.compile(
    r'\biphone\s*\d{1,2}[e]?(?:\s*(?:pro\s*max|pro|plus|mini|air))?(?!\w)'
    r'|\b(?:(?:samsung\s*)?(?:galaxy\s*)?)'
    r'(?:[samf]\s*\d{1,3}s?(?:\s*(?:ultra|fe|plus|\+))?'
    r'|z?\s*(?:fold|flip)\s*\d{1,2})(?:\s*[45]g)?(?!\w)'
    r'|\bredmi\s*note\s*\d{1,2}(?:\s*pro(?:\s*(?:plus|\+))?)?'
    r'(?:\s*[45]g)?(?!\w)'
    r'|\bpoco\s*[xfm]\s*\d{1,2}(?:\s*(?:pro\s*max|pro|ultra))?'
    r'(?:\s*5g)?(?!\w)'
)


def phones(text):
    result = {}
    normalized = re.sub(r'\bip\s*(?=\d)', 'iphone ', normalize(text))
    for match in PHONE_PATTERN.finditer(normalized):
        name = match.group().strip()
        key = re.sub(r'samsung|galaxy|\s+', '', name).replace('plus', '+')
        if key.startswith(('fold', 'flip')):
            key = 'z' + key
        result[key] = name
    return result


TOPICS = {
    'giá': r'\b(?:gia|bao nhieu tien|gia tien|gia ban|bao nhieu trieu|muc gia|chi phi)\b',
    'RAM': r'\bram\b',
    'chip': r'\b(?:chip|chipset|processor|cpu|vi xu ly|vi xu li|bo xu ly|cau hinh phan cung)\b',
    'bộ nhớ': r'\b(?:bo nho|dung luong luu tru|ban dung luong|rom|luu tru)\b',
    'màn hình': r'\b(?:man hinh|display|inch|tan so quet|tan so lam tuoi|hz|privacy display)\b',
    'camera': r'\b(?:camera|may anh|chup anh|chup hinh|chup hinh anh|quay phim|quay video|quay chup)\b',
    'pin': r'\b(?:pin|mah|sac)\b',
    'S Pen': r'\b(?:s pen|spen|but)\b',
    'chơi game': r'\b(?:choi game|gaming|hieu nang|cay game|chien game)\b',
    'chống nước': r'\b(?:chong nuoc|ip68|ip67)\b',
    'màu sắc': r'\b(?:mau sac|mau nao|mau gi|may mau)\b',
    'ra mắt': r'\b(?:ra mat|cong bo|phat hanh)\b',
    'kết nối': r'\b(?:ban mang|ket noi mang|bien the ket noi|nhung phien ban)\b',
    'giới thiệu': r'\b(?:la dien thoai gi|loai thiet bi|phan khuc|dinh vi)\b',
}


def topics(text):
    normalized = normalize(text)
    # "đánh giá" is a review, not a price query.
    normalized = normalized.replace('danh gia', 'nhan xet')
    normalized = normalized.replace('bo nho ram', 'ram')
    # Vietnamese "sắc" (colour) must not be interpreted as "sạc" (charging).
    if re.search(r'\b(?:mau sac|mau nao|mau gi)\b', normalized):
        normalized = re.sub(r'\bmau sac\b', 'mau nao', normalized)
    return {name for name, pattern in TOPICS.items() if re.search(pattern, normalized)}


class FAQEngine:
    def __init__(self, records):
        self.records = records
        self.exact = {}
        for record in records:
            self.exact.setdefault(normalize(record['question']), []).append(record)
        self.catalog = [(r, set(phones(r['question'])), topics(r['question'])) for r in records]
        # Reviewed canonical factual entries; resolve by question, never by a
        # fragile Excel row number. Assessment questions keep their own intent.
        self.canonical_chip = {}
        for key, question in [('iphone17e','iPhone 17e dùng chip gì?'),
                              ('redminote15','Redmi Note 15 dùng chip gì?')]:
            matches = self.exact.get(normalize(question), [])
            if len(matches)==1:
                self.canonical_chip[key] = matches[0]

    @staticmethod
    def render(records):
        unique = list({r['row']: r for r in records}.values())
        return '\n\n'.join(r['answer'].strip() for r in unique), [r['row'] for r in unique]

    def compare(self, requested, wanted):
        """Line up the same attributes without inferring winners or filling gaps."""
        wanted = wanted - {'giới thiệu', 'kết nối', 'ra mắt', 'màu sắc'}
        by_phone = {
            key: [(r, t) for r, models, t in self.catalog if models == {key}]
            for key in requested
        }
        available = set().union(*(t for rows in by_phone.values() for _, t in rows))
        # Always show common purchasing criteria for a general comparison. Optional
        # features appear only when at least one compared product has such a row.
        scope = wanted or ({'giá', 'chip', 'RAM', 'bộ nhớ', 'màn hình', 'camera', 'pin'} | available)
        criteria = [
            ('Giá tham khảo', {'giá'}), ('Chip / RAM', {'chip', 'RAM'}),
            ('Bộ nhớ', {'bộ nhớ'}), ('Màn hình', {'màn hình'}),
            ('Camera', {'camera'}), ('Pin / sạc', {'pin'}),
            ('Chơi game', {'chơi game'}), ('Chống nước', {'chống nước'}),
            ('S Pen', {'S Pen'}),
        ]
        sections = ['So sánh theo dữ liệu hiện có:']
        for key, display in requested.items():
            if not by_phone[key]:
                sections.append(f'Chưa có dữ liệu cho {display}; không dùng thông số của phiên bản khác để thay thế.')
        sources = []
        has_missing = False
        for title, group in criteria:
            selected_topics = group & scope
            if not selected_topics:
                continue
            if group == {'chip', 'RAM'} and len(selected_topics) == 1:
                title = 'Chip' if 'chip' in selected_topics else 'RAM'
            lines = [title + ':']
            for key, display in requested.items():
                candidates = by_phone[key]
                matching = [r for r, t in candidates if t & selected_topics]
                answer, rows = self.render(matching)
                known = set().union(*(t for _, t in candidates))
                missing = selected_topics - known
                lines.append(f'{display}:')
                if answer:
                    lines.append(answer)
                    sources.extend(rows)
                if missing:
                    has_missing = True
                    lines.append(f'Chưa có dữ liệu về {", ".join(sorted(missing))}.')
            sections.append('\n'.join(lines))
        if 'giá' in scope:
            sections.append('Giá trong dữ liệu là giá tham khảo; cần đối chiếu đúng dung lượng và tình trạng máy khi mua.')
        if has_missing:
            sections.append('Các mục còn thiếu chưa đủ cơ sở để kết luận máy nào hơn ở tiêu chí đó.')
        return '\n\n'.join(sections), list(dict.fromkeys(sources))

    def direct(self, question):
        """Return a grounded answer, or None when semantic retrieval is needed."""
        norm = normalize(question)
        model_keys=set(phones(question))
        if len(model_keys)==1 and topics(question)=={'chip'} and not re.search(r'\b(?:manh|tot|game|hieu nang|anh huong|so sanh)\b',norm):
            canonical=self.canonical_chip.get(next(iter(model_keys)))
            if canonical is not None:
                return self.render([canonical])
        exact = self.exact.get(norm)
        if exact:
            if len({normalize(r['answer']) for r in exact}) > 1:
                return 'Dữ liệu có nhiều đáp án khác nhau cho câu hỏi này. Cần kiểm tra lại các dòng nguồn.', [r['row'] for r in exact]
            return self.render(exact[:1])
        if norm in {'chao', 'xin chao', 'chao ban', 'hello', 'hi'}:
            return 'Chào bạn! Bạn muốn tìm hiểu điện thoại nào và cần biết giá hay thông số gì?', []
        requested = phones(question)
        wanted = topics(question)
        # A distinctive feature can identify a product only from matching source
        # answers; never substitute a randomly retrieved phone for a general query.
        if not requested and 'privacy display' in norm:
            matching = [r for r in self.records if 'privacy display' in normalize(r['answer'])]
            if matching:
                return self.render(matching)
        compare = bool(re.search(r'\b(?:so sanh|khac nhau|khac biet|khac gi|hay|so voi)\b', norm))
        if not requested:
            if wanted or compare or re.search(r'\b(?:iphone|samsung|redmi|galaxy)\b', norm):
                return 'Bạn cho mình tên và phiên bản máy cụ thể nhé (ví dụ iPhone 15 Pro Max hoặc Samsung S26 Ultra).', []
            return None
        # Do not silently omit an unnamed/underspecified comparison partner.
        if compare and len(requested) < 2:
            if re.search(r'\bredmi\s+note\b(?!\s*\d)', norm):
                return 'Tên Redmi Note chưa đủ để xác định máy. Bạn bổ sung số đời và phiên bản của Redmi Note để mình so sánh đúng hai mẫu nhé.', []
            return 'Bạn muốn so sánh với mẫu nào? Hãy ghi đầy đủ tên và phiên bản của cả hai máy.', []
        if compare:
            return self.compare(requested, wanted)
        parts, sources = [], []
        for key, display in requested.items():
            candidates = [(r, t) for r, models, t in self.catalog if models == {key}]
            if not candidates:
                parts.append(f'Chưa có dữ liệu cho {display}; mình không lấy thông tin của phiên bản khác để thay thế.')
                continue
            if not wanted and not compare:
                parts.append(f'Bạn muốn biết giá, RAM, chip, camera, pin hay thông tin nào của {display}?')
                continue
            chosen = []
            missing = []
            for topic in sorted(wanted):
                matches = [r for r, t in candidates if topic in t]
                if not matches:
                    missing.append(topic)
                else:
                    # All rows for this topic are kept: e.g. price tiers/storage variants.
                    chosen.extend(matches)
            if compare and not wanted:
                chosen = [r for r, t in candidates if t]
            answer, rows = self.render(chosen)
            section = [f'{display}:'] if len(requested) > 1 else []
            if answer:
                section.append(answer)
                sources.extend(rows)
            if missing:
                section.append(f'Chưa có dữ liệu về {", ".join(missing)} của {display} trong kho hiện tại.')
            if not answer and not missing:
                section.append(f'Chưa có thông số phù hợp để đối chiếu {display}.')
            parts.append('\n'.join(section))
        return '\n\n'.join(parts), list(dict.fromkeys(sources))

    def safe_documents(self, question, documents):
        """Never use a model number found only in an answer to identify a product."""
        requested = set(phones(question))
        wanted = topics(question)
        accepted = []
        for doc in documents:
            ref = doc.metadata.get('question', '')
            models = set(phones(ref))
            if requested and (not models or not models.issubset(requested)):
                continue
            if wanted and not wanted.issubset(topics(ref)):
                continue
            # Unnamed/general questions cannot be answered with arbitrary product specs.
            if not requested and models:
                continue
            if SequenceMatcher(None, normalize(question), normalize(ref)).ratio() < 0.45:
                continue
            accepted.append(doc)
        return accepted


class BoundedWorker:
    """One daemon worker; never queue inference or share a model concurrently.

    The caller's wait is bounded even during an uninterruptible native prefill.
    A timed-out job keeps the gate until it actually exits; later calls fall back.
    """
    def __init__(self):
        self.gate = threading.Lock()

    def run(self, job, fallback, seconds):
        deadline = time.monotonic() + seconds
        def current_fallback():
            return fallback() if callable(fallback) else fallback
        if not self.gate.acquire(blocking=False):
            return current_fallback()
        result = queue.Queue(maxsize=1)
        def execute():
            try:
                result.put(job(deadline))
            except Exception:
                logging.getLogger(__name__).exception('Inference failed; returning grounded fallback')
                result.put(current_fallback())
            finally:
                self.gate.release()
        threading.Thread(target=execute, daemon=True).start()
        try:
            return result.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty:
            return current_fallback()
