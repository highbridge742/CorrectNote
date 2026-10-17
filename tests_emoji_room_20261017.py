# -*- coding: utf-8 -*-
"""Every emoji takes the same room, whichever font showed it first.

2026-10-17 (CI build-windows, tests_emoji_color 218): Tk 8.6.12+ keeps, for the
whole process, the fallback font that first served each emoji outside the BMP.
After ＭＳ ゴシック (TkFixedFont), BIZ UD ゴシック or 游明朝 had shown 😀 first,
😀 took one em in every font while ❤️ and other emoji took the emoji font's
room. emoji_color.prime asks the emoji font first when an emoji comes into a
pane. Each case runs in a fresh process (the memory is per process).
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import emoji_color

HERE = Path(__file__).resolve().parent
CHILD = r'''
import json, sys, tkinter as tk
sys.path.insert(0, '.')
import emoji_color
from analysis_work import observe_text
first, how = sys.argv[1], sys.argv[2]
root = tk.Tk(); root.geometry('460x260+40+40')
if how == 'columns':
    emoji_color.emoji_columns(root)          # its probe Text comes first
else:
    pane = tk.Text(root, font=(first, 11), height=3); pane.pack()
    observe_text(pane)
    pane.insert('1.0', 'a\U0001F600b a\U0001F468‍\U0001F469‍\U0001F467b a\U0001F525b a\U0001F44D\U0001F3FDb')
    root.update()
w = tk.Text(root, font=('Meiryo', 11), padx=14, pady=12, bg='#f0f0ed'); w.pack(fill='both', expand=True)
o = emoji_color.install(w)
if o is None:
    print('RESULT ' + json.dumps(None)); sys.exit()
root.update()
w.insert('1.0', 'a❤️b\na\U0001F600b\na\U0001F468‍\U0001F469‍\U0001F467b\na\U0001F525b\na\U0001F44D\U0001F3FDb')
for _ in range(3):
    o.refresh(); root.update()
out = {'tk': str(root.tk.call('info', 'patchlevel')),
       'labels': [[p[4], p[2]] for p in o.placements()]}
print('RESULT ' + json.dumps(out, ensure_ascii=False))
root.destroy()
'''


def run_child(first, how='pane'):
    r = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', CHILD, first, how], cwd=HERE,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8', timeout=120)
    line = next((l for l in r.stdout.splitlines() if l.startswith('RESULT ')), None)
    if line is None:
        raise AssertionError(r.stdout[-2000:])
    return json.loads(line[7:])


@unittest.skipUnless(sys.platform == 'win32', 'Direct2D on Windows')
class FirstFontTests(unittest.TestCase):
    def check(self, got):
        if got is None:
            self.skipTest('Direct2D unavailable')
        widths = [w for _, w in got['labels']]
        self.assertEqual(len(widths), 5, got)
        self.assertLessEqual(max(widths) - min(widths), 1, got)

    def test_emoji_take_one_room_whichever_font_showed_them_first(self):
        for first in ('MS Gothic', 'BIZ UDGothic', 'Yu Mincho', 'Meiryo UI', 'Meiryo', 'Arial'):
            with self.subTest(first=first):
                self.check(run_child(first))

    def test_the_columns_probe_does_not_narrow_an_emoji(self):
        self.check(run_child('', 'columns'))


class PrimeTests(unittest.TestCase):
    def fake(self, level):
        widget = mock.Mock()
        widget.tk.call.side_effect = lambda *a: level if a[:2] == ('info', 'patchlevel') else 0
        return widget

    def test_tk_869_is_left_alone(self):
        widget = self.fake('8.6.9')
        with mock.patch.object(emoji_color, '_PRIMED', set()), \
                mock.patch.object(emoji_color, '_PRIMES', {}), \
                mock.patch.object(emoji_color.sys, 'platform', 'win32'):
            emoji_color.prime(widget, 'a\U0001F600b')
            self.assertEqual(emoji_color._PRIMED, set())
        measured = [c for c in widget.tk.call.call_args_list if c.args[:2] == ('font', 'measure')]
        self.assertEqual(measured, [])

    def test_only_new_emoji_are_asked_once(self):
        widget = self.fake('8.6.12')
        with mock.patch.object(emoji_color, '_PRIMED', set()), \
                mock.patch.object(emoji_color, '_PRIMES', {}), \
                mock.patch.object(emoji_color.sys, 'platform', 'win32'):
            emoji_color.prime(widget, 'a\U0001F600\U00020BB7b')      # 𠮷 is not an emoji
            emoji_color.prime(widget, '\U0001F600\U0001F525')
        measured = [c.args[3] for c in widget.tk.call.call_args_list if c.args[:2] == ('font', 'measure')]
        self.assertEqual(measured, ['\U0001F600', '\U0001F525'])


if __name__ == '__main__':
    unittest.main()
