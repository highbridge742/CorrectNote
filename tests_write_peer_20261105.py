# -*- coding: utf-8 -*-
"""The read-only correction pane is written through a second view of its text, without being set writable each time
(Text.configure lays out the whole pane: 2026-11-05). Opens a small window. Made-up text."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest import mock

import ui_projection as U
from analysis_work import observe_text


class Peer(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('400x200+30+30')
        self.t = tk.Text(self.root, wrap='word')
        self.t.pack(fill='both', expand=True)
        self.t.insert('1.0', '\n'.join('%d 行目の作り物の文です。' % k for k in range(1, 300)))
        self.changed = []
        observe_text(self.t)
        self.t._correctnote_observers.setdefault('changed', []).append(self.changed.append)
        self.t.configure(state='disabled')
        self.root.update()

    def tearDown(self):
        self.root.destroy()

    def write(self, *args):
        U.start_writing(self.t)
        try:
            self.t.tk.call(self.t._w, *args)
        finally:
            U.stop_writing(self.t)

    def test_text_changes_and_the_pane_stays_read_only(self):
        self.write('replace', '5.0', '5.2', '書き換え')
        self.assertTrue(self.t.get('5.0', '5.end').startswith('書き換え'))
        self.assertEqual(str(self.t.cget('state')), 'disabled')
        before = self.t.get('1.0', 'end-1c')
        self.t.insert('1.0', '打っても入らない')        # no writing now
        self.assertEqual(self.t.get('1.0', 'end-1c'), before)

    def test_the_observers_hear_it(self):
        self.write('insert', '2.0', 'あ')
        self.assertEqual(len(self.changed), 1)
        self.assertEqual(self.changed[0][:2], ('insert', '2.0'))

    def test_the_view_cursor_and_selection_stay(self):
        self.t.see('200.0')
        self.t.mark_set('insert', '200.3')
        self.t.tag_add('sel', '201.0', '201.2')
        self.root.update()
        top = self.t.index('@0,0')
        self.write('insert', '250.0', 'あ')
        self.write('replace', '205.0', '205.1', 'ん')
        self.root.update()
        self.assertEqual(self.t.index('@0,0'), top)
        self.assertEqual(self.t.index('insert'), '200.3')
        self.assertEqual(tuple(map(str, self.t.tag_ranges('sel'))), ('201.0', '201.2'))

    def test_the_cursor_follows_text_put_before_it(self):
        self.t.mark_set('insert', '3.2')
        self.write('insert', '3.0', 'あい')
        self.assertEqual(self.t.index('insert'), '3.4')

    def test_tags_are_shared(self):
        self.t.tag_configure('fixed', foreground='red')
        self.write('insert', '4.0', '赤', 'fixed')
        self.assertEqual(tuple(map(str, self.t.tag_ranges('fixed'))), ('4.0', '4.1'))

    def test_the_writer_is_never_on_screen_and_goes_with_the_pane(self):
        self.write('insert', '1.0', 'あ')
        name = self.t._correctnote_write_peer_name
        self.assertEqual(int(self.t.tk.call('winfo', 'ismapped', name)), 0)
        self.t.destroy()
        self.root.update()
        self.assertEqual(int(self.root.tk.call('winfo', 'exists', name)), 0)


class WithoutPeer(unittest.TestCase):
    def test_the_old_way_when_there_is_no_peer(self):
        states = []
        pane = SimpleNamespace(config=lambda **k: states.append(k['state']), tk=None, _w='.x')
        U.start_writing(pane)
        U.stop_writing(pane)
        self.assertEqual(states, ['normal', 'disabled'])

    def test_the_switch(self):
        states = []
        pane = SimpleNamespace(config=lambda **k: states.append(k['state']), tk=mock.Mock(), _w='.x')
        with mock.patch.object(U, 'WRITE_THROUGH_PEER', False):
            U.start_writing(pane)
            U.stop_writing(pane)
        self.assertEqual(states, ['normal', 'disabled'])
        pane.tk.call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
