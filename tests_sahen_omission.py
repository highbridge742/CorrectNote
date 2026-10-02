# -*- coding: utf-8 -*-
"""Action-tail omissions use native forms without inventing a new stem."""
import unittest
import contextual_repair as C
import oddness as O

class SahenOmissionTests(unittest.TestCase):
    def test_omitted_functional_key_keeps_the_action_head(self):
        for original,expected in (('ほぞんました','ほぞんしました'),('へんこうれています','へんこうされています'),('けんされば','けんさすれば')):
            rows=C.sahen_omission_repairs(original)
            self.assertIn(expected,[r.reading for r in rows],original)
            self.assertTrue(all(r.operation=='omission' and r.pressed=='' for r in rows))
        self.assertNotIn('けんさされば',[r.reading for r in C.sahen_omission_repairs('けんされば')])
    def test_natural_tails_and_nominal_compounds_are_not_omissions(self):
        for original in ('けんさして','けんさします','けんさされて','けんされい','せっていれい'):
            self.assertEqual(C.sahen_omission_repairs(original),(),original)
    def test_optional_tail_scope_does_not_replace_a_native_head(self):
        from tests_analysis_async import initial
        import corrector
        a=initial();tokenize=corrector.make_tokenizer(a.store)
        targets=C.targets_for_line('あんじんしました',tokenize,a.store,a.dict_index)
        tails=[target for target in targets if target.boundary_kind=='sahen_tail']
        self.assertTrue(tails)
        self.assertTrue(all(target.preserved_head=='あんじ' for target in tails))
        self.assertEqual(C.sahen_omission_repairs('あんじんしました'),())

    def test_unfinished_polite_omission_keeps_the_actual_tail(self):
        repairs=C.sahen_open_omission_repairs('ほせいまし','ゆうせんして')
        self.assertEqual({r.reading for r in repairs},{'ほせいしまし'})
        self.assertEqual({(r.operation,r.pressed,r.intended) for r in repairs},
                         {('omission','','し')})
        for reading,before in (('ほせいしまし','ゆうせんして'),
                               ('ほせいまぇ','ゆうせんして'),
                               ('せつめいまし',''),('なまし','')):
            self.assertFalse(C.sahen_open_omission_repairs(reading,before),reading)
        from tests_analysis_async import initial
        import app
        state=initial()
        for source,expected in (('ゆうせんしてほせいまし','優先して補正しまし'),
                                ('かくにんしてほぞんまし','確認して保存しまし'),
                                ('ゆうせんしてほせいまし。','優先して補正しまし。')):
            result=app.correct_line(source,state.store,input_method='kana',
                decisions=state.decisions,dict_index=state.dict_index,context_vec=None)
            self.assertEqual(result['corrected'],expected,source)
            self.assertFalse(result['odd_spans'],source)
        for source in ('せつめいまし','なまし','ゆうせんしてほせいまぇ'):
            result=app.correct_line(source,state.store,input_method='kana',
                decisions=state.decisions,dict_index=state.dict_index,context_vec=None)
            self.assertEqual(result['corrected'],source)

    def test_generated_conditional_keeps_its_actual_native_form(self):
        for changed in ('気おされば','検査されば','説明すれば'):
            self.assertEqual(O.changed_modern_ba_allowed('壊れた入力',changed),changed=='説明すれば')
        self.assertTrue(O.changed_modern_ba_allowed('言わば資料を見つ','言わば資料を見た'))

if __name__=='__main__':unittest.main()
