import unittest

from answer_engine import FAQEngine


def row(number, question, answer):
    return {'row': number, 'question': question, 'answer': answer}


RECORDS = [
    row(2, 'iPhone 17 Pro Max có chip và RAM gì?', 'Dữ liệu mẫu: Chip A19 Pro, RAM 12GB.'),
    row(3, 'iPhone 17 Pro Max màn hình thế nào?', 'Màn hình mẫu 6,9 inch.'),
    row(4, 'iPhone 17 Pro Max có giá bao nhiêu?', 'Giá tham khảo từ 35,99 triệu đồng.'),
    row(5, 'iPhone 17 Pro Max chơi game có tốt không?', 'Phù hợp chơi game; nhiệt độ tùy thiết lập.'),
    row(6, 'iPhone 17 Pro có chip và RAM gì?', 'THÔNG SỐ CỦA PHIÊN BẢN KHÁC.'),
    row(7, 'Samsung S23 có chip gì?', 'Dữ liệu mẫu: Snapdragon 8 Gen 2.'),
    row(8, 'Samsung S23 giá bao nhiêu?', 'Giá mẫu từ 11-13 triệu đồng.'),
    row(9, 'So sánh chip iPhone 15 và Samsung S22?', 'Đây là đáp án so sánh có sẵn trong Excel.'),
]


class Comparisons(unittest.TestCase):
    def setUp(self):
        self.engine = FAQEngine(RECORDS)

    def test_unknown_partner_shows_gaps_and_no_variant_substitution(self):
        answer, sources = self.engine.direct('so sánh iphone 17 pro max và iphone 12 pro max')
        self.assertIn('Chip / RAM:', answer)
        self.assertIn('Màn hình:', answer)
        self.assertIn('Chưa có dữ liệu cho iphone 12 pro max', answer)
        self.assertIn('iphone 12 pro max:\nChưa có dữ liệu về RAM, chip.', answer)
        self.assertIn('tùy thiết lập', answer)
        self.assertNotIn('THÔNG SỐ CỦA PHIÊN BẢN KHÁC', answer)
        self.assertEqual(set(sources), {2, 3, 4, 5})
        self.assertIn('chưa đủ cơ sở', answer)

    def test_requested_attribute_only(self):
        answer, sources = self.engine.direct('so sánh RAM iPhone 17 Pro Max và Samsung S23')
        self.assertIn('RAM:', answer)
        self.assertIn('samsung s23:\nChưa có dữ liệu về RAM.', answer)
        self.assertNotIn('Màn hình:', answer)
        self.assertNotIn('Giá tham khảo:', answer)
        self.assertNotIn('Snapdragon', answer)
        self.assertEqual(sources, [2])

    def test_combined_attribute_keeps_partial_missing_explicit(self):
        answer, sources = self.engine.direct('so sánh chip và RAM iPhone 17 Pro Max với Samsung S23')
        self.assertIn('Snapdragon 8 Gen 2.', answer)
        self.assertIn('Chưa có dữ liệu về RAM.', answer)
        self.assertEqual(set(sources), {2, 7})
        self.assertEqual(answer.count('Dữ liệu mẫu: Chip A19 Pro, RAM 12GB.'), 1)

    def test_missing_price_does_not_reuse_other_variant(self):
        answer, sources = self.engine.direct('so sánh giá iPhone 17 Pro với Samsung S23')
        self.assertIn('iphone 17 pro:\nChưa có dữ liệu về giá.', answer)
        self.assertNotIn('35,99', answer)
        self.assertEqual(sources, [8])

    def test_exact_comparison_faq_preserved(self):
        answer, sources = self.engine.direct('So sánh chip iPhone 15 và Samsung S22?')
        self.assertEqual(answer, RECORDS[-1]['answer'])
        self.assertEqual(sources, [9])

    def test_partial_model_asks_for_missing_variant(self):
        answer, sources = self.engine.direct('so sánh Redmi Note với Samsung Galaxy S26 Ultra')
        self.assertIn('số đời và phiên bản', answer)
        self.assertEqual(sources, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
