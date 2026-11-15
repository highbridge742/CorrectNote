# -*- coding: utf-8 -*-
"""本文の行 ⇔ 欄の行 の変換の決まり（body_index・2026-11-15 タイトルと目次を本文の Text の中の字にする作り替えの1段目）。
画面は使わない。本物の Tk の Text に、見出し H 行を置いた時の位置と照らし合わせる試験も入れる（自分の窓だけ）。"""
import tkinter as tk
import unittest

import body_index as B


class Rules(unittest.TestCase):
    def test_shift_in_moves_only_absolute_rows(self):
        self.assertEqual(B.shift_in('1.0', 3), '4.0')
        self.assertEqual(B.shift_in('12.5', 3), '15.5')
        self.assertEqual(B.shift_in('2.end', 3), '5.end')
        self.assertEqual(B.shift_in('1.0+5c', 3), '4.0+5c')
        self.assertEqual(B.shift_in('3.2 lineend', 3), '6.2 lineend')
        self.assertEqual(B.shift_in('1.0 + 2 lines', 3), '4.0 + 2 lines')
        for same in ('insert', 'end', 'end-1c', 'insert linestart', '@10,20', 'sel.first', 'current', 'cn_mark'):
            self.assertEqual(B.shift_in(same, 3), same)

    def test_zero_height_passes_through(self):
        args = ['index', '1.0']
        self.assertEqual(B.translate(args, 0), (args, None))
        self.assertEqual(B.shift_in('1.0', 0), '1.0')
        self.assertEqual(B.shift_out('4.0', 0), '4.0')

    def test_shift_out_and_the_header_rows(self):
        self.assertEqual(B.shift_out('4.0', 3), '1.0')
        self.assertEqual(B.shift_out('10.7', 3), '7.7')
        self.assertEqual(B.shift_out('3.5', 3), '1.0')        # 見出しの中は本文の頭へ寄せる
        self.assertEqual(B.shift_out('1.0', 3), '1.0')
        self.assertEqual(B.shift_out('', 3), '')

    def test_commands(self):
        h = 2
        self.assertEqual(B.translate(['insert', '1.0', 'x'], h)[0], ['insert', '3.0', 'x'])
        self.assertEqual(B.translate(['delete', '1.0', '2.end'], h)[0], ['delete', '3.0', '4.end'])
        self.assertEqual(B.translate(['get', '-displaychars', '1.0', 'end'], h)[0], ['get', '-displaychars', '3.0', 'end'])
        self.assertEqual(B.translate(['compare', '1.0', '<', '2.0'], h)[0], ['compare', '3.0', '<', '4.0'])
        self.assertEqual(B.translate(['mark', 'set', 'insert', '2.3'], h)[0], ['mark', 'set', 'insert', '4.3'])
        self.assertEqual(B.translate(['tag', 'add', 'sel', '1.0', '1.end'], h)[0], ['tag', 'add', 'sel', '3.0', '3.end'])
        self.assertEqual(B.translate(['tag', 'nextrange', 'odd', '1.0', 'end'], h)[0], ['tag', 'nextrange', 'odd', '3.0', 'end'])
        args, out = B.translate(['search', '-count', 'n', '--', 'あ', '1.0', 'end'], h)
        self.assertEqual(args, ['search', '-count', 'n', '--', 'あ', '3.0', 'end'])
        self.assertEqual(out('5.2'), '3.2')
        self.assertEqual(out(''), '')
        args, out = B.translate(['tag', 'ranges', 'odd'], h)
        self.assertEqual(out('3.0 3.4 5.1 5.2'), ('1.0', '1.4', '3.1', '3.2'))
        args, out = B.translate(['dump', '-text', '1.0', '2.0'], h)
        self.assertEqual(args, ['dump', '-text', '3.0', '4.0'])
        self.assertEqual(out(('text', 'ab', '3.0', 'text', 'c', '4.0')), ('text', 'ab', '1.0', 'text', 'c', '2.0'))
        self.assertEqual(B.translate(['yview', 'moveto', '0.5'], h)[0], ['yview', 'moveto', '0.5'])
        self.assertEqual(B.translate(['yview', '2.0'], h)[0], ['yview', '4.0'])
        self.assertEqual(B.translate(['yview', '1.0'], h)[0], ['yview', '1.0'])     # 1行目へ＝文書の頭（見出しの上）
        self.assertEqual(B.translate(['see', '1.0'], h)[0], ['see', '3.0'])


class AgainstTk(unittest.TestCase):
    """本物の Text に見出し2行＋本文を入れ、変換した呼び出しが本文だけを見ることを確かめる。"""
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.t = tk.Text(self.root)
        self.t.insert('1.0', '題\n目次\n本文1\n本文2')
        self.h = 2

    def call(self, *args):
        new, out = B.translate(list(args), self.h, self.t.tk.splitlist)
        got = self.t.tk.call(self.t._w, *new)
        return out(got) if out else got

    def test_reads_and_writes_see_only_the_body(self):
        self.assertEqual(self.call('get', '1.0', 'end-1c'), '本文1\n本文2')
        self.assertEqual(self.call('index', 'end-1c'), '2.3')
        self.call('insert', '1.0', '先')
        self.assertEqual(self.t.get('1.0', 'end-1c'), '題\n目次\n先本文1\n本文2')
        self.call('delete', '2.0', '2.end')
        self.assertEqual(self.call('get', '1.0', 'end-1c'), '先本文1\n')
        self.call('tag', 'add', 'odd', '1.1', '1.3')
        self.assertEqual(self.call('tag', 'ranges', 'odd'), ('1.1', '1.3'))
        self.assertEqual(self.call('search', '本文', '1.0', 'end'), '1.1')

    def test_header_position_comes_back_as_the_body_head(self):
        self.t.mark_set('insert', '1.1')                 # 見出しの中（生の位置）
        self.assertEqual(self.call('index', 'insert'), '1.0')


class TclMatchesPython(unittest.TestCase):
    """変換は Tcl の手続き（打つたびに速い）。決まりは translate() と同じであること。"""
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.py = tk.Text(self.root)
        self.tcl = tk.Text(self.root)
        for t in (self.py, self.tcl):
            t.insert('1.0', '題\n目次\n本文1 本文\n本文2\n本文3')
            t.tag_add('odd', '3.1', '3.3')
            t.tag_add('odd', '5.0', '5.2')
            t.mark_set('insert', '4.1')
        B.install(self.tcl, 2)

    def via_python(self, *args):
        new, out = B.translate(list(args), 2, self.py.tk.splitlist)
        got = self.py.tk.call(self.py._w, *new)
        return out(got) if out else got

    def test_reads(self):
        calls = [('get', '1.0', 'end-1c'), ('get', '2.0', '2.end'), ('index', 'insert'), ('index', 'end-1c'),
                 ('index', '1.0+3c'), ('index', '2.end'), ('compare', '1.0', '<', '2.0'),
                 ('tag', 'ranges', 'odd'), ('tag', 'nextrange', 'odd', '1.0', 'end'), ('tag', 'prevrange', 'odd', 'end'),
                 ('tag', 'nextrange', 'odd', '3.0', '3.end'), ('tag', 'names', '1.1'), ('search', '本文', '1.0', 'end'),
                 ('search', '-backwards', '--', '本文', 'end'), ('search', 'ない', '1.0', 'end'),
                 ('dump', '-text', '2.0', '2.end'), ('count', '-chars', '1.0', '2.0'), ('mark', 'next', '2.0')]
        for args in calls:
            py = self.via_python(*args)
            tcl = self.tcl.tk.call(self.tcl._w, *args)
            norm = lambda v: tuple(str(x) for x in self.root.tk.splitlist(v if isinstance(v, tuple) else str(v)))
            self.assertEqual(norm(tcl), norm(py), args)

    def test_writes(self):
        for args in (('insert', '1.0', '先'), ('delete', '2.0', '2.2'), ('replace', '1.0', '1.1', '置'),
                     ('tag', 'add', 'x', '1.0', '1.2'), ('tag', 'remove', 'odd', '1.0', 'end'), ('mark', 'set', 'm', '2.1')):
            self.via_python(*args)
            self.tcl.tk.call(self.tcl._w, *args)
        self.assertEqual(self.tcl.tk.call(self.tcl._cn_body_raw, 'get', '1.0', 'end-1c'), self.py.get('1.0', 'end-1c'))
        self.assertEqual(str(self.tcl.index('m')), '2.1')
        self.assertEqual([str(v) for v in self.tcl.tk.call(self.tcl._cn_body_raw, 'tag', 'ranges', 'x')],
                         [str(v) for v in self.py.tag_ranges('x')])

    def test_first_line_goes_to_the_very_top(self):
        self.tcl.tk.call(self.tcl._w, 'yview', '1.0')
        self.assertEqual(str(self.tcl.tk.call(self.tcl._cn_body_raw, 'index', '@0,0')), '1.0')

    def test_errors_stay_tcl_errors(self):
        with self.assertRaises(tk.TclError):
            self.tcl.index('no_such_mark')
        self.assertEqual(self.tcl.cget('wrap'), self.py.cget('wrap'))


if __name__ == '__main__':
    unittest.main()
