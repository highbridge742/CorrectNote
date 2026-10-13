import unittest
from unittest.mock import patch
import morphology as M

class ContextualVerbReadingTests(unittest.TestCase):
    def test_native_whole_verb_needs_its_real_finite_continuation(self):
        for reading,face in (('あるか','歩か'),('とどか','届か')):
            self.assertFalse(M.native_spelling_only(reading,face))
            for tail in ('なかった','なかった。次の文です。'):
                with self.subTest(reading=reading,tail=tail):
                    self.assertTrue(M.native_spelling_only(reading,face,following=tail))
            for tail in ('','な','\tなかった','。なかった','資料がなかった','なか','なく'):
                with self.subTest(reading=reading,tail=tail):
                    self.assertFalse(M.native_spelling_only(reading,face,following=tail))
        for tail in ('ない','ないか','と聞きます','もしれません'):
            self.assertFalse(M.native_spelling_only('あるか','歩か',following=tail))
        self.assertTrue(M.native_spelling_only('とどか','届か',following='ないか'))
        self.assertFalse(M.native_spelling_only('あるく','歩か',following='なかった'))
        self.assertFalse(M.native_spelling_only('有るか','歩か',following='なかった'))

    def test_original_questions_keep_final_particles_in_common_gate(self):
        import corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();self.addCleanup(set_active,None);tok=C.make_tokenizer(a.store)
        for source in ('あるか','そこにあるか','あるかな','あるか。なかった','あるか\tなかった','あるかない','あるかないか','そこにあるかないか','あれはとどか'):
            head='とどか' if 'とどか' in source else 'あるか';face='届か' if head=='とどか' else '歩か'
            start=source.index(head)
            accepted,reason=C._check_replacement(source,(start,start+3,face,'かな入力'),a.store,tok,a.dict_index,a.decisions,spelling=True,conv_taken=((start,start+3),))
            self.assertIsNone(accepted,(source,reason))
        source='公園であるかなかった';start=source.index('あるか')
        accepted,reason=C._check_replacement(source,(start,start+3,'歩か','かな入力'),a.store,tok,a.dict_index,a.decisions,spelling=True,conv_taken=((start,start+3),))
        self.assertIsNotNone(accepted,reason)

    def test_original_ascii_still_uses_local_and_full_gate(self):
        import corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        a=initial();self.addCleanup(set_active,None);source='kouendearukanakatta';calls=[];native=C._check_replacement
        def observe(*args,**kwargs):calls.append((args[0],args[1]));return native(*args,**kwargs)
        def run():return correct_line(source,a.store,input_method='romaji',context_vocab={},dict_index=a.dict_index,decisions=a.decisions,context_vec=a.context_vec)
        with patch.object(C,'_check_replacement',observe):r=run()
        self.assertEqual(r['corrected'],'公園で歩かなかった');self.assertFalse(r['odd_spans'])
        self.assertTrue(any(text==source for text,replacement in calls))
        self.assertTrue(any(replacement[2]=='歩か' for text,replacement in calls))
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):self.assertEqual(run()['corrected'],source)
        a.decisions.protect('arukana');self.assertEqual(run()['corrected'],source)

    def test_missing_native_row_and_wrong_reading_preserve_old_fallback(self):
        native=M.dictionary_inflections
        for rows in ((),None,(('動詞,自立,*,*','未然形','歩く','ぷねら'),)):
            with patch.object(M,'dictionary_inflections',side_effect=lambda text:rows if text=='歩か' else native(text)):
                self.assertFalse(M.native_spelling_only('あるか','歩か',following='なかった'))

    def test_cancelled_native_lookup_and_final_grammar_do_not_publish(self):
        from analysis_context import request_scope,SupersededAnalysis
        import reading_segments as R
        M.tokenize('歩か');native=M.dictionary_inflections
        for answer in (native('歩か'),(),None):
            stale=False
            def obsolete(text):
                nonlocal stale
                value=native(text)
                if text=='歩か':stale=True;return answer
                return value
            with request_scope(lambda:stale,poll_interval=1000),patch.object(M,'dictionary_inflections',obsolete):
                with self.assertRaises(SupersededAnalysis):M.native_spelling_only('あるか','歩か',following='なかった')
        for answer in (True,False):
            stale=False
            def final(*args,**kwargs):
                nonlocal stale
                stale=True;return answer
            with request_scope(lambda:stale,poll_interval=1000),patch.object(R,'_completed_native_verb_surface',final):
                with self.assertRaises(SupersededAnalysis):M.native_spelling_only('あるか','歩か',following='なかった')

if __name__=='__main__':unittest.main()
