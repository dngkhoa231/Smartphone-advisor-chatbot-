import unittest
from answer_engine import phones, topics, FAQEngine
from recommendations import RecommendationEngine

class ReviewRegressions(unittest.TestCase):
    def test_vietnamese_colours_do_not_match_charging(self):
        self.assertEqual(topics('Redmi Note 15 có những màu sắc nào?'), {'màu sắc'})
        self.assertIn('pin', topics('Redmi Note 15 sạc bao nhiêu W?'))

    def test_iphone_abbreviation(self):
        self.assertEqual(set(phones('ip15 pro có gì?')), {'iphone15pro'})
        self.assertEqual(set(phones('ip15 thường')), {'iphone15'})

    def test_samsung_recommendation_does_not_include_poco(self):
        self.assertFalse(RecommendationEngine._brand_allowed('pocox8pro', 'muốn mua samsung'))

    def test_general_comparison_keeps_comparable_attributes(self):
        rows = [{'row': 1, 'question': 'iPhone 15 dùng chip gì?', 'answer': 'A16 Bionic'},
                {'row': 2, 'question': 'iPhone 15 Plus dùng chip gì?', 'answer': 'A16 Bionic'}]
        answer, sources = FAQEngine(rows).direct('Nâng cấp phân khúc giữa iPhone 15 Plus so với iPhone 15?')
        self.assertIn('A16 Bionic', answer)
        self.assertEqual(set(sources), {1, 2})

    def test_ambiguous_duplicate_answers_are_not_silently_selected(self):
        rows = [{'row': 1, 'question': 'Máy A là gì?', 'answer': 'X'},
                {'row': 2, 'question': 'Máy A là gì?', 'answer': 'Y'}]
        answer, sources = FAQEngine(rows).direct('Máy A là gì?')
        self.assertIn('kiểm tra lại', answer)
        self.assertEqual(sources, [1, 2])

if __name__ == '__main__': unittest.main()
