"""変換ウィンドウの試験（2026-10-26）。python -X utf8 -m unittest tests_convert_window_20261026"""
import os
import unittest

import convert_window as cw

# 試験では外のアプリへ貼らない（16:05Z、うにさんの窓へ本物の Ctrl+V が送られた）
os.environ['CORRECTNOTE_NO_EXTERNAL_PASTE'] = '1'
cw.ConvertWindow._paste_outside = lambda self, text, to_clip, tries=6: False


class TestReorderings(unittest.TestCase):
    def test_unis_example(self):
        # うにさん 04:46Z の例（このケースで要る並び）
        got = cw.reorderings('友達と映画館で映画を見た。')
        for want in ('映画を友達と映画館で見た。', '映画を映画館で友達と見た。'):
            self.assertIn(want, got)
        # うにさん 16:12Z: 助詞で終わる並びは出さない
        self.assertNotIn('映画を見た。友達と映画館で。', got)
        self.assertNotIn('友達と映画館で映画を見た。', got)
        # 原文の最初の文節（友達と）が頭のものから、次に映画館で、映画を、述語が頭のものは最後
        heads = [next(h for h in ('友達と', '映画館で', '映画を', '見た') if g.startswith(h)) for g in got]
        order = ['友達と', '映画館で', '映画を', '見た']
        self.assertEqual(heads, sorted(heads, key=order.index))
        self.assertEqual(len(got), len(set(got)))

    def test_predicate_moves_forward(self):
        got = cw.reorderings('家族で週末に出掛けた。')
        self.assertEqual(got, ['週末に家族で出掛けた。'])

    def test_parallel_to_stays_together(self):
        got = cw.reorderings('猫と犬が庭で遊ぶ。')
        self.assertNotIn('庭で遊ぶ。猫と犬が。', got)
        self.assertFalse(any(s.startswith('犬が') for s in got))

    def test_ni_naru_kept_with_predicate(self):
        for s in cw.reorderings('雨で試合が中止になった。'):
            self.assertIn('中止になった', s)

    def test_comma_kept_inside(self):
        got = cw.reorderings('彼は、昨日の夜、駅前で友達に会ったらしい。')
        self.assertIn('彼は、駅前で友達に会ったらしい。昨日の夜。', got)
        self.assertNotIn('彼は、昨日の夜、駅前で会ったらしい。友達に。', got)

    def test_limit(self):
        got = cw.reorderings('昨日、彼は駅前で友達に本を渡したらしい。')
        self.assertLessEqual(len(got), cw._LIMIT)

    def test_many_phrases_fast(self):
        # 文節が多くても全部の並べ替えは作らない（v3 は 8文節 1.9秒・9文節 約20秒だった）
        import time
        s = '去年の夏、兄は、友達と、車で、海へ、朝早く、静かに、楽しく、のんびり、ゆっくり、出かけた。'
        self.assertGreaterEqual(len(cw.phrases(s)[0]), 9)
        t = time.time()
        got = cw.reorderings(s)
        self.assertLess(time.time() - t, 0.5)
        self.assertEqual(len(got), cw._LIMIT)

    def test_fragment_uses_comma(self):
        # うにさん 14:50Z: 述語で終わらない句は区切りも末尾も読点
        got = cw.reorderings('そこからすぐ上は')
        self.assertIn('そこから上は、すぐ、', got)
        self.assertFalse(any('。' in g for g in got))

    def test_noun_ending_uses_full_stop(self):
        # うにさん 15:59Z: 名詞で終わる句は区切りは読点・末尾は句点
        got = cw.reorderings('考えを文章にするメモ帳、CorrectNote')
        self.assertTrue(got and all(g.endswith('。') and g.count('。') == 1 for g in got))
        self.assertIn('CorrectNote、考えを文章にするメモ帳。', got)

    def test_bracket_note_no_separator(self):
        # うにさん 14:53Z: 括弧の注は中間に句点が要らない
        self.assertEqual(cw.reorderings('くぅーん（犬の鳴き声）'), ['（犬の鳴き声）くぅーん'])

    def test_english_unreadable_hidden(self):
        self.assertIsNone(cw.english_order('くぅーん（犬の鳴き声）'))
        self.assertFalse(cw.english_order('友達と映画館で映画を見た。').startswith('(I)'))

    def test_comma_kept_unless_last(self):
        got = cw.reorderings('アタシはほら、かよわい女の子なんだから。')
        self.assertIn('アタシはかよわい女の子なんだから。ほら。', got)
        self.assertNotIn('アタシはほらかよわい女の子なんだから。', got)

    def test_tab_cells_are_separate(self):
        head, lines = cw.build_lines('単独で文節を作ることができるか\t活用の有無\t品詞名')
        self.assertNotIn('\t', head)
        self.assertFalse(any('\t' in l or '活用の有無' in l for l in lines))

    def test_bullet_stays_first(self):
        got = cw.reorderings('・友達と映画館で映画を見た。')
        self.assertTrue(got and all(g.startswith('・') and g.count('・') == 1 for g in got))
        got = cw.reorderings('1. 友達と映画館で映画を見た。')
        self.assertTrue(all(g.startswith('1. ') for g in got))

    def test_no_end_mark(self):
        self.assertEqual(cw.reorderings('この部屋は明るい'), ['明るい。この部屋は。'])

    def test_single_phrase(self):
        self.assertEqual(cw.reorderings('寝た。'), [])


class TestEnglish(unittest.TestCase):
    # うにさん 15:04Z（英文→日本語の文法で名詞は英語）・15:05Z（英文→英文の倒置）
    def test_english_lines(self):
        head, lines = cw.build_lines('I read a book at the library. The cake is very sweet.')
        self.assertIn('At the library, I read a book.', lines)
        self.assertIn('A book, I read at the library.', lines)
        # 30字以上の選択は最初の文末までだけ。後ろの文は並べない（v20・うにさん 10-27 02:14Z）
        self.assertNotIn('cake はとても甘い', lines)
        self.assertFalse(any('cake' in l for l in lines))
        head, lines = cw.build_lines('The cake is very sweet.')
        self.assertIn('cake はとても甘い', lines)
        # 日本語の長い選択は1行目も最初の文末まで
        head, lines = cw.build_lines('昨日は家族で週末に駅前の映画館へ出掛けた。今日は友達と公園でゆっくり休んだ。')
        self.assertEqual(head, '昨日は家族で週末に駅前の映画館へ出掛けた。')
        self.assertFalse(any('公園' in l for l in lines))

    def test_japanese_order(self):
        import en_convert as ec
        self.assertEqual(ec.japanese_order('My mother wrote a letter to my friend.'), 'mother が friend に letter を書いた')
        self.assertEqual(ec.japanese_order('I met my friend at the station.'), 'station で friend に会った')
        self.assertIsNone(ec.japanese_order('Hello.'))

    def test_reorder_starts_with_original_first(self):
        import en_convert as ec
        got = ec.english_reorderings('We traveled to Kyoto by train last summer.')
        self.assertTrue(got[0].startswith('We '))
        self.assertIn('Last summer, we traveled to Kyoto by train.', got)
        self.assertNotIn('We traveled to Kyoto by train last summer.', got)

    def test_japanese_unchanged(self):
        self.assertFalse(cw._is_english('友達と映画館で映画を見た。'))


class TestSynonyms(unittest.TestCase):
    # うにさん 16:12Z: 類語のある語は原文を類語に置き換えた行も
    def test_synonym_lines(self):
        try:
            import synonyms
            if not synonyms.available():
                self.skipTest('類語の表が無い')
        except ImportError:
            self.skipTest('synonyms.py が無い')
        got = cw.synonym_lines('家族で週末に出掛けた。')
        self.assertTrue(got)
        # うにさん 17:08Z: 類語のある語は同時に置き換える（1行目は 家族 も 週末 も替わる）
        self.assertFalse('家族' in got[0] or '週末' in got[0])
        # うにさん 10-27 01:18Z: k 行目は各語の k 番目の類語（同じ候補を繰り返さない）。
        # 候補が尽きた語は原文のまま、原文と同じ所は灰色
        firsts = [g.split('で')[0] for g in got]
        self.assertEqual(len(firsts), len(set(firsts)))
        for g in got:
            for a, z in g.gray:
                self.assertIn(g[a:z], '家族で週末に出掛けた。')
        head, lines = cw.build_lines('家族で週末に出掛けた。')
        self.assertTrue(set(got) <= set(lines))


class TestBuildLines(unittest.TestCase):
    def test_head_and_english_last(self):
        head, lines = cw.build_lines('家族で週末に出掛けた。')
        self.assertEqual(head, '家族で週末に出掛けた。')
        self.assertEqual(lines[-1], 'Went out with 家族 on 週末.')
        self.assertFalse(any(l.startswith(' ') for l in lines))

    def test_cache(self):
        a = cw.sections_for('母は花が好きだ。')
        self.assertIs(a, cw.sections_for('母は花が好きだ。'))


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'Tk が無い')
class TestWindow(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from types import SimpleNamespace
        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = tk.Text(self.root)
        self.editor.pack()
        self.editor.insert('1.0', '雨が降った。\n家族で週末に出掛けた。')
        self.app = SimpleNamespace(root=self.root, editor=self.editor)
        cw._instance = None

    def tearDown(self):
        self.root.destroy()

    def texts(self, win):
        return [b.cget('text') for b in cw._instance.buttons]

    def test_line_then_selection_follows(self):
        self.editor.mark_set('insert', '2.3')
        win = cw.open_from_app(self.app)
        self.assertEqual(cw._instance.first.cget('text'), '家族で週末に出掛けた。')
        self.assertIn('週末に家族で出掛けた。', self.texts(win))
        # 選び直すと1行目と並びが変わる
        self.editor.tag_add('sel', '1.0', '1.end')
        self.root.update()
        self.root.after(150)
        self.root.update()
        self.assertEqual(cw._instance.first.cget('text'), '雨が降った。')
        self.assertEqual(1, sum(t.endswith('が。') for t in self.texts(win)))   # 全部助詞終わりなら1つだけ

    def test_click_inserts_into_editor(self):
        self.editor.mark_set('insert', '2.3')
        cw.open_from_app(self.app)
        self.editor.mark_set('insert', 'end')
        cw._instance.buttons[0].invoke()
        self.assertIn(cw._instance.buttons[0].cget('text'), self.editor.get('1.0', 'end'))
        self.assertEqual(self.root.clipboard_get(), cw._instance.buttons[0].cget('text'))

    def test_pos_styles_follow_editor(self):
        # うにさん 16:06Z: 品詞ごとの大きさと色を窓の中にも
        from pos_font import POS_COLOR_TAGS, POS_FONT_TAGS
        self.editor.tag_configure(POS_COLOR_TAGS['名詞'], foreground='#ff0000')
        self.editor.tag_configure(POS_FONT_TAGS['動詞'], font=('TkDefaultFont', 20))
        self.editor.mark_set('insert', '2.3')
        cw.open_from_app(self.app)
        w = cw._instance.first.widget
        colored = [t for t in w.tag_names('1.0') if w.tag_cget(t, 'foreground') == '#ff0000']
        self.assertTrue(colored)      # 家族 は名詞
        self.assertIn('20', str(w.tag_cget(w.tag_names('1.6')[0], 'font')))   # 出掛け は動詞

    def test_no_external_paste_gate(self):
        self.editor.mark_set('insert', '2.3')
        cw.open_from_app(self.app)
        self.assertIsNone(cw._instance._outside_front())    # 偽の app・環境変数のどちらでも外へ貼らない

    def test_gray_prefix_and_sections(self):
        # うにさん 17:08Z: 倒置は1行上と同じ所まで灰色・境目に 0.5 行
        self.editor.mark_set('insert', '2.3')
        cw.open_from_app(self.app)
        lines = cw._instance.buttons
        second = lines[1].widget if len(lines) > 1 else None
        head, reorder, syn, eng = cw.build_sections('家族で週末に出掛けた。')
        self.assertTrue(reorder and eng)
        w = lines[0].widget
        n = cw._common_prefix(head, reorder[0])
        if n:
            self.assertIn('same_as_above', w.tag_names('1.0'))
        self.assertNotIn('same_as_above', w.tag_names(f'1.0+{n}c'))
        spacers = [c for c in cw._instance.rows.winfo_children() if c.winfo_class() == 'Frame' and not c.winfo_children()]
        self.assertEqual(len(spacers), sum(1 for p in (reorder, syn, eng) if p))

    def test_width_follows_longest(self):
        self.editor.mark_set('insert', '1.1')
        win = cw.open_from_app(self.app)
        self.root.update()
        narrow = win.winfo_width()
        # 2行以上を選んだときは一番上の空でない行だけ（v18）なので、長い2行目だけを選ぶ
        self.editor.tag_add('sel', '2.0', 'end-1c')
        self.root.update()
        self.root.after(150)
        self.root.update()
        self.root.update_idletasks()
        self.assertGreater(win.winfo_width(), narrow)


if __name__ == '__main__':
    unittest.main()
