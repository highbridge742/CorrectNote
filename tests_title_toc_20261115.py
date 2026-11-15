# -*- coding: utf-8 -*-
"""本文の上のタイトルと目次の決まり（2026-11-15 うにさん「タイトルと目次を実装します」「本文の1行目として保存します。
また、その下は空白行として保存する」）。画面を使わない決まりだけ（作った例文）。"""
import os
import tempfile
import unittest
from unittest import mock

import file_format as fmt
import title_toc as T


class Toc(unittest.TestCase):
    def test_bookmarked_rows_with_text(self):
        lines = ['はじめに', '本文です。', 'まとめ']
        self.assertEqual(T.toc_entries(lines, {1, 3}), [(1, 1, 'はじめに'), (3, 3, 'まとめ')])

    def test_blank_bookmark_mirrors_the_next_written_row(self):
        lines = ['', '  ', '第一章', '本文', '', '第二章']
        self.assertEqual(T.toc_entries(lines, {1, 5}), [(1, 3, '第一章'), (5, 6, '第二章')])

    def test_blank_until_the_next_bookmark_is_left_out(self):
        lines = ['', '', '第二章']
        self.assertEqual(T.toc_entries(lines, {1, 3}), [(3, 3, '第二章')])

    def test_blank_last_row_is_left_out(self):
        lines = ['第一章', '本文', '']
        self.assertEqual(T.toc_entries(lines, {1, 3}), [(1, 1, '第一章')])

    def test_no_bookmarks_no_toc(self):
        self.assertEqual(T.toc_entries(['あ', 'い'], set()), [])
        self.assertEqual(T.toc_entries(['あ'], {5, 0, 'x'}), [])     # 範囲の外・変な値は無視

    def test_text_is_trimmed(self):
        self.assertEqual(T.toc_entries(['　見出し  '], {1}), [(1, 1, '見出し')])


class SaveAs(unittest.TestCase):
    def test_empty_title_takes_the_file_name(self):
        self.assertEqual(T.title_for_save_as('', r'C:\docs\旅のメモ.txt'), '旅のメモ')
        self.assertEqual(T.title_for_save_as('  ', '/x/a.b.txt'), 'a.b')

    def test_written_title_stays(self):
        self.assertEqual(T.title_for_save_as('旅行記', r'C:\docs\旅のメモ.txt'), '旅行記')

    def test_one_line(self):
        self.assertEqual(T.one_line('一行目\n二行目'), '一行目')


class FileRoundTrip(unittest.TestCase):
    def setUp(self):
        os.environ.pop('CN_TITLE_TOC', None)
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, 'memo.txt')

    def write(self, title, body, metadata=None):
        text, meta = T.compose_for_save(title, body, metadata, fmt)
        with open(self.path, 'wb') as f:
            f.write(fmt.encode(text, meta))
        T.save_record(self.folder, self.path, title)

    def read(self):
        with open(self.path, 'rb') as f:
            content, meta = fmt.decode(f.read())
        return T.split_loaded(content, meta, self.path, self.folder, fmt)

    def test_title_round_trip(self):
        body = '一行目\n\n三行目'
        self.write('旅行記', body)
        raw = open(self.path, 'rb').read().decode('utf-8')
        self.assertEqual(raw.replace('\r\n', '\n'), '旅行記\n\n一行目\n\n三行目')     # 頭にタイトル＋空白行
        got, meta, title = self.read()
        self.assertEqual((got, title), (body, '旅行記'))
        # 本文の行番号（ブックマーク）はずれない: 読み込んだ本文は保存前の本文と同じ行数・同じ並び
        self.assertEqual(got.split('\n'), body.split('\n'))

    def test_no_title_adds_no_rows(self):
        body = 'あ\nい'
        self.write('', body)
        self.assertEqual(open(self.path, 'rb').read().decode('utf-8').replace('\r\n', '\n'), body)
        self.assertEqual(self.read(), (body, fmt.decode(open(self.path, 'rb').read())[1], ''))

    def test_unrecorded_first_line_and_blank_is_body(self):
        with open(self.path, 'w', encoding='utf-8', newline='') as f:
            f.write('見出し\r\n\r\n本文')                 # 外で作った「1行目＋空白行」のファイル
        got, _meta, title = self.read()
        self.assertEqual((got, title), ('見出し\n\n本文', ''))

    def test_record_differs_from_the_first_line(self):
        self.write('旅行記', '本文')
        with open(self.path, 'w', encoding='utf-8', newline='') as f:
            f.write('別の見出し\r\n\r\n本文')             # 外で1行目を書き換えた
        got, _meta, title = self.read()
        self.assertEqual((got, title), ('別の見出し\n\n本文', ''))

    def test_second_row_not_blank_is_body(self):
        self.write('旅行記', '本文')
        with open(self.path, 'w', encoding='utf-8', newline='') as f:
            f.write('旅行記\r\n続き\r\n本文')
        self.assertEqual(self.read()[2], '')

    def test_mixed_endings_are_kept(self):
        body = 'a\nb\nc'
        meta = {'encoding': 'utf-8', 'newline': 'w', 'endings': 'lw', 'tail': ''}
        self.write('題', body, meta)
        got, back, title = self.read()
        self.assertEqual((got, title), (body, '題'))
        self.assertEqual(back['endings'], 'lw')

    def test_switch_off_changes_nothing(self):
        with mock.patch.dict(os.environ, {'CN_TITLE_TOC': '0'}):
            text, meta = T.compose_for_save('旅行記', '本文', None, fmt)
            self.assertEqual(text, '本文')
            self.write('旅行記', '本文')
            self.assertEqual(self.read()[2], '')

    def test_record_removed_when_title_cleared(self):
        self.write('旅行記', '本文')
        self.assertIn(T._key(self.path), T.load_records(self.folder))
        self.write('', '本文')
        self.assertNotIn(T._key(self.path), T.load_records(self.folder))


class Savedata(unittest.TestCase):
    def test_record_moves_to_savedata(self):
        import app
        self.assertIn('doc_titles.json', app.SAVEDATA_NAMES)

    def test_session_keeps_the_title_apart(self):
        from session import new_tab
        tab = new_tab(text='本文', title='タブの名前', doc_title='旅行記\n余分')
        self.assertEqual(tab['doc_title'], '旅行記')
        self.assertEqual(tab['title'], 'タブの名前')
        self.assertEqual(tab['text'], '本文')                   # 本文にはタイトルを入れない
        self.assertNotIn('doc_title', new_tab(text='本文'))


if __name__ == '__main__':
    unittest.main()
