# -*- coding: utf-8 -*-
"""類語の段（synonyms.py・wlsp_synonyms.json.gz・2026-10-26 うにさん「分類語彙表の全部を入れて、候補欄に
類語の段を作る」）。

- 同じ分類番号・段落・小段落の語が、意味ごとの組で出る（意見 → 声・忠告 が別の組）
- 用言は元の活用に合わせる（食べた → 食った・大きかった → でかかった）。副詞はそのまま（とても → 随分）
- 英字の語・代名詞には出さない。同じ読みの書き分け（早く → はやく・速く）は類語にしない
- 候補欄に「― 類語 ―」の段が出て、押すと語が入れ替わり、元に戻す1手で戻る（選び直しとしては覚えない）
"""
import types
import unittest
from unittest.mock import Mock

import synonyms


def flat(senses):
    return [w for group in senses for w in group]


@unittest.skipUnless(synonyms.available(), 'wlsp_synonyms.json.gz が無い')
class SynonymTests(unittest.TestCase):
    def test_table_keeps_every_class_and_the_licence(self):
        import gzip, json, os
        with gzip.open(os.path.join(os.path.dirname(synonyms.__file__), synonyms.TABLE), 'rt',
                       encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('CC BY-NC-SA 3.0', data['license'])
        self.assertIn('国立国語研究所', data['license'])
        self.assertIn('masayu-a/WLSP', data['source'])
        classes = {e[0] for entries in data['words'].values() for e in entries}
        self.assertEqual(classes, {'体', '用', '相', '他'})
        self.assertEqual(data['words']['意見'][0], ['体', '1.3061', '11', '01'])
        self.assertIn('大きな', data['words'])          # 大きい／な をほどいた形

    def test_words_walks_every_headword(self):
        # 補正の semantic_class・文変換の context_skeleton が使う公開の回し方（Table._words の代わり）
        table = synonyms.load_table()
        got = dict(table.words())
        self.assertEqual(len(got), 79613)
        self.assertEqual(got['意見'], table.entries('意見'))
        self.assertIn(['体', '1.3061', '11', '01'], got['意見'])
        self.assertTrue(all(len(e) == 4 for entries in got.values() for e in entries))
        self.assertEqual(dict(synonyms.Table().words()), {})

    def test_senses_come_in_groups(self):
        got = synonyms.synonyms('意見')
        where = {w: i for i, group in enumerate(got) for w in group}
        self.assertIn('声', where)
        self.assertIn('忠告', where)
        self.assertNotEqual(where['声'], where['忠告'])        # 別の意味の組
        self.assertNotIn('意見', where)

    def test_inflection_follows_the_original(self):
        self.assertIn('食った', flat(synonyms.synonyms('食べた')))
        self.assertIn('でかかった', flat(synonyms.synonyms('大きかった')))
        self.assertIn('問うた', flat(synonyms.synonyms('聞いた')))     # ウ音便
        self.assertIn('随分', flat(synonyms.synonyms('とても')))
        for word in flat(synonyms.synonyms('食べます')):
            self.assertTrue(word.endswith('ます'), word)

    def test_limits(self):
        got = synonyms.synonyms('ゆっくり')
        self.assertTrue(all(len(group) <= synonyms.PER_SENSE for group in got))
        self.assertLessEqual(len(flat(got)), synonyms.TOTAL)

    def test_left_alone(self):
        for word in ('big', 'Hello', '彼', '1', '', '早く'):
            self.assertEqual(synonyms.synonyms(word), [], word)


@unittest.skipUnless(synonyms.available(), 'wlsp_synonyms.json.gz が無い')
class SynonymMenuTests(unittest.TestCase):
    """候補欄の段と入れ替え（tests_gui_editing と同じ、作りかけの app の上で）。"""

    def setUp(self):
        import tkinter as tk
        import app
        self.root = tk.Tk()
        self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root, undo=True)
        a.status = Mock()
        a._mark_typed = Mock()
        a._invalidate_units_cache = Mock()
        a._on_change = Mock()
        a.editor.insert('1.0', '昨日はたくさん食べた。')
        a.editor.edit_separator()

    def tearDown(self):
        self.a = None
        self.root.destroy()

    def test_section_and_replace_and_undo(self):
        a = self.a
        unit = dict(text='食べた', start=7, end=10, kind='word')
        chosen = []
        items = a._synonym_menu_items(unit, chosen.append)
        self.assertEqual(items[0], (a.SYNONYM_HEAD, None))
        labels = [label.strip() for label, cb in items if cb is not None]
        self.assertIn('食った', labels)
        # 押すと入れ替わる
        cb = next(cb for label, cb in items if label.strip() == '食った')
        a._replace_unit_text(a.editor, 1, unit, '食った')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '昨日はたくさん食った。')
        a._mark_typed.assert_called_once_with(1, 7, 10)
        a._on_change.assert_called_once()
        # 元に戻す1手で戻る
        a.editor.edit_undo()
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '昨日はたくさん食べた。')
        # 押した関数は choose に語を渡す
        cb()
        self.assertEqual(chosen, ['食った'])

    def test_no_section_for_particles_ranges_and_english(self):
        a = self.a
        self.assertEqual(a._synonym_menu_items(dict(text='は', functional=True), print), [])
        self.assertEqual(a._synonym_menu_items(dict(text='食べた', kind='range'), print), [])
        self.assertEqual(a._synonym_menu_items(dict(text='big'), print), [])

    def test_stale_unit_is_not_replaced(self):
        a = self.a
        a._replace_unit_text(a.editor, 1, dict(text='走った', start=7, end=10), '駆けた')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '昨日はたくさん食べた。')

    def test_result_pane_replaces_the_source_range(self):
        # 左右に並べた表示の補正欄で押すと、本文の対応する範囲が入れ替わる（2026-10-26 うにさん「補正欄から類語が出ません」）
        import tkinter as tk
        a = self.a
        a.result_view = tk.Text(self.root)
        a.editor.delete('1.0', 'end')
        a.editor.insert('1.0', 'とてもおおきかった。去年')
        a.editor.edit_separator()
        a.result_view.insert('1.0', 'とても大きかった。去年')      # 補正欄は直った形（おおきかった → 大きかった）
        unit = dict(text='大きかった', start=3, end=8, kind='word')
        items = a._synonym_menu_items(unit, lambda t: a._replace_result_unit_in_source(1, unit, t))
        labels = [label.strip() for label, cb in items if cb is not None]
        self.assertIn('でかかった', labels)
        cb = next(cb for label, cb in items if label.strip() == 'でかかった')
        cb()
        self.assertEqual(a.editor.get('1.0', 'end-1c'), 'とてもでかかった。去年')
        a.editor.edit_undo()
        self.assertEqual(a.editor.get('1.0', 'end-1c'), 'とてもおおきかった。去年')

    def test_result_pane_undo_and_redo_reach_the_source(self):
        # 補正欄で類語を選んだあと、補正欄の Ctrl+Z（<<Undo>>）で選ぶ前の本文に戻り、Ctrl+Y（<<Redo>>）で
        # 類語に戻る（2026-10-27 うにさん「補正欄で再変換候補から類語を選ぶと、Undoで戻せない」）。
        # 本物のキーは送らず、補正欄に仮想の出来事を起こす
        import tkinter as tk
        a = self.a
        a.result_view = tk.Text(self.root)
        a.editor.delete('1.0', 'end')
        a.editor.insert('1.0', 'とてもおおきかった。去年')
        a.editor.edit_reset()       # 開いたばかりの本文（ここより前には戻らない）
        a.result_view.insert('1.0', 'とても大きかった。去年')
        a.result_view.configure(state='disabled')       # 本物の補正欄と同じく編集不可
        a._bind_result_undo()
        unit = dict(text='大きかった', start=3, end=8, kind='word')
        a._replace_result_unit_in_source(1, unit, 'でかかった')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), 'とてもでかかった。去年')
        a._on_change.reset_mock()
        a.result_view.event_generate('<<Undo>>')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), 'とてもおおきかった。去年')
        a._on_change.assert_called_once()
        a.result_view.event_generate('<<Redo>>')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), 'とてもでかかった。去年')
        # 戻すものが無くなっても落ちない
        for _ in range(5):
            a.result_view.event_generate('<<Undo>>')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), 'とてもおおきかった。去年')

    def test_memo_pane_undo_and_redo(self):
        # メモ欄で類語を選んだときも、メモ欄の Ctrl+Z（<<Undo>>）1回で戻り、Ctrl+Y（<<Redo>>）でやり直せる
        a = self.a
        unit = dict(text='食べた', start=7, end=10, kind='word')
        a._replace_unit_text(a.editor, 1, unit, '食った')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '昨日はたくさん食った。')
        a.editor.event_generate('<<Undo>>')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '昨日はたくさん食べた。')
        a.editor.event_generate('<<Redo>>')
        self.assertEqual(a.editor.get('1.0', 'end-1c'), '昨日はたくさん食った。')

    def test_english_heading(self):
        import ui_lang_en
        self.assertEqual(ui_lang_en.TABLE[self.a.SYNONYM_HEAD], '― Synonyms ―')


if __name__ == '__main__':
    unittest.main()
