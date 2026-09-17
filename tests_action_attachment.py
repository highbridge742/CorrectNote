# -*- coding: utf-8 -*-
"""An actual action prefix participates in the full candidate grammar."""
import unittest
from dataclasses import replace
import morphology as M
import reading_segments as R
import contextual_repair as CR
import corrector as C


@unittest.skipUnless(M.dictionary_inflections('保存'),'requires native dictionary')
class ActionAttachmentTests(unittest.TestCase):
    def test_original_action_and_polite_end_are_shared_with_target(self):
        self.assertEqual(R.native_polite_action_prefixes('ほぞんくします'),(3,))
        self.assertEqual(R.native_polite_action_prefixes('かくにんくします'),(4,))
        self.assertEqual(R.native_polite_action_prefixes('ぷねらくします'),())
        self.assertEqual(R.native_polite_action_prefixes('ほぞんくし'),())
        self.assertEqual(R.native_polite_action_prefixes('ひょうきがありました'),())
        self.assertEqual(R.native_polite_action_prefixes('きかかんがありました'),())
        source='しゃしんをえらんでほぞんくします'
        target=CR.RepairTarget(source,9,len(source),0,len(source),
            (('品詞文法','未説明のかな語尾',9,len(source)),),True,'','kana_request')
        derived=[t for t in CR._native_action_tail_targets((target,)) if t!=target]
        self.assertEqual(len(derived),1)
        self.assertEqual((derived[0].text,derived[0].preserved_head),('ほぞんくします','ほぞん'))
        self.assertEqual(derived[0].anomalies,target.anomalies)
        self.assertEqual(derived[0].context,target.context)
        for item in (replace(target,anomalies=()),replace(target,structural=False)):
            self.assertEqual(CR._native_action_tail_targets((item,)),[item])

    def test_common_final_proof_covers_wide_narrow_and_written_candidates(self):
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='しゃしんをえらんでほぞんくします'
        for start,end,candidate in ((12,16,'かします'),(12,14,'かし'),
                (12,14,'燃し'),(9,16,'ほぞんかします')):
            result,why=C._check_replacement(text,(start,end,candidate,'かな入力'),
                a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNone(result)
            self.assertEqual(why,'unproven_native_action_attachment')
        for tail in ('します','もします','はします'):
            self.assertTrue(CR.changed_native_action_attachment_allowed(text,12,16,tail))
        self.assertFalse(CR.changed_native_action_attachment_allowed('かくにんくします',3,6,'隠し'))

    def test_complete_repairs_and_native_alternatives(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (
                ('しゃしんをえらんでほぞんくします。','しゃしんをえらんでほぞんします。'),
                ('ほぞんくします。','ほぞんします。'),
                ('かくにんくします。','かくにんします。')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],expected)
            self.assertEqual(result.get('odd_spans'),[])
        for source in ('ほぞんもします。','ほぞんはします。','かくにんします。',
                       'しゃしんをえらんでほぞんします。','保存先を開きます。',
                       'ごまをすります。','入力にします。','保存や検索をします。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)


if __name__=='__main__':unittest.main()
