# -*- coding: utf-8 -*-
"""Changed native chains retain the completion rules past their edit boundary."""
import unittest
import morphology as M
import oddness as O
import contextual_repair as R


@unittest.skipUnless(M.dictionary_inflections('読む'), 'requires native dictionary')
class FiniteCopulaTests(unittest.TestCase):
    def test_terminal_conjunction_keeps_native_past_copula_scope(self):
        def legacy(t):
            return (t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form)
        previous,following=map(legacy,M.tokenize('確認しましただ')[-2:])
        split=O._terminal_polite_auxiliary_parts(previous,following)
        self.assertEqual([r[0] for r in split],['た','だ'])
        self.assertEqual([(r[3],r[4]) for r in split],[(5,6),(6,7)])
        self.assertFalse(O._terminal_polite_auxiliary_parts(
            previous[:4]+(previous[4]-1,)+previous[5:],following))
        self.assertFalse(O._terminal_polite_auxiliary_parts(
            previous[:2]+('ぷねら',)+previous[3:],following))
        for text in ('再点検しましただ','再点検しましただ。','保存しましただ！'):
            self.assertFalse(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)
            self.assertFalse(O.changed_auxiliary_chain_allowed(text,0,3,text.replace('点検','調査').replace('保存','編集')),text)
        for text in ('確認しましたただ資料がありません','確認しましただけ',
                     '確認しましたただし条件があります','確認しました。ただ、',
                     '確認しました、ただ、','確認しましたただ	資料',
                     '確認しました「ただ」'):
            self.assertTrue(O.changed_auxiliary_chain_allowed(text,0,2,'調査'+text[2:]),text)

    def test_terminal_past_change_keeps_gate_quotes_and_separate_scope(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            source='保ぞんしましただ'
            accepted,reason=C._check_replacement(source,(0,3,'保存','かな入力'),
                a.store,tok,a.dict_index,a.decisions)
            self.assertIsNone(accepted)
            self.assertEqual(reason,'native_auxiliary_chain')
            source='保ぞんしました'
            accepted,reason=C._check_replacement(source,(0,3,'保存','かな入力'),
                a.store,tok,a.dict_index,a.decisions)
            self.assertIsNotNone(accepted,reason)
            for source in ('「保ぞんしましただ」と入力しました。','「保存しましただ」という文字列'):
                result=app.correct_line(source,a.store,input_method='kana',
                    dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['analysis_status'],'complete')
            for source,changed in (('調査。読みましただ','確認。読みましただ'),
                                   ('調査\t読みましただ','確認\t読みましただ')):
                self.assertTrue(O.changed_auxiliary_chain_allowed(changed,0,2,source))
        finally:set_active(None)


    def test_polite_negative_keeps_its_actual_auxiliary_before_a_copula(self):
        def legacy(token):
            return (token.surface,token.pos+':'+token.pos_sub,token.reading,
                    token.start,token.end,token.has_reading,token.infl_form)
        parts=M.tokenize('しませんです')
        previous,a,b=map(legacy,parts[-3:])
        self.assertTrue(O.finite_copula_aux_mismatch(a,b,previous))
        self.assertFalse(O.finite_copula_aux_mismatch(a,b))
        self.assertFalse(O.finite_copula_aux_mismatch(a,b,
            previous[:4]+(previous[4]-1,)+previous[5:]))
        self.assertFalse(O.finite_copula_aux_mismatch(a,b,
            previous[:2]+('ぷねら',)+previous[3:]))
        for text in ('保存しませんです','保存しませんだ','保存しませんですよ'):
            self.assertFalse(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)
            self.assertFalse(R._productive_predicate(text,'保存'),text)
        for text in ('保存しませんでした','保存しないです','保存しませんからです',
                     '保存しませんで失礼しました','食べるんです','知らんです'):
            self.assertTrue(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)

    def test_polite_negative_change_keeps_source_quotes_and_other_clauses(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=C.make_tokenizer(a.store)
        try:
            source='保ぞんしませんです'
            accepted,reason=C._check_replacement(source,(0,3,'保存','かな入力'),
                a.store,tok,a.dict_index,a.decisions)
            self.assertIsNone(accepted)
            self.assertEqual(reason,'native_auxiliary_chain')
            normal='保ぞんしませんでした'
            accepted,reason=C._check_replacement(normal,(0,3,'保存','かな入力'),
                a.store,tok,a.dict_index,a.decisions)
            self.assertIsNotNone(accepted,reason)
            for source in ('「保ぞんしませんです」と入力しました。',
                           '「保存しませんです」という文字列'):
                result=app.correct_line(source,a.store,input_method='kana',
                    dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result['analysis_status'],'complete')
            for source,changed in (('点検。読みませんです','確認。読みませんです'),
                                   ('点検\t読みませんです','確認\t読みませんです')):
                self.assertTrue(O.changed_auxiliary_chain_allowed(changed,0,2,source))
        finally:set_active(None)


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
        # Same-key Shift plus a neighboring-key replacement at the same
        # original position is forbidden. Keep the old fixture as a key
        # rejection; unshifted つ -> さ reaches the auxiliary validation.
        for source,expected in (('かいてはけっしますです。','original_key_shift_state'),
                                ('かいてはけつしますです。','native_auxiliary_chain')):
            target = R.RepairTarget(source, 3, 7, 0, len(source), (), True, source[7:])
            accepted, reason = R.validate(target, 'はけさし', C, tk, a.store, a.dict_index)
            self.assertFalse(accepted,source)
            self.assertEqual(reason,expected)

    def test_changed_nominal_keeps_its_unchanged_suru_auxiliary_chain(self):
        for source,changed in (('確認しますです','保存しますです'),
                               ('確認しますだ','保存しますだ'),
                               ('確認しただ','保存しただ')):
            with self.subTest(source=source):
                # Wide or exact character edits must check the same chain.
                self.assertFalse(O.changed_auxiliary_chain_allowed(changed,0,2,source))
                self.assertFalse(O.changed_auxiliary_chain_allowed(changed,0,len(changed),source))
        for source,changed in (('確認します','保存します'),
                               ('確認しませんでした','保存しませんでした'),
                               ('確認するのです','保存するのです'),
                               ('確認。読みますです','保存。読みますです'),
                               ('確認をしますです','保存をしますです'),
                               ('「確認」しますです','「保存」しますです'),
                               ('確認	読みますです','保存	読みますです')):
            with self.subTest(source=source):
                self.assertTrue(O.changed_auxiliary_chain_allowed(changed,0,2,source))

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
