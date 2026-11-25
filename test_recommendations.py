import unittest

from recommendations import RecommendationEngine, parse_budget
from answer_engine import phones


def record(row, question, answer):
    return {'row': row, 'question': question, 'answer': answer}


FIXTURE = [
    record(2, 'Samsung S23 giá bao nhiêu?', 'Giá tham khảo từ 11 - 13 triệu đồng, tùy phiên bản.'),
    record(3, 'Samsung S23 chơi game có tốt không?', 'Máy phù hợp với chơi game nặng; nhiệt độ phụ thuộc thiết lập.'),
    record(4, 'Samsung S23 Ultra giá bao nhiêu?', 'Giá tham khảo từ 17 - 20 triệu đồng.'),
    record(5, 'Samsung S23 Ultra chơi game có tốt không?', 'Máy phù hợp với game nặng.'),
    record(6, 'iPhone 15 Pro giá bao nhiêu?', 'Cần cập nhật giá theo dung lượng và tình trạng hàng.'),
    record(7, 'iPhone 15 Pro chơi game tốt không?', 'Máy phù hợp với các game yêu cầu hiệu năng cao.'),
    record(8, 'Samsung A06 giá bao nhiêu?', 'Giá khoảng 2,8 - 3,2 triệu đồng.'),
    record(9, 'Samsung A06 phù hợp nhu cầu nào?', 'Dùng cơ bản, không phù hợp chơi game.'),
    record(10, 'iPhone 13 giá bao nhiêu?', 'Giá từ khoảng 11 - 13 triệu đồng.'),
    record(11, 'iPhone 13 chơi game tốt không?', 'Đáp ứng tốt các game phổ biến.'),
    record(12, 'Samsung A07 5G giá bao nhiêu?', 'Giá 150-180 USD.'),
    record(13, 'Samsung A07 5G chơi game tốt không?', 'Máy phù hợp với gaming nhẹ.'),
]


class BudgetParsing(unittest.TestCase):
    def test_malformed_and_extreme_amounts_do_not_raise(self):
        for value in ['15,5,5tr', '15.000.000 triệu', '15..5tr',
                      '999999999999999999999999999999 triệu',
                      '9' * 5000 + 'tr', '9' * 5000 + ' đồng',
                      '15 - ' + '9' * 5000 + ' triệu',
                      '0 triệu', '15-10 triệu']:
            with self.subTest(value=value[:50]):
                self.assertIsNone(parse_budget(value))
                RecommendationEngine(FIXTURE).answer('tôi có ' + value + ' cần máy chơi game')

    def test_amounts_and_ranges(self):
        for question, expected in [
            ('tôi có 15tr', (0, 15_000_000)),
            ('15 triệu', (0, 15_000_000)),
            ('15.000.000', (0, 15_000_000)),
            ('15,000,000 đồng', (0, 15_000_000)),
            ('15tr500', (0, 15_500_000)),
            ('15,5 triệu', (0, 15_500_000)),
            ('15-16 triệu', (15_000_000, 16_000_000)),
            ('15tr đến 16tr', (15_000_000, 16_000_000)),
            ('15.000.000 - 16.000.000', (15_000_000, 16_000_000)),
            ('dưới 15 triệu', (0, 14_999_999)),
            ('tối đa 15 triệu', (0, 15_000_000)),
            ('S23 RAM 8GB có chơi game tốt không', None),
            ('150 USD', None),
        ]:
            with self.subTest(question=question):
                self.assertEqual(parse_budget(question), expected)


class Recommendations(unittest.TestCase):
    def setUp(self):
        self.engine = RecommendationEngine(FIXTURE)

    def test_broad_budget_lists_models_without_asking_for_priority(self):
        sample = [
            record(20, 'Samsung S23 Ultra giá bao nhiêu?', 'Giá 17 - 20 triệu đồng.'),
            record(21, 'Samsung S23 Ultra chip gì?', 'Snapdragon 8 Gen 2.'),
            record(22, 'Samsung S23 Ultra camera thế nào?', 'Camera chính 200MP.'),
            record(23, 'Samsung S23 Ultra pin bao nhiêu?', 'Pin 5.000mAh.'),
            record(24, 'iPhone 14 Pro Max giá bao nhiêu?', 'Giá 20 - 24 triệu đồng.'),
            record(25, 'iPhone 14 Pro Max camera thế nào?', 'Camera chính 48MP.'),
            record(26, 'iPhone 14 Pro Max chip gì?', 'A16 Bionic.'),
        ]
        answer, rows = RecommendationEngine(sample).answer('điện thoại nào đầy đủ tiện nghi trong tầm giá 16tr - 20tr')
        self.assertIn('Samsung S23 Ultra', answer)
        self.assertNotIn('iPhone 14 Pro Max', answer)
        self.assertNotIn('bạn ưu tiên', answer)
        self.assertEqual(set(rows), {20, 21, 22, 23})

    def test_three_needs_lists_partial_matches_with_missing_criterion(self):
        sample = [
            record(20, 'Samsung S23 Ultra giá bao nhiêu?', 'Giá 17 - 20 triệu đồng.'),
            record(21, 'Samsung S23 Ultra camera thế nào?', 'Camera chính 200MP.'),
            record(22, 'Samsung S23 Ultra pin bao nhiêu?', 'Pin 5.000mAh.'),
        ]
        answer, rows = RecommendationEngine(sample).answer('tư vấn điện thoại chơi game chụp ảnh và pin ngân sách 16-20 triệu')
        self.assertIn('Samsung S23 Ultra', answer)
        self.assertIn('Chưa đủ dữ liệu về chơi game', answer)
        self.assertEqual(set(rows), {20, 21, 22})

    def test_camera_request_shortlists_without_claiming_photo_quality(self):
        from answer_engine import topics
        self.assertIn('camera', topics('chụp hình đẹp'))
        sample = [
            record(20, 'Samsung A55 giá bao nhiêu?', 'Giá tham khảo 9 triệu đồng.'),
            record(21, 'Samsung A55 camera bao nhiêu MP?', 'Camera chính 50MP.'),
            record(22, 'Samsung S23 giá bao nhiêu?', 'Giá tham khảo 12 triệu đồng.'),
            record(23, 'Samsung S23 camera bao nhiêu MP?', 'Camera chính 50MP.'),
        ]
        answer, rows = RecommendationEngine(sample).answer('tôi có 10tr điện thoại nào chụp hình tốt')
        self.assertEqual(rows, [20, 21])
        self.assertIn('samsung a55', answer.lower())
        self.assertIn('chưa đủ ảnh mẫu', answer)

    def test_budget_filters_variants_prices_and_negatives(self):
        answer, rows = self.engine.answer('tôi có 15tr muốn điện thoại chơi game tốt máy nào cũng được')
        self.assertIn(2, rows)
        self.assertIn(3, rows)
        self.assertIn(10, rows)
        self.assertNotIn(4, rows)
        self.assertNotIn(6, rows)
        self.assertNotIn(8, rows)
        self.assertNotIn(12, rows)
        self.assertNotIn('Bạn cho mình tên', answer)
        self.assertIn('tham khảo', answer)
        self.assertIn('không đảm bảo mọi phiên bản', answer)

    def test_budget_gaming_picks_specific_poco_variant_without_asking_model(self):
        sample = [
            record(20, 'POCO X8 Pro Max 12GB/256GB giá bao nhiêu?', 'Giá 14.590.000đ cho bản 12GB/256GB.'),
            record(21, 'POCO X8 Pro Max chơi game có tốt không?', 'Dimensity 9500s và màn 120Hz phù hợp chơi game.'),
            record(22, 'POCO X8 Pro 8GB/256GB giá bao nhiêu?', 'Giá 12.490.000đ cho bản 8GB/256GB.'),
            record(23, 'POCO X8 Pro chơi game có tốt không?', 'Dimensity 8500-Ultra phù hợp chơi game.'),
        ]
        self.assertEqual(len(phones('POCO X8 Pro Max và POCO X8 Pro')), 2)
        answer, rows = RecommendationEngine(sample).answer('điện thoại tầm 15tr chơi game tốt')
        self.assertTrue(answer.startswith('Với ngân sách 15 triệu'))
        self.assertIn('gợi ý POCO X8 Pro Max', answer)
        self.assertIn('12GB/256GB', answer)
        self.assertEqual(set(rows), {20, 21, 22, 23})
        self.assertNotIn('Bạn cho mình tên', answer)

    def test_brand_and_named_model(self):
        _, rows = self.engine.answer('tôi có 15tr mua Samsung chơi game')
        self.assertEqual(set(rows), {2, 3})
        answer, rows = self.engine.answer('iPhone 15 Pro chơi game ngân sách 15tr')
        self.assertEqual(set(rows), {6, 7})
        self.assertIn('chưa thể xác nhận', answer)
        self.assertNotIn('s23', answer)

    def test_excluded_brand(self):
        _, rows = self.engine.answer('15tr chơi game không mua Samsung')
        self.assertEqual(set(rows), {10, 11})

    def test_strict_range_is_not_just_upper_bound(self):
        answer, rows = self.engine.answer('điện thoại nào chơi game trong tầm giá 15-16 triệu')
        self.assertEqual(rows, [])
        self.assertIn('chưa có mẫu', answer)

    def test_budget_overlap_preserves_price_qualification(self):
        answer, rows = self.engine.answer('chơi game ngân sách 12 triệu')
        self.assertIn('11 - 13 triệu', answer)
        self.assertIn('không đảm bảo mọi phiên bản', answer)
        self.assertEqual(set(rows), {2, 3, 10, 11})

    def test_no_gaming_evidence_is_not_invented(self):
        engine = RecommendationEngine(FIXTURE[:1])
        answer, rows = engine.answer('tôi có 15tr muốn điện thoại chơi game')
        self.assertEqual(rows, [])
        self.assertIn('chưa có mẫu', answer)

    def test_named_negative_and_over_budget(self):
        answer, rows = self.engine.answer('Samsung A06 chơi game ngân sách 15 triệu')
        self.assertIn('không khuyến nghị', answer)
        self.assertEqual(set(rows), {8, 9})
        answer, rows = self.engine.answer('Samsung S23 Ultra chơi game ngân sách 15 triệu')
        self.assertIn('ngoài khoảng ngân sách', answer)
        self.assertEqual(set(rows), {4, 5})

    def test_clarify_missing_budget_not_phone(self):
        answer, _ = self.engine.answer('điện thoại nào chơi game tốt')
        self.assertIn('bao nhiêu tiền', answer)
        self.assertIsNone(self.engine.answer('RAM S23 bao nhiêu'))
        self.assertIsNone(self.engine.answer('S23 chơi game tốt không'))

    def test_factual_gaming_questions_do_not_start_shopping(self):
        for question in ['chơi game là gì?', 'RAM có ảnh hưởng chơi game không?',
                         'Chơi game có nhanh hết pin không?', 'Gaming nghĩa là gì?']:
            with self.subTest(question=question):
                self.assertIsNone(self.engine.answer(question))

    def test_multiple_needs_require_and_render_all_evidence(self):
        fixture = [
            record(20, 'Samsung S23 giá bao nhiêu?', 'Giá 12 triệu đồng.'),
            record(21, 'Samsung S23 camera thế nào?', 'Camera chính 50MP.'),
            record(22, 'Samsung S24 giá bao nhiêu?', 'Giá 14 triệu đồng.'),
            record(23, 'Samsung S24 camera thế nào?', 'Camera chính 50MP.'),
            record(24, 'Samsung S24 pin bao nhiêu?', 'Pin 4.000mAh.'),
        ]
        engine = RecommendationEngine(fixture)
        answer, rows = engine.answer('tư vấn điện thoại 15 triệu có camera và pin')
        self.assertEqual(set(rows), {22, 23, 24})
        self.assertIn('Camera chính 50MP', answer)
        self.assertIn('Pin 4.000mAh', answer)
        answer, rows = engine.answer('Samsung S23 ngân sách 15 triệu camera và pin')
        self.assertEqual(set(rows), {20, 21})
        self.assertIn('thiếu thông tin về pin', answer)


if __name__ == '__main__':
    unittest.main(verbosity=2)
