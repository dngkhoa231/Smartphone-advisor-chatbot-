"""Budget filtering based only on priced, explicitly supported Excel records."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from answer_engine import PHONE_PATTERN, normalize, phones, topics


def _money_text(text):
    text = unicodedata.normalize('NFKD', text.lower().replace('đ', 'd'))
    return ''.join(c for c in text if not unicodedata.combining(c)).replace('–', '-').replace('—', '-')


NUMBER = r'\d+(?:[.,]\d+)*'
UNIT = r'(?:trieu|tr)(?![a-z])'
MILLION_RANGE = re.compile(rf'(?<![\w.,])({NUMBER})\s*(?:{UNIT})?\s*(?:-|den|toi)\s*({NUMBER})\s*{UNIT}')
MILLION = re.compile(rf'(?<![\w.,])({NUMBER})\s*{UNIT}(?:(\d{{1,3}})(?!\d))?')
DONG = re.compile(r'(?<![\w.,])(?:\d{1,3}(?:[.,]\d{3}){2,}|\d{7,})(?:\s*(?:vnd|dong|d))?(?![\w.,])')
MAX_MONEY = 1_000_000_000_000


def _million(value):
    # Reject malformed decimals and impractical magnitudes before conversion.
    if len(value) > 24 or not re.fullmatch(r'\d+(?:[.,]\d{1,6})?', value):
        return None
    try:
        amount = Decimal(value.replace(',', '.')) * 1_000_000
        return int(amount) if amount.is_finite() and 0 < amount <= MAX_MONEY else None
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _dong(value):
    digits = re.sub(r'\D', '', value)
    if not digits or len(digits) > 13:
        return None
    amount = int(digits)
    return amount if 0 < amount <= MAX_MONEY else None


def _money_values(text):
    """Return explicit VND prices; never interpret USD, model numbers or RAM."""
    text = _money_text(text)
    match = MILLION_RANGE.search(text)
    if match:
        low, high = _million(match[1]), _million(match[2])
        return (low, high) if low is not None and high is not None and low <= high else None
    match = MILLION.search(text)
    if match:
        value = _million(match[1])
        if value is None:
            return None
        value += int(match[2]) * 1_000 if match[2] else 0
        return (value, value) if value <= MAX_MONEY else None
    matches = list(DONG.finditer(text))
    if matches:
        value = _dong(matches[0].group())
        if value is None:
            return None
        if len(matches) > 1 and re.fullmatch(r'\s*(?:-|den|toi)\s*', text[matches[0].end():matches[1].start()]):
            high = _dong(matches[1].group())
            return (value, high) if high is not None and value <= high else None
        return value, value
    return None


def parse_budget(question):
    """A single budget is a ceiling; an explicit range preserves both bounds."""
    values = _money_values(question)
    if values is None:
        return None
    low, high = values
    if low == high:
        low = 0
    text = normalize(question)
    if re.search(r'\b(?:duoi|it hon|nho hon)\b', text) and not re.search(r'\b(?:khong duoi|khong it hon)\b', text):
        high -= 1
    return (low, high) if high > 0 else None


def _display_money(value):
    return f'{value / 1_000_000:g}'.replace('.', ',') + ' triệu'


def _negative_gaming(record):
    answer = normalize(record['answer'])
    relevant = re.search(r'\b(?:game|gaming)\b', normalize(record['question']) + ' ' + answer)
    return bool(relevant and (
        answer.startswith(('khong ', 'chua ')) or
        re.search(r'\b(?:khong|chua)\b.{0,65}\b(?:phu hop|dap ung|choi duoc|choi tot|gaming|choi game)\b', answer)
    ))


def _gaming_evidence(record):
    question, answer = normalize(record['question']), normalize(record['answer'])
    relevant = re.search(r'\b(?:game|gaming)\b', question + ' ' + answer)
    # Thermal/battery/FPS questions alone are not evidence of suitability.
    suitability = re.search(r'\b(?:phu hop|dap ung tot|choi tot|co the choi|gaming (?:tot|tam trung|nhe))\b', answer)
    return bool(relevant and suitability and not _negative_gaming(record))


def _informative_evidence(record):
    answer = normalize(record['answer'])
    return not re.search(r'\b(?:chua co du lieu|chua co thong tin|can kiem tra|nen kiem tra|co the khac)\b', answer)


class RecommendationEngine:
    def __init__(self, records):
        self.products = {}
        for record in records:
            identified = phones(record['question'])
            if len(identified) != 1:
                continue
            key, display = next(iter(identified.items()))
            original = re.search(PHONE_PATTERN.pattern, record['question'], flags=re.IGNORECASE)
            product = self.products.setdefault(key, {'name': original.group().strip() if original else display, 'records': []})
            product['records'].append(record)

    @staticmethod
    def _brand_allowed(key, question):
        groups = {
            'iphone': key.startswith('iphone'),
            'samsung': not key.startswith(('iphone', 'redmi', 'poco')),
            'redmi': key.startswith('redmi'),
            'poco': key.startswith('poco'),
        }
        text = normalize(question).replace('galaxy', 'samsung').replace('apple', 'iphone')
        excluded = set(re.findall(r'\b(?:khong (?:muon |lay |mua |chon |dung )?|tru )\s*(iphone|samsung|redmi|poco|xiaomi)\b', text))
        mentioned = set(re.findall(r'\b(iphone|samsung|redmi|poco|xiaomi)\b', text)) - excluded
        if 'xiaomi' in excluded:
            excluded.update({'redmi', 'poco'})
        if 'xiaomi' in mentioned:
            mentioned.update({'redmi', 'poco'})
        excluded.discard('xiaomi')
        mentioned.discard('xiaomi')
        if any(groups[name] for name in excluded):
            return False
        if 'android' in text and groups['iphone']:
            return False
        return not mentioned or any(groups[name] for name in mentioned)

    def answer(self, question):
        text = normalize(question)
        budget = parse_budget(question)
        requested = phones(question)
        needs = topics(question) - {'giá'}
        gaming = bool(re.search(r'\b(?:game|gaming)\b', text))
        shopping = bool(re.search(r'\b(?:tu van|goi y|nen mua|dien thoai nao|may nao|ngan sach|tam gia|toi co|minh co|muon mua|can mua|chon may)\b', text))
        if budget is None:
            if 'privacy display' in text:
                return None
            if not requested and shopping:
                return 'Bạn dự định chi tối đa bao nhiêu tiền? Mình sẽ lọc theo ngân sách và nhu cầu, không cần bạn chọn sẵn tên máy.', []
            return None
        if not (shopping or gaming or requested or re.fullmatch(r'[\d\s.,]+(?:tr|trieu|dong|vnd)?', _money_text(question).strip())):
            return None
        broad_request = not needs and not requested

        candidates = []
        partial_candidates = []
        named_missing = []
        rows = []
        for key, product in self.products.items():
            if requested and key not in requested:
                continue
            if not self._brand_allowed(key, question):
                continue
            price_rows = [r for r in product['records'] if 'giá' in topics(r['question'])]
            priced = [(r, _money_values(r['answer'])) for r in price_rows]
            priced = [(r, value) for r, value in priced if value is not None]
            evidence = [r for r in product['records'] if _gaming_evidence(r)][:1] if gaming else []
            if broad_request:
                for need in ('chip', 'camera', 'pin', 'màn hình'):
                    found = next((r for r in product['records'] if need in topics(r['question'])), None)
                    if found is not None and found not in evidence and _informative_evidence(found):
                        evidence.append(found)
            missing_needs = set()
            for need in sorted(needs - {'chơi game'} if gaming else needs):
                matching_need = [r for r in product['records'] if need in topics(r['question']) and _informative_evidence(r)]
                if matching_need:
                    if matching_need[0] not in evidence:
                        evidence.append(matching_need[0])
                else:
                    missing_needs.add(need)
            negative = gaming and any(_negative_gaming(r) for r in product['records'])
            if gaming and (negative or not any(_gaming_evidence(r) for r in evidence)):
                missing_needs.add('chơi game')
            if negative:
                evidence = [r for r in evidence if not _gaming_evidence(r)]
            matching = [(r, value) for r, value in priced if value[0] <= budget[1] and value[1] >= budget[0]]
            if broad_request:
                # A whole quoted price range must fit; mere overlap is not enough
                # to present an unnamed model as within the customer's budget.
                certain = [(r, value) for r, value in matching if value[0] >= budget[0] and value[1] <= budget[1]]
                if certain and len(evidence) >= 2:
                    price_record, value = min(certain, key=lambda pair: pair[1][0])
                    candidates.append((value[0], product['name'], price_record, evidence[:3]))
                continue
            if requested:
                selected = ([matching[0][0]] if matching else [r for r, _ in priced[:1]] or price_rows[:1]) + evidence
                if not matching:
                    reason = ('Giá ghi trong dữ liệu nằm ngoài khoảng ngân sách của bạn.' if priced else
                              'Chưa có giá bằng VND đủ cụ thể trong dữ liệu, nên chưa thể xác nhận máy nằm trong ngân sách.')
                elif gaming and 'chơi game' in missing_needs:
                    reason = ('Dữ liệu không khuyến nghị máy này cho chơi game.' if negative else
                              'Có giá tham khảo trong ngân sách, nhưng dữ liệu chưa đủ để đánh giá khả năng chơi game.')
                elif missing_needs:
                    reason = 'Có giá tham khảo trong ngân sách, nhưng dữ liệu còn thiếu thông tin về ' + ', '.join(sorted(missing_needs)) + '.'
                else:
                    reason = 'Có mức giá tham khảo giao với ngân sách; cần xác nhận giá và phiên bản cụ thể trước khi chọn.'
                if negative:
                    selected += [r for r in product['records'] if _negative_gaming(r)][:1]
                named_missing.append(product['name'] + ':\n' + '\n'.join(r['answer'].strip() for r in selected) + '\n' + reason)
                rows.extend(r['row'] for r in selected)
                continue
            if len(needs) >= 2 and matching and evidence and missing_needs:
                price_record, value = min(matching, key=lambda pair: pair[1][0])
                matched_count = len(needs) - len(missing_needs)
                if matched_count > 0:
                    full_fit = value[0] >= budget[0] and value[1] <= budget[1]
                    partial_candidates.append((full_fit, matched_count, value[0], product['name'], price_record, evidence[:3], missing_needs))
            if matching and evidence and not missing_needs:
                price_record, value = min(matching, key=lambda pair: pair[1][0])
                full_fit = value[0] >= budget[0] and value[1] <= budget[1]
                candidates.append((value[0], product['name'], price_record, evidence, full_fit))

        if requested:
            for key, display in requested.items():
                if key not in self.products:
                    named_missing.append(f'{display}: Chưa có dữ liệu để đối chiếu giá và nhu cầu.')
            return '\n\n'.join(named_missing) + '\n\nGiá trong Excel là giá tham khảo, không phải giá bán được cập nhật trực tiếp.', list(dict.fromkeys(rows))

        ceiling = (_display_money(budget[1]) if budget[0] == 0 else
                   f'{_display_money(budget[0])}–{_display_money(budget[1])}')
        if not candidates:
            if partial_candidates:
                if any(item[0] for item in partial_candidates):
                    partial_candidates = [item for item in partial_candidates if item[0]]
                partial_candidates.sort(key=lambda item: (-item[1], -item[2], item[3]))
                sections = [f'Chưa có mẫu nào trong khoảng {ceiling} có đủ dữ liệu để khẳng định đáp ứng tất cả nhu cầu. Đây là các mẫu gần nhất để bạn cân nhắc:']
                for _, _, _, name, price, evidence, missing_needs in partial_candidates[:3]:
                    details = '\n'.join(r['answer'].strip() for r in evidence)
                    sections.append(f'{name}:\n{price["answer"].strip()}\n{details}\nChưa đủ dữ liệu về {", ".join(sorted(missing_needs))}.')
                    rows.extend([price['row']] + [r['row'] for r in evidence])
                sections.append('Giá chỉ để tham khảo; khả năng phù hợp thực tế cần được kiểm tra thêm trước khi mua.')
                return '\n\n'.join(sections), list(dict.fromkeys(rows))
            return (f'Với ngân sách {ceiling}, kho dữ liệu hiện chưa có mẫu đáp ứng đồng thời khoảng giá và nhu cầu này với đủ thông tin để đề xuất. '
                    'Mình không lấy máy thiếu giá hoặc thiếu thông tin về nhu cầu bạn nêu để khẳng định là phù hợp. '
                    'Bạn có thể mở rộng khoảng giá hoặc bổ sung giá và đánh giá của các mẫu muốn cân nhắc vào dữ liệu.'), []
        if broad_request:
            candidates.sort(key=lambda item: (-len(item[3]), -item[0], item[1]))
            choices = candidates[:3]
            sections = [f'Với ngân sách {ceiling}, đây là {len(choices)} mẫu có giá và thông số để bạn cân nhắc theo dữ liệu hiện có:']
            for _, name, price, evidence in choices:
                details = '\n'.join(r['answer'].strip() for r in evidence)
                sections.append(f'{name}:\n{price["answer"].strip()}\n{details}')
                rows.extend([price['row']] + [r['row'] for r in evidence])
            sections.append('Đây là danh sách tham khảo từ Excel, chưa phải xếp hạng trải nghiệm thực tế. Giá, dung lượng và tình trạng máy cần kiểm tra lại trước khi mua.')
            return '\n\n'.join(sections), list(dict.fromkeys(rows))
        if any(item[4] for item in candidates):
            candidates = [item for item in candidates if item[4]]
        # Order by listed starting price, not an invented performance benchmark.
        candidates.sort(key=lambda item: (-item[0], item[1]))
        nearby = [item for item in candidates if item[0] >= budget[1] * 0.7]
        choices = (nearby or candidates)[:2]
        priority = 'chơi game' if gaming else ('chụp ảnh' if 'camera' in needs else 'nhu cầu bạn nêu')
        sections = [f'Với ngân sách {ceiling} và ưu tiên {priority}, mình gợi ý {choices[0][1]} để cân nhắc theo dữ liệu hiện có. Các mẫu dưới đây được xếp theo giá khởi điểm giảm dần, không phải thứ hạng hiệu năng thực tế.']
        for position, (_, name, price, evidence, _) in enumerate(choices):
            details = '\n'.join(r['answer'].strip() for r in evidence)
            label = f'Mẫu tham khảo {position + 1}'
            sections.append(f'{label} — {name}:\n{price["answer"].strip()}\n{details}')
            rows.extend([price['row']] + [r['row'] for r in evidence])
        sections.append('Giá ghi trong Excel chỉ để tham khảo, không đảm bảo mọi phiên bản đều vừa ngân sách; bạn nên kiểm tra giá và dung lượng trước khi mua.')
        if gaming:
            sections.append('Gợi ý chơi game này dựa trên thông số và mô tả trong dữ liệu; nhóm chưa đo FPS, nhiệt độ hoặc pin khi chơi thực tế.')
        if 'camera' in needs:
            sections.append('Kho hiện có thông số camera nhưng chưa đủ ảnh mẫu và đánh giá chất lượng ảnh để khẳng định mẫu nào chụp đẹp nhất.')
        return '\n\n'.join(sections), list(dict.fromkeys(rows))
