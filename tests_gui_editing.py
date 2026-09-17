# -*- coding: utf-8 -*-
"""Real Tk regression tests for user editing boundaries and selection targets."""
import os
import types
import unittest
from unittest.mock import Mock,patch
import tkinter as tk
import app

class EditingTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root=self.root
        self.a.editor=tk.Text(self.root,undo=True)
        self.a.result_view=tk.Text(self.root,undo=False)
        self.a.settings={'layout':'split','dark_mode':False}
        self.a._autofix_reset=Mock();self.a._reset_typed_marks=Mock()
        self.a._pad_blank_lines=Mock();self.a._mark_dirty=Mock();self.a._analyze=Mock()
        # Keep the user's system clipboard untouched: replace only this Tcl
        # interpreter's selection accessor used by the native Text paste binding.
        self.root.tk.call('rename','::tk::GetSelection','::tk::GetSelectionSaved')
        self.root.tk.call('proc','::tk::GetSelection','args','return $::test_paste_text')
        self.root.tk.setvar('::test_paste_text','貼り付けた文')
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def text(self):return self.a.editor.get('1.0','end-1c')
    def test_shift_space_arrows_keep_logical_line_anchor(self):
        from tests_tk_keys import deliver_key
        a = self.a
        a.status = Mock()
        for w in (a.editor, a.result_view):
            w.configure(width=5, wrap='char')
            w.insert('1.0', '最初の行\n長い行😀を折り返して表示します\n三行目\n四行目')
            w.mark_set(a._sel_anchor_mark(w), '1.0')
            w.mark_set('insert', '2.3')
            a._install_line_selection_keys(w)
            deliver_key(w, '<Shift-space>', 'space', 32, state=1)
            self.assertEqual(w.get('sel.first', 'sel.last'), '長い行😀を折り返して表示します')
            for sequence, key, expected in (
                    ('<Shift-Down>', 'Down', ('2.0', '3.end')),
                    ('<Shift-Down>', 'Down', ('2.0', '4.end')),
                    ('<Shift-Up>', 'Up', ('2.0', '3.end')),
                    ('<Shift-Up>', 'Up', ('2.0', '2.end')),
                    ('<Shift-Up>', 'Up', ('1.0', '2.end')),
                    ('<Shift-Up>', 'Up', ('1.0', '2.end'))):
                deliver_key(w, sequence, key, 40 if key == 'Down' else 38, state=1)
                self.assertEqual(tuple(str(i) for i in w.tag_ranges('sel')),
                                 tuple(w.index(i) for i in expected))
            self.assertEqual(w.index(a._sel_anchor_mark(w)), w.index('2.end'))

    def test_line_selection_trim_empty_line_and_release(self):
        from tests_tk_keys import deliver_key
        a = self.a
        a.status = Mock()
        w = a.editor
        w.insert('1.0', '先頭\n  本文　\n\n末尾')
        a._install_line_selection_keys(w)
        w.mark_set('insert', '2.2')
        for _ in range(2):
            deliver_key(w, '<Shift-space>', 'space', 32, state=1)
        self.assertEqual(w.get('sel.first', 'sel.last'), '本文')
        deliver_key(w, '<Shift-Down>', 'Down', 40, state=1)
        self.assertEqual(w.get('sel.first', 'sel.last'), '  本文　\n')
        deliver_key(w, '<KeyRelease-Shift_L>', 'Shift_L', 16, state=1, event_type=3)
        self.assertIsNone(w._line_selection)
        self.assertIsNone(a._on_extend_line_selection(types.SimpleNamespace(widget=w), 1))
        w.mark_set('insert', '3.0')
        deliver_key(w, '<Shift-space>', 'space', 32, state=1)
        self.assertFalse(w.tag_ranges('sel'))
        deliver_key(w, '<Shift-Down>', 'Down', 40, state=1)
        self.assertEqual(w.get('sel.first', 'sel.last'), '\n末尾')
        w.tag_remove('sel', '1.0', 'end')
        w.mark_set('insert', '1.0')
        self.assertIsNone(a._on_extend_line_selection(types.SimpleNamespace(widget=w), -1))
        self.assertIsNone(w._line_selection)

    def test_search_replacement_is_one_undo_and_redo(self):
        w=self.a.editor;before='最初の文😀\n次の文\n'
        w.insert('1.0',before);w.edit_reset()
        self.a._replace_editor_text('最初の文😀\n置換した文\n')
        w.event_generate('<<Undo>>');self.assertEqual(self.text(),before)
        w.event_generate('<<Redo>>');self.assertEqual(self.text(),'最初の文😀\n置換した文\n')
    def test_paste_undo_keeps_preceding_typed_text(self):
        w=self.a.editor;w.insert('1.0','先に打った文');w.mark_set('insert','end-1c')
        w.event_generate('<<Paste>>');self.assertEqual(self.text(),'先に打った文貼り付けた文')
        w.event_generate('<<Undo>>');self.assertEqual(self.text(),'先に打った文')
        w.event_generate('<<Redo>>');self.assertEqual(self.text(),'先に打った文貼り付けた文')
    def test_undo_after_paste_and_autofix_never_erases_preceding_text(self):
        a=self.a;w=a.editor;w.insert('1.0','先に打った文');w.mark_set('insert','end-1c')
        self.root.tk.setvar('::test_paste_text','と貼付ご');w.event_generate('<<Paste>>')
        original=self.text();corrected='先に打った文と貼付語'
        a.unified_autofix_on=lambda:True;a.store=types.SimpleNamespace(_tokenize_fn=lambda text:[])
        a.choices=None;a._known_kana_word=lambda text:False
        a._autofix_live_records=lambda:[];a._change_is_inside_typed=lambda *args:True
        a._typed_ranges_of_row=lambda row:[];a._restore_typed_ranges=Mock()
        a._autofix_remember=Mock();a._repaint_autofix_tags=Mock()
        a.line_results=[dict(original=original,corrected=corrected,pending=False)]
        with patch.object(app,'build_line_units',return_value=(corrected,[])):
            self.assertTrue(a._apply_unified_autofix())
        w.event_generate('<<Undo>>');self.assertEqual(self.text(),original)
        w.event_generate('<<Undo>>');self.assertEqual(self.text(),'先に打った文')
    def test_quote_drag_hides_hover_until_button_released(self):
        a=self.a;a._pick_mode='key';a._layout_is_unified=lambda:True
        unit=dict(text='単語',start=0,end=2)
        a._editor_unit_under_pointer=lambda event:(1,unit)
        a._unit_under_pointer=lambda event:(1,unit);a._set_pane_cursor=Mock()
        for widget,handler in ((a.editor,a._on_editor_motion),(a.result_view,a._on_result_motion)):
            widget.insert('1.0','単語');widget.tag_add('hover','1.0','1.2')
            handler(types.SimpleNamespace(state=0x100,widget=widget,x=1,y=1))
            self.assertFalse(widget.tag_ranges('hover'))
            handler(types.SimpleNamespace(state=0,widget=widget,x=1,y=1))
            self.assertTrue(widget.tag_ranges('hover'))
    def test_f2_uses_selected_correction_pane(self):
        a=self.a;a._ime_fkey_skip=lambda event:None;a._dropdown=None
        a._layout_is_unified=lambda:False;a._f2_cycle=None;a._quick_win=None
        unit=dict(text='完了',base='官僚',start=0,end=2,kind='fixed',detail=('官僚','完了','同音'))
        a.line_results=[dict(original='官僚',corrected='完了')];a.line_units=[[unit]]
        a.editor.insert('1.0','官僚');a.result_view.insert('1.0','完了')
        a.result_view.mark_set('insert','1.2')
        a._f2_show_or_skip=Mock(return_value='break')
        a._editor_line_units=Mock(return_value=[])
        a._on_f2_candidates(types.SimpleNamespace(widget=a.result_view))
        self.assertTrue(a._f2_show_or_skip.called)
        self.assertIs(a._f2_show_or_skip.call_args.args[2],a.result_view)
        self.assertEqual(a._f2_show_or_skip.call_args.args[1]['detail'],unit['detail'])

    def test_projection_preserves_document_and_real_edit_changes_generation(self):
        import analysis_work_app as work
        from session import SessionStore,new_tab
        a=self.a;a.session=SessionStore();a.session.tabs=[new_tab(text='資料')]
        a.editor.insert('1.0','資料')
        work.select_document(a,'資料');work.install(a)
        a._input_document.remember(0,2,'資料','しりょう')
        before=work.token(a)
        with work.display_update(a):a.editor.replace('1.0','end-1c','データ')
        self.assertEqual(work.token(a),before)
        self.assertEqual(a._input_document.text,'資料')
        self.assertTrue(work.has_readings(a))
        with work.display_update(a):a.editor.replace('1.0','end-1c','資料')
        a.editor.insert('end-1c','を保存')
        self.assertNotEqual(work.token(a),before)
        self.assertEqual(a._input_document.text,'資料を保存')
        self.assertTrue(work.has_readings(a))

    def test_tab_save_and_round_trip_preserve_live_reading(self):
        import analysis_work_app as work
        from session import SessionStore,new_tab
        a=self.a;a.session=SessionStore();a.session.tabs=[new_tab(text='資料'),new_tab(text='別の資料')]
        a.editor.insert('1.0','資料');work.select_document(a,'資料');work.install(a)
        a._input_document.remember(0,2,'資料','しりょう')
        before=work.token(a)
        a.session.update_active(new_tab(text='資料'))
        self.assertEqual(work.token(a),before)
        a.session.active=1
        with work.display_update(a):a.editor.replace('1.0','end-1c','別の資料')
        work.select_document(a,'別の資料')
        self.assertFalse(work.has_readings(a))
        a.session.active=0
        with work.display_update(a):a.editor.replace('1.0','end-1c','資料')
        work.select_document(a,'資料')
        self.assertTrue(work.has_readings(a))
        self.assertNotEqual(work.token(a),before)


    def test_merged_word_menu_uses_actual_change_pair_and_protects_source_word(self):
        a=self.a;a.dict_index=types.SimpleNamespace(ready=True);a.store=None;a.context_vec=None
        a._unit_surroundings=lambda *args:();a._analysis_items=lambda *args,**kwargs:[]
        a._to_original_span=lambda *args:(0,2)
        a._reject_correction=Mock();a._protect_word=Mock()
        a.result_view.insert('1.0','寒い日だ。')
        unit=dict(start=0,end=2,text='寒い',base='寒い',reading='さむい',
                  kind='fixed',detail=('ぃ','い','かな入力'))
        a.line_units=[[unit]];a.line_results=[dict(original='寒ぃ日だ。',corrected='寒い日だ。')]
        menu=[];a._make_dropdown=lambda items,x,y:menu.extend(items)
        with patch.object(app,'build_candidates',return_value=[]):
            a._open_dropdown(types.SimpleNamespace(x_root=0,y_root=0),1,unit)
        next(cb for label,cb in menu if '元の入力に戻す' in label)()
        a._reject_correction.assert_called_once_with('ぃ','い')
        next(cb for label,cb in menu if '今後直さない' in label)()
        a._protect_word.assert_called_once_with('寒ぃ')



    def _open_find_fixture(self, replace=False):
        self.a.settings.update(find_match_case=False, find_whole_word=False,
                               find_regex=False, find_wrap=True)
        # Map owned, transparent test windows before sending native events.
        self.root.attributes('-alpha', 0)
        self.root.deiconify();self.root.update()
        toplevel = tk.Toplevel
        def transparent_top(*args, **kwargs):
            dialog = toplevel(*args, **kwargs)
            dialog.attributes('-alpha', 0)
            return dialog
        with patch.object(tk, 'Toplevel', side_effect=transparent_top):
            self.a.open_find_dialog(replace)
        self.root.update()
        return self.a._find_entry, self.a._replace_entry

    def _find_button(self, label):
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        return next(w for w in children(self.a._find_dialog)
                    if isinstance(w, tk.Button) and w.cget('text') == label)

    def test_find_insert_buttons_use_last_field_and_replace_selection(self):
        find, replace = self._open_find_fixture(True)
        find.insert(0, '前後');find.icursor(1)
        self._find_button('タブを挿入').invoke()
        self.assertEqual(find.get(), '前\t後')
        self.assertEqual(find.index('insert'), 2)
        replace.insert(0, '消す範囲');replace.selection_range(0, 2)
        replace.event_generate('<FocusIn>')
        self._find_button('改行を挿入').invoke()
        self.assertEqual(replace.get(), '\n範囲')
        self.assertEqual(self.a._find_replacement.get(), '\n範囲')
        self.assertEqual(find.get(), '前\t後')
        self.assertFalse(replace.selection_present())
        self.a._hide_replace_row()
        self._find_button('改行を挿入').invoke()
        self.assertEqual(find.get(), '前\t\n後')

    def test_marked_entry_native_edits_copy_and_paste_keep_real_characters(self):
        find, _ = self._open_find_fixture()
        text = '😀\t↵\u2003\n終'
        self.a._find_query.set(text)
        self.assertEqual(find.get(), text)
        find.selection_range(0, 'end')
        self.assertEqual(self.root.tk.call('tk::EntryGetSelection', find._w), text)
        units = int(self.root.tk.call('string', 'length', '😀'))
        find.delete(units, units+1)
        self.assertEqual(find.get(), '😀↵\u2003\n終')
        find.insert(units, '\t')
        self.assertEqual(find.get(), text)
        find.selection_range(0, 'end')
        self.root.tk.setvar('::test_paste_text', '貼付\t\n次')
        find.event_generate('<<Paste>>')
        self.assertEqual(find.get(), '貼付\t\n次')
        self.assertEqual(self.a._find_query.get(), find.get())
        self.assertEqual(self.root.tk.call(find._native, 'get'), '貼付\u2003↵次')

    def test_find_multiline_selection_and_reopening_replacement_keep_value(self):
        text = '選択\tした\n範囲'
        self.a.editor.insert('1.0', text)
        self.a.editor.tag_add('sel', '1.0', 'end-1c')
        find, replace = self._open_find_fixture()
        self.assertEqual(find.get(), text)
        self.a.open_find_dialog(True)
        self.assertEqual(replace.get(), text)
        self.a._close_find_dialog()
        self.a._find_last_text = text
        self.a.editor.tag_remove('sel', '1.0', 'end')
        find, _ = self._open_find_fixture()
        self.assertEqual(find.get(), text)

    def test_find_and_replace_real_tab_newline_and_literal_marks(self):
        find, replace = self._open_find_fixture(True)
        before = '先頭😀\t\n次\n末尾↵\u2003'
        for regex in (False, True):
            with self.subTest(regex=regex):
                self.a.editor.delete('1.0', 'end')
                self.a.editor.insert('1.0', before)
                self.a.editor.edit_reset()
                self.a._find_regex.set(regex)
                self.a._find_query.set('\t\n')
                self.a._find_replacement.set('\n\t')
                self.a._do_find()
                self.assertEqual(self.a.editor.get('sel.first', 'sel.last'), '\t\n')
                self.a._do_replace_all()
                self.assertEqual(self.text(), '先頭😀\n\t次\n末尾↵\u2003')
                self.a.editor.edit_undo()
                self.assertEqual(self.text(), before)
        self.a._find_query.set('↵\u2003')
        self.a._find_replacement.set('記号')
        self.a._do_replace_all()
        self.assertEqual(self.text(), '先頭😀\t\n次\n末尾記号')

    def test_newline_search_and_single_replace_skip_padding(self):
        self._open_find_fixture(True)
        text='\n \t\n先頭😀\n\n末尾\n\t\n\n'
        self.a.editor.insert('1.0',text)
        self.a._find_query.set('\n');self.a._find_replacement.set('|')
        self.a.editor.mark_set('insert','1.0')
        self.a._do_find()
        self.assertEqual(self.a._index_to_offset('sel.first'),text.index('\n',text.index('先頭')))
        self.a._do_find(True)
        self.assertEqual(self.a._index_to_offset('sel.first'),text.index('末尾')-1)
        # A manually selected leading newline must only find the next match.
        self.a._select_span((0,1))
        self.a._do_replace()
        self.assertEqual(self.text(),text)
        self.a._do_replace()
        self.assertEqual(self.text(),text.replace('😀\n','😀|',1))
        self.a._close_find_dialog()
        self.a.editor.mark_set('insert','1.0')
        self.a._find_next_shortcut()
        self.assertEqual(self.a.editor.get('sel.first','sel.last'),'\n')
        self.assertEqual(self.a._index_to_offset('sel.first'),self.text().index('末尾')-1)

    def test_newline_replace_all_and_select_all_share_content_lines(self):
        self._open_find_fixture(True)
        text='\n \t\n 先頭😀 \t\n\n末尾 \t\n \t\n\n'
        self.a.editor.insert('1.0',text);self.a.editor.edit_reset()
        self.a._on_select_all()
        self.assertEqual(self.a.editor.get('sel.first','sel.last'),' 先頭😀 \t\n\n末尾 \t')
        self.a._find_query.set('\n');self.a._find_replacement.set('|')
        self.a._do_replace_all()
        self.assertEqual(self.text(),'\n \t\n 先頭😀 \t||末尾 \t\n \t\n\n')
        self.assertEqual(self.a._find_status.cget('text'),'2 件置換しました')
        self.a.editor.edit_undo()
        self.assertEqual(self.text(),text)
        self.a.editor.delete('1.0','end');self.a.editor.insert('1.0',' \t\n\n')
        self.a._on_select_all()
        self.assertEqual(self.a.editor.get('sel.first','sel.last'),' \t\n\n')
        self.a._do_replace_all()
        self.assertEqual(self.text(),' \t\n\n')

    def test_marked_entry_errors_disabled_state_and_cleanup(self):
        find, _ = self._open_find_fixture()
        self.a._find_query.set('前\t\n後')
        with self.assertRaises(tk.TclError):
            find.cget('unsupported_option')
        find.configure(state='readonly')
        find.insert(0, '無効');find.delete(0, 'end')
        self.assertEqual(find.get(), '前\t\n後')
        find.configure(state='normal')
        errors=[]
        self.root.report_callback_exception=lambda *args: errors.append(args)
        find.after_idle(lambda: None)
        self.a._close_find_dialog()
        self.root.update()
        self.assertFalse(errors)

    def test_marked_entry_tab_rectangles_follow_selection_and_colors(self):
        from marked_entry import MarkedEntry
        self.root.attributes('-alpha', 0)
        value = tk.StringVar(self.root, '前\t\t後\n続き')
        colors = ['#f3f0e8', '#ece8de']
        entry = MarkedEntry(self.root, textvariable=value, tab_colors=lambda: colors,
                            width=25, font=('Yu Gothic UI', 10))
        entry.pack();self.root.deiconify();self.root.update()
        visible=lambda: [m for m in entry._marks if m.winfo_manager()]
        self.assertEqual(len(visible()), 2)
        self.assertEqual([m.cget('bg') for m in visible()], colors)
        self.assertTrue(all(m.winfo_width() > 2 for m in visible()))
        entry.selection_range(1, 2);entry._schedule_paint();self.root.update()
        self.assertEqual(len(visible()), 1)
        entry.selection_clear();colors[:]=['#2b3036', '#333a41']
        entry.configure(font=('Yu Gothic UI', 12));self.root.update()
        self.assertEqual([m.cget('bg') for m in visible()], colors)
        self.assertEqual(entry.get(), value.get())



class HalfwidthAutofixTkTests(unittest.TestCase):
    def setUp(self):
        import morphology
        if not morphology.HAS_JANOME:self.skipTest('native dictionary')
        from tests_analysis_async import initial
        from analysis_worker import Runtime,snapshot
        import analysis_async,analysis_work_app
        self.root=tk.Tk();self.root.withdraw()
        a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);a.root=self.root
        a.editor=tk.Text(self.root,undo=True);a.result_view=tk.Text(self.root)
        state=initial();a.__dict__.update(vars(state))
        a.settings=dict(a.settings,layout='unified',unified_autofix=True,input_method_auto=False)
        a._typed_shadow=[''];a.editor.insert('1.0','fythw@');a._mark_typed_from_shadow()
        runtime=Runtime();runtime.set_state(snapshot(a))
        value=runtime.execute(dict(kind='line',line='fythw@',input_method='kana',context=[]))
        self.assertEqual(value['result']['corrected'],'半角で')
        a.line_results=[value['result']];analysis_async._unit_values(a,value['result'],value)
        a._known_kana_word=lambda text:False;a._units_are_pending=lambda:False
        a._mark_dirty=Mock();a._schedule_whitespace_paint=Mock();a._sz_check_shrink=Mock()
        a._design33_watch=Mock();a._maybe_start_pick_from_equals=Mock();a._redraw_gutter_now=Mock()
        a._analyze=Mock();a._analyze_job=None;a._after_id=None;a._analyze_pos=1;a._analyze_todo=[0]
        a._analyze_text='fythw@';a._analyze_dependencies=analysis_async.state_key(a)
        a._analyze_work=analysis_work_app.token(a)
        a._refresh_after_analysis=lambda learn=False:a._apply_unified_autofix()
        a._ime_comp='fythw@';a._ime_comp_reading='';a._ime_first_kana='';a._ime_last_result=''
        a._remember_ime_pair=Mock()

    def tearDown(self):
        if getattr(self,'root',None) is not None:
            self.root.destroy()
            from tests_tk_keys import release_tk_fixture
            release_tk_fixture(self,'a','root')

    def pump(self):
        self.root.after(380,self.root.quit);self.root.mainloop()

    def test_finished_analysis_is_applied_after_ime_commit_without_reanalysis(self):
        import ime_watch
        a=self.a
        with patch.object(ime_watch,'composition_active',return_value=True):
            self.assertFalse(a._apply_unified_autofix())
        with patch.object(ime_watch,'composition_active',return_value=False), \
             patch.object(ime_watch,'read_composition',return_value={}):
            a._ime_reading_tick();self.pump()
        self.assertEqual(a.editor.get('1.0','1.end'),'半角で')
        a._analyze.assert_not_called()
        a.editor.edit_undo();self.assertEqual(a.editor.get('1.0','1.end'),'fythw@')

    def test_commit_schedules_missing_analysis_without_key_release(self):
        import ime_watch
        a=self.a;a._analyze_text=''
        with patch.object(ime_watch,'composition_active',return_value=False), \
             patch.object(ime_watch,'read_composition',return_value={}):
            a._ime_reading_tick();self.pump()
        a._analyze.assert_called_once()

    def test_cached_autofix_waits_for_commit_and_keeps_untyped_text(self):
        import ime_watch
        a=self.a;a.editor.tag_remove(a.TYPED_TAG,'1.0','end')
        with patch.object(ime_watch,'composition_active',return_value=True):
            self.assertFalse(a._apply_unified_autofix())
            a._analyze_if_changed()
            self.assertEqual(a.editor.get('1.0','1.end'),'fythw@')
        with patch.object(ime_watch,'composition_active',return_value=False), \
             patch.object(ime_watch,'read_composition',return_value={}):
            a._ime_reading_tick();self.pump()
        self.assertEqual(a.editor.get('1.0','1.end'),'fythw@')
        a._analyze.assert_not_called()

    def test_waiting_result_recovers_when_composition_text_was_not_observed(self):
        import ime_watch
        a=self.a;a._ime_comp=''
        with patch.object(ime_watch,'composition_active',return_value=True):
            self.assertFalse(a._apply_unified_autofix())
        with patch.object(ime_watch,'composition_active',return_value=False):
            a._ime_reading_tick();self.pump()
        self.assertEqual(a.editor.get('1.0','1.end'),'半角で')
        a._analyze.assert_not_called()

    def test_layout_reset_discards_waiting_projection_without_repeated_refresh(self):
        import ime_watch
        a=self.a
        with patch.object(ime_watch,'composition_active',return_value=True):
            self.assertFalse(a._apply_unified_autofix())
        a.settings['layout']='split';a.restore_autofix_originals()
        self.assertFalse(a._unified_autofix_waiting_ime)
        a._refresh_after_analysis=Mock();a._analyze_if_changed()
        a._refresh_after_analysis.assert_not_called()

    def test_ime_ascii_handlers_schedule_without_key_release(self):
        a=self.a;a._on_change=Mock()
        event=types.SimpleNamespace(widget=a.editor,keysym='Delete',char='.',keycode=46)
        self.assertEqual(a._on_ime_ascii_key(event),'break')
        a._on_change.assert_called_once()
        a._on_change.reset_mock()
        event=types.SimpleNamespace(widget=a.editor,keysym='F1',char='p',keycode=112)
        self.assertEqual(a._ime_fkey_insert(event),'break')
        a._on_change.assert_called_once()


if __name__=='__main__':unittest.main()


class CrossTabQuoteTests(unittest.TestCase):
    def setUp(self):
        from session import SessionStore, new_tab
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root, undo=True)
        a.result_view = tk.Text(self.root)
        a.session = SessionStore()
        a.session.tabs = [new_tab(text='前😀置換対象後'), new_tab(text='引用する語')]
        a.current_file = None; a._dirty = False; a.bookmarks = set()
        a._pick_mode = None; a._last_equals_pos = None
        a.status = Mock(); a.editor_header = Mock(); a.result_header = Mock()
        a.pick_mode_btn = Mock(); a._layout_is_unified = lambda: False
        a._close_dropdown = Mock(); a._set_pane_cursor = Mock()
        a._update_header_visibility = Mock(); a._on_change = Mock()
        a._schedule_session_save = Mock()
        a._on_quick_change = Mock()
        a.editor_source_text = lambda: a.editor.get('1.0', 'end-1c')
        def load(initial=False):
            # Real Tk delete/insert reproduces the disappearing target marks.
            tab = a.session.current()
            a.editor.delete('1.0', 'end')
            a.editor.insert('1.0', tab['text'])
            a.editor.mark_set('insert', app._stable_text_index(a.editor, tab['cursor']))
            a._restore_pick_origin_marks()
        a._load_active_tab = load
        load()

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root')

    def test_pick_other_tab_replaces_original_selection_and_returns(self):
        a = self.a; w = a.editor
        w.tag_add('sel', '1.0+2c', '1.0+6c')
        a._start_pick_mode(False)
        origin = a.session.current()
        a._switch_tab(1)
        self.assertEqual(a._pick_mode, 'f1')
        self.assertEqual(w.get('1.0', 'end-1c'), '引用する語')
        a._pick_lines(w, 1, 1)
        self.assertIs(a.session.current(), origin)
        self.assertEqual(w.get('1.0', 'end-1c'), '前😀引用する語後')
        self.assertEqual(a.session.tabs[1]['text'], '引用する語')
        self.assertIsNone(a._pick_mode)

    def test_quote_replaces_mapped_selection_after_unified_display_changes_length(self):
        a = self.a; w = a.editor
        a.session.tabs[0]['text'] = '前😀しりょう後'
        a.editor_source_text = lambda: a.session.current()['text']
        def load(initial=False):
            w.delete('1.0', 'end')
            w.insert('1.0', a.session.current()['text'].replace('しりょう', '資料'))
            a._restore_pick_origin_marks()
        a._load_active_tab = load
        load()
        w.tag_add('sel', '1.0+2c', '1.0+4c')
        a._start_pick_mode(False)
        a._switch_tab(1)
        a._pick_insert('引用')
        self.assertEqual(w.get('1.0', 'end-1c'), '前😀引用後')

    def test_quote_is_one_undo_and_redo_after_return_to_origin(self):
        from analysis_work import observe_text
        a = self.a; w = a.editor
        observe_text(w)
        w.tag_add('sel', '1.0+2c', '1.0+6c')
        a._start_pick_mode(False)
        a._switch_tab(1)
        a._pick_insert('引用😀')
        self.assertEqual(w.get('1.0', 'end-1c'), '前😀引用😀後')
        w.edit_undo()
        self.assertEqual(w.get('1.0', 'end-1c'), '前😀置換対象後')
        w.edit_redo()
        self.assertEqual(w.get('1.0', 'end-1c'), '前😀引用😀後')

    def test_closed_quick_target_does_not_insert_into_main_editor(self):
        a = self.a
        a._quick_text = tk.Text(self.root)
        a._quick_text.insert('1.0', '簡易入力')
        a._start_pick_mode(False, target='quick')
        a._switch_tab(1)
        a._quick_text.destroy()
        a._quick_text = None
        a._pick_insert('引用')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '前😀置換対象後')
        self.assertIsNone(a._pick_mode)
        a._on_change.assert_not_called()

    def test_return_to_original_identity_after_tab_reorder(self):
        a = self.a; w = a.editor
        w.mark_set('insert', '1.0+2c')
        a._start_pick_mode(False)
        origin = a.session.current()
        a._switch_tab(1)
        a.session.tabs.reverse(); a.session.active = 0
        a._pick_insert('語')
        self.assertIs(a.session.current(), origin)
        self.assertEqual(a.session.active, 1)
        self.assertEqual(w.get('1.0', 'end-1c'), '前😀語置換対象後')

    def _start_equals(self):
        a = self.a; w = a.editor
        w.delete('1.0', 'end'); w.insert('1.0', '前😀=後')
        w.mark_set('insert', '1.0+3c')
        w.mark_set(a._PICK_EQUALS_START, 'insert-1c')
        w.mark_set(a._PICK_EQUALS_END, 'insert')
        a._start_pick_mode(True)

    def test_equals_quote_survives_tab_shortcut_and_replaces_only_equals(self):
        a = self.a
        self._start_equals()
        for key in ('Tab', 'ISO_Left_Tab', 'Next', 'Prior'):
            result = a._on_pick_mode_keypress(types.SimpleNamespace(
                widget=a.editor, keysym=key, char='', state=4, keycode=34))
            self.assertIsNone(result)
            self.assertEqual(a._pick_mode, 'equals')
        a._switch_tab(1)
        a._pick_insert('引用')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '前😀引用後')
        self.assertEqual(a.session.active, 0)

    def test_cancel_in_other_tab_keeps_equals_and_does_not_restart_on_return(self):
        a = self.a
        self._start_equals()
        a._switch_tab(1)
        a._on_pick_mode_keypress(types.SimpleNamespace(keysym='Escape'))
        self.assertIsNone(a._pick_mode)
        self.assertEqual(a.session.active, 1)
        self.assertEqual(a.session.tabs[0]['text'], '前😀=後')
        a._switch_tab(0)
        a._maybe_start_pick_from_equals()
        self.assertIsNone(a._pick_mode)
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '前😀=後')

    def test_closed_original_never_inserts_into_another_tab(self):
        a = self.a
        a._start_pick_mode(False)
        a._switch_tab(1)
        a.session.tabs.pop(0); a.session.active = 0
        a._pick_insert('勝手に追加しない')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '引用する語')
        self.assertIsNone(a._pick_mode)

    def test_quick_destination_survives_main_tab_switch_and_returns(self):
        a = self.a
        a._quick_text = tk.Text(self.root)
        a._quick_text.insert('1.0', '簡易:')
        a._quick_text.mark_set('insert', 'end-1c')
        a._start_pick_mode(False, target='quick')
        a._switch_tab(1)
        a._pick_insert('引用')
        self.assertEqual(a._quick_text.get('1.0', 'end-1c'), '簡易:引用')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '前😀置換対象後')
        self.assertEqual(a.session.active, 0)


    def test_keyboard_selection_enter_returns_to_origin_without_newline(self):
        a=self.a;w=a.editor
        w.tag_add('sel','1.0+2c','1.0+6c')
        a._start_pick_mode(False);a._switch_tab(1)
        w.tag_add('sel','1.0','1.0+3c')
        event=types.SimpleNamespace(widget=w,keysym='Return',char='\r',state=0)
        self.assertEqual(a._on_pick_mode_keypress(event),'break')
        self.assertEqual(a.session.active,0)
        self.assertEqual(w.get('1.0','end-1c'),'前😀引用す後')
        self.assertIsNone(a._pick_mode)

    def test_keyboard_pick_reads_disabled_result_and_quick_selection(self):
        a=self.a;w=a.editor
        for source in (a.result_view,tk.Text(self.root)):
            if source is not a.result_view:a._quick_text=source
            w.mark_set('insert','1.0+2c');a._start_pick_mode(False)
            source.config(state='normal');source.insert('1.0','引用😀\n次')
            source.tag_add('sel','1.0','end-1c')
            if source is a.result_view:source.config(state='disabled')
            event=types.SimpleNamespace(widget=source,keysym='KP_Enter',char='',state=0)
            self.assertEqual(a._on_pick_mode_keypress(event),'break')
            self.assertIn('引用😀\n次',w.get('1.0','end-1c'))
            self.assertIsNone(a._pick_mode)

    def test_keyboard_equals_selection_survives_navigation_and_replaces_equals(self):
        a=self.a;self._start_equals();a._switch_tab(1)
        for key in ('Left','Right','Up','Down','Home','End','Prior','Next'):
            event=types.SimpleNamespace(widget=a.editor,keysym=key,char='',state=1)
            self.assertIsNone(a._on_pick_mode_keypress(event));self.assertEqual(a._pick_mode,'equals')
        a.editor.tag_add('sel','1.0','1.0+2c')
        self.assertEqual(a._on_pick_mode_keypress(types.SimpleNamespace(
            widget=a.editor,keysym='Return',char='\r',state=0)),'break')
        self.assertEqual(a.editor.get('1.0','end-1c'),'前😀引用後')

    def test_empty_selection_and_ime_confirm_do_not_quote(self):
        a=self.a;a._start_pick_mode(False);before=a.editor.get('1.0','end-1c')
        event=types.SimpleNamespace(widget=a.editor,keysym='Return',char='\r',state=0)
        self.assertEqual(a._on_pick_mode_keypress(event),'break')
        self.assertEqual(a.editor.get('1.0','end-1c'),before);self.assertEqual(a._pick_mode,'f1')
        a.editor.tag_add('sel','1.0','1.0+2c')
        from unittest.mock import patch
        with patch('ime_watch.composition_active',return_value=True):
            self.assertIsNone(a._on_pick_mode_keypress(event))
        self.assertEqual(a._pick_mode,'f1')
        event.char='漢'
        self.assertIsNone(a._on_pick_mode_keypress(event))
        self.assertEqual(a.editor.get('1.0','end-1c'),before)

    def test_quote_cursor_stays_xterm_through_hover_leave_and_scroll_restore(self):
        a=self.a;a._set_pane_cursor=app.CorrectNoteApp._set_pane_cursor.__get__(a)
        a._start_pick_mode(False)
        for pane in (a.editor,a.result_view):
            self.assertEqual(pane.cget('cursor'),'xterm')
            a._set_pane_cursor(pane,'hand2');self.assertEqual(pane.cget('cursor'),'xterm')
            a._set_pane_cursor(pane,'arrow');self.assertEqual(pane.cget('cursor'),'xterm')
        a._scroll_cursor=[(a.result_view,'arrow')]
        a.result_view.config(cursor='none');a._scroll_cursor_restore()
        self.assertEqual(a.result_view.cget('cursor'),'xterm')
        a._end_pick_mode()
        self.assertEqual(a.editor.cget('cursor'),'xterm')
        self.assertEqual(a.result_view.cget('cursor'),'arrow')
