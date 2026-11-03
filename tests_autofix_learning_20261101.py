# -*- coding: utf-8 -*-
"""統合表示の自動反映で書き換えた字を、「打った文」として学ばない（app._autofix_keep_written・2026-11-01・
うにさん 10-22「学習で補正を悪くしない」）。

自動反映の控えが生きている間は原文（editor_source_text）を学ぶので、自動の字は入らない。行を自分で書き換えると
控えが落ち、自動で直した字が原文になって語彙に入っていた。落とすときにその行に残った自動の字（fixed）を覚え、
学習の前に消す。自分で選び直した字（chosen）と、自分で打った字は今どおり学ぶ。"""
import tkinter as tk
import unittest
from types import SimpleNamespace

import app


class AutofixLearningTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root)
        a.learned = []
        a._learn_english_now = lambda text: None
        a._learned_lines = set()
        a.line_results = []
        a._analyze_text = ''
        a._learn_tokens_in_background = a.learned.append
        a._apply_learned_tokens = lambda tokens, text: a.learned.append(text)

    def tearDown(self):
        self.root.destroy()

    def drop_after_edit(self, applied, spans, now):
        """自動反映した行（applied）を、自分で now に書き換えた（控えが落ちる）。"""
        self.a.editor.delete('1.0', 'end')
        self.a.editor.insert('1.0', now)
        rec = {'applied': applied, 'spans': spans, 'pane': 'editor'}
        self.a._autofix_keep_written(rec, 1, now)

    def learn(self, text):
        self.a._analyze_text = text
        self.a._learn_now(text)
        return self.a.learned[-1]

    def test_an_automatic_fix_left_in_an_edited_row_is_not_learned(self):
        self.drop_after_edit('野外文章の例', ((0, 2, 'fixed', 'やがい'),), '野外文章の例です')
        got = self.learn('野外文章の例です')
        self.assertNotIn('野外', got)
        self.assertIn('文章の例です', got)

    def test_a_chosen_word_and_typed_words_are_learned(self):
        self.drop_after_edit('会議の資料', ((3, 5, 'chosen', 'しりょう'),), '会議の資料を作る')
        self.assertEqual(self.learn('会議の資料を作る'), '会議の資料を作る')

    def test_other_rows_and_a_removed_fix_are_learned(self):
        self.drop_after_edit('野外文章', ((0, 2, 'fixed', 'やがい'),), '野外文章')
        self.a.editor.insert('end', '\n野外で遊ぶ')
        self.assertIn('野外で遊ぶ', self.learn('野外文章\n野外で遊ぶ').split('\n'))
        self.a.editor.delete('1.0', '1.end')
        self.a.editor.insert('1.0', '長い文章')                # 自動の字を自分で消した
        self.assertEqual(self.a._autofix_written_masks(), {})


if __name__ == '__main__':
    unittest.main()
