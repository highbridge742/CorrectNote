# -*- coding: utf-8 -*-
import tkinter as tk
import unittest
from unittest.mock import Mock
import app
from session import SessionStore, new_tab


class AllTabsSearchTkTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root)
        a.result_view = tk.Text(self.root)
        a.session = SessionStore()
        a.session.tabs = [new_tab('古い内容', title='一つ目'),
                          new_tab('\n\n😀資料\tひとつ\n\n資料ふたつ\n\n', title='二つ目')]
        a.editor.insert('1.0', '未保存の資料')
        a.editor_source_text = lambda: a.editor.get('1.0', 'end-1c')
        a._find_query = tk.StringVar(master=self.root, value='資料')
        a._find_regex = tk.BooleanVar(master=self.root, value=False)
        a._find_match_case = tk.BooleanVar(master=self.root, value=False)
        a._find_whole_word = tk.BooleanVar(master=self.root, value=False)
        a._find_status = tk.Label(self.root)
        a._find_dialog = self.root
        a._remember_find_text = Mock()
        a._place_dialog = Mock()
        a.current_file = None; a._dirty = True; a.bookmarks = set()
        a._pick_mode = None
        a._schedule_session_save = Mock()
        def load(initial=False):
            a.editor.delete('1.0', 'end')
            a.editor.insert('1.0', a.session.current()['text'])
        a._load_active_tab = load

    def tearDown(self):
        self.a._close_all_tab_results()
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root')

    def select_hit(self, iid):
        self.a._all_tab_tree.selection_set(iid)
        return self.a._open_all_tab_hit()

    def test_unsaved_text_and_reordered_tab_unicode_navigation(self):
        a = self.a
        a._do_find_all_tabs()
        self.assertEqual(len(a._all_tab_hits), 3)
        self.assertEqual(a._all_tab_tree.item('2', 'values')[1], '3:2')
        target = a.session.tabs[1]
        a.session.tabs.reverse(); a.session.active = 1
        self.select_hit('2')
        self.assertIs(a.session.current(), target)
        self.assertEqual(a.editor.get('sel.first', 'sel.last'), '資料')
        self.assertEqual(a.session.tabs[1]['text'], '未保存の資料')

    def test_internal_newlines_only_and_zero_width_regex(self):
        a = self.a
        a._find_query.set('\n')
        a._do_find_all_tabs()
        spans = [(hit[2], hit[3]) for hit in a._all_tab_hits.values()]
        self.assertEqual(spans, [(9, 10), (10, 11)])
        a._find_regex.set(True)
        a._find_query.set(r'(?=資料)')
        a._do_find_all_tabs()
        self.assertEqual(a._all_tab_hits, {})
        a._find_query.set('[')
        a._do_find_all_tabs()
        self.assertIn('正規表現', a._find_status.cget('text'))

    def test_stale_hit_refreshes_without_jumping_to_wrong_text(self):
        a = self.a
        a._do_find_all_tabs()
        a.session.tabs[1]['text'] = '別の資料'
        self.select_hit('2')
        self.assertEqual(a.session.active, 0)
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '未保存の資料')
        self.assertEqual(len(a._all_tab_hits), 2)
        self.assertIn('文章が変わった', a._all_tab_notice.cget('text'))

    def test_closed_tab_result_is_removed_without_switching(self):
        a = self.a
        a._do_find_all_tabs()
        a.session.tabs.pop()
        self.select_hit('2')
        self.assertEqual(a.session.active, 0)
        self.assertEqual(len(a._all_tab_hits), 1)
        self.assertIn('閉じられた', a._all_tab_notice.cget('text'))

    def test_source_span_maps_to_shorter_unified_display(self):
        a = self.a
        a.session.tabs[1]['text'] = '😀しりょうを読む'
        a._find_query.set('しりょう')
        a._do_find_all_tabs()
        a.editor_source_text = lambda: ('未保存の資料' if a.session.active == 0
                                        else '😀しりょうを読む')
        def load(initial=False):
            a.editor.delete('1.0', 'end')
            a.editor.insert('1.0', '😀資料を読む')
        a._load_active_tab = load
        self.select_hit('1')
        self.assertEqual(a.editor.get('sel.first', 'sel.last'), '資料')

    def test_pending_scan_is_cancelled_when_query_changes_or_window_closes(self):
        a = self.a
        a.editor.delete('1.0', 'end'); a.editor.insert('1.0', '資料 ' * 1000)
        a._do_find_all_tabs()
        self.assertIsNotNone(a._all_tab_search_job)
        a._find_query.set('不存在')
        a._do_find_all_tabs()
        self.root.update()
        self.assertEqual(a._all_tab_hits, {})
        a._find_query.set('資料')
        a._do_find_all_tabs()
        a._close_all_tab_results()
        self.root.update()
        self.assertIsNone(a._all_tab_search_job)
        self.assertEqual(a._all_tab_hits, {})
