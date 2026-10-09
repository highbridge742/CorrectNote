import unittest
from unittest.mock import patch
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class FocusedIMEMeaningTests(unittest.TestCase):
    def setUp(self):
        from tests_analysis_async import initial
        import corrector as C
        self.a=initial();self.tokenize=C.make_tokenizer(self.a.store)
    def tearDown(self):
        from last_choice import set_active
        set_active(None)
    def correct(self,source):
        import app
        return app.correct_line(source,self.a.store,input_method='kana',
            dict_index=self.a.dict_index,decisions=self.a.decisions,context_vec=None)

    def test_same_focused_source_condition_and_real_tail_ownership(self):
        from kana_spelling import _unresolved_focused_nominal as unresolved
        from ime_spelling import _reinterprets_function_attachment as conflict
        for focus in ('だけ','ばかり','など'):
            self.assertTrue(unresolved('','もも',focus+'にします'))
            self.assertTrue(conflict('もも'+focus+'にします',0,2,'桃'))
            self.assertTrue(unresolved('','もも',focus+'\tを食べます'))
        self.assertFalse(unresolved('','もも','を食べます'))
        self.assertFalse(unresolved('','ねこ','だけを見ます'))
        self.assertFalse(unresolved('','ぷねら','だけにします'))
        self.assertFalse(conflict('ねこだけを見ます',0,2,'猫'))
        with patch('last_choice.surface_for_reading',return_value='桃'):
            self.assertFalse(conflict('ももだけにします',0,2,'桃'))

    def test_first_ime_routes_retain_the_same_unresolved_noun(self):
        from ime_language import JapaneseIME
        from ime_spelling import project_first_words
        from ime_full_field import additional_first_words
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest(ime.error)
            supplied=ime.convert_words('ももだけにします')
            self.assertIsNotNone(supplied)
        self.assertIsNone(project_first_words('ももだけにします',self.a.store,
            self.a.dict_index,self.a.decisions,self.tokenize))
        self.assertIsNone(additional_first_words('ももだけにします',None,self.a.store,
            self.a.dict_index,self.a.decisions,self.tokenize))
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'桃' if rd=='もも' else None):
            proposal=project_first_words('ももだけにします',self.a.store,
                self.a.dict_index,self.a.decisions,self.tokenize)
            self.assertIsNotNone(proposal)
            self.assertEqual(proposal[0],'桃だけにします')
            self.assertIn((0,2,'桃'),proposal[1])

    def test_field_closure_cannot_select_the_noun_but_other_field_can_spell(self):
        for source in ('ももだけにします。\t','ももだけにします。\t資料を保存します。',
                '資料を保存します。\tももだけにします。','ももだけ\tを食べます。',
                '桃だけにします。\t','腿だけにします。\t'):
            with self.subTest(source=source):
                result=self.correct(source)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        source='ももだけにします。\tねこだけを見ます。'
        result=self.correct(source)
        self.assertEqual(result['corrected'],'ももだけにします。\t猫だけを見ます。')
        self.assertFalse(result['odd_spans'])

    def test_shared_final_gate_keeps_ambiguity_choices_and_positive_evidence(self):
        import corrector as C
        def check(source,face):
            return C._check_replacement(source,(0,2,face,'かな入力'),self.a.store,
                self.tokenize,self.a.dict_index,self.a.decisions,
                conv_taken=((0,2),),spelling=True)
        self.assertEqual(check('ももだけにします','桃'),(None,'original_function_attachment'))
        accepted,reason=check('ねこだけを見ます','猫')
        self.assertIsNotNone(accepted,reason)
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'桃' if rd=='もも' else None):
            accepted,reason=check('ももだけにします','桃')
            self.assertIsNotNone(accepted,reason)
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            self.assertEqual(self.correct('ねこだけを見ます。\t')['corrected'],'ねこだけを見ます。\t')

    def test_wide_spelling_retains_each_actual_focused_source_noun(self):
        import corrector as C
        from ime_spelling import _reinterprets_function_attachment as conflict
        source='ももだけにします'
        for end,face in ((2,'桃'),(len(source),'桃だけにします')):
            with self.subTest(end=end):
                result=C._check_replacement(source,(0,end,face,'かな入力'),self.a.store,
                    self.tokenize,self.a.dict_index,self.a.decisions,
                    conv_taken=((0,end),),spelling=True)
                self.assertEqual(result,(None,'original_function_attachment'))
        self.assertTrue(conflict('資料\tももだけにします',3,3+len(source),'桃だけにします'))
        self.assertTrue(conflict('ももだけ\tを食べます',0,4,'桃だけ'))
        self.assertFalse(conflict('ねこだけを見ます',0,9,'猫だけを見ます'))
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'桃' if rd=='もも' else None):
            self.assertFalse(conflict(source,0,len(source),'桃だけにします'))

if __name__=='__main__':unittest.main()
