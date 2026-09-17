# -*- coding: utf-8 -*-
"""Explicit kana intrusion choices retain their complete grammatical range."""
import sys
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
import morphology as M
from candidates import particle_intrusion_candidates

@unittest.skipUnless(M.HAS_JANOME, 'requires native Janome dictionary')
class ParticleCandidateTests(unittest.TestCase):
    def test_native_and_kana_boundaries_preserve_spelling(self):
        for original, expected in (('文書に気は、', '文書には'),
                ('ぶんしょにきは、', 'ぶんしょには'), ('画面にきは、', '画面には'),
                ('文書できは、', '文書では'), ('ぶんしょにきはみだしがあります。', 'ぶんしょには'), ('画面からきは、', '画面からは')):
            with self.subTest(original=original):
                got = particle_intrusion_candidates(original, 0, len(original))
                chosen = next(c for c in got if c['surface'] == expected)
                start, end = chosen['span']
                self.assertEqual(original[start:end], chosen['base'])
                self.assertEqual(original[:start]+chosen['surface']+original[end:], expected+original[end:])

    def test_only_original_adjacent_keys_and_valid_particle_pair(self):
        for text in ('文書にんは、', '文書にには、', '文書にはは、',
                     '文書にぎは、', '本をきは、', '文書がきは、', '説明の続きは、'):
            with self.subTest(text=text):
                self.assertFalse(particle_intrusion_candidates(text, 0, len(text)))

    def test_menu_reuses_ready_index_without_full_reading_table(self):
        index=SimpleNamespace(surfaces_for_reading=lambda rd:['文書'] if rd=='ぶんしょ' else [])
        with patch('reading_segments.native_nominal_phrase_faces',side_effect=AssertionError('full table')):
            got=particle_intrusion_candidates('ぶんしょにきは、',0,8,index)
        self.assertEqual(got[0]['surface'],'ぶんしょには')
        from reading_segments import native_common_noun_reading
        self.assertTrue(native_common_noun_reading('文書','ぶんしょ'))
        self.assertFalse(native_common_noun_reading('文書','ぶんしょう'))
        self.assertFalse(native_common_noun_reading('田中','たなか'))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertFalse(native_common_noun_reading('文書','ぶんしょ'))

    def test_selected_range_must_contain_intrusion(self):
        text = '前文。文書に気は、後文。'
        self.assertFalse(particle_intrusion_candidates(text, 3, 5))
        got = particle_intrusion_candidates(text, 6, 7)
        self.assertEqual(got[0]['span'], (3, 8))
        self.assertEqual(got[0]['surface'], '文書には')
        self.assertFalse(particle_intrusion_candidates(text, -1, 5))

    def test_long_line_keeps_global_coordinates_with_local_tokenization(self):
        prefix='前の文章です。'*1000
        text=prefix+'文書に気は、'
        with patch.object(M,'tokenize',wraps=M.tokenize) as tokenize:
            got=particle_intrusion_candidates(text,len(prefix)+3,len(prefix)+4)
        self.assertEqual(got[0]['span'],(len(prefix),len(prefix)+5))
        self.assertTrue(all(len(call.args[0])<=33 for call in tokenize.call_args_list))

    def test_natural_continuations_and_bare_unfinished_input_are_not_deleted(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('文書に気は', '文書に気は配っています。', '庭に木はあります。',
                     'ここにきはありません。', '説明の続きは明日です。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)

@unittest.skipUnless(sys.platform == 'win32' and M.HAS_JANOME, 'Windows native UI')
class ParticleChoiceTkTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        import app
        self.root=tk.Tk();self.root.withdraw()
        a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root=self.root;a.editor=tk.Text(self.root);a.result_view=tk.Text(self.root)
        a._quick_text=tk.Text(self.root);a._quick_win=self.root
        a.settings={'input_method':'kana'};a.choices=Mock();a.choices.lookup.return_value=None
        a.store=Mock();a.dict_index=Mock();a.dict_index.ready=True;a.context_vec=None
        a.dict_index.surfaces_for_reading=lambda r:['文書'] if r=='ぶんしょ' else []
        a._editor_changes=[];a._quick_changes=[];a.status=Mock();a._dropdown=None
        a._unit_surroundings=lambda *args:[];a._functional_kanji_cands=lambda *args:[]
        a._odd_run_candidates=lambda *args:[];a._halfwidth_candidates=lambda *args:[]
        a._odd_menu_items=lambda *args:[];a._analysis_items=lambda *args,**kwargs:[]
        a.autofix_span_at=lambda *args,**kwargs:None;a._autofix_menu_items=lambda *args,**kwargs:[]
        a._result_correction_menu_items=lambda *args,**kwargs:[];a._to_original_span=lambda *args:None
        a._find_change=lambda *args:None;a.unified_autofix_on=lambda:False
        for name in ('_make_dropdown','_close_dropdown','_invalidate_units_cache',
                     '_invalidate_analysis_cache','_remember_recent','_mark_typed','_on_change',
                     '_analyze','_analyze_quick','_render_corrected','_update_status','_reselect_after_choice'):
            setattr(a,name,Mock())
        a._supersede_prior_choice=Mock(return_value=None);a._choice_reading=lambda *args:''
        self.source='前文。文書に気は、後文。'
        for widget in (a.editor,a.result_view,a._quick_text):widget.insert('1.0',self.source)
        self.unit=dict(start=6,end=7,text='気',base='気',reading='き',prev='に',next='は',kind='plain',detail=None)
        a.line_units=[[self.unit]];a._quick_units=[[self.unit]];a.line_texts=[self.source]
        a.line_results=[dict(original=self.source,corrected=self.source,details=[])]

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')

    def test_all_three_menus_offer_and_apply_the_same_complete_range(self):
        import app
        a=self.a
        with patch.object(app,'build_candidates',return_value=[]),patch.object(app,'symbol_candidates',return_value=[]):
            for pane in ('editor','result','quick'):
                with self.subTest(pane=pane):
                    a.choices.record.reset_mock();a._make_dropdown.reset_mock()
                    if pane=='editor':
                        items=a._editor_dropdown_items(1,self.unit,a.line_units[0]);widget=a.editor
                    elif pane=='result':
                        a._open_dropdown(SimpleNamespace(x_root=0,y_root=0),1,self.unit)
                        items=a._make_dropdown.call_args.args[0];widget=a.result_view
                    else:
                        a._open_quick_dropdown(SimpleNamespace(x_root=0,y_root=0),1,self.unit)
                        items=a._make_dropdown.call_args.args[0];widget=a._quick_text
                    callback=next(cb for label,cb in items if label.strip()=='文書には')
                    self.assertEqual(widget.get('1.0','end-1c'),self.source)
                    a.choices.record.assert_not_called()
                    callback()
                    self.assertEqual(a.choices.record.call_args.args[:2],('文書に気は','文書には'))
                    if pane!='result':
                        self.assertEqual(widget.get('1.0','end-1c'),'前文。文書には、後文。')
                    else:
                        a._render_corrected.assert_called_once()

    def test_automatic_deletion_can_be_restored_in_split_and_unified_panes(self):
        import app
        from tests_analysis_async import initial
        from decisions import DecisionStore
        runtime=initial();a=self.a;source='文書に気は、'
        def corrected():
            return app.correct_line(source,runtime.store,dict_index=runtime.dict_index,
                decisions=a.decisions,input_method='kana')
        a._result_correction_menu_items=type(a)._result_correction_menu_items.__get__(a)
        a._reanalyze_all=Mock()
        for pane in ('input','result','unified'):
            with self.subTest(pane=pane):
                a.decisions=DecisionStore();a.decisions.save=Mock()
                result=corrected();self.assertEqual(result['corrected'],'文書には、')
                a.line_results=[result];a.line_texts=[source]
                for widget,text in ((a.editor,source),(a.result_view,result['corrected'])):
                    widget.delete('1.0','end');widget.insert('1.0',text)
                if pane=='unified':
                    a.editor.delete('1.0','end');a.editor.insert('1.0',result['corrected'])
                    a._autofix_pane=lambda w=None:(a.editor,'_autofix_records',Mock())
                    a._autofix_record_for_row=lambda *args:None
                    span=(*result['spans'][0],'fixed',result['details'][0][0])
                    items=type(a)._autofix_menu_items(a,1,span)
                else:
                    is_source=pane=='input'
                    start,end=(result['original_spans'] if is_source else result['spans'])[0]
                    items=a._result_correction_menu_items(1,dict(start=start,end=end),source=is_source)
                self.assertTrue(any(label=='― 自動補正 ―' for label,cb in items))
                next(cb for label,cb in items if '元の入力に戻す' in label)()
                self.assertTrue(a.decisions.blocks('文書に気は','文書には'))
                self.assertEqual(corrected()['corrected'],source)
                if pane=='unified':self.assertEqual(a.editor.get('1.0','end-1c'),source)

    def test_stale_candidate_is_rejected_before_edit_or_learning(self):
        a=self.a
        for widget,choose in ((a.editor,lambda c:a._editor_choose_word(1,self.unit,c)),
                (a.result_view,lambda c:a._choose_word(self.unit,c,1)),
                (a._quick_text,lambda c:a._quick_choose_word(1,self.unit,c))):
            with self.subTest(widget=str(widget)):
                cand=a._particle_choice_candidates(1,self.unit,widget,[self.unit])[0]
                widget.delete('1.0','end');widget.insert('1.0','別の文章です。')
                a.choices.record.reset_mock();choose(cand)
                self.assertEqual(widget.get('1.0','end-1c'),'別の文章です。')
                a.choices.record.assert_not_called()

    def test_romaji_and_unrelated_selection_do_not_offer_kana_intrusions(self):
        a=self.a;a.settings['input_method']='romaji'
        self.assertFalse(a._particle_choice_candidates(1,self.unit,a.editor,[self.unit]))
        a.settings['input_method']='kana'
        changed=dict(self.unit,text='木')
        self.assertFalse(a._particle_choice_candidates(1,changed,a.editor,[self.unit]))

if __name__=='__main__':unittest.main()
