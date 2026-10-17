# -*- coding: utf-8 -*-
"""End / Shift+End on a wrapped line never leave the cursor inside a character.

2026-10-17 うにさん「折り返しの行末の文字が化ける」: Tk's `display lineend`
can point inside a multi-byte character on the display rows of a wrapped
line. End and Shift+End use it; the character then shows as 「ã」
and two invisible ones, and typing there stores the split bytes. The edit
observer replaces it with the same place computed from indexes that never split.
Only made-up text is used.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from analysis_work import observe_text

LINES = ('「メニュー」を開いて「縮小表示 ― 右ダブルクリック」「Ctrl＋左右キーで移動」にGIFを入れる予定です。'
         'もう少し長くして、折り返しが何度も起きるようにします。',
         'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん、でした。',
         'This English line wraps too, so the same keys are checked without multi-byte characters.')
NL = chr(10)


def split_chars(text):
    return [hex(ord(c)) for c in text if '\u0080' <= c <= 'ÿ']


class LineEndTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry('+40+40')
        self.text = tk.Text(self.root, font=('Yu Gothic UI', 11), wrap='word', width=30, undo=True)
        self.text.pack()
        observe_text(self.text, lambda *a: None)
        self.raw = self.text._w + '_correctnote_work'
        self.plain = tk.Text(self.root, font=('Yu Gothic UI', 11), wrap='word', width=30)
        self.plain.pack()

    def tearDown(self):
        self.root.destroy()

    def layouts(self):
        """(line, width, wrap, display rows) for many widths."""
        for line in LINES:
            for width in range(18, 64, 3):
                for wrap in ('word', 'char'):
                    for w in (self.text, self.plain):
                        w.configure(width=width, wrap=wrap)
                        w.delete('1.0', 'end')
                        w.insert('1.0', line)
                    self.root.update()
                    count = self.text.count('1.0', '1.end', 'displaylines')
                    yield line, width, wrap, (int(count[0]) if count else 0) + 1

    def reset(self, line):
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', line)
        self.root.update()

    def test_end_and_shift_end_then_typing_never_split_a_character(self):
        self.text.focus_force()
        cases = 0
        for line, width, wrap, rows in self.layouts():
            for k in range(rows):
                for key in ('End', 'Shift-End'):
                    self.reset(line)
                    self.text.mark_set('insert', self.text.index('1.0 + %d display lines display linestart' % k))
                    self.text.event_generate('<%s>' % key)
                    self.text.insert('insert', NL)
                    self.text.insert('insert', '「')
                    got = self.text.get('1.0', 'end-1c')
                    cases += 1
                    with self.subTest(width=width, wrap=wrap, row=k, key=key):
                        self.assertEqual(split_chars(got), [])
                        self.assertEqual(got.replace(NL, '').replace('「', ''), line.replace('「', ''))
        self.assertGreater(cases, 300)

    def test_same_place_as_tk_where_tk_does_not_split(self):
        compared = 0
        for line, width, wrap, rows in self.layouts():
            for k in range(rows):
                expr = '1.0 + %d display lines display lineend' % k
                # Tk's own answer (the observer bypassed) and whether it splits a character.
                self.text.tk.call(self.raw, 'mark', 'set', 'probe', expr)
                self.text.tk.call(self.raw, 'insert', 'probe', 'X')
                splits = bool(split_chars(str(self.text.tk.call(self.raw, 'get', '1.0', 'end-1c'))))
                self.reset(line)
                if splits:
                    continue
                native = str(self.text.tk.call(self.raw, 'index', expr))
                with self.subTest(width=width, wrap=wrap, row=k):
                    self.assertEqual(self.text.index(expr), native)
                compared += 1
        self.assertGreater(compared, 50)

    def test_text_saying_the_words_is_stored_as_typed(self):
        for words in ('end display lineend', '1.0 display lineend', 'x display lineend y'):
            self.text.delete('1.0', 'end')
            self.text.insert('1.0', words)
            self.text.replace('1.0', 'end-1c', words + words)
            with self.subTest(words=words):
                self.assertEqual(self.text.get('1.0', 'end-1c'), words + words)
                self.assertEqual(self.text.search(words, '1.0'), '1.0')

    def test_other_moves_are_unchanged(self):
        self.text.focus_force()
        for line, width, wrap, rows in self.layouts():
            for k in range(rows):
                for keys in (('Right',) * 5, ('Down',), ('Up',), ('Home',), ('Left',) * 3):
                    for w in (self.text, self.plain):
                        w.mark_set('insert', w.index('1.0 + %d display lines display linestart' % k))
                        w.focus_force()
                        # ↑↓ keep the column in ::tk::Priv, shared by both widgets.
                        w.tk.eval('array unset ::tk::Priv prevPos')
                        for key in keys:
                            w.event_generate('<%s>' % key)
                    with self.subTest(width=width, wrap=wrap, row=k, keys=keys):
                        self.assertEqual(self.text.index('insert'), self.plain.index('insert'))
            for y in range(2, self.text.winfo_height(), 9):
                for x in range(0, self.text.winfo_width(), 23):
                    with self.subTest(width=width, wrap=wrap, x=x, y=y):
                        self.assertEqual(self.text.index('@%d,%d' % (x, y)), self.plain.index('@%d,%d' % (x, y)))


def child():
    """The real app (copied folder, made-up text): End, Enter and 「 on every wrapped row."""
    sys.path.insert(0, os.getcwd())
    import app
    from session import new_tab
    mult = {'名詞': 1.1, '動詞': 1.1, '形容詞': 1.1, '副詞': 1.1, '助動詞': 1.1, '数詞': 1.2}
    Path('settings.json').write_text(json.dumps(dict(
        layout='split', input_method='kana', input_method_auto=False, show_ctrl_boundaries=True,
        pos_font_multipliers=mult, theme='sumi', decor='nami')), encoding='utf8')
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=LINES[0])])),
                                    encoding='utf8')
    root = tk.Tk()
    a = None
    out = dict(cases=0, split=[])
    try:
        with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
                patch.object(app.CorrectNoteApp, '_learn_now', lambda *args: None):
            a = app.CorrectNoteApp(root)
            w = a.editor
            end = time.monotonic() + 3
            while time.monotonic() < end:
                root.update()
                time.sleep(0.01)
            for width in range(700, 1300, 37):
                root.geometry('%dx520+40+40' % width)
                for _ in range(20):
                    root.update()
                count = w.count('1.0', '1.end', 'displaylines')
                rows = (int(count[0]) if count else 0) + 1
                for k in range(1, rows):
                    w.delete('1.0', 'end')
                    w.insert('1.0', LINES[0])
                    a._on_change()
                    root.update()
                    w.focus_force()
                    w.mark_set('insert', w.index('1.0 + %d display lines display linestart' % k))
                    w.event_generate('<End>')
                    w.insert('insert', NL + '「')
                    a._on_change()
                    root.update()
                    out['cases'] += 1
                    bad = split_chars(w.get('1.0', 'end-1c'))
                    if bad:
                        out['split'].append((width, k, bad[:4]))
            print('RESULT ' + json.dumps(out, ensure_ascii=False), flush=True)
    finally:
        if a:
            a._on_close()
        else:
            root.destroy()


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class AppLineEndTests(unittest.TestCase):
    def test_end_enter_and_bracket_in_the_real_editor(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-lineend-') as folder:
            dest = Path(folder)
            for path in source.iterdir():
                if path.is_file() and (path.suffix == '.py' or path.name in NAMES):
                    shutil.copyfile(path, dest / path.name)
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                                 cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf8',
                                 timeout=300)
            line = next((l for l in run.stdout.splitlines() if l.startswith('RESULT ')), None)
            self.assertIsNotNone(line, run.stdout[-3000:])
            r = json.loads(line[7:])
        self.assertGreater(r['cases'], 10)
        self.assertEqual(r['split'], [])


if __name__ == '__main__':
    if '--child' in sys.argv:
        child()
    else:
        unittest.main()
