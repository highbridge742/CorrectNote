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
        # App startup installs this same proxy, including the legacy Tk
        # UTF-16 undo fix. A raw Text would test a different editing path.
        from analysis_work import observe_text
        observe_text(self.a.editor)
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
        w.tag_remove('sel', '1.0', 'end')
        w.mark_set('insert', '3.0')
        deliver_key(w, '<Shift-space>', 'space', 32, state=1)
        self.assertFalse(w.tag_ranges('sel'))
        deliver_key(w, '<Shift-Down>', 'Down', 40, state=1)
        self.assertEqual(w.get('sel.first', 'sel.last'), '\n末尾')
        w.tag_remove('sel', '1.0', 'end')
        w.mark_set('insert', '1.0')
        self.assertIsNone(a._on_extend_line_selection(types.SimpleNamespace(widget=w), -1))
        self.assertIsNone(w._line_selection)

    def test_shift_space_expands_existing_multiline_selection_in_both_directions(self):
        from tests_tk_keys import deliver_key
        a = self.a; a.status = Mock()
        for w in (a.editor, a.result_view):
            w.insert('1.0', '先頭行\n前😀長い行\n中の行\n末尾の行\n次の行')
            a._install_line_selection_keys(w)
            if w is a.result_view: w.config(state='disabled')
            for upward in (False, True):
                w.tag_remove('sel', '1.0', 'end')
                w.tag_add('sel', '2.0+2c', '4.2')
                w.mark_set('insert', '2.0+2c' if upward else '4.2')
                deliver_key(w, '<Shift-space>', 'space', 32, state=1)
                self.assertEqual(w.get('sel.first','sel.last'), '前😀長い行\n中の行\n末尾の行')
                self.assertEqual(w.index('insert'), w.index('2.0' if upward else '4.end'))
                # Keep the active side when extending or shrinking the range.
                step = -1 if upward else 1
                a._on_extend_line_selection(types.SimpleNamespace(widget=w), step)
                expected = ('1.0','4.end') if upward else ('2.0','5.end')
                self.assertEqual(tuple(str(i) for i in w.tag_ranges('sel')),tuple(w.index(i) for i in expected))
                a._on_extend_line_selection(types.SimpleNamespace(widget=w), -step)
                self.assertEqual(w.get('sel.first','sel.last'), '前😀長い行\n中の行\n末尾の行')

    def test_shift_space_selection_ending_at_next_line_start_excludes_that_line(self):
        a=self.a; a.status=Mock();w=a.editor
        w.insert('1.0','最初\n途中\n末尾')
        w.tag_add('sel','1.1','3.0');w.mark_set('insert','3.0')
        a._on_select_line_text(types.SimpleNamespace(widget=w))
        self.assertEqual(w.get('sel.first','sel.last'),'最初\n途中')
        self.assertEqual(w.index('insert'),w.index('2.end'))

    def test_search_replacement_is_one_undo_and_redo(self):
        w=self.a.editor;before='最初の文😀\n次の文\n'
        w.insert('1.0',before);w.edit_reset()
        self.a._replace_editor_text('最初の文😀\n置換した文\n')
        w.event_generate('<<Undo>>');self.assertEqual(self.text(),before)
        w.event_generate('<<Redo>>');self.assertEqual(self.text(),'最初の文😀\n置換した文\n')
    def _tracked_search_fixture(self):
        import analysis_work_app as work
        from session import SessionStore,new_tab
        a=self.a;w=a.editor
        lines=['同じ内容の行です。']*20
        lines[1]='対象😀';lines[7]='確認';lines[9]='対象😀'
        source='\n'.join(lines);w.insert('1.0',source);w.edit_reset()
        a.session=SessionStore();a.session.tabs=[new_tab(text=source)]
        a.bookmarks={3,8,15};a.editor_gutter=Mock();a.result_gutter=Mock()
        a._schedule_session_save=Mock();a._prepare_pick_calculation_edit=None
        a.editor_source_text=lambda:w.get('1.0','end-1c')
        work.select_document(a,source);work.install(a)
        at=source.index('確認');self.assertTrue(a._input_document.remember(at,at+2,'確認','かくにん'))
        self._open_find_fixture(True)
        return source

    def test_search_changes_only_matches_and_preserves_middle_bookmark_and_ime_reading(self):
        before=self._tracked_search_fixture();a=self.a;w=a.editor
        a._find_query.set('対象');a._find_replacement.set('置換\n後')
        a._do_replace_all();expected=before.replace('対象','置換\n後')
        self.assertEqual(self.text(),expected);self.assertEqual(a.bookmarks,{4,9,17})
        occurrences=a._input_document.occurrences
        self.assertEqual(len(occurrences),1)
        self.assertEqual((occurrences[0].start,occurrences[0].surface,occurrences[0].reading),
                         (expected.index('確認'),'確認','かくにん'))
        a._autofix_reset.assert_not_called();a._reset_typed_marks.assert_not_called()
        self.assertEqual(a._typed_shadow,expected.split('\n'))
        w.edit_undo();self.assertEqual(self.text(),before);self.assertEqual(a.bookmarks,{3,8,15})
        w.edit_redo();self.assertEqual(self.text(),expected);self.assertEqual(a.bookmarks,{4,9,17})

    def test_single_and_empty_regex_replacements_preserve_other_rows(self):
        before=self._tracked_search_fixture();a=self.a
        a._find_query.set('対象');a._find_replacement.set('変更')
        at=before.rindex('対象');a._select_span((at,at+2));a._do_replace()
        expected=before[:at]+'変更'+before[at+2:]
        self.assertEqual(self.text(),expected);self.assertEqual(a.bookmarks,{3,8,15})
        self.assertEqual(a._input_document.occurrences[0].surface,'確認')
        generation=a._input_document.generation
        a._find_query.set('変更');a._find_replacement.set('変更');a._do_replace_all()
        self.assertEqual(a._input_document.generation,generation)
        a._find_regex.set(True);a._find_query.set('(?=確認)');a._find_replacement.set('追加\n')
        a._do_replace_all()  # Existing search deliberately skips empty matches.
        self.assertEqual(self.text(),expected);self.assertEqual(a.bookmarks,{3,8,15})
        a._find_query.set('(変更)');a._find_replacement.set('追加\n\\1')
        a._do_replace_all();expected=expected.replace('変更','追加\n変更')
        self.assertEqual(self.text(),expected);self.assertEqual(a.bookmarks,{3,8,16})
        self.assertEqual(a._input_document.occurrences[0].start,expected.index('確認'))
        a._find_query.set('(同じ)');a._find_replacement.set('\\2')
        a._do_replace_all();self.assertEqual(self.text(),expected)
        self.assertIn('正しくありません',a._find_status.cget('text'))

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
        a._analyze = Mock()
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

    def test_quote_calculator_decimal_parser(self):
        from quote_calculator import calculate
        for expression, expected in (
                ('1+2*3','7'), ('（１２＋３）×２','30'), ('0.1+0.2','0.3'),
                ('10/4','2.5'), ('1-3','-2'), ('-.5*2','-1'),
                ('12÷3+２','6'), ('-0.00','0'), ('４２','42'), ('1-(2-3)','2'),
                ('　１．５ ＋ ２　','3.5'), ('８−３','5')):
            with self.subTest(expression=expression):self.assertEqual(calculate(expression),expected)
        for expression in ('', '1+', '1/0', '2**8', '1=2', '__import__("os")',
                           '1 2', '1\n+2', '（1+2', '1e5', 'x+2', '2²', '2³+1', '①+②', '½+1'):
            with self.subTest(expression=expression):self.assertIsNone(calculate(expression))

    def _type_quote_expression(self, widget, expression):
        # Invoke the real Text class binding, including selection replacement.
        from tests_tk_keys import deliver_key
        widget.bind('<KeyPress>', self.a._on_pick_mode_keypress)
        for char in expression:
            deliver_key(widget, '<KeyPress>', char, 0, char=char)

    def _enter_quote_expression(self, widget, key='Return'):
        with patch('ime_watch.composition_active',return_value=False):
            return self.a._on_pick_mode_keypress(types.SimpleNamespace(
                widget=widget, keysym=key, char='\r', state=0))

    def _calculated_text(self, quick=False):
        from quote_calculator import apply_to_result
        a=self.a
        doc=a._quick_calculation_document if quick else a._input_document
        return apply_to_result(dict(original=doc.text,corrected=doc.text),doc.calculations)['corrected']

    def test_quote_append_recalculates_the_existing_source_expression(self):
        import analysis_work_app as work
        a=self.a;w=a.editor
        work.select_document(a,a.editor_source_text());work.install(a)
        w.mark_set('insert','1.0+2c')
        a._on_editor_ctrl_c();self._type_quote_expression(w,'1-2')
        self._enter_quote_expression(w)
        self.assertEqual(self._calculated_text(),'前😀-1置換対象後')
        for suffix,answer in (('+3','2'),('*4','11'),('/2','5')):
            a._on_editor_ctrl_c();self._type_quote_expression(w,suffix)
            self._enter_quote_expression(w)
            self.assertIsNone(a._pick_mode)
            self.assertEqual(self._calculated_text(),'前😀'+answer+'置換対象後')
            self.assertEqual(len(a._input_document.calculations),1)
        self.assertEqual(a._input_document.calculations[0].surface,'1-2+3*4/2')

    def test_quote_append_does_not_join_an_unconfirmed_or_separated_prefix(self):
        import analysis_work_app as work
        a=self.a;w=a.editor
        w.replace('1.0','end-1c','1-2 ')
        work.select_document(a,a.editor_source_text());work.install(a)
        w.mark_set('insert','end-1c')
        a._on_editor_ctrl_c();self._type_quote_expression(w,'+3')
        self._enter_quote_expression(w)
        self.assertEqual(self._calculated_text(),'1-2 3')
        w.insert('insert','　')
        a._on_editor_ctrl_c();self._type_quote_expression(w,'+4')
        self._enter_quote_expression(w)
        self.assertEqual(self._calculated_text(),'1-2 3　4')

    def test_copy_quote_keeps_source_and_undo_invalidates_calculation(self):
        a=self.a;w=a.editor
        import analysis_work_app as work
        work.select_document(a,a.editor_source_text());work.install(a)
        w.mark_set('insert','1.0+2c');w.edit_reset()
        self.assertEqual(a._on_editor_ctrl_c(),'break')
        self._type_quote_expression(w,'12+3*4')
        before=w.get('1.0','end-1c')
        self.assertEqual(self._enter_quote_expression(w),'break')
        self.assertEqual(w.get('1.0','end-1c'),before)
        self.assertEqual(self._calculated_text(),'前😀24置換対象後')
        self.assertIsNone(a._pick_mode)
        self.assertNotIn(a._PICK_CALC_END,w.mark_names())
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'前😀置換対象後')
        self.assertFalse(a._input_document.calculations)
        w.edit_redo();self.assertEqual(w.get('1.0','end-1c'),before)
        self.assertFalse(a._input_document.calculations)

    def test_button_quote_replaces_original_selection_with_halfwidth_result(self):
        a=self.a;w=a.editor
        w.tag_add('sel','1.0+2c','1.0+6c');w.mark_set('insert','1.0+6c')
        a.toggle_pick_mode(calculate=True)
        self._type_quote_expression(w,'１２÷４')
        self._enter_quote_expression(w,'KP_Enter')
        self.assertEqual(w.get('1.0','end-1c'),'前😀１２÷４後')
        self.assertEqual(self._calculated_text(),'前😀3後')
        self.assertIsNone(a._pick_mode)

    def test_quick_copy_quote_calculates_without_changing_editor(self):
        a=self.a;w=a._quick_text=tk.Text(self.root,undo=True)
        w.insert('1.0','前後');w.mark_set('insert','1.1')
        self.assertEqual(a._on_quick_ctrl_c(),'break')
        self._type_quote_expression(w,'(2+3)*4')
        self._enter_quote_expression(w)
        self.assertEqual(w.get('1.0','end-1c'),'前(2+3)*4後')
        self.assertEqual(self._calculated_text(quick=True),'前20後')
        self.assertEqual(a.editor.get('1.0','end-1c'),'前😀置換対象後')
        self.assertIsNone(a._pick_mode);a._on_quick_change.assert_called_once()

    def test_equals_and_f1_quote_calculate_explicit_arithmetic(self):
        import analysis_work_app as work
        a=self.a;w=a.editor
        for via_equals in (True,False):
            w.replace('1.0','end-1c','前後');w.mark_set('insert','1.1')
            work.select_document(a,a.editor_source_text());work.install(a)
            if via_equals:a._on_equal_key(types.SimpleNamespace(widget=w,char='=',keysym='equal',state=0))
            else:a.toggle_pick_mode()
            self._type_quote_expression(w,'1+2');self._enter_quote_expression(w)
            self.assertIsNone(a._pick_mode);self.assertEqual(self._calculated_text(),'前3後')

    def test_calculation_invalid_expression_and_ime_enter_keep_text_and_mode(self):
        a=self.a;w=a.editor;w.mark_set('insert','1.end')
        a._on_editor_ctrl_c();self._type_quote_expression(w,'12/')
        before=w.get('1.0','end-1c');self._enter_quote_expression(w)
        self.assertEqual(w.get('1.0','end-1c'),before);self.assertEqual(a._pick_mode,'f1')
        self._type_quote_expression(w,'3')
        event=types.SimpleNamespace(widget=w,keysym='Return',char='\r',state=0)
        with patch('ime_watch.composition_active',return_value=True):
            self.assertIsNone(a._on_pick_mode_keypress(event))
        self.assertTrue(w.get('1.0','end-1c').endswith('12/3'))
        self._enter_quote_expression(w)
        self.assertTrue(w.get('1.0','end-1c').endswith('12/3'))
        self.assertTrue(self._calculated_text().endswith('4'));self.assertIsNone(a._pick_mode)

    def test_unsupported_power_keeps_the_original_and_quote_mode(self):
        a=self.a;w=a.editor;w.mark_set('insert','1.end')
        a._on_editor_ctrl_c();self._type_quote_expression(w,'2²')
        before=w.get('1.0','end-1c');self._enter_quote_expression(w)
        self.assertEqual(w.get('1.0','end-1c'),before)
        self.assertEqual(a._pick_mode,'f1')
        self.assertFalse(getattr(getattr(a,'_input_document',None),'calculations',()))

    def test_quote_marks_preserve_both_edges_of_a_changed_number(self):
        a=self.a;w=a.editor;before='前😀40後';after='前😀四十後'
        w.replace('1.0','end-1c',before);w.mark_set('insert','1.0+2c')
        a._on_editor_ctrl_c();w.mark_set(a._PICK_CALC_END,'1.0+4c')
        mapped=a._pick_marks_after_row_change(w,1,before,after)
        w.replace('1.0','1.end',after)
        for mark,index in mapped.items():w.mark_set(mark,index)
        self.assertEqual(w.get(a._PICK_MARK,a._PICK_CALC_END),'四十')
        a.editor_source_text=lambda:before
        a._capture_pick_origin_marks(before)
        self.assertEqual(a._pick_tab_marks[a._PICK_MARK],(1,2))
        self.assertEqual(a._pick_tab_marks[a._PICK_CALC_END],(1,4))
        w.mark_set(a._PICK_MARK,'1.0');w.mark_set(a._PICK_CALC_END,'1.0')
        a._restore_pick_origin_marks()
        self.assertEqual(w.get(a._PICK_MARK,a._PICK_CALC_END),'四十')

    def test_calculation_range_survives_tab_return_and_excludes_other_tab(self):
        a=self.a;w=a.editor;w.mark_set('insert','1.0+2c')
        a._on_editor_ctrl_c();self._type_quote_expression(w,'5+6')
        a._switch_tab(1);self._type_quote_expression(w,'1+2')
        other=w.get('1.0','end-1c');self._enter_quote_expression(w)
        self.assertEqual(w.get('1.0','end-1c'),other);self.assertEqual(a._pick_mode,'f1')
        a._switch_tab(0);w.mark_set('insert',a._PICK_CALC_END)
        self._enter_quote_expression(w)
        self.assertEqual(w.get('1.0','end-1c'),'前😀5+6置換対象後')
        self.assertEqual(self._calculated_text(),'前😀11置換対象後')

    def test_calculation_mode_still_quotes_selected_text(self):
        a=self.a;w=a.editor;w.mark_set('insert','1.0+2c')
        a._on_editor_ctrl_c();a._switch_tab(1)
        w.tag_add('sel','1.0','1.end');self._enter_quote_expression(w)
        self.assertEqual(w.get('1.0','end-1c'),'前😀引用する語置換対象後')
        self.assertIsNone(a._pick_mode)

    def test_calculation_document_moves_current_ranges_without_creating_readings(self):
        from analysis_work import Document
        doc=Document('test','前12+3後')
        self.assertTrue(doc.remember_calculation(1,5,'12+3','15'))
        self.assertFalse(doc.occurrences)
        doc.update('追加\n前12+3後')
        values=doc.row_calculations(1,'前12+3後')
        self.assertEqual((values[0].start,values[0].end,values[0].result),(1,5,'15'))
        self.assertFalse(doc.row_readings(1,'前12+3後'))
        doc.update('追加\n前12+4後')
        self.assertFalse(doc.calculations)
        self.assertFalse(doc.remember_calculation(4,8,'12+4','999'))

    def test_calculation_result_keeps_unrelated_corrections_and_anomaly_ranges(self):
        from analysis_work import Calculation
        from quote_calculator import apply_to_result
        result=dict(original='誤12+3悪',corrected='正しい12+3悪',
            details=[('誤','正しい','test')],original_spans=[(0,1)],spans=[(0,3)],
            odd_spans=[(1,5),(5,6)],unsure_spans=[(5,6)],odd_reasons=[(1,5,'numeric'),(5,6,'remaining')])
        got=apply_to_result(result,[Calculation(1,5,'12+3','15')])
        self.assertEqual(got['original'],'誤12+3悪')
        self.assertEqual(got['corrected'],'正しい15悪')
        self.assertEqual(got['original_spans'],[(0,1),(1,5)])
        self.assertEqual(got['spans'],[(0,3),(3,5)])
        self.assertEqual(got['odd_spans'],[(5,6)])
        self.assertEqual(got['odd_reasons'],[(5,6,'remaining')])
        self.assertEqual(result['corrected'],'正しい12+3悪')

    def test_calculation_keeps_external_anomaly_and_refreshes_diagnosis(self):
        from analysis_work import Calculation
        from quote_calculator import apply_to_result
        source='前12+3後'
        result=dict(original=source,corrected=source,odd_spans=[(0,6)],
            odd_reasons=[(0,6,'remaining')],diagnosis={'stale':True})
        got=apply_to_result(result,[Calculation(1,5,'12+3','15')],
            tokenize_fn=lambda text:[])
        self.assertEqual(got['corrected'],'前15後')
        self.assertEqual(got['odd_spans'],[(0,1),(5,6)])
        self.assertEqual(got['odd_reasons'],[(0,1,'remaining'),(5,6,'remaining')])
        self.assertEqual(got['diagnosis']['unreplaced_odd_spans'],[[0,1],[5,6]])
        self.assertEqual(got['diagnosis']['language_state'],'anomaly_unrepaired')
        self.assertNotIn('stale',got['diagnosis'])

    def test_calculation_obeys_correction_stop_without_confusing_purple_suppression(self):
        from analysis_work import Calculation
        from quote_calculator import apply_to_result
        from decisions import DecisionStore
        result=dict(original='12+3',corrected='12+3')
        entries=[Calculation(0,4,'12+3','15')];decisions=DecisionStore()
        decisions.leave_odd_alone('12+3')
        self.assertEqual(apply_to_result(result,entries,decisions)['corrected'],'15')
        decisions.reject('12+3','15')
        self.assertEqual(apply_to_result(result,entries,decisions)['corrected'],'12+3')

    def test_calculated_number_stays_halfwidth_without_changing_other_choice(self):
        from analysis_work import Calculation
        from quote_calculator import apply_to_result
        from units import build_line_units
        result=apply_to_result(dict(original='12+3と15',corrected='12+3と15'),
            [Calculation(0,4,'12+3','15')])
        choices=Mock();choices.originals.return_value=['15'];choices.lookup.return_value='十五'
        text,units=build_line_units(result,lambda text:[],choices)
        self.assertEqual(text,'15と十五')
        self.assertTrue(any(u.get('detail')==('12+3','15','計算') for u in units))

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

    def test_closing_quick_input_cancels_only_its_own_quote_mode(self):
        a=self.a
        for target in ('quick','editor'):
            with self.subTest(target=target):
                q=a._quick_text=tk.Text(self.root,undo=True)
                a._quick_win=types.SimpleNamespace(destroy=q.destroy)
                a._quick_after_id=None
                a._start_pick_mode(False,target=target,calculate=True)
                a._close_quick_capture()
                self.assertIsNone(a._quick_text)
                self.assertIsNone(a._quick_after_id)
                if target=='quick':self.assertIsNone(a._pick_mode)
                else:
                    self.assertEqual(a._pick_mode,'f1')
                    self.assertEqual(a._pick_target,'editor')
                    a._end_pick_mode()

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


class QuickSentEnterTests(EditingTkTests):
    def _bind_sent_keys(self):
        from tests_tk_keys import deliver_key
        a=self.a;w=a.editor;a._sz_note_key=Mock();a._pick_mode=None
        w.insert('1.0','送信した文字');a._mark_quick_sent('1.0',6)
        w.bind('<KeyPress>',a._on_editor_typed);w.bind('<KeyRelease>',a._on_editor_typed)
        w.bind('<Return>',a._on_editor_typed);w.bind('<KeyRelease-Return>',a._on_editor_typed)
        return deliver_key,w
    def test_plain_enter_keeps_color_and_selection_enter_resets_both_colors(self):
        deliver,w=self._bind_sent_keys();a=self.a
        w.mark_set('insert','1.end')
        with patch('ime_watch.composition_active',return_value=False):
            deliver(w,'<Return>','Return',13,char='\r')
            deliver(w,'<KeyRelease-Return>','Return',13,char='\r',event_type=3)
            self.assertTrue(w.tag_ranges('quick_sent_a'));self.assertEqual(self.text(),'送信した文字\n')
            a._mark_quick_sent('1.2',2);self.assertTrue(w.tag_ranges('quick_sent_b'))
            w.tag_add('sel','1.1','1.3');w.mark_set('insert','1.3')
            deliver(w,'<Return>','Return',13,char='\r')
        self.assertEqual(self.text(),'送\nた文字\n')
        self.assertFalse(w.tag_ranges('quick_sent_a'));self.assertFalse(w.tag_ranges('quick_sent_b'))
    def test_release_quote_and_ime_enter_do_not_clear_existing_color(self):
        deliver,w=self._bind_sent_keys();a=self.a
        w.tag_add('sel','1.0','1.2')
        with patch('ime_watch.composition_active',return_value=False):
            deliver(w,'<KeyRelease-Return>','Return',13,char='\r',event_type=3)
            self.assertTrue(w.tag_ranges('quick_sent_a'))
            a._pick_mode='f1';a._on_editor_typed(types.SimpleNamespace(widget=w,char='\r',state=0,type='2'))
            self.assertTrue(w.tag_ranges('quick_sent_a'));a._pick_mode=None
        with patch('ime_watch.composition_active',return_value=True):
            a._on_editor_typed(types.SimpleNamespace(widget=w,char='\r',state=0,type='2'))
        self.assertTrue(w.tag_ranges('quick_sent_a'))

    def test_selection_outside_insertion_point_does_not_clear_color(self):
        deliver,w=self._bind_sent_keys()
        w.tag_add('sel','1.1','1.3');w.mark_set('insert','1.end')
        with patch('ime_watch.composition_active',return_value=False):
            deliver(w,'<Return>','Return',13,char='\r')
        self.assertEqual(self.text(),'送信した文字\n')
        self.assertTrue(w.tag_ranges('quick_sent_a'))



class QuoteEnterCommandTests(CrossTabQuoteTests):
    def _command_source(self,text='引用先\n第二😀行\n第三行'):
        import analysis_work_app as work
        a=self.a;w=a.editor
        if a._pick_mode:a._end_pick_mode(keep_equals=True)
        w.replace('1.0','end-1c',text);w.tag_remove('sel','1.0','end');w.mark_set('insert','1.end')
        work.select_document(a,a.editor_source_text());work.install(a)
        return w
    def test_integer_and_fullwidth_integer_quote_the_line_and_remove_the_command(self):
        for token,value in (('2','第二😀行'),('２','第二😀行'),('03','第三行')):
            with self.subTest(token=token):
                w=self._command_source();self.a.toggle_pick_mode()
                self._type_quote_expression(w,token);self._enter_quote_expression(w)
                self.assertEqual(w.get('1.0','end-1c'),'引用先'+value+'\n第二😀行\n第三行')
                self.assertIsNone(self.a._pick_mode);self.assertFalse(self.a._input_document.calculations)
    def test_self_line_excludes_typed_token_and_blank_line_removes_only_the_command(self):
        for source,token,expected in (('引用先\n第二行','1','引用先引用先\n第二行'),
                                     ('引用先\n\n第三行','2','引用先\n\n第三行')):
            w=self._command_source(source);self.a.toggle_pick_mode()
            self._type_quote_expression(w,token);self._enter_quote_expression(w)
            self.assertEqual(w.get('1.0','end-1c'),expected);self.assertIsNone(self.a._pick_mode)
    def test_invalid_line_and_incomplete_arithmetic_keep_text_and_mode(self):
        for token in ('0','9999','1+','3.5'):
            w=self._command_source();self.a.toggle_pick_mode();self._type_quote_expression(w,token)
            before=w.get('1.0','end-1c');self._enter_quote_expression(w)
            self.assertEqual(w.get('1.0','end-1c'),before);self.assertIsNotNone(self.a._pick_mode)
            self.assertFalse(self.a._input_document.calculations)
    def test_f1_insert_equals_and_button_share_arithmetic(self):
        a=self.a
        for entry in ('f1','insert','equals','button'):
            with self.subTest(entry=entry):
                w=self._command_source();a.settings={'insert_quote_enabled':True}
                if entry=='equals':a._on_equal_key(types.SimpleNamespace(widget=w,char='=',keysym='equal',state=0))
                elif entry=='insert':a._on_insert_quote(types.SimpleNamespace(widget=w,char='',keysym='Insert',state=0))
                else:a.toggle_pick_mode(calculate=True) if entry=='button' else a.toggle_pick_mode()
                self._type_quote_expression(w,'１２＋３×２');self._enter_quote_expression(w)
                self.assertIsNone(a._pick_mode)
                self.assertEqual(self._calculated_text(),'引用先18\n第二😀行\n第三行')
                self.assertNotIn('=',a.editor_source_text())
    def test_quick_input_row_reference_uses_main_editor_and_replaces_the_typed_digits(self):
        a=self.a;self._command_source();a._quick_text=tk.Text(self.root,undo=True)
        q=a._quick_text;q.insert('1.0','簡易');q.mark_set('insert','1.end')
        a._start_pick_mode(False,target='quick');self._type_quote_expression(q,'2');self._enter_quote_expression(q)
        self.assertEqual(q.get('1.0','end-1c'),'簡易第二😀行');self.assertIsNone(a._pick_mode)
        self.assertEqual(a.editor.get('1.0','end-1c'),'引用先\n第二😀行\n第三行')
    def test_equals_row_reference_removes_trigger_and_does_not_calculate(self):
        a=self.a;w=self._command_source();a._on_equal_key(types.SimpleNamespace(widget=w,char='=',keysym='equal',state=0))
        self._type_quote_expression(w,'2');self._enter_quote_expression(w)
        self.assertEqual(w.get('1.0','end-1c'),'引用先第二😀行\n第二😀行\n第三行')
        self.assertIsNone(a._pick_mode);self.assertFalse(a._input_document.calculations)
