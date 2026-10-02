# -*- coding: utf-8 -*-
"""Changed native chains retain the completion rules past their edit boundary."""
import unittest
import morphology as M
import oddness as O
import contextual_repair as R


@unittest.skipUnless(M.dictionary_inflections('読む'), 'requires native dictionary')
class FiniteCopulaTests(unittest.TestCase):
    def test_broken_past_attachment_does_not_prove_a_completed_ending(self):
        import corrector as C
        tok=C.make_tokenizer(None)
        for broken,fixed in (('検討しらた','検討したら'),
                             ('運びましらた','運びましたら')):
            self.assertTrue(R._preserves_completed_auxiliary_end(tok(broken),tok(fixed)))
        for source,candidate in (('検討した','検討して'),('運びました','運びまして')):
            self.assertFalse(R._preserves_completed_auxiliary_end(tok(source),tok(candidate)))
        for source in ('検討した','運びました'):
            self.assertTrue(R._preserves_completed_auxiliary_end(tok(source),tok(source)))

    def test_final_particles_do_not_supply_a_modifiers_nominal_host(self):
        import reading_segments as S
        self.assertTrue(S._native_non_nominal_modifier_tail('か'))
        self.assertFalse(S._native_non_nominal_modifier_tail('ぽねです'))
        for source,prefix in (('かんたんなぽねです','かんたんな'),
                              ('おおきなぽねです','おおきな')):
            self.assertIn((0,len(prefix)),S.native_adnominal_modifier_ranges(source))

    def test_finite_past_is_not_a_second_nominal_copula_stem(self):
        import reading_segments as R
        for text in ('よんだだ','読んだだ','たべただ','学生だだ'):
            self.assertFalse(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)
        for text in ('よんだ','よんだなら','よんだら','がくせいだったなら'):
            self.assertTrue(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)
        self.assertFalse(R.completed_native_verb_reading('よんだだ',True,False))
        self.assertFalse(R.completed_native_reading_link('ほんをよんだだなら',allow_unclassified=True))
        self.assertTrue(R.completed_native_reading_link('ほんをよんだなら',allow_unclassified=True))
        self.assertTrue(O.changed_auxiliary_chain_allowed('資料を確認。「読んだだ」',0,2))

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
