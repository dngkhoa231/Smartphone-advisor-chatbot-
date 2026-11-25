import unittest

from answer_engine import phones, topics
from conversation_context import contextual_question
from recommendations import parse_budget


class Context(unittest.TestCase):
    shopping = 'tôi có 15tr tôi muốn 1 chiếc điện thoại chơi game tốt điện thoại nào cũng được'

    def test_named_followup_keeps_need_and_budget(self):
        question = contextual_question('iphone 15 pro', [self.shopping])
        self.assertEqual(set(phones(question)), {'iphone15pro'})
        self.assertIn('chơi game', topics(question))
        self.assertEqual(parse_budget(question), (0, 15_000_000))

    def test_general_request_does_not_stick_to_previous_phone(self):
        question = contextual_question(self.shopping, ['iphone 15 pro'])
        self.assertEqual(phones(question), {})

    def test_specs_followup_keeps_phone_but_drops_budget_filter(self):
        question = contextual_question('còn pin thì sao', [self.shopping, 'iphone 15 pro'])
        self.assertEqual(set(phones(question)), {'iphone15pro'})
        self.assertEqual(topics(question), {'pin'})
        self.assertIsNone(parse_budget(question))

    def test_budget_reply_remembers_gaming(self):
        question = contextual_question('15 triệu', ['điện thoại nào chơi game tốt'])
        self.assertIn('chơi game', topics(question))
        self.assertEqual(parse_budget(question), (0, 15_000_000))

    def test_new_budget_wins(self):
        question = contextual_question('tôi có 20tr muốn mua máy chơi game', [self.shopping])
        self.assertEqual(parse_budget(question), (0, 20_000_000))

    def test_fresh_chat_and_unrelated_questions_do_not_inherit(self):
        self.assertEqual(contextual_question('iphone 15 pro', []), 'iphone 15 pro')
        self.assertEqual(contextual_question('Snapdragon là gì?', [self.shopping, 'iphone 15 pro']), 'Snapdragon là gì?')
        self.assertEqual(contextual_question('RAM là gì?', ['iphone 15 pro']), 'RAM là gì?')

    def test_multi_phone_context_does_not_guess_reference(self):
        question = contextual_question('pin thì sao', ['so sánh iPhone 15 Pro với Samsung S23'])
        self.assertEqual(phones(question), {})

    def test_history_validation_and_brand(self):
        self.assertEqual(contextual_question('hi', {'question': self.shopping}), 'hi')
        self.assertEqual(contextual_question('hi', [None, 12, {}]), 'hi')
        question = contextual_question('15tr', ['muốn mua Samsung chơi game'])
        self.assertIn('samsung', question)
        self.assertIn('chơi game', topics(question))

    def test_named_price_followup(self):
        question = contextual_question('iphone 15', ['giá iPhone 13 bao nhiêu'])
        self.assertEqual(set(phones(question)), {'iphone15'})
        self.assertEqual(topics(question), {'giá'})

    def test_brand_change_drops_previous_phone(self):
        question = contextual_question('còn Samsung thì sao', [self.shopping, 'iphone 15 pro'])
        self.assertEqual(phones(question), {})
        self.assertIn('chơi game', topics(question))
        self.assertEqual(parse_budget(question), (0, 15_000_000))

    def test_spec_question_does_not_erase_shopping_budget(self):
        question = contextual_question('máy nào chơi game tốt hơn',
                                       [self.shopping, 'iphone 15 pro', 'còn pin thì sao'])
        self.assertEqual(phones(question), {})
        self.assertEqual(parse_budget(question), (0, 15_000_000))

    def test_camera_preference_reply_keeps_budget(self):
        prior = ['tôi có 10tr điện thoại nào chụp hình tốt']
        for message in ['chụp ảnh', 'chụp hình']:
            with self.subTest(message=message):
                resolved = contextual_question(message, prior)
                self.assertEqual(parse_budget(resolved), (0, 10_000_000))
                self.assertIn('camera', topics(resolved))
                self.assertEqual(phones(resolved), {})

    def test_broad_shopping_followups_keep_budget_and_needs(self):
        prior = ['điện thoại nào đầy đủ tiện nghi trong tầm giá 16tr - 20tr']
        all_three = contextual_question('cả 3 cái đó', prior)
        self.assertEqual(parse_budget(all_three), (16_000_000, 20_000_000))
        self.assertTrue({'chơi game', 'camera', 'pin'} <= topics(all_three))
        camera = contextual_question('tôi ưu tiên chụp ảnh và sử dụng cơ bản', prior + ['cả 3 cái đó'])
        self.assertEqual(parse_budget(camera), (16_000_000, 20_000_000))
        self.assertIn('camera', topics(camera))
        self.assertEqual(phones(camera), {})

    def test_new_budget_request_after_partial_comparison(self):
        previous = ['so sánh Redmi Note với Samsung Galaxy S26 Ultra']
        for message in ['Tôi có 15 triệu, muốn điện thoại chơi game tốt',
                        '15tr chơi game tốt',
                        'Tôi cần 1 chiếc điện thoại chơi game, ngân sách 15tr',
                        'Có 15 triệu cần máy chơi game',
                        'tư vấn điện thoại chơi game tầm 15 triệu']:
            with self.subTest(message=message):
                question = contextual_question(message, previous)
                self.assertEqual(question, message)
                self.assertEqual(phones(question), {})
                self.assertNotIn('samsung', question.lower())
                self.assertEqual(parse_budget(question), (0, 15_000_000))

    def test_complete_budget_query_drops_old_phone_and_brand(self):
        message = 'Tôi có 15 triệu, muốn điện thoại chơi game tốt'
        for previous in [['iphone 15 pro'], ['muốn mua Samsung chơi game'],
                         ['muốn mua Android chơi game'], ['giá Samsung S23']]:
            with self.subTest(previous=previous):
                self.assertEqual(contextual_question(message, previous), message)

    def test_pronoun_keeps_one_clear_phone_with_new_budget(self):
        question = contextual_question('15tr máy này chơi game tốt không', ['iphone 15 pro'])
        self.assertEqual(set(phones(question)), {'iphone15pro'})
        self.assertEqual(parse_budget(question), (0, 15_000_000))

    def test_partial_comparison_never_guesses_the_recognized_phone(self):
        previous = ['so sánh Redmi Note với Samsung Galaxy S26 Ultra']
        for message in ['pin thì sao', 'máy này chơi game tốt không', 'nó có tốt không', '15 triệu']:
            with self.subTest(message=message):
                self.assertEqual(phones(contextual_question(message, previous)), {})

    def test_explicit_comparison_does_not_inherit_gaming_or_budget(self):
        for message in ['so sánh iphone 17 pro max và iphone 12 pro max',
                        'so sánh S23 và S24', 'S23 khác nhau với S24 thế nào',
                        'iPhone 15 và iPhone 16']:
            with self.subTest(message=message):
                self.assertEqual(contextual_question(message, [self.shopping]), message)

    def test_comparison_starts_new_context_for_later_phone_reply(self):
        question = contextual_question('iPhone 15', [self.shopping, 'so sánh S23 và S24'])
        self.assertIsNone(parse_budget(question))
        self.assertNotIn('chơi game', topics(question))


if __name__ == '__main__':
    unittest.main(verbosity=2)
