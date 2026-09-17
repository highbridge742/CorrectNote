# -*- coding: utf-8 -*-
"""A changed noun needs support from the predicate kept in its original case."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('送る'),'requires native dictionary')
class ChangedNominalCaseTests(unittest.TestCase):
    def test_changed_noun_retains_its_unchanged_action(self):
        for original,changed,expected in (
                ('あとで良けれをおくります。','あとで池をおくります。',False),
                ('手が未を送ります。','手紙を送ります。',True),
                ('しりょにうをよみます。','資料をよみます。',True),
                ('ぬでをあらいます。','筆をあらいます。',True),
                ('赤けれをよみます。','筆をよみます。',False),
                ('がぞあを保存します。','がぞうを保存します。',True),
                ('しりょにうをよみます。','資料をよみなす。',True)):
            with self.subTest(original=original,changed=changed):
                self.assertEqual(S.changed_nominal_object_allowed(original,changed),expected)

    def test_wide_and_small_edits_share_the_same_unchanged_tail(self):
        source='あとで良けれをおくります。'
        self.assertFalse(S.changed_nominal_object_allowed(source,'あとで池をおくります。'))
        self.assertFalse(S.changed_nominal_object_allowed('あとで良けれをおくります。','あとで池をおくります。'))
        self.assertTrue(S.changed_nominal_object_allowed('あどで池をおくります。','あとで池をおくります。'))
        self.assertTrue(S.changed_nominal_object_allowed('よみなす。池をおくります。','よみます。池をおくります。'))

    def test_unclassified_nominal_and_nonargument_uses_keep_their_existing_scope(self):
        for original,changed in (
                ('ぬで','筆'),('ぬでを','筆を'),('ぬでを書いた人','筆を書いた人'),
                ('ぬでをながめながら話します。','筆をながめながら話します。'),
                ('ぬでを送られます。','筆を送られます。')):
            with self.subTest(original=original):
                self.assertTrue(S.changed_nominal_object_allowed(original,changed))
        self.assertTrue(S.changed_nominal_object_allowed('ぬでをよみます。','筆をよみます。'))
        text='池をおくります。'
        self.assertTrue(S.changed_nominal_object_allowed(text,text))

    def test_common_final_check_stops_the_wrong_location_candidate(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        accepted,reason=C._check_replacement('あとで良けれをおくります。',
            (3,6,'池','かな入力'),a.store,tk,a.dict_index,a.decisions)
        self.assertIsNone(accepted)
        self.assertEqual(reason,'unproven_changed_object_predicate')

    def test_application_keeps_the_unresolved_source_and_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        text='あとで良けれをおくります。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],text)
        self.assertTrue(result.get('odd_spans'))


if __name__=='__main__':unittest.main()
