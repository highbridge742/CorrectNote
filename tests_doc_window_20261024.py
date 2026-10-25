# -*- coding: utf-8 -*-
"""A tab shown in a second window (doc_window・2026-10-23 うにさん「ファイルタブの右クリックメニューに『別の
ウィンドウで表示する』。新しい窓で同じ文書を表示し、元の窓のタブは残す。同じ文書を2つの窓で開いている間は、
片方の編集を即もう片方に反映」・1.16 に入れる 2026-10-24).

The memo goes through the app's own command (observe_text with the Unicode undo wrapper), as in the app. The
second windows are transparent and off the screen (the test's own Tk only)."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, doc_window, session
from analysis_work import observe_text

UNIT = dict(start=3, end=4, text='鏡', base='鏡', prev='', next='', reading='かがみ')


class _HiddenTop(tk.Toplevel):
    """Never seen: transparent and off the screen before it is first drawn."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.attributes('-alpha', 0)
        self.geometry('+10000+100')

    def geometry(self, spec=None):
        if spec is not None and not spec.endswith('+10000+100'):
            size = spec.split('+')[0]
            spec = size + '+10000+100'
        return super().geometry(spec)


class _Session(SimpleNamespace):
    def current(self):
        return self.tabs[self.active]


class DocWindowTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.top = patch.object(doc_window.tk, 'Toplevel', _HiddenTop); self.top.start()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root, undo=True, autoseparators=True)
        observe_text(a.editor)
        a.session = _Session(tabs=[session.new_tab(text='今日は鏡が良い\n二行目'),
                                   session.new_tab(text='別のタブ')], active=0)
        a.editor.insert('1.0', a.session.tabs[0]['text'])
        a.editor.edit_reset(); a.editor.edit_separator()
        self.changes = []
        a._on_change = lambda: self.changes.append(a.editor.get('1.0', 'end-1c'))
        a._capture_session = lambda: a.session.current().__setitem__('text', a.editor.get('1.0', 'end-1c'))
        a._schedule_session_save = lambda: None
        a._refresh_tab_bar = lambda: None
        a._schedule_whitespace_paint = lambda delay=None: None
        a._set_window_icons_win32 = lambda win: None
        a._dirty = False

        def core(initial=False):          # the memo shows the current tab (as _load_active_tab_core does)
            a.editor.delete('1.0', 'end')
            a.editor.insert('1.0', a.session.current().get('text') or '')
            a.editor.edit_reset()
        a._load_active_tab_core = core

    def tearDown(self):
        for window in list(getattr(self.a, '_doc_windows', ())):
            window.close()
        self.top.stop()
        self.root.destroy()

    def switch(self, index):
        a = self.a
        a._capture_session()
        a.session.active = index
        a._load_active_tab()
        self.root.update()

    def test_the_peer_shares_the_memo_both_ways(self):
        a = self.a
        window = a._open_in_window(0)
        self.root.update()
        self.assertEqual(window.mode, 'peer')
        peer = window.text
        self.assertEqual(peer.get('1.0', 'end-1c'), '今日は鏡が良い\n二行目')
        peer.mark_set('insert', '2.0')
        peer.insert('insert', '追加')                     # typed in the second window
        self.assertEqual(a.editor.get('2.0', '2.end'), '追加二行目')
        a.editor.insert('1.0', '頭')                      # typed in the main window
        self.assertEqual(peer.get('1.0', '1.end'), '頭今日は鏡が良い')
        peer.delete('1.0', '1.1')
        self.assertEqual(a.editor.get('1.0', '1.end'), '今日は鏡が良い')
        # the peer's undo is the memo's (one history)
        peer.edit_undo()
        self.assertEqual(a.editor.get('1.0', '1.end'), '頭今日は鏡が良い')
        # the same window again: the open one comes to the front
        self.assertIs(a._open_in_window(0), window)
        self.assertEqual(len(a._doc_windows), 1)

    def test_other_tab_in_the_main_window_keeps_a_copy_and_writes_back(self):
        a = self.a
        window = a._open_in_window(0)
        self.root.update()
        self.switch(1)
        self.assertEqual(window.mode, 'copy')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '別のタブ')
        self.assertEqual(window.text.get('1.0', 'end-1c'), '今日は鏡が良い\n二行目')
        edited = []
        a._doc_window_edited = lambda w: edited.append(w)
        window.text.insert('end', '\n三行目')                # typed in the copy
        self.root.update()
        self.assertEqual(a.session.tabs[0]['text'], '今日は鏡が良い\n二行目\n三行目')
        self.assertFalse(a.session.tabs[0]['saved'])
        self.assertEqual(edited, [window])
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '別のタブ')  # the main window's tab is untouched
        self.switch(0)
        self.assertEqual(window.mode, 'peer')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '今日は鏡が良い\n二行目\n三行目')
        window.text.insert('1.0', 'x')
        self.assertEqual(a.editor.get('1.0', '1.1'), 'x')

    def test_bold_after_an_emoji_is_written_back_in_place(self):
        # Tk 8.6 on Windows reports UTF-16 columns: an emoji counts twice there. The copy writes the B/I/U/S
        # back in Python characters, as text_format keeps them (2026-10-24)
        from text_format import STYLE_TAGS, _position
        a = self.a
        a.session.tabs[1]['text'] = '前😀太字の後\n二行目😀😀太字'
        window = a._open_in_window(1)                    # the main window shows tab 0: a copy
        self.root.update()
        self.assertEqual(window.mode, 'copy')
        tag = STYLE_TAGS['bold']
        window.text.tag_add(tag, '1.0+2c', '1.0+4c')
        window.text.tag_add(tag, '2.0+5c', '2.0+7c')
        window.text.insert('end', '！')                    # typed: written back
        self.root.update()
        spans = a.session.tabs[1]['text_styles']['bold']
        self.assertEqual(spans, [[1, 2, 1, 4], [2, 5, 2, 7]])
        lines = a.session.tabs[1]['text'].split('\n')
        self.assertEqual([lines[r - 1][c:c2] for r, c, _, c2 in spans], ['太字', '太字'])
        # opened again from the tab: the same places
        window.close()
        again = a._open_in_window(1)
        self.root.update()
        ranges = again.text.tag_ranges(tag)
        self.assertEqual([list(_position(again.text, a_) + _position(again.text, z))
                          for a_, z in zip(ranges[0::2], ranges[1::2])], [[1, 2, 1, 4], [2, 5, 2, 7]])

    def test_closing_the_window_or_its_tab(self):
        a = self.a
        window = a._open_in_window(0)
        self.root.update()
        peer = window.text._w
        window.close()
        self.root.update()
        self.assertEqual(a._doc_windows, [])
        self.assertEqual(self.root.tk.call('info', 'commands', peer), '')       # the procedure is gone too
        self.assertEqual(a.editor.get('1.0', '1.end'), '今日は鏡が良い')         # the memo stays
        a.editor.insert('1.0', 'まだ使える')
        # the tab goes: its window goes with it
        window = a._open_in_window(1)
        other = a._open_in_window(0)
        self.root.update()
        a.session.tabs.pop(1)
        a._close_doc_windows(only_gone=True)
        self.assertEqual(a._doc_windows, [other])
        self.assertFalse(window.window.winfo_exists())
        a._close_doc_windows()
        self.assertEqual(a._doc_windows, [])

    def test_ctrl_w_closes_the_second_window_not_the_tab(self):
        # 2026-10-24 うにさん「Ctrl+W は本体のタブではなくバックアップの窓を閉じる（『別のウィンドウで表示する』の窓も同じ）」
        a = self.a
        closed_tabs = []
        self.root.bind_all('<Control-w>', lambda e: (closed_tabs.append(True), 'break')[1])
        window = a._open_in_window(0)
        self.root.update()
        window.text.focus_force(); self.root.update()
        window.text.event_generate('<Control-w>')
        self.root.update()
        self.assertFalse(window.window.winfo_exists())
        self.assertEqual(closed_tabs, [])
        self.assertEqual(a._doc_windows, [])

    def choose_stubs(self):
        a = self.a
        a._candidate_selection_unit = lambda row, unit, cand, widget: unit
        a.unified_autofix_on = lambda: False
        a._mark_typed = lambda *args: None
        a._invalidate_units_cache = a._invalidate_analysis_cache = lambda: None
        a._supersede_prior_choice = lambda *args: None
        a.choices = SimpleNamespace(record=lambda *args: None, save=lambda: None)
        a._choice_reading = lambda unit, cand: ''
        a._remember_recent = lambda surface: None
        a._editor_changes = []
        a.status = SimpleNamespace(config=lambda **kw: None)
        a._retain_contextual_selection = lambda *args: None
        a._analyze_quick = lambda: None
        a._forget_chain = lambda *args: None
        a._dropdown_via_f2 = True

    def test_one_undo_in_the_second_window_brings_the_chosen_word_back(self):
        # 2026-10-23 「再変換で候補から選んだあと、1回アンドゥすると…これは1回で元に戻す」 in the second window too
        a = self.a
        self.choose_stubs()
        window = a._open_in_window(0)
        self.root.update()
        a._editor_choose_word(1, dict(UNIT), {'surface': '機嫌'})
        self.assertEqual(window.text.get('1.0', '1.end'), '今日は機嫌が良い')
        window.text.edit_undo()
        self.assertEqual(window.text.get('1.0', '1.end'), '今日は鏡が良い')      # one undo
        window.text.edit_redo()
        self.assertEqual(window.text.get('1.0', '1.end'), '今日は機嫌が良い')    # one redo

    def test_escape_in_the_second_window_clears_the_copy_frame(self):
        # 2026-10-24 の既定: Esc (not converting) ends the copy frame and the larger letters, as in the main window
        a = self.a
        cleared = []
        a._clear_copy_emphasis = lambda: cleared.append(True)
        a._composing = lambda widget: False
        a._copy_frame = None
        window = a._open_in_window(0)
        self.root.update()
        a._copy_emphasis = object()
        self.assertIn('_escape', window.text.bind('<Escape>'))
        window._escape(SimpleNamespace(widget=window.text))
        self.assertEqual(cleared, [True])
        a._composing = lambda widget: True                  # Esc belongs to the IME while converting
        window._escape(SimpleNamespace(widget=window.text))
        self.assertEqual(cleared, [True])
        self.switch(1)                                      # the copy as well
        a._composing = lambda widget: False
        window._escape(SimpleNamespace(widget=window.text))
        self.assertEqual(cleared, [True, True])

    def test_whitespace_marks_in_the_peer_and_in_the_copy(self):
        a = self.a
        window = a._open_in_window(0)
        self.root.update()
        self.assertIn(window.text, a._whitespace_targets())
        self.switch(1)
        self.assertEqual(window.mode, 'copy')
        self.assertIn(window.text, a._whitespace_targets())  # 2026-10-24 の既定: the copy too
        window.close()
        self.assertNotIn(window.text, a._whitespace_targets())

    def run_in_mainloop(self, *steps):
        done = []

        def run():
            for step in steps:
                step()
                self.root.update()
            done.append(True)
            self.root.after(50, self.root.quit)
        self.root.after(30, run)
        self.root.mainloop()
        self.assertEqual(done, [True])

    def test_theme_switches_inside_the_mainloop_with_second_windows(self):
        # As backup_view (2026-10-23 うにさん「…ダークモード切替するとアプリがクラッシュする」): the switch asks every
        # widget for options a Text does not have (-selectcolor); through the peer's command that must stay
        # Tk's own answer, not an error kept by tkinter and raised from mainloop()
        a = self.a
        light, dark = app.LIGHT_PALETTE, app.DARK_PALETTE
        to_dark = {light[k]: dark[k] for k in app._PALETTE_KEYS if light[k] != dark[k]}
        to_light = {v: k for k, v in to_dark.items()}
        a.editor.configure(bg=light['PANEL'], selectbackground=light['EDITOR_SEL_BG'])
        seen = []

        def switch(mapping):
            def step():
                app.CorrectNoteApp._restyle_widget(self.root, mapping, {})
                for window in a._doc_windows:
                    window.restyle()
            return step

        def ask():
            try:
                peer.text.cget('selectcolor')
            except tk.TclError as error:
                seen.append(str(error))
        peer = a._open_in_window(0)
        self.run_in_mainloop(ask, switch(to_dark), switch(to_light))                 # the peer
        copy = a._open_in_window(1)                                                  # the copy (tab 1 not shown)
        self.run_in_mainloop(switch(to_dark), switch(to_light), switch(to_dark))     # both
        self.run_in_mainloop(copy.close, switch(to_light), switch(to_dark))          # one closed just before
        self.assertEqual(seen, ['unknown option "-selectcolor"'])
        self.assertEqual(str(peer.text.cget('bg')), dark['PANEL'])
        self.assertEqual(str(a.editor.cget('bg')), dark['PANEL'])


if __name__ == '__main__':
    unittest.main()
