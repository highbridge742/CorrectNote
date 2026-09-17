# -*- coding: utf-8 -*-
"""Changed native chains retain the completion rules past their edit boundary."""
import unittest
import morphology as M
import oddness as O
import contextual_repair as R


@unittest.skipUnless(M.dictionary_inflections('読む'), 'requires native dictionary')
class FiniteCopulaTests(unittest.TestCase):
    def test_completed_auxiliary_cannot_become_a_copular_stem(self):
        for text in ('読みますです', '読みますだ', '読みまいです',
                     '美しいですです', 'かいてはけさしますです'):
            with self.subTest(text=text):
                self.assertFalse(O.changed_auxiliary_chain_allowed(text, 0, len(text)))
        for text, head in (('読みますです','読み'), ('読みますだ','読み'),
                           ('読みまいです','読み'), ('美しいですです','美しい')):
            with self.subTest(text=text):
                self.assertFalse(R._productive_predicate(text, head))

    def test_unchanged_suffix_is_checked_after_an_inserted_particle_and_verb(self):
        text = 'かいてはけさしますです。'
        self.assertFalse(O.changed_auxiliary_chain_allowed(text, 3, 7))
        import corrector as C
        from tests_analysis_async import initial
        a = initial(); tk = C.make_tokenizer(a.store)
        source = 'かいてはけっしますです。'
        target = R.RepairTarget(source, 3, 7, 0, len(source), (), True, source[7:])
        accepted, reason = R.validate(target, 'はけさし', C, tk, a.store, a.dict_index)
        self.assertFalse(accepted)
        self.assertEqual(reason, 'native_auxiliary_chain')

    def test_normal_inflection_and_separate_clauses_remain_available(self):
        for text in ('読みませんでした', '読まないです', '読みますまい',
                     '読みまいと思います', '読みますからです', '美しいです',
                     'ますます元気です', '二つです', '真衣です', '升田です'):
            with self.subTest(text=text):
                self.assertTrue(O.changed_auxiliary_chain_allowed(text, 0, len(text)))
        for text, head in (('読みませんでした','読み'), ('読まないです','読ま'),
                           ('読みますまい','読み'), ('美しいです','美しい')):
            with self.subTest(text=text):
                self.assertTrue(R._productive_predicate(text, head))
        # An independent quoted or later colloquial phrase is outside this edit.
        for text in ('資料を確認。「読みますです」', '資料を確認。読みますです。',
                     '資料は、読みますです。'):
            with self.subTest(text=text):
                self.assertTrue(O.changed_auxiliary_chain_allowed(text, 0, 2))


if __name__ == '__main__':
    unittest.main()
