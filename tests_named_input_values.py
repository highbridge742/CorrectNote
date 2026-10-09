import unittest
from copy import copy
from unittest.mock import patch
import literal_examples as L
import morphology as M


class NamedInputValueTests(unittest.TestCase):
    def test_named_values_share_exact_closed_quote_and_label(self):
        for label in ('入力','出力'):
            for link in ('という','といった'):
                for after in ('','です。','なら確認します。','を確認します。','がある。','の値です。'):
                    source='前。😀「ぽね『文字』」 '+link+'　'+label+after
                    with self.subTest(source=source):
                        lo=source.index('「')+1;hi=source.index('」')
                        self.assertEqual(L.protected_ranges(source),[(lo,hi)])
        source='「ぽね」という入力\t別欄'
        self.assertEqual(L.protected_ranges(source),[(1,3)])
        seen=[];tokenize=M.tokenize
        source='「原文を解析しない」という入力'
        with patch.object(M,'tokenize',side_effect=lambda s:(seen.append(s) or tokenize(s))):
            self.assertTrue(L._input_output_value_report(source,0,source.index('」')))
        self.assertEqual(seen,['という入力'])

    def test_named_values_require_local_nominal_label_not_compound_or_action(self):
        for source in ('「ぽね」という入力装置','「ぽね」という入力方式',
                       '「ぽね」という入力 装置','「ぽね」という入力値',
                       '「ぽね」という入力ミス装置','「ぽね」という入力する',
                       '「ぽね」という入力して','「ぽね」という入力します',
                       '「ぽね」という入力ます','「ぽね」という入力ぷねら',
                       '「ぽね」\tという入力','「ぽね」という\t入力',
                       '「ぽね」\nという入力','「ぽね」といった\n出力',
                       '「ぽね」と 言う入力','「ぽね」と話します。',
                       '入力を調べて「ぽね」と言った。','「ぽね」',
                       '「ぽねという入力','「ぽね』という入力',
                       '（ぽね）という入力','「ぽね」という文章を校正します。'):
            with self.subTest(source=source):self.assertEqual(L.protected_ranges(source),[])

    def test_named_values_require_each_original_token_and_dictionary(self):
        source='「ぽね」という入力を確認します。';end=source.index('」')
        suffix=source[end+1:];parts=M.tokenize(suffix);tokenize=M.tokenize
        for index,field,value in (
                (0,'reading','というう'),(0,'pos','動詞'),(0,'pos_sub','格助詞:一般'),
                (0,'base_form','といった'),(0,'start',1),(0,'end',2),(0,'has_reading',False),
                (1,'reading','しゅつりょく'),(1,'pos','動詞'),(1,'base_form','出力'),
                (1,'infl_form','連用形'),(1,'start',2),(1,'end',6),(1,'has_reading',False),
                (2,'surface','が'),(2,'reading','が'),(2,'pos','名詞'),
                (2,'start',6),(2,'end',7),(2,'has_reading',False)):
            changed=[copy(t) for t in parts];setattr(changed[index],field,value)
            with self.subTest(index=index,field=field),patch.object(M,'tokenize',
                    side_effect=lambda s:changed if s==suffix else tokenize(s)):
                self.assertFalse(L._input_output_value_report(source,0,end))
        entries=M.dictionary_inflections
        for missing in ('という','入力','を'):
            with patch.object(M,'dictionary_inflections',
                    side_effect=lambda s:() if s==missing else entries(s)):
                self.assertFalse(L._input_output_value_report(source,0,end),missing)
        source='「ぽね」といった出力なら';end=source.index('」');suffix=source[end+1:]
        parts=M.tokenize(suffix)
        for field,value in (('reading','ならば'),('base_form','ます'),('infl_form','基本形'),
                            ('pos_sub','偽'),('end',len(suffix)-1)):
            changed=[copy(t) for t in parts];setattr(changed[-1],field,value)
            with patch.object(M,'tokenize',side_effect=lambda s:changed if s==suffix else tokenize(s)):
                self.assertFalse(L._input_output_value_report(source,0,end),field)

    def test_named_value_mask_keeps_outside_correction_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        state=initial()
        def result(source):
            return app.correct_line(source,state.store,input_method='kana',
                dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
        try:
            source='「ごにゅぅりょくしたきー」という入力'
            r=result(source)
            self.assertEqual(r['corrected'],source)
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            outer=source+'\t話を纏路手文章にします。'
            r=result(outer)
            self.assertEqual(r['corrected'],source+'\t話をまとめて文章にします。')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertTrue(r['original_spans'])
            self.assertTrue(all(a>=outer.index('話') for a,b in r['original_spans']))
            with patch.object(C,'_check_replacement',return_value=(None,'test_gate')):
                r=result(outer)
                self.assertEqual(r['corrected'],outer)
                self.assertEqual(r['analysis_status'],'complete')
            raw=source+'。変更するない'
            r=result(raw)
            self.assertEqual(r['corrected'],raw)
            self.assertTrue(r['odd_spans'])
            self.assertTrue(all(a>=raw.index('変更') for a,b in r['odd_spans']))
        finally:set_active(None)


if __name__=='__main__':unittest.main()
