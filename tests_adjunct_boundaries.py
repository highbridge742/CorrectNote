"""Source adjunct boundaries stay separate from the following word/action."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.HAS_JANOME, 'requires native Janome dictionary')
class AdjunctBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a = initial()

    def result(self, text):
        import app
        a = self.a
        return app.correct_line(text, a.store, input_method='kana', dict_index=a.dict_index,
            context_vec=None, decisions=a.decisions)

    def test_normal_phase_adjunct_and_written_object_keep_text_without_purple(self):
        for prefix in ('とうちゃくまえに', 'とうちゃくごに', 'しゅっぱつまえに', 'しゅっぱつごに'):
            with self.subTest(prefix=prefix):
                text = prefix + '写真をならべます。'
                result = self.result(text)
                self.assertEqual(result['corrected'], text)
                self.assertFalse(result.get('odd_spans'))

    def test_following_typo_is_repaired_and_its_result_is_stable(self):
        for prefix in ('とうちゃくまえに', 'とうちゃくごに', 'しゅっぱつまえに', 'しゅっぱつごに'):
            with self.subTest(prefix=prefix):
                expected = prefix + '写真をならべます。'
                result = self.result(prefix + 'しゃしまをならべます。')
                assert_repaired_spelling(self, result, expected)
                self.assertFalse(result.get('odd_spans'))
                again = self.result(result['corrected'])
                self.assertEqual(again['corrected'], result['corrected'])
                self.assertFalse(again.get('odd_spans'))

    def test_adjunct_does_not_certify_unknown_following_content_or_hide_other_typo(self):
        self.assertFalse(R.intact_native_reading('とうちゃくごにぷねらをならべます'))
        text = 'にゅ力ミス。とうちゃくごに写真をならべます。'
        result = self.result(text)
        assert_repaired_spelling(self, result, '入力ミス。とうちゃくごに写真をならべます。')
        self.assertFalse(result.get('odd_spans'))


    def test_participating_counts_and_attested_adverb_allow_only_following_repair(self):
        for prefix in ('ひとりで', 'ふたりで', 'さんにんで', 'よにんで', 'じゅうにんで',
                       'さぎょうのまえに', 'しごとのまえに'):
            with self.subTest(prefix=prefix):
                result = self.result(prefix + 'しゃしまをならべます。')
                assert_repaired_spelling(self, result, prefix + '写真をならべます。')
                self.assertFalse(result.get('odd_spans'))
                again = self.result(result['corrected'])
                self.assertEqual(again['corrected'], result['corrected'])
                self.assertFalse(again.get('odd_spans'))
        result = self.result('あとでしゃしまをならべます。')
        assert_repaired_spelling(self, result, 'あとでしゃしんをならべます。')
        self.assertFalse(result.get('odd_spans'))

    def test_count_copula_whole_adverb_and_genitive_stay_unchanged(self):
        for text in ('ひとりでした。', 'さんにんでした。', 'ひとりでしゃべります。',
                     'ひとりでに動きます。', 'ふたりでしゅっぱつします。',
                     'よにんで写真をならべます。', 'ともだちの写真をならべます。',
                     'ひとりでともだちの写真をならべます。'):
            with self.subTest(text=text):
                result = self.result(text)
                self.assertEqual(result['corrected'], text)
                self.assertFalse(result.get('odd_spans'))

    def test_counted_agent_proof_does_not_supply_an_object_or_an_action(self):
        for prefix in ('ひとりめで', 'にさつで', 'ひとで'):
            with self.subTest(prefix=prefix):
                self.assertFalse(R.native_counted_agent_prefix(prefix))
        for text in ('ひとりでぷねらをならべます。', 'さぎょうのまえにぷねらをならべます。'):
            with self.subTest(text=text):
                self.assertFalse(R.intact_native_reading(text))
                self.assertEqual(self.result(text)['corrected'], text)


if __name__ == '__main__':
    unittest.main()