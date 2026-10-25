# -*- coding: utf-8 -*-
"""Keys and words while the IME is converting (2026-10-22).

うにさん「変換中にCtrl+F2またはAlt+F2すると、入力していた文字が一部欠けて入力されることがある…
Githubのリリース版で発生し、開発環境では発生しない」: the IME hands its commit to Tk as key presses
while Ctrl or Alt is still held, and the Text class ignores such presses. Tk 8.6.9 marks them
(%E -3); Tk 8.6.12 (the release build) does not, so they are matched against the commit asked for.

「変換中にF1で引用開始してクリックで引用すると、文字の左側にペーストされる。変換中にF4を
おすと、入力した文字の左側にペーストされる。変換中に単語帳の登録文字をクリックすると、変換の
文字が消えてペーストされる。これらは、右側にペーストする」: the conversion is committed first and
the text goes after it. When the IME committed on its own right before the key, the key waits for
that text to land. The word book commits as the click begins (word_book). The real IME is
exercised by tools_local/ime_fix_20261022/probe_app_keys.py and probe_app_f2.py. Withdrawn root,
no clipboard."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, ime_watch
import tests_bracket_composition as bracket_tests


class CompositionInsertTests(unittest.TestCase):
    setUp = bracket_tests.BracketCompositionTests.setUp
    tearDown = bracket_tests.BracketCompositionTests.tearDown
    wait = bracket_tests.BracketCompositionTests.wait

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update(); time.sleep(.005)

    def text(self):
        return self.editor.get('1.0', 'end-1c')

    def fake_paste(self):
        # Tk's paste at the cursor, without the clipboard
        self.editor.bind('<<Paste>>', lambda e: (self.editor.insert('insert', '貼'), 'break')[1])

    def converting(self):
        # An IME conversion of 入力中 at the cursor; committing it puts the text in a moment later
        self.active = [True]
        def commit(hwnd):
            def native():self.editor.insert('insert', '入力中');self.active[0] = False
            self.root.after(30, native);return True
        return (patch.object(ime_watch, 'composition_active', side_effect=lambda hwnd:self.active[0]),
                patch.object(ime_watch, 'read_composition', return_value={'comp':'入力中'}),
                patch.object(ime_watch, 'complete_composition', side_effect=commit))

    def test_characters_delivered_with_ctrl_held_are_the_commit_asked_for(self):
        w = self.editor
        self.a._pending_bracket_composition = dict(kind=0, pair=('（', '）'), comp='入力中', prefix='前',
                                                   suffix='後', tab=self.tab, widget=w, until=time.monotonic() + 1)
        for ch in '入力中':     # Tk 8.6.12 gives %E 1, the Text class would ignore them with Ctrl
            self.assertEqual(self.a._on_bracket_ime_char('1', ch), 'break')
        self.assertEqual(self.text(), '前入力中後')
        # Anything else is the user's key, left to the Text class
        self.assertEqual(self.a._on_bracket_ime_char('1', '字'), '')
        w.delete('1.1', '1.4'); w.mark_set('insert', '1.1')
        self.assertEqual(self.a._on_bracket_ime_char('1', '力'), '')

    def test_a_commit_made_right_before_the_key_is_waited_for(self):
        self.fake_paste()
        self.a._ime_commit_queue = [(self.editor.winfo_id(), '入力中')]
        event = SimpleNamespace(widget=self.editor, keysym='F4', char='', state=0)
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.assertEqual(self.a._on_f4_paste(event), 'break')
            self.assertEqual(self.text(), '前後')                   # not pasted before the commit
            self.editor.insert('insert', '入力中')                   # Tk delivers the commit
            self.pump(.1)
        self.assertEqual(self.text(), '前入力中貼後')

    def test_word_book_word_goes_after_the_committed_text(self):
        a, b, c = self.converting()
        with a, b, c:
            self.assertTrue(self.a._insert_word_book_text('単語', self.editor))
            self.assertEqual(self.text(), '前後')
            self.wait(lambda:self.a._pending_bracket_composition is None)
        self.assertEqual(self.text(), '前入力中単語後')
        self.assertEqual(self.editor.index('insert'), '1.6')

    def test_word_book_word_waits_for_a_commit_on_its_way(self):
        # The word book committed the conversion as the click began; its text lands just after
        self.a._ime_commit_queue = [(self.editor.winfo_id(), '入力中')]
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.assertTrue(self.a._insert_word_book_text('単語', self.editor))
            self.editor.insert('insert', '入力中')
            self.pump(.1)
        self.assertEqual(self.text(), '前入力中単語後')

    def test_quote_picked_while_converting_goes_after_the_committed_text(self):
        w = self.editor
        self.a._pick_mode = 'f1'; self.a._pick_target = 'editor'; self.a._pick_had_selection = False
        self.a._pick_origin_tab = None; self.a.status = tk.Label(self.root)
        self.a._end_pick_mode = lambda keep_equals=True:None
        self.a._on_change = lambda *args:None
        w.mark_set(self.a._PICK_MARK, '1.1'); w.mark_gravity(self.a._PICK_MARK, 'left')
        a, b, c = self.converting()
        with a, b, c:
            self.a._pick_insert('引用')
            self.assertEqual(self.text(), '前後')
            self.wait(lambda:self.a._pending_bracket_composition is None and '引用' in self.text())
        self.assertEqual(self.text(), '前入力中引用後')

    def test_ctrl_v_while_converting_pastes_after_the_committed_text(self):
        # 2026-10-22 うにさん「変換中にCtrl+Vでペーストすると、左側に出ます。Windowsメモ帳では
        # 右側に出たので、右に出るようにする」
        self.fake_paste()
        a, b, c = self.converting()
        with a, b, c:
            self.assertEqual(self.a._on_paste_while_converting(str(self.editor)), 'break')
            self.assertEqual(self.text(), '前後')
            self.wait(lambda:self.a._pending_bracket_composition is None and '貼' in self.text())
        self.assertEqual(self.text(), '前入力中貼後')
        # Not converting: Tk's own paste goes on
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.assertEqual(self.a._on_paste_while_converting(str(self.editor)), '')

    def test_word_book_shown_by_its_key_commits_the_conversion_first(self):
        # 「変換中にショートカットキーで単語帳を出すと、変換中の文字が消えます。変換中に単語帳を
        # 閉じた場合は消えません」
        shown = []
        self.a._word_book = SimpleNamespace(window=None)
        self.root.focus_get = lambda:self.editor
        a, b, c = self.converting()
        with a, b, c:
            self.assertTrue(self.a._commit_before_word_book(lambda:shown.append(self.text())))
            self.assertEqual(shown, [])
            self.wait(lambda:shown)
        self.assertEqual(shown, ['前入力中後'])
        # Closing it (shown, not minimized) leaves the conversion alone
        self.a._word_book = SimpleNamespace(window=SimpleNamespace(state=lambda:'normal'))
        with patch.object(ime_watch, 'composition_active', return_value=True):
            self.assertFalse(self.a._commit_before_word_book(lambda:None))

    def paste_with(self, text):
        # Tk's own paste, reading this text instead of the OS clipboard (this interpreter only)
        self.root.tk.call('rename', '::tk::GetSelection', '::tk::SavedGetSelection')
        reader = self.root.register(lambda *args: text)
        self.root.tk.call('proc', '::tk::GetSelection', 'args', 'return [%s {*}$args]' % reader)
        self.addCleanup(lambda: (self.root.tk.call('rename', '::tk::GetSelection', ''),
                                 self.root.tk.call('rename', '::tk::SavedGetSelection', '::tk::GetSelection')))

    def bracket_key(self, state=0):
        self.a._on_commit_run_event('key', '0', 'F2', str(self.editor))
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.a._on_f5_brackets(SimpleNamespace(widget=self.editor, keysym='F2', char='', state=state))

    def test_bracket_key_right_after_a_paste_wraps_what_was_pasted(self):
        # 2026-10-23 うにさん「貼り付けた直後に F2 を押したら、貼り付けた範囲を括弧で囲む」
        self.paste_with('貼った字')
        w = self.editor
        self.a._install_commit_run(w); self.a._install_paste_after_commit(w)
        for state, expected in ((0, '前（貼った字）後'), (4, '前（貼った字）後'), (0x20000, '前貼った字（）後')):
            with self.subTest(state=state), patch.object(ime_watch, 'composition_active', return_value=False):
                w.delete('1.0', 'end'); w.insert('1.0', '前後'); w.mark_set('insert', '1.1')
                self.a._forget_bracket_cycle(); self.a._forget_commit_run()
                w.event_generate('<<Paste>>')
                self.assertEqual(self.text(), '前貼った字後')
                self.bracket_key(state)
                self.assertEqual(self.text(), expected)
        # Not right after it: a cursor move in between
        with patch.object(ime_watch, 'composition_active', return_value=False):
            w.delete('1.0', 'end'); w.insert('1.0', '前後'); w.mark_set('insert', '1.1')
            self.a._forget_bracket_cycle(); self.a._forget_commit_run()
            w.event_generate('<<Paste>>')
            self.a._on_commit_run_event('key', '0', 'Left', str(w)); w.mark_set('insert', '1.4')
            self.bracket_key()
        self.assertEqual(self.text(), '前貼った（）字後')

    def test_bracket_key_right_after_a_word_book_word_wraps_it(self):
        w = self.editor
        self.a._install_commit_run(w)
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.a._insert_word_book_text('単語', w)
        self.bracket_key()
        self.assertEqual(self.text(), '前（単語）後')

    def test_each_word_book_click_is_one_undo(self):
        # 2026-10-23 うにさん「単語帳のクリック一手一手が履歴に残らないようで、アンドゥで一気に戻ります」
        self.editor.edit_reset()
        self.editor.insert('insert', 'あ')          # typed text right before
        with patch.object(ime_watch, 'composition_active', return_value=False):
            self.a._insert_word_book_text('単語', self.editor)
            self.a._insert_word_book_text('語', self.editor)
        self.assertEqual(self.text(), '前あ単語語後')
        self.editor.edit_undo(); self.assertEqual(self.text(), '前あ単語後')
        self.editor.edit_undo(); self.assertEqual(self.text(), '前あ後')
        self.editor.edit_undo(); self.assertEqual(self.text(), '前後')

    def test_word_book_keeps_the_place_it_opened_at(self):
        # 「最初はカーソルの近くに出るが、すぐに左の離れたほうや、画面の左上に飛んで行って
        # しまいます」: the first showing settles a moment later and puts the window back where
        # Windows first put it; the place is held until then (also left of the primary monitor)
        from word_book import WordBook
        book = WordBook.__new__(WordBook)
        book.app = SimpleNamespace(root=self.root); book._drag_anchor = None
        book.window = win = tk.Toplevel(self.root); win.attributes('-alpha', 0)
        for x, y in ((-1500, 100), (12000, 300)):
            win.geometry('150x100+40+40'); win.update()
            book._hold_place(x, y, 6)
            win.geometry('+60+60')           # what the settling showing does
            self.pump(.4)
            self.assertEqual((win.winfo_x(), win.winfo_y()), (x, y))
        win.destroy()

    def test_word_book_opens_near_the_pointer_inside_its_screen(self):
        from word_book import word_book_near_pointer
        area = (-1920, 0, 0, 1040)                                # a monitor left of the primary
        self.assertEqual(word_book_near_pointer((-1000, 300), (150, 200), area), (-984, 316))
        # Near the bottom: moved up just enough; near the right edge: moved left
        self.assertEqual(word_book_near_pointer((-1000, 1000), (150, 200), area), (-984, 832))
        self.assertEqual(word_book_near_pointer((-60, 300), (150, 200), area), (-158, 316))
        # Taller than the screen: from its top
        self.assertEqual(word_book_near_pointer((-1000, 900), (150, 2000), area), (-984, 0))

    def test_quick_window_grown_past_the_bottom_moves_up(self):
        win = tk.Toplevel(self.root); win.attributes('-alpha', 0)
        win.geometry('200x150+10000+500'); win.update()
        title = win.winfo_rooty() - win.winfo_y(); border = win.winfo_rootx() - win.winfo_x()
        win.geometry('200x300'); win.update()
        with patch.object(app, 'monitor_work_area', return_value=(9000, 0, 11000, 700)):
            self.a._keep_quick_above_bottom(win); win.update()
        self.assertEqual(win.winfo_y(), 700 - (300 + title + border))
        with patch.object(app, 'monitor_work_area', return_value=(9000, 400, 11000, 700)):
            win.geometry('200x600'); win.update()
            self.a._keep_quick_above_bottom(win); win.update()
        self.assertEqual(win.winfo_y(), 400)                    # never above the top
        win.destroy()

    def test_quote_mark_follows_the_commit_made_after_f1(self):
        w = self.editor
        self.a._pick_mode = 'f1'
        w.mark_set(self.a._PICK_MARK, '1.1'); w.mark_gravity(self.a._PICK_MARK, 'left')
        self.a._pick_after_composition = w
        w.insert('insert', '入力中')
        self.a._start_commit_run(w, '入力中')
        self.assertEqual(w.index(self.a._PICK_MARK), '1.4')
        self.assertIsNone(self.a._pick_after_composition)


if __name__ == '__main__':
    unittest.main()
