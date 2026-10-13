# -*- coding: utf-8 -*-
"""IME-off restoration owns only its source keys and unchanged context."""
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
import corrector as C
import halfwidth as H
import morphology as M
from tests_analysis_async import initial
from last_choice import set_active
from correction_entry import correct_line

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class RomajiCompletionTests(unittest.TestCase):
    def setUp(self):
        self.state=initial()
        self.addCleanup(set_active,None)
        self.tok=C.make_tokenizer(self.state.store)
    def finish(self,line='shouninが法廷で話します。',fixed='しょうにん',start=0,end=7,**kw):
        s=self.state
        return C._finish_halfwidth_candidate(line,start,end,fixed,s.store,self.tok,
            s.dict_index,s.decisions,input_method='romaji',**kw)
    def run_line(self,text,mode='romaji'):
        s=self.state
        return correct_line(text,s.store,context_vocab={},input_method=mode,
            dict_index=s.dict_index,decisions=s.decisions,context_vec=s.context_vec)
    def assert_complete(self,source,expected,mode='romaji'):
        row=self.run_line(source,mode)
        self.assertEqual(row['corrected'],expected,source)
        self.assertEqual(row['odd_spans'],[],source)
        self.assertEqual(row['analysis_status'],'complete',source)
        self.assertFalse(any(r.get('state')=='truncated' for r in row.get('search_reports',())))
    def test_native_completed_reading_is_not_a_spelling_answer(self):
        self.assertTrue(H._complete_romaji_reading('ゆうびんきょく',self.state.store))
        with patch('reading_segments.completed_native_reading',return_value=False), \
             patch('reading_segments.native_nominal_phrase_faces',return_value=()), \
             patch.object(H,'makes_sense_as_japanese',return_value=False):
            self.assertFalse(H._complete_romaji_reading('しょるいがとどきます',self.state.store))
    def test_original_ascii_passes_common_gate_before_native_projection(self):
        with patch.object(C,'_check_replacement',return_value=(None,'forced')) as gate, \
             patch('ime_spelling.project_first_words') as project:
            self.assertIsNone(self.finish())
            project.assert_not_called()
        self.assertEqual(gate.call_args.args[0],'shouninが法廷で話します。')
        self.assertEqual(gate.call_args.args[1][:3],(0,7,'しょうにん'))
        self.assertEqual(gate.call_args.kwargs['halfwidth_taken'],((0,7),))
    def test_native_unavailable_preserves_checked_restoration(self):
        with patch('ime_language.JapaneseIME') as provider:
            provider.return_value.__enter__.return_value.available=False
            self.assertEqual(self.finish(),'しょうにん')
            self.assertIsNone(self.finish(native_context_required=True))
        with patch('ime_spelling.project_first_words',side_effect=OSError('provider unavailable')):
            self.assertEqual(self.finish(),'しょうにん')
        with patch('ime_spelling.project_first_words',side_effect=ValueError('programming failure')):
            with self.assertRaises(ValueError):self.finish()
    def test_malformed_or_crossing_projection_cannot_rewrite_neighbor(self):
        for projected,edits in [('証人が法廷で話します',((-1,5,'証人'),)),
                ('証人が法廷で話します',((0,6,'証人'),)),
                ('証人が法廷で話します',((0,99,'証人'),)),
                ('証人が法廷で話します',((0,0,'証人'),)),
                ('証人が法廷で話します',((0,5,'証人'),(2,4,'証人'))),
                ('無関係な出力',((0,5,'証人'),))]:
            with self.subTest(edits=edits),patch('ime_spelling.project_first_words',return_value=(projected,edits,True)):
                self.assertEqual(self.finish(),'しょうにん')
    def test_outside_projection_is_not_applied_and_local_spelling_is_rechecked(self):
        source='shouninがはなします。';gate=C._check_replacement;seen=[]
        def checked(line,edit,*args,**kwargs):
            seen.append((line,edit,kwargs))
            if kwargs.get('spelling') and line=='しょうにんがはなします。':return None,'forced_original_context'
            return gate(line,edit,*args,**kwargs)
        proposal=('証人が話します',((0,5,'証人'),(6,9,'話し')),True)
        with patch('ime_spelling.project_first_words',return_value=proposal),patch.object(C,'_check_replacement',side_effect=checked):
            self.assertEqual(self.finish(source),'しょうにん')
        self.assertTrue(any(line=='しょうにんがはなします。' and k.get('spelling') for line,_,k in seen))
    def test_final_original_gate_can_reject_only_finished_spelling(self):
        gate=C._check_replacement
        def checked(line,edit,*args,**kwargs):
            if 'shounin' in line and edit[2]=='証人':return None,'forced_original_gate'
            return gate(line,edit,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=checked):
            self.assertEqual(self.finish(),'しょうにん')
    def test_partial_original_block_and_preceding_clause_keep_offsets(self):
        source='前文。shouninが法廷で話します。後文。';self.state.decisions.protect('ouni')
        self.assertIsNone(self.finish(source,start=3,end=10))
        self.state.decisions.unprotect('ouni')
        self.state.decisions.reject('shounin','証人')
        self.assertEqual(self.finish(source,start=3,end=10),'しょうにん')
    def test_raw_decision_store_retains_its_whole_line_block_contract(self):
        # The ordinary entry scopes decisions; a raw store here keeps
        # the existing common gate's whole-source protection.
        self.state.decisions.protect('法廷')
        self.assertIsNone(self.finish())
    def test_native_context_finishes_noun_and_predicate_without_outside_changes(self):
        cases=(('shoruiが届きます。','書類が届きます。'),
               ('gakuseiが話します。','学生が話します。'),
               ('前文。shouninが法廷で話します。後文。','前文。証人が法廷で話します。後文。'),
               ('病気をnaoshimasu。','病気を治します。'),
               ('機械をnaoshimasu。','機械を直します。'),
               ('shoruinohozon','書類の保存'),
               ('kakuninshitekarakaerimasu','確認してから帰ります'))
        for source,expected in cases:
            with self.subTest(source=source):self.assert_complete(source,expected)
    def test_space_and_unknown_sense_are_not_false_kanji_completion(self):
        for source,expected in (('病気を naoshimasu。','病気を naoshimasu。'),
                ('機械を naoshimasu。','機械を naoshimasu。'),
                ('shouninが商品を売ります。','shouninが商品を売ります。')):
            with self.subTest(source=source):self.assert_complete(source,expected)
    def test_english_literal_path_and_url_are_preserved(self):
        for source in ('change remote delete manage','https://example.com/shoruinohozon',r'C:\notes\shoruinohozon.txt'):
            with self.subTest(source=source):self.assert_complete(source,source)
    def test_new_native_reading_keeps_original_ascii_expression_context(self):
        for source in ('const shoruinohozon = 1;', 'shoruinohozon=1',
                'shoruinohozon　=　12', 'value = shoruinohozon',
                "value = 'shoruinohozon'", 'value = "shoruinohozon"',
                'print( shoruinohozon )','func( shoruinohozon );',
                'obj . shoruinohozon','value == shoruinohozon',
                'print(  shoruinohozon  )','obj .  shoruinohozon'):
            with self.subTest(source=source):self.assert_complete(source,source)
        self.assert_complete('value = 1。shoruiが届きます。','value = 1。書類が届きます。')
        self.assert_complete('shoruinohozon\t病気をnaoshimasu。','書類の保存\t病気を治します。')

    def test_seed_restoration_does_not_require_new_native_context(self):
        from unittest.mock import Mock
        accept=Mock(side_effect=AssertionError('old seed route must not call native acceptance'))
        with patch.object(H,'_complete_romaji_reading',side_effect=AssertionError('old seed route')):
            self.assertEqual(H.correct_romaji('pasokon',self.state.store,Mock(return_value=[]),
                native_context_accept=accept),'パソコン')
        accept.assert_not_called()

    def test_native_context_completion_is_projected_once(self):
        import ime_spelling
        with patch.object(ime_spelling,'project_first_words',wraps=ime_spelling.project_first_words) as project:
            self.assert_complete('shoruinohozon','書類の保存')
        self.assertEqual(sum(c.args[0]=='しょるいの保存' for c in project.call_args_list),1)

    def test_source_clause_does_not_borrow_another_column_or_quote(self):
        # Boundary evidence is independent of whether this bare noun has a
        # spelling proposal. The projector must never receive another field.
        for suffix in ('\t法廷で話します','⇒法廷で話します','「法廷で話します」','。法廷で話します'):
            line='前文。shounin'+suffix
            with self.subTest(suffix=suffix), \
                    patch.object(C,'_check_replacement',side_effect=lambda line,edit,*a,**k:(edit,'accepted')), \
                    patch('ime_spelling.project_first_words',return_value=None) as project:
                self.assertEqual(self.finish(line,start=3,end=10),'しょうにん')
                self.assertEqual(project.call_args.args[0],'しょうにん')

    def test_common_gate_and_partial_user_block_apply_at_app_entry(self):
        source='shoruiが届きます。'
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            self.assert_complete(source,source)
        self.state.decisions.protect('horu');self.assert_complete(source,source)

if __name__=='__main__':unittest.main()
