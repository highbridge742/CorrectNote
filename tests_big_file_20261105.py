# -*- coding: utf-8 -*-
"""A very large file does not stop the app: no learning from it, no character-by-character comparison, no splitting of
the whole text for each slice of painting (2026-11-05 うにさん: dropping the file with the most characters froze the app,
and it froze again after each restart). No window. Made-up text."""
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import app
import boundary_colors


class Learning(unittest.TestCase):
    def fake(self):
        a = SimpleNamespace(_learn_after_id=1, _learned_lines=set(), LEARN_MAX_CHARS=app.CorrectNoteApp.LEARN_MAX_CHARS,
                            english=[], background=[], line_results=[], _analyze_text='')
        a._learn_english_soon = a.english.append
        a._learn_tokens_in_background = a.background.append
        a._autofix_written_masks = lambda: {}
        return a

    def test_a_huge_text_is_not_learned_at_all(self):
        a = self.fake()
        app.CorrectNoteApp._learn_now(a, '語' * (a.LEARN_MAX_CHARS + 1))
        self.assertEqual(a.english, [])
        self.assertEqual(a.background, [])

    def test_a_long_row_is_left_out_and_the_others_are_learned(self):
        a = self.fake()
        long_row = 'x' * 5000
        with mock.patch('janome_import.HAS_JANOME', True):
            app.CorrectNoteApp._learn_now(a, '今日の文です。\n' + long_row + '\n明日の文です。')
        self.assertEqual(a.english, ['今日の文です。\n明日の文です。'])
        self.assertEqual(a.background, ['今日の文です。\n明日の文です。'])

    def test_an_ordinary_text_is_as_before(self):
        a = self.fake()
        with mock.patch('janome_import.HAS_JANOME', True):
            app.CorrectNoteApp._learn_now(a, '今日の文です。\n明日の文です。')
        self.assertEqual(a.english, ['今日の文です。\n明日の文です。'])
        self.assertEqual(a.background, ['今日の文です。\n明日の文です。'])


class LongRowQuestion(unittest.TestCase):
    def ask(self, content, answer=True):
        a = SimpleNamespace(ASK_ROW_CHARS=app.CorrectNoteApp.ASK_ROW_CHARS, root=None)
        with mock.patch.object(app.messagebox, 'askyesno', return_value=answer) as box:
            got = app.CorrectNoteApp._agree_to_long_row(a, 'x.json', content)
        return got, box.call_count

    def test_an_ordinary_file_is_not_asked_about(self):
        self.assertEqual(self.ask('short\n' * 100000), (True, 0))
        self.assertEqual(self.ask('x' * (app.CorrectNoteApp.ASK_ROW_CHARS - 1)), (True, 0))

    def test_a_very_long_row_is_asked_about(self):
        self.assertEqual(self.ask('x' * app.CorrectNoteApp.ASK_ROW_CHARS, True), (True, 1))
        self.assertEqual(self.ask('x' * app.CorrectNoteApp.ASK_ROW_CHARS, False), (False, 1))


class LongRowWords(unittest.TestCase):
    def test_the_question_as_the_owner_worded_it_in_both_languages(self):
        import ui_lang, ui_lang_en
        a = SimpleNamespace(ASK_ROW_CHARS=1, root=None)
        with mock.patch.object(app.messagebox, 'askyesno', return_value=True) as box:
            app.CorrectNoteApp._agree_to_long_row(a, 'x.json', 'ab')
        title, message = box.call_args.args
        self.assertEqual(message, 'x.json' + chr(10) * 2 + 'ファイルの容量が大きいため、開くのに時間が掛かります。開いてよろしいですか？')
        table = ui_lang._table('en')
        self.assertEqual(ui_lang._translate(table, message), 'x.json' + chr(10) * 2 + 'This file is large, so it will take time to open. Do you want to open it?')
        self.assertEqual(ui_lang._translate(table, title), 'Confirm')


class ImeReadings(unittest.TestCase):
    def fake(self, text):
        kept = []
        return SimpleNamespace(ime_readings=SimpleNamespace(keep_only_in=kept.append), kept=kept,
                               session=SimpleNamespace(tabs=[dict(text=text)]), LEARN_MAX_CHARS=app.CorrectNoteApp.LEARN_MAX_CHARS,
                               editor_source_text=lambda: text)

    def test_not_with_a_huge_tab_open(self):
        a = self.fake('語' * (app.CorrectNoteApp.LEARN_MAX_CHARS + 1))
        app.CorrectNoteApp._prune_ime_readings(a)
        self.assertEqual(a.kept, [])

    def test_as_before_otherwise(self):
        a = self.fake('今日の文です。')
        app.CorrectNoteApp._prune_ime_readings(a)
        self.assertEqual(len(a.kept), 1)


class ChangedSpan(unittest.TestCase):
    def slow(self, before, after):
        if before == after:
            return None
        head = 0
        n = min(len(before), len(after))
        while head < n and before[head] == after[head]:
            head += 1
        tail = 0
        while tail < n - head and before[len(before) - 1 - tail] == after[len(after) - 1 - tail]:
            tail += 1
        return head, len(before) - tail

    def test_the_same_span_as_comparing_each_character(self):
        cases = [('', ''), ('', 'a'), ('a', ''), ('abc', 'abc'), ('abc', 'abd'), ('abc', 'xbc'), ('abcabc', 'abc'), ('abc', 'abcabc'),
                 ('aaaa', 'aa'), ('aa', 'aaaa'), ('abXcd', 'abcd'), ('abcd', 'abYYcd'), ('😀a', '😀b'), ('a\nb', 'a\nc\nb')]
        for before, after in cases:
            self.assertEqual(app.CorrectNoteApp._changed_span(before, after), self.slow(before, after), (before, after))

    def test_a_large_text_is_quick(self):
        before = 'あ' * 8000000
        after = before[:4000000] + 'ん' + before[4000000:]
        t = time.perf_counter()
        self.assertEqual(app.CorrectNoteApp._changed_span(after, before), (4000000, 4000001))
        self.assertLess(time.perf_counter() - t, 1.0)


if __name__ == '__main__':
    unittest.main()
