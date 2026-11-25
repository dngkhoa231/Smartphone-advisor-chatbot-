"""Resolve short follow-ups from user questions in the current chat only."""
import re

from answer_engine import normalize, phones, topics
from recommendations import parse_budget


def _comparison(text):
    return bool(re.search(r'\b(?:so sanh|khac nhau|khac biet)\b', normalize(text)) or len(phones(text)) > 1)


def _resolve(question, previous, remembered_budget=None):
    if not previous:
        return question
    text = normalize(question)
    # A complete comparison is a new request, not a short model-name reply.
    if _comparison(question):
        return question
    current_phones, previous_phones = phones(question), phones(previous)
    current_topics, previous_topics = topics(question), topics(previous)
    budget, previous_budget = parse_budget(question), parse_budget(previous) or remembered_budget
    broad_reply = bool(re.fullmatch(r'(?:ca (?:3|ba)(?: cai| may| lua chon)?(?: do)?|tat ca|ca ba)', text))
    definition = bool(re.search(r'\b(?:la gi|nghia la|hoat dong|tai sao)\b', text))
    if definition:
        return question
    previous_comparison = _comparison(previous)
    pronoun = bool(re.search(r'\b(?:may nay|con nay|dien thoai nay|mau nay|chiec nay|no)\b', text))
    brand_followup = bool(not current_phones and not definition and len(text.split()) <= 10 and
                          re.search(r'\b(?:iphone|apple|samsung|galaxy|redmi|xiaomi|android)\b', text))
    shopping = bool(re.search(
        r'\b(?:dien thoai nao|may nao|tu van|goi y|nen mua|muon mua|can mua|chon may|'
        r'(?:muon|can|tim) (?:mot |1 |chiec |mot chiec |1 chiec )?(?:dien thoai|may))\b', text)) or brand_followup
    # A new budget plus a stated need is self-contained, even in a short message.
    # Only an explicit reference such as "máy này" can keep the previous model.
    fresh_request = bool(not current_phones and not pronoun and not brand_followup and (
        (budget and (current_topics - {'giá'} or shopping)) or
        (shopping and current_topics - {'giá'})))
    broad = shopping or bool(re.search(r'\b(?:bat ky|cung duoc)\b', text))
    named_only = bool(len(current_phones) == 1 and not current_topics and not budget and len(text.split()) <= 9)
    budget_only = bool(budget and not current_phones and not current_topics and len(text.split()) <= 9)
    short_followup = bool(len(text.split()) <= 12 and (
        current_topics or re.search(r'\b(?:may nay|con nay|no|thi sao|con|vay)\b', text)))
    # Definitions and unrelated complete questions must not inherit a product.
    additions = []
    if (not current_phones and not fresh_request and not previous_comparison and
            (pronoun or (short_followup and not broad and not budget_only)) and len(previous_phones) == 1):
        additions.extend(previous_phones.values())
    if not current_topics and not fresh_request and not previous_comparison and (named_only or budget_only or shopping):
        additions.extend(sorted(previous_topics if named_only else previous_topics - {'giá'}))
    needs = current_topics or (previous_topics if named_only or budget_only or shopping else set())
    preference_reply = bool(not current_phones and not previous_phones and len(text.split()) <= 12 and
                            current_topics and (len(text.split()) <= 6 or re.search(r'\b(?:uu tien|toi muon|minh muon)\b', text)))
    if broad_reply and previous_budget and not previous_comparison and not current_phones:
        additions.append('tư vấn điện thoại chơi game chụp ảnh và pin')
    if not budget and previous_budget and not previous_comparison and (shopping or named_only or preference_reply or broad_reply or 'chơi game' in needs):
        low, high = previous_budget
        additions.append(f'ngân sách {low}-{high} đồng' if low else f'ngân sách tối đa {high} đồng')
    if not current_phones and not re.search(r'\b(?:iphone|apple|samsung|galaxy|redmi|xiaomi|android)\b', text):
        if (budget_only or shopping) and not fresh_request and not previous_comparison and not re.search(r'\b(?:bat ky|cung duoc)\b', text):
            brands = re.findall(
                r'\b(?:khong (?:muon |lay |mua |chon |dung )?|tru )?(?:iphone|apple|samsung|galaxy|redmi|xiaomi|android)\b',
                normalize(previous))
            # A previously named phone is not a user preference for that brand.
            if not previous_phones:
                additions.extend(brands)
    return question + ('; ' + '; '.join(additions) if additions else '')


def contextual_question(question, question_history=None):
    """History is bounded client-supplied context, never instructions or DB queries."""
    if not isinstance(question_history, list):
        return question
    previous = ''
    remembered_budget = None
    for earlier in question_history[-8:]:
        if isinstance(earlier, str) and 0 < len(earlier) <= 2000:
            previous = _resolve(earlier, previous, remembered_budget)
            remembered_budget = parse_budget(earlier) or (None if _comparison(earlier) else remembered_budget)
    return _resolve(question, previous, remembered_budget)
