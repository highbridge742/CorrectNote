# -*- coding: utf-8 -*-
"""タイトルと目次を本文の Text の中の字として置く形（title_inline・body_index・2026-11-15 うにさん「本文と目次が同じ
仕組みの中で動くことはできないのか」）。自分で作った Tk の窓の中だけで確かめる（本物のキー送り・クリップボードは使わない。
キーは自分の窓への event_generate、ペーストはクリップボードの関数を差し替える）。作った例文。"""
import os
import tkinter as tk
import types
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import body_index as B
import title_inline as TI


def _tk():
    try:
        root = tk.Tk()
    except tk.TclError:
        raise unittest.SkipTest('no display')
    return root


class Switch(unittest.TestCase):
    def test_on_by_default(self):
        # 2026-11-15 から既定（本文の中の形）。=0 で前の重ねる形
        self.assertTrue(TI.enabled({}))
        self.assertFalse(TI.enabled({'CN_TITLE_TOC_INLINE': '0'}))
        self.assertTrue(TI.enabled({'CN_TITLE_TOC_INLINE': '1'}))
        self.assertFalse(TI.enabled({'CN_TITLE_TOC_INLINE': '1', 'CN_TITLE_TOC': '0'}))


class LinkColor(unittest.TestCase):
    """目次の青（2026-11-15 うにさん「ダークモードで目次の青色が見えにくい」）。暗い地では地とのコントラスト 7:1 以上、
    本文の字（11:1 以上）より目立ちすぎない明るさ。"""
    def test_dark_themes_get_a_readable_blue(self):
        import title_toc as T
        for bg in ('#25292d', '#172035', '#23201d', '#000000', '#3a3a3a'):
            color = T.link_color(T._hex_rgb(bg), True)
            self.assertGreaterEqual(T.contrast(T._hex_rgb(color), T._hex_rgb(bg)), T.LINK_CONTRAST, (bg, color))
        self.assertEqual(T.link_color(T._hex_rgb('#25292d'), True), '#9cc8ff')
        self.assertEqual(T.link_color(T._hex_rgb('#f0f0ed'), False), T.LINK_LIGHT)


class BracketCycleOnTitle(unittest.TestCase):
    def test_the_title_keeps_its_bracket_cycle(self):
        # タイトルに F2 を続けて押すと、本文と同じく次の括弧に入れ替わる（巡回の控えを捨てない）
        import app
        title, tab = object(), object()
        fake = NS(editor=object(), session=NS(current=lambda: tab), _title_toc=NS(title=title), _quick_text=None)
        self.assertTrue(app.CorrectNoteApp._bracket_owner_valid(fake, dict(widget=title, tab=tab)))
        self.assertFalse(app.CorrectNoteApp._bracket_owner_valid(fake, dict(widget=title, tab=object())))


class BodyRows(unittest.TestCase):
    """body_index を本物の Text に掛けた時の、Tk 自身の決まりとの継ぎ目。"""
    def setUp(self):
        self.root = _tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.t = tk.Text(self.root, undo=True)
        B.install(self.t, 2)
        self.raw = lambda *a: self.t.tk.call(self.t._cn_body_raw, *a)
        self.raw('insert', '1.0', '題\n目次\n')
        self.t.insert('1.0', '本文1\n本文2')
        self.t.edit_reset()

    def head(self):
        return [str(self.raw('get', '%d.0' % r, '%d.end' % r)) for r in (1, 2)]

    def test_delete_all_of_the_body_keeps_the_header(self):
        # Tk は「行の頭から end まで」を消すと前の改行も消す: 見出しの最後の改行を消さない（タブの入れ替えで本文の1行目が
        # 見出しに呑まれた）
        self.t.delete('1.0', 'end')
        self.assertEqual(self.head(), ['題', '目次'])
        self.assertEqual(self.t.get('1.0', 'end-1c'), '')
        self.t.insert('1.0', 'あ\nい')
        self.assertEqual(self.t.get('1.0', 'end-1c'), 'あ\nい')
        self.assertEqual(self.head(), ['題', '目次'])
        self.t.replace('1.0', 'end', 'う')
        self.assertEqual((self.head(), self.t.get('1.0', 'end-1c')), (['題', '目次'], 'う'))

    def test_backspace_and_selection_stop_at_the_body_head(self):
        self.t.mark_set('insert', '1.0')
        self.t.delete('insert-1c')
        self.assertEqual(self.head(), ['題', '目次'])
        self.t.tag_add('sel', '1.0-3c', '1.2')
        self.assertEqual([str(v) for v in self.t.tag_ranges('sel')], ['1.0', '1.2'])

    def test_tk_undo_replays_in_body_rows(self):
        # Tk 自身の Undo は「欄の名前 delete 生の位置」で呼び返す。その上の層（観察者）には本文の位置で届く
        seen = []
        work = self.t._w + '_test_work'
        self.t.tk.call('rename', self.t._w, work)

        def observer(*args):
            if args and str(args[0]) in ('insert', 'delete'):
                seen.append([str(a) for a in args[:3]])
            return self.t.tk.call(work, *args)
        self.t.tk.createcommand(self.t._w, observer)
        self.t.insert('2.0', 'k')
        self.t.edit_separator()
        seen.clear()
        self.t.edit_undo()
        self.assertEqual(self.t.get('1.0', 'end-1c'), '本文1\n本文2')
        self.assertEqual(self.head(), ['題', '目次'])
        self.assertIn(['delete', '2.0', '2.1'], seen)
        self.t.edit_redo()
        self.assertEqual(self.t.get('1.0', 'end-1c'), '本文1\nk本文2')

    def test_untranslate(self):
        self.assertEqual(B.untranslate(['delete', '5.0', '5.1'], 2), ['delete', '3.0', '3.1'])
        self.assertEqual(B.untranslate(['insert', '4.2', 'x'], 2), ['insert', '2.2', 'x'])
        self.assertEqual(B.untranslate(['mark', 'set', 'insert', '3.0'], 2), ['mark', 'set', 'insert', '1.0'])
        self.assertEqual(B.untranslate(['see', 'insert'], 2), ['see', 'insert'])

    def test_a_peer_shares_the_height(self):
        name = self.t._w + '_test_peer'
        self.t.tk.call(self.t._w, 'peer', 'create', name)
        self.addCleanup(lambda: self.t.tk.call('destroy', name))
        shim = types.SimpleNamespace(_w=name, tk=self.t.tk)
        B.install(shim, 0, share=self.t._cn_body_state)
        self.assertEqual(str(self.t.tk.call(name, 'get', '1.0', '1.end')), '本文1')
        self.t.tk.call(name, 'delete', '1.0', 'end')            # 書く道の分身が全部を書き直す
        self.assertEqual(self.head(), ['題', '目次'])
        B.set_height(self.t, 1)                                # 分け合う: 片方を変えれば両方
        self.assertEqual(str(self.t.tk.call(name, 'get', '1.0', '1.end')), '目次')
        self.assertEqual(B.height(shim), 1)


class Inline(unittest.TestCase):
    def setUp(self):
        os.environ.pop('CN_TITLE_TOC', None)
        self.root = _tk()
        self.root.geometry('760x520+40+40')
        self.addCleanup(self.root.destroy)
        body = tk.Frame(self.root)
        body.pack(fill='both', expand=True)
        left, right = tk.Frame(body), tk.Frame(body)
        left.pack(side='left', fill='both', expand=True)
        right.pack(side='left', fill='both', expand=True)
        font = ('Yu Gothic UI', 11)
        self.editor = tk.Text(left, undo=True, wrap='word', font=font, padx=14, pady=12, width=1)
        self.result = tk.Text(right, wrap='word', font=font, padx=14, pady=12, width=1, state='disabled')
        TI.prepare(self.editor)
        TI.prepare(self.result)
        self.editor.pack(fill='both', expand=True)
        self.result.pack(fill='both', expand=True)
        self.text = '\n'.join('%d行目の文です。' % i for i in range(1, 41))
        self.editor.insert('1.0', self.text)
        self.result.configure(state='normal')
        self.result.insert('1.0', self.text)
        self.result.configure(state='disabled')
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self.bookmarks = {3, 10}
        self.jumps = []
        self.app = NS(_body=body, editor=self.editor, result_view=self.result, _editor_wrap=left, _result_wrap=right,
                      bookmarks=self.bookmarks, settings={'dark_mode': False},
                      editor_source_text=lambda: self.editor.get('1.0', 'end-1c'),
                      _goto_line=lambda row, **kw: self.jumps.append(row), _layout_is_unified=lambda: False,
                      _editor_font=lambda: font, store=NS(_tokenize_fn=lambda line: []),
                      _show_copy_frame=mock.Mock(), _schedule_session_save=mock.Mock())
        self.toc = TI.InlineTitleToc(self.app)
        self.app._title_toc = self.toc
        self.toc.set_title('試しの題', layout=False)
        self.toc.refresh_toc(force=True)
        self.root.update()
        self.raw = lambda *a: self.editor.tk.call(self.editor._cn_body_raw, *a)
        self.editor.focus_force()
        self.root.update()

    def key(self, keysym, state=0):
        self.editor.event_generate('<KeyPress>', keysym=keysym, state=state, when='now')
        self.editor.event_generate('<KeyRelease>', keysym=keysym, state=state, when='now')
        self.root.update()

    def click_title(self, right_of_text=30):
        info = self.raw('dlineinfo', '1.0')
        x, y = int(info[0]) + int(info[2]) + right_of_text, int(info[1]) + int(info[3]) // 2
        self.editor.event_generate('<Button-1>', x=x, y=y, when='now')
        self.editor.event_generate('<ButtonRelease-1>', x=x, y=y, when='now')
        self.root.update()

    def click_body(self, row):
        info = self.editor.dlineinfo('%d.0' % row)
        self.editor.event_generate('<Button-1>', x=info[0] + 2, y=info[1] + 3, when='now')
        self.editor.event_generate('<ButtonRelease-1>', x=info[0] + 2, y=info[1] + 3, when='now')
        self.root.update()

    def hidden(self, widget, r):
        """生の行 r の字が、欄の地の色で塗られて見えないか（下線・線もなし）。"""
        raw = lambda *a: widget.tk.call(widget._cn_body_raw, *a)
        names = [str(n) for n in raw('tag', 'names', '%d.0' % r)]
        blank = [n for n in names if n in (TI.TAG_TITLE_BLANK, TI.TAG_LINK_BLANK, TI.TAG_RULE_BLANK)]
        if not blank or any(n in names for n in (TI.TAG_LINK, TI.TAG_RULE, TI.TAG_TITLE)):
            return False
        ground = str(widget.cget('background'))
        tag = blank[0]
        return (str(raw('tag', 'cget', tag, '-foreground')) == ground and
                str(raw('tag', 'cget', tag, '-selectforeground')) == ground and
                [str(x) for x in raw('tag', 'names')].index(tag) > max([str(x) for x in raw('tag', 'names')].index(n)
                                                                    for n in names if n != tag))

    def row(self, widget, r):
        return str(widget.tk.call(widget._cn_body_raw, 'get', '%d.0' % r, '%d.end' % r))

    # 見出しは本文の外 ------------------------------------------------------------
    def test_header_is_not_part_of_the_body(self):
        self.assertEqual(self.row(self.editor, 1), '試しの題')
        self.assertEqual([self.row(self.editor, r) for r in (2, 3)], ['3行目の文です。', '10行目の文です。'])
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)      # 保存・解析が読む本文
        self.assertEqual(self.editor.index('end-1c'), '40.9')
        self.assertEqual(self.editor.search('試しの題', '1.0', 'end'), '')
        self.assertFalse(self.editor.edit_modified())                      # 見出しを書いても変更の印は立たない
        self.assertFalse(self.editor.edit('canundo'))                     # Undo にも積まない

    def test_header_writes_keep_body_undo(self):
        # 見出しは見えない分身から書き、Undo は分身の configure で外す（本文の欄は configure しない）
        self.editor.insert('2.0', 'k')
        self.editor.edit_separator()
        with mock.patch.object(self.editor, 'configure') as conf:
            # 目次の数は変えない（数が変わると見出しの行の数が変わり、Undo の控えは tab_undo の道で預けて返す: 別の試験）
            self.toc.set_title('別の題', layout=False)
            self.toc.refresh_toc(force=True)
        conf.assert_not_called()
        self.assertEqual(self.row(self.editor, 1), '別の題')
        self.assertEqual(str(self.editor.cget('undo')), '1')
        self.editor.edit_undo()
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)
        self.assertEqual(self.row(self.editor, 1), '別の題')
        self.assertTrue(self.hidden(self.result, 1))

    def test_undo_steps_reach_the_editor_observers(self):
        # Tk は Undo の一手を、いちばん新しい分身（見出しを書く分身）の名前で呼び返す。それも本文の欄の命令へ回り、
        # 上の層（観察者・undo_feedback）には本文の位置で届く（2026-11-15 tests_gui_undo_feedback が落ちた件）
        seen = []
        work = self.editor._w + '_test_observer'
        self.editor.tk.call('rename', self.editor._w, work)

        def observer(*args):
            if args and str(args[0]) in ('insert', 'delete'):
                seen.append([str(a) for a in args[:3]])
            return self.editor.tk.call(work, *args)
        self.editor.tk.createcommand(self.editor._w, observer)
        self.editor.insert('2.0', '甲😀')
        self.editor.edit_separator()
        seen.clear()
        self.editor.edit_undo()
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)
        self.assertEqual(self.row(self.editor, 1), '試しの題')
        self.assertTrue(any(s[0] == 'delete' and s[1].startswith('2.') for s in seen), seen)

    def test_right_pane_has_blank_rows_of_the_same_height(self):
        # 2026-11-15 うにさん「タイトルと目次は、分割表示の時は左側だけでよい」: 右は字の無い空の見出し。前の試験
        # （右にも同じ見出しの字）は仕様の変更で書き換えた。左右の本文の行の高さはそろったまま
        h = TI.head_rows(self.editor)
        self.assertEqual(TI.head_rows(self.result), h)
        for r in range(1, h):
            self.assertTrue(self.hidden(self.result, r), r)          # 字は置くが地の色（見えない・選んでも見えない）
        self.assertEqual(self.result.get('1.0', 'end-1c'), self.text)
        for r in range(1, h + 2):
            a = self.editor.tk.call(self.editor._cn_body_raw, 'dlineinfo', '%d.0' % r)
            b = self.result.tk.call(self.result._cn_body_raw, 'dlineinfo', '%d.0' % r)
            self.assertEqual((int(a[1]), int(a[3])), (int(b[1]), int(b[3])), r)
        self.assertEqual(self.editor.dlineinfo('5.0')[1], self.result.dlineinfo('5.0')[1])
        self.assertEqual(self.result.tag_ranges(TI.TAG_LINK), ())
        self.assertEqual(self.result.tag_ranges(TI.TAG_RULE), ())

    def test_scrolling_up_by_lines_reaches_the_top(self):
        # 隠した行が見出しにあると、Tk の行送り（yview scroll units）がそこで止まった（右ドラッグ・ホイール）
        self.editor.yview('20.0')
        self.root.update()
        for _ in range(60):
            self.editor.yview_scroll(-1, 'units')
            self.root.update()
        self.assertEqual(str(self.raw('index', '@0,0')), '1.0')
        for _ in range(60):
            self.editor.yview_scroll(1, 'units')
            self.root.update()
        self.assertGreater(int(str(self.raw('index', '@0,0')).split('.')[0]), TI.head_rows(self.editor))

    # タイトルの行で直に打つ --------------------------------------------------------
    def test_typing_in_the_title_row(self):
        self.click_title()
        self.assertTrue(self.toc.has_cursor())
        self.assertEqual(str(self.raw('index', 'insert')), '1.4')          # カーソルはタイトルの行の末尾
        for ks in ('a', 'b', 'BackSpace', 'Left', 'c'):
            self.key(ks)
        self.assertEqual(self.toc.get_title(), '試しの題ca')
        self.assertEqual(self.row(self.editor, 1), '試しの題ca')
        self.assertTrue(self.hidden(self.result, 1))           # 分割の右には見出しの字を見せない（2026-11-15 仕様変更）
        self.assertEqual(str(self.raw('index', 'insert')), '1.5')
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)
        self.assertFalse(self.editor.edit_modified())

    def test_ime_text_and_paste_go_to_the_title(self):
        self.click_title()
        target = self.toc.typing_target(self.editor)                     # app._insert_ime_text の行き先
        self.assertIs(target, self.toc.title)
        target.tk.call('tk::TextInsert', target, 'の')
        self.root.update()
        self.assertEqual(self.row(self.editor, 1), '試しの題の')
        self.key('Home', 1)                                               # Shift+Home: 選択もタイトルの行に出る
        self.assertEqual([str(v) for v in self.raw('tag', 'ranges', 'sel')], ['1.0', '1.5'])
        with mock.patch.object(self.toc.title, 'clipboard_get', return_value='貼った\n字'):
            self.editor.event_generate('<<Paste>>', when='now')
            self.root.update()
        self.assertEqual(self.toc.get_title(), '貼った')                    # 1行だけ（title_toc.one_line）
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)

    def test_body_bindings_wait_while_typing_the_title(self):
        hits = []
        self.editor.bind('<KeyPress>', lambda e: hits.append(e.keysym), add=True)
        self.click_title()
        self.key('x')
        self.assertEqual(hits, [])                    # 打鍵の記録・解析などの本文の束縛は走らない
        self.click_body(4)
        self.assertFalse(self.toc.has_cursor())
        self.key('y')
        self.assertEqual(hits, ['y'])
        self.assertEqual(self.editor.get('4.0', '4.2'), 'y4')
        self.assertEqual(self.toc.get_title(), '試しの題x')

    def test_click_in_the_body_is_one_click(self):
        self.click_title()
        self.click_body(2)
        self.assertEqual(self.editor.index('insert'), '2.0')
        self.assertEqual(self.editor.tag_ranges('sel'), ())                # 作り直したクリックがダブルクリックにならない
        self.key('BackSpace')                                             # 選択が無いので改行1つだけ
        self.assertEqual(self.editor.get('1.0', '1.end'), '1行目の文です。2行目の文です。')

    def test_backspace_at_the_body_head_keeps_the_header(self):
        self.click_body(1)
        self.editor.mark_set('insert', '1.0')
        self.key('BackSpace')
        self.assertEqual(self.row(self.editor, 1), '試しの題')
        self.assertEqual(self.editor.get('1.0', 'end-1c'), self.text)

    def test_down_leaves_the_title(self):
        self.click_title()
        self.key('Down')
        self.assertFalse(self.toc.has_cursor())
        self.assertEqual(self.editor.index('insert'), '1.0')

    def test_switching_tabs_leaves_the_title(self):
        self.click_title()
        self.toc.switched('別の題')
        self.assertFalse(self.toc.has_cursor())
        self.assertEqual(self.row(self.editor, 1), '別の題')

    # 目次 ---------------------------------------------------------------------
    def test_jump_near_the_top_keeps_the_toc_in_view(self):
        # 頭から見せても飛び先が収まるなら、頭から（目次も見えたまま）。収まらない時は今まで通り（真ん中へ）
        calls = []
        self.app._goto_line = lambda row, **kw: calls.append((row, kw))
        self.toc.jump(3)
        self.toc.jump(38)
        self.assertEqual(calls, [(3, {'stay_at_top': True}), (38, {})])

    def test_theme_change_recolors_the_toc(self):
        link = lambda: str(self.raw('tag', 'cget', TI.TAG_LINK, '-foreground'))
        self.assertEqual(link(), '#1f5fbf')
        self.editor.configure(background='#25292d')
        self.result.configure(background='#25292d')
        self.toc.restyle()                       # app._apply_theme が呼ぶ
        self.assertEqual(link(), '#9cc8ff')
        hidden = str(self.result.tk.call(self.result._cn_body_raw, 'tag', 'cget', TI.TAG_LINK_BLANK, '-foreground'))
        self.assertEqual(hidden, '#25292d')     # 右の空きは新しい地の色で

    def test_toc_row_jumps_only_on_the_left(self):
        info = self.raw('dlineinfo', '3.0')
        self.editor.event_generate('<Button-1>', x=int(info[0]) + 5, y=int(info[1]) + 3, when='now')
        self.root.update()
        self.assertEqual(self.jumps, [10])
        info = self.result.tk.call(self.result._cn_body_raw, 'dlineinfo', '3.0')
        self.result.event_generate('<Button-1>', x=int(info[0]) + 5, y=int(info[1]) + 3, when='now')
        self.root.update()
        self.assertEqual(self.jumps, [10])                                 # 補正欄の目次は反応しない

    def test_header_rows_follow_the_toc(self):
        # 隠した行は持たない: 見出しはタイトル1行＋目次の数＋下の線（目次が無ければタイトルだけ）
        t = tk.Text(self.root, undo=True)
        TI.prepare(t)
        t.insert('1.0', 'あ\nい\nう')
        raw = lambda r: str(t.tk.call(t._cn_body_raw, 'get', '%d.0' % r, '%d.end' % r))
        self.assertEqual(TI.head_rows(t), 1)
        self.assertEqual(TI.write(t, '題', [(1, 1, 'あ'), (2, 2, 'い'), (3, 3, 'う')]), 4)
        self.assertEqual(TI.head_rows(t), 5)
        self.assertEqual([raw(r) for r in range(1, 6)], ['題', 'あ', 'い', 'う', ''])
        self.assertEqual(t.get('1.0', 'end-1c'), 'あ\nい\nう')
        self.assertEqual(t._cn_head_rows, [1, 2, 3])
        self.assertEqual(TI.write(t, '題', [(1, 1, 'あ')]), -2)
        self.assertEqual([raw(r) for r in range(1, 4)], ['題', 'あ', ''])
        self.assertEqual(TI.write(t, '題', []), -2)
        self.assertEqual(TI.head_rows(t), 1)
        self.assertEqual(t.get('1.0', 'end-1c'), 'あ\nい\nう')
        self.assertEqual(t.tag_ranges('cn_head_hidden'), ())

    def test_resizing_hands_the_undo_steps_over_like_a_tab_switch(self):
        snapshot = {'undo': [(1, [], [])], 'redo': []}
        feedback = mock.Mock(take=mock.Mock(return_value=snapshot))
        self.app._tab_undo = NS(feedback=feedback)
        with mock.patch.object(self.editor, 'edit_reset') as reset:
            self.toc._resized(2)
        feedback.take.assert_called_once_with()
        reset.assert_called_once_with()
        feedback.give.assert_called_once_with(snapshot)


if __name__ == '__main__':
    unittest.main()
