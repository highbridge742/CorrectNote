# -*- coding: utf-8 -*-
"""Original finite polite meaning survives physical and IME proposals."""
import unittest
import reading_segments as R

class PoliteSourceTailTests(unittest.TestCase):
    def test_missing_host_can_be_completed(self):
        for original,changed in (('説明ました','説明しました'),('説明ません','説明しません'),('説明です','説明です'),('説明でした','説明でした')):
            with self.subTest(original=original):self.assertTrue(R.preserves_native_polite_auxiliary(original,changed))
    def test_existing_polite_tail_is_not_erased(self):
        for original,changed in (('説明ました','説明した'),('説明ません','説明せん'),('調べます','調べまい'),('説明でした','説明だった'),('調べませんでした','調べました')):
            with self.subTest(original=original):self.assertFalse(R.preserves_native_polite_auxiliary(original,changed))
    def test_lexical_letters_and_unfinished_auxiliary_do_not_supply_a_tail(self):
        for text in ('ますます','マス','アマゾン','説明まし','いますとーる'):
            with self.subTest(text=text):self.assertEqual(R.native_polite_auxiliary_chains(text),())
    def test_invalid_auxiliary_attachment_does_not_freeze_a_bad_tail(self):
        for bad in ('調べますう','調べますき','調べますだ'):
            with self.subTest(bad=bad):
                self.assertEqual(R.native_polite_auxiliary_chains(bad),())
                self.assertTrue(R.preserves_native_polite_auxiliary(bad,'調べますか'))
        for good in ('調べましょう','調べました','調べません','調べませんでした'):
            with self.subTest(good=good):
                self.assertTrue(R.native_polite_auxiliary_chains(good))
                self.assertFalse(R.preserves_native_polite_auxiliary(good,'調べる'))

    def test_finite_tail_survives_a_question_or_connected_clause(self):
        for source,changed in (('調べますか','調べるか'),('調べますが','調べるが'),
                ('調べますと説明にあります','調べると説明にあります'),
                ('調べます。未知れた部分','調べる。未知れた部分')):
            with self.subTest(source=source):
                self.assertFalse(R.preserves_native_polite_auxiliary(source,changed))

    def test_unchanged_host_and_tail_survive_pending_lexical_spelling(self):
        self.assertTrue(R.preserves_native_polite_auxiliary(
            'ふあいるをひらきます','ふぁいるをひらきます'))
        self.assertFalse(R.preserves_native_polite_auxiliary(
            '調べます','調べました'))

    def test_other_column_cannot_replace_original_tail(self):
        self.assertFalse(R.preserves_native_polite_auxiliary('説明ました\t説明しました','説明した\t説明しました'))
    def test_confirmed_spelling_change_keeps_the_same_polite_auxiliary(self):
        for source,changed in (('確認しましょぅ','確認しましょう'),
                ('よいでしょぅか。確認しましょぅ。','よいでしょうか。確認しましょぅ。')):
            self.assertTrue(R.preserves_native_polite_auxiliary(source,changed))
        self.assertFalse(R.preserves_native_polite_auxiliary('確認しましょぅ','確認した'))

    def test_open_native_politeness_survives_without_freezing_its_inflection(self):
        for source in ('説明まし','読みまし','説明でし'):
            with self.subTest(source=source):
                self.assertEqual(R.native_polite_auxiliary_chains(source),())
                self.assertTrue(R.native_polite_auxiliary_chains(source,include_open=True))
        for source,changed in (('説明まし','説明しまし'),('説明まし','説明します'),
                ('説明まし','説明しました'),('説明でし','説明です'),
                ('ほせいまし','補正しまし')):
            with self.subTest(source=source,changed=changed):
                self.assertTrue(R.preserves_native_polite_auxiliary(source,changed))
        for source,changed in (('説明まし','説明した'),('ほせいまし','干せまいし'),
                ('ゆうせんしてほせいまし','優先して干せいくし'),
                ('説明まし\t記録します','説明した\t記録します'),
                ('説明まし。記録します','説明した。記録します')):
            with self.subTest(source=source,changed=changed):
                self.assertFalse(R.preserves_native_polite_auxiliary(source,changed))

    def test_open_auxiliary_is_not_inferred_from_lexical_letters(self):
        for source in ('ますます','なまし','やましい','アマゾン','いますとーる'):
            with self.subTest(source=source):
                self.assertEqual(R.native_polite_auxiliary_chains(source,include_open=True),())

    def test_unrelated_words_can_change(self):
        self.assertTrue(R.preserves_native_polite_auxiliary('説明をかくにんします','説明を確認します'))

if __name__=='__main__':unittest.main()
