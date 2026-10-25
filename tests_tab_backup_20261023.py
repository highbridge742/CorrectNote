# -*- coding: utf-8 -*-
"""Backups of each tab (2026-10-23 うにさん).

「保存のたびにそのタブのバックアップを作る。朝4時（ローカル時刻）をまたぐまでは同じ1つを上書き、またいだら
新しいバックアップに切り替える。1タブにつき残す数はパラメータ（既定5、0〜20、0なら作らない）。超えた古いもの
から捨てる。タブ右クリックで、既存メニューの下に、新しい順でバックアップを並べ、保存日時を出す。選ぶと別
ウィンドウで開く。バックアップの窓は見るだけ（編集不可、選択とコピーは可）。窓の中に『このバックアップを
削除する』ボタン、確認ダイアログのあと、その1つだけ消す」. The clock is given to save(); temporary folders only."""
import datetime as dt
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import app, session, tab_backup

KEY = 'id:test'


def at(day, hour, minute=0):
    return dt.datetime(2026, 10, day, hour, minute)


class BackupFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.base = self.dir.name

    def tearDown(self):
        self.dir.cleanup()

    def kept(self):
        return [(when, tab_backup.read(path)) for when, path in tab_backup.list_backups(self.base, KEY)]

    def test_one_backup_until_four_in_the_morning(self):
        tab_backup.save(self.base, KEY, '一', 5, moment=at(23, 10))
        tab_backup.save(self.base, KEY, '二', 5, moment=at(23, 23))
        tab_backup.save(self.base, KEY, '三', 5, moment=at(24, 3, 59))     # still the same day
        self.assertEqual(self.kept(), [(at(24, 3, 59), '三')])
        tab_backup.save(self.base, KEY, '四', 5, moment=at(24, 4, 0))      # a new day
        self.assertEqual(self.kept(), [(at(24, 4, 0), '四'), (at(24, 3, 59), '三')])

    def test_only_the_newest_are_kept_and_zero_keeps_none(self):
        for day in range(20, 27):
            tab_backup.save(self.base, KEY, '第%d日' % day, 3, moment=at(day, 12))
        self.assertEqual([text for _w, text in self.kept()], ['第26日', '第25日', '第24日'])
        self.assertIsNone(tab_backup.save(self.base, 'id:other', '本文', 0, moment=at(26, 12)))
        self.assertEqual(tab_backup.list_backups(self.base, 'id:other'), [])

    def test_the_same_text_again_writes_nothing(self):
        first = tab_backup.save(self.base, KEY, '同じ', 5, moment=at(23, 10))
        self.assertEqual(tab_backup.save(self.base, KEY, '同じ', 5, moment=at(23, 11)), first)
        self.assertEqual(self.kept(), [(at(23, 10), '同じ')])

    def test_a_failure_does_not_raise(self):
        blocker = os.path.join(self.base, tab_backup.FOLDER)
        open(blocker, 'w').close()            # a file where the folder should be
        self.assertIsNone(tab_backup.save(self.base, KEY, '本文', 5, moment=at(23, 10)))

    def test_manual_backups_are_counted_apart_from_the_daily_ones(self):
        tab_backup.save(self.base, KEY, '毎日', 2, moment=at(23, 9))
        for minute in range(4):
            tab_backup.save_manual(self.base, KEY, '手動%d' % minute, 3, moment=at(23, 10, minute))
        manual = [tab_backup.read(p) for _w, p in tab_backup.list_backups(self.base, KEY, manual=True)]
        self.assertEqual(manual, ['手動3', '手動2', '手動1'])               # over 3: the oldest manual one goes
        self.assertEqual(self.kept(), [(at(23, 9), '毎日')])                # the daily one is left alone
        tab_backup.save(self.base, KEY, '毎日2', 2, moment=at(23, 11))      # same day: replaces only the daily one
        self.assertEqual(self.kept(), [(at(23, 11), '毎日2')])
        self.assertEqual(len(tab_backup.list_backups(self.base, KEY, manual=True)), 3)
        both = tab_backup.list_all(self.base, KEY)
        self.assertEqual([(w.hour, w.minute, m) for w, _p, m in both],
                         [(11, 0, False), (10, 3, True), (10, 2, True), (10, 1, True)])
        # Made twice within one second: both kept
        tab_backup.save_manual(self.base, 'id:twice', '一', 5, moment=at(23, 12))
        tab_backup.save_manual(self.base, 'id:twice', '二', 5, moment=at(23, 12))
        self.assertEqual([tab_backup.read(p) for _w, p in tab_backup.list_backups(self.base, 'id:twice', manual=True)],
                         ['二', '一'])
        self.assertIsNone(tab_backup.save_manual(self.base, KEY, '本文', 0, moment=at(23, 12)))

    def test_keys(self):
        self.assertEqual(tab_backup.tab_key(dict(backup_id='abc', path='C:/x.txt')), 'id:abc')
        self.assertTrue(tab_backup.tab_key(dict(path='C:/x.txt')).startswith('path:'))
        self.assertIsNone(tab_backup.tab_key(dict(text='本文')))


class SessionIdTests(unittest.TestCase):
    def test_the_id_stays_with_the_tab(self):
        with tempfile.TemporaryDirectory() as folder:
            store = session.SessionStore(os.path.join(folder, 's.json'))
            store.tabs = [session.new_tab(text='本文', backup_id='abc')]
            store.update_active(session.new_tab(text='本文を直した'))   # the periodic capture
            self.assertEqual(store.tabs[0]['backup_id'], 'abc')
            self.assertTrue(store.save())
            again = session.SessionStore(os.path.join(folder, 's.json'))
            self.assertTrue(again.load())
            self.assertEqual(again.tabs[0]['backup_id'], 'abc')


class AppBackupTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.session = SimpleNamespace(tabs=[session.new_tab(text='作り文の一行目\n二行目'),
                                          session.new_tab(text='', path=None)], active=0)
        a._editor_font = lambda: ('Yu Gothic', 10)
        self.patch = patch.object(app, 'app_dir', return_value=self.dir.name)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.root.destroy()
        self.dir.cleanup()

    def test_saving_backs_up_and_the_tab_menu_lists_them(self):
        a = self.a
        a._name_tabs_for_backup()
        self.assertTrue(a.session.tabs[0].get('backup_id'))
        self.assertNotIn('backup_id', a.session.tabs[1])               # an empty tab: nothing to keep
        a._backup_tabs()
        items = a._tab_backup_items(0)
        self.assertEqual(items[0][0], '― バックアップ（新しい順） ―')
        self.assertEqual(len(items), 2)
        self.assertEqual(a._tab_backup_items(1), [('― バックアップ（まだありません） ―', None)])
        a.BACKUP_KEEP = 0
        a.session.tabs[0]['text'] = '変えた'
        a._backup_tabs()
        self.assertEqual(len(a._tab_backup_items(0)), 2)                 # 0: nothing new

    def test_the_window_shows_it_read_only_and_deletes_only_that_one(self):
        a = self.a
        a._name_tabs_for_backup(); a._backup_tabs()
        (when, path), = tab_backup.list_backups(self.dir.name, tab_backup.tab_key(a.session.tabs[0]))
        window = a._open_backup(path, when, '作り文')
        text = window.text
        self.assertEqual(text.get('1.0', 'end-1c'), '作り文の一行目\n二行目')
        text.insert('1.0', '打った'); text.delete('1.0', 'end')           # typing, cutting: refused
        self.assertEqual(text.get('1.0', 'end-1c'), '作り文の一行目\n二行目')
        text.tag_add('sel', '1.0', '1.3')
        self.assertEqual(text.get('sel.first', 'sel.last'), '作り文')     # selection (and copy) work
        with patch('backup_view.messagebox.askyesno', return_value=False):
            self.assertFalse(window.ask_delete())
        self.assertTrue(os.path.exists(path))
        with patch('backup_view.messagebox.askyesno', return_value=True):
            self.assertTrue(window.ask_delete())
        self.assertFalse(os.path.exists(path))

    def test_the_window_is_larger_with_the_memos_selection_spaces_and_emoji(self):
        # 2026-10-23 うにさん「開いた時点で今よりも大きくする」「絵文字に色がないので塗る」「スペースの表示も
        # 対応する」「範囲選択の色が濃すぎる」
        import emoji_color
        a = self.a
        self.root.attributes('-alpha', 0); self.root.geometry('1000x700+10000+100'); self.root.deiconify()
        self.root.update()
        a.session.tabs[0]['text'] = '全角　と半角 の空白 😀'
        a._name_tabs_for_backup(); a._backup_tabs()
        (when, path), = tab_backup.list_backups(self.dir.name, tab_backup.tab_key(a.session.tabs[0]))
        a._schedule_whitespace_paint = lambda delay=None: None
        with patch.object(app, 'monitor_work_area', return_value=(10000, 0, 11920, 1040)):
            window = a._open_backup(path, when, '作り文')
        window.window.update()
        self.assertGreaterEqual(window.window.winfo_width(), 700)            # 75% of the main window
        self.assertGreaterEqual(window.window.winfo_height(), 500)
        self.assertEqual(str(window.text.cget('selectbackground')), app.EDITOR_SEL_BG)
        self.assertEqual(str(window.text.cget('selectforeground')), app.INK)
        if emoji_color.renderer() is not None:
            self.assertIsNotNone(getattr(window.text, '_correctnote_emoji_color', None))
        # The space marks: the same targets and setting as the memo
        self.assertIn(window.text, a._whitespace_targets())
        a.settings = SimpleNamespace(get=lambda key, default=None: True if key == 'show_whitespace' else default)
        a._window_dragging = lambda: False
        a._align_pane_rows = a._paint_end_rule = lambda: None
        a._configure_whitespace_tags()
        a._paint_whitespace()
        tags = set()
        for index in ('1.2', '1.5'):
            tags |= set(window.text.tag_names(index))
        self.assertTrue(tags & set(a.WS_TAGS), tags)
        self.assertEqual(window.text.get('1.0', 'end-1c'), '全角　と半角 の空白 😀')   # read only, unchanged
        window.close()
        self.assertNotIn(window.text, a._whitespace_targets())

    def test_theme_switches_with_backup_windows_open_or_just_closed(self):
        # 2026-10-23 うにさん「バックアップウインドウ表示中に、ダークモード切替するとアプリがクラッシュする」:
        # the colours of open backup windows follow (light → dark → light), with two open, and right after
        # one was closed; nothing raises
        a = self.a
        a.session.tabs[0]['text'] = '作り文　です'
        a._name_tabs_for_backup(); a._backup_tabs()
        (when, path), = tab_backup.list_backups(self.dir.name, tab_backup.tab_key(a.session.tabs[0]))
        a._schedule_whitespace_paint = lambda delay=None: None
        first = a._open_backup(path, when, '作り文')
        second = a._open_backup(path, when, '作り文')
        light, dark = app.LIGHT_PALETTE, app.DARK_PALETTE
        to_dark = {light[k]: dark[k] for k in app._PALETTE_KEYS if light[k] != dark[k]}
        to_light = {v: k for k, v in to_dark.items()}
        for mapping, palette in ((to_dark, dark), (to_light, light), (to_dark, dark)):
            app.CorrectNoteApp._restyle_widget(self.root, mapping, {})
            a._configure_whitespace_tags()
            self.root.update()
            for window in (first, second):
                if window.window.winfo_exists():
                    self.assertEqual(str(window.text.cget('bg')), palette['PANEL'])
                    self.assertEqual(str(window.text.cget('selectbackground')), palette['EDITOR_SEL_BG'])
            if second.window.winfo_exists():
                second.close()                                      # the next switch comes right after
        self.assertFalse(second.window.winfo_exists())
        self.assertEqual(a._whitespace_targets(), [first.text])
        first.close()

    def run_in_mainloop(self, *steps):
        """Run steps from inside root.mainloop() (as the app does), then quit; the mainloop must end by
        itself. An error kept by tkinter from a widget command would be raised here."""
        done = []

        def run():
            for step in steps:
                step()
                self.root.update()
            done.append(True)
            self.root.after(50, self.root.quit)
        self.root.after(30, run)
        self.root.mainloop()
        self.assertEqual(done, [True])

    def test_the_read_only_box_answers_like_tk_inside_the_mainloop(self):
        # 2026-10-23 うにさん「バックアップウインドウ表示中に、ダークモード切替するとアプリがクラッシュする」:
        # unknown option "-selectcolor" from the read-only box ended mainloop()
        import backup_view
        t = tk.Text(self.root)
        t.insert('1.0', '本文')
        backup_view.make_read_only(t)
        seen = []

        def ask():
            try:
                t.cget('selectcolor')
            except tk.TclError as error:
                seen.append(str(error))
            t.insert('end', '打った'); t.delete('1.0', 'end'); t.edit_undo()
            seen.append(t.get('1.0', 'end-1c'))
        self.run_in_mainloop(ask)
        self.assertEqual(seen, ['unknown option "-selectcolor"', '本文'])

    def test_theme_switches_inside_the_mainloop_with_backup_windows(self):
        # The same switch as the View menu's dark mode, from inside the mainloop: no window, one, two, and
        # one closed just before
        a = self.a
        a.session.tabs[0]['text'] = '作り文　です 😀'
        a._name_tabs_for_backup(); a._backup_tabs()
        (when, path), = tab_backup.list_backups(self.dir.name, tab_backup.tab_key(a.session.tabs[0]))
        a._schedule_whitespace_paint = lambda delay=None: None
        light, dark = app.LIGHT_PALETTE, app.DARK_PALETTE
        to_dark = {light[k]: dark[k] for k in app._PALETTE_KEYS if light[k] != dark[k]}
        to_light = {v: k for k, v in to_dark.items()}

        def switch(mapping):
            def step():
                app.CorrectNoteApp._restyle_widget(self.root, mapping, {})
                a._configure_whitespace_tags()
            return step
        self.run_in_mainloop(switch(to_dark), switch(to_light))                     # no window
        first = a._open_backup(path, when, '作り文')
        self.run_in_mainloop(switch(to_dark), switch(to_light))                     # one
        second = a._open_backup(path, when, '作り文')
        self.run_in_mainloop(switch(to_dark), switch(to_light), switch(to_dark))    # two
        self.run_in_mainloop(second.close, switch(to_light), switch(to_dark))       # one closed just before
        self.assertEqual(str(first.text.cget('bg')), dark['PANEL'])
        first.close()

    def test_the_search_bar_marks_the_hits_and_moves_between_them(self):
        # 2026-10-23 うにさん「バックアップウインドウに専用の検索欄を設ける。別ウインドウで出さず、入力欄が置いてある」
        from tests_copy_find_emphasis_20261023 import size_at
        a = self.a
        a.FIND_EMPHASIS_PERCENT = 130
        a.session.tabs[0]['text'] = '鏡を見た。\n鏡の前で😀鏡を拭いた。\n終わり'
        a._name_tabs_for_backup(); a._backup_tabs()
        (when, path), = tab_backup.list_backups(self.dir.name, tab_backup.tab_key(a.session.tabs[0]))
        a._schedule_whitespace_paint = lambda delay=None: None
        window = a._open_backup(path, when, '作り文')
        self.root.update()
        window.focus_find(); window.find_entry.focus_force(); self.root.update()
        window.find_var.set('鏡')                                   # each letter typed searches at once
        self.assertEqual(window.find_count.cget('text'), '1／3 件')
        t = window.text
        self.assertEqual(len(t.tag_ranges(window.FIND_TAG)) // 2, 3)
        self.assertEqual(t.get(*t.tag_ranges(window.FIND_CURRENT_TAG)), '鏡')
        self.assertEqual(size_at(t, '2.0'), 13)                      # the letters 1.3x, as the memo's search
        self.assertEqual(str(t.tag_cget(window.FIND_TAG, 'background')), app.FOUND_BG)
        window.find_entry.event_generate('<Return>')
        self.assertEqual(window.find_count.cget('text'), '2／3 件')
        window.find_entry.event_generate('<Return>')
        self.assertEqual(window.find_count.cget('text'), '3／3 件')
        # Read through Tk's own tag indices: on Tk 8.6.9 an index string after an emoji (from tag_ranges) is in
        # UTF-16 columns and reading it back is one letter off
        current = window.FIND_CURRENT_TAG
        self.assertEqual(t.get(current + '.first', current + '.last'), '鏡')        # the one after the emoji
        self.assertEqual(t.get(current + '.last', current + '.last lineend'), 'を拭いた。')
        window.find_entry.event_generate('<Shift-Return>')
        self.assertEqual(window.find_count.cget('text'), '2／3 件')
        window.find_var.set('ない言葉')
        self.assertEqual(window.find_count.cget('text'), '見つかりません')
        self.assertEqual(t.tag_ranges(window.FIND_TAG), ())
        window.find_var.set('鏡')
        # 2026-10-24 うにさん「検索の後で Esc を押したら、検索の強調表示を消す（欄の文字はそのまま）。窓は Esc で閉じない」
        window.find_entry.event_generate('<Escape>')                 # the marks go, the words stay
        self.assertEqual((window.find_var.get(), window.find_count.cget('text'), t.tag_ranges(window.FIND_TAG)),
                         ('鏡', '', ()))
        self.assertEqual(size_at(t, '2.0'), 10)
        self.assertTrue(window.window.winfo_exists())
        self.assertEqual(t.get('1.0', 'end-1c'), '鏡を見た。\n鏡の前で😀鏡を拭いた。\n終わり')   # still read only
        window.find_entry.event_generate('<Escape>')                 # again: the window stays
        self.root.update()
        self.assertTrue(window.window.winfo_exists())
        window.find_entry.event_generate('<Return>')                 # Enter: the same words are searched again
        self.assertEqual(window.find_count.cget('text'), '1／3 件')
        window.close()

    def test_the_field_looks_like_a_field_the_cross_empties_it_and_ctrl_w_closes_the_window(self):
        # 2026-10-24 うにさん: 1.「検索欄が入力欄に見えない（ダークモードで枠も背景も無いように見える）」 2.「検索欄を空に
        # するボタン（×）を ▲ の左に」 4.「窓は Esc で閉じない。Ctrl+W で閉じる。バックアップの窓がアクティブな時の
        # Ctrl+W は本体のタブではなくバックアップの窓を閉じる」
        a = self.a
        a.session.tabs[0]['text'] = '鏡を見た。'
        a._name_tabs_for_backup(); a._backup_tabs()
        (when, path), = tab_backup.list_backups(self.dir.name, tab_backup.tab_key(a.session.tabs[0]))
        a._schedule_whitespace_paint = lambda delay=None: None
        closed_tabs = []
        a._close_tab = lambda: closed_tabs.append(True)
        self.root.bind_all('<Control-w>', lambda e: (a._close_tab(), 'break')[1])     # as the main window does
        light, dark = app.LIGHT_PALETTE, app.DARK_PALETTE
        window = a._open_backup(path, when, '作り文')
        self.root.update()
        e = window.find_entry
        for palette in (light, dark):
            if palette is dark:
                to_dark = {light[k]: dark[k] for k in app._PALETTE_KEYS if light[k] != dark[k]}
                app.CorrectNoteApp._restyle_widget(self.root, to_dark, {})
                with patch.multiple(app, **{k: dark[k] for k in ('BG', 'PANEL', 'INK', 'MUTED', 'ACCENT')}):
                    window.refresh_find_colors()
            self.assertNotEqual(str(e.cget('bg')).lower(), str(window.text.cget('bg')).lower())   # its own background
            self.assertEqual(int(e.cget('highlightthickness')), 1)                                 # a 1px border
            self.assertNotEqual(str(e.cget('highlightbackground')).lower(), str(e.cget('bg')).lower())
        # × sits left of ▲ and empties the field; the marks go
        bar = window.find_bar.pack_slaves()
        self.assertLess(bar.index(window.find_clear), bar.index(window.find_prev))
        self.assertEqual(window.find_clear.cget('text'), '×')
        window.find_var.set('鏡')
        self.assertTrue(window.text.tag_ranges(window.FIND_TAG))
        window.find_clear.invoke()
        self.assertEqual((window.find_var.get(), window.text.tag_ranges(window.FIND_TAG)), ('', ()))
        # Ctrl+W in the backup window closes it, not the main window's tab
        window.text.focus_force(); self.root.update()
        window.text.event_generate('<Control-w>')
        self.root.update()
        self.assertFalse(window.window.winfo_exists())
        self.assertEqual(closed_tabs, [])

    def test_the_file_menu_makes_a_manual_backup_and_the_tab_menu_marks_it(self):
        a = self.a
        a.session.current = lambda: a.session.tabs[a.session.active]
        a._schedule_session_save = lambda: None
        flashed = []
        a._flash_editor_header = flashed.append
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='保存')
        a._file_menu, a._manual_backup_index = menu, 1
        menu.add_command(label=a._manual_backup_label(), command=a._make_manual_backup)
        a.BACKUP_MANUAL_KEEP = 2
        a._refresh_file_menu()
        self.assertEqual(menu.entrycget(1, 'label'), '手動でバックアップを作成（最大2個）')
        self.assertEqual(menu.entrycget(1, 'state'), 'normal')
        for _ in range(3):
            self.assertTrue(a._make_manual_backup())
        key = tab_backup.tab_key(a.session.tabs[0])
        self.assertTrue(key.startswith('id:'))                             # a tab without a file got its id
        self.assertEqual(len(tab_backup.list_backups(self.dir.name, key, manual=True)), 2)
        self.assertIn('最大 2 個', flashed[-1])
        a._name_tabs_for_backup(); a._backup_tabs()                          # and one daily backup
        labels = [label for label, _ in a._tab_backup_items(0)[1:]]
        self.assertEqual(sum(label.endswith('（手動）') for label in labels), 2)
        self.assertEqual(len(labels), 3)
        _label, open_it = next(item for item in a._tab_backup_items(0)[1:] if item[0].endswith('（手動）'))
        window = open_it()
        self.assertTrue(window.window.title().startswith('手動のバックアップ'))
        with patch('backup_view.messagebox.askyesno', return_value=True):
            self.assertTrue(window.ask_delete())                             # deleted the same way
        self.assertEqual(len(tab_backup.list_backups(self.dir.name, key, manual=True)), 1)
        # 0: greyed out, and nothing is made
        a.BACKUP_MANUAL_KEEP = 0
        a._refresh_file_menu()
        self.assertEqual(menu.entrycget(1, 'state'), 'disabled')
        self.assertIsNone(a._make_manual_backup())
        # An empty tab: nothing is made
        a.BACKUP_MANUAL_KEEP = 5
        a.session.active = 1
        self.assertIsNone(a._make_manual_backup())
        self.assertIn('空', flashed[-1])


if __name__ == '__main__':
    unittest.main()
