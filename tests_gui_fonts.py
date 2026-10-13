# -*- coding: utf-8 -*-
"""Font preferences across normal, overview and quick-entry widgets."""
import json
import tkinter as tk
import tkinter.font as tkfont
import types
import unittest
from unittest.mock import Mock, patch, mock_open

import app
from settings import Settings, DEFAULT_EDITOR_FONT
from pos_font import font_size


class FontSettingsTests(unittest.TestCase):
    def test_load_valid_fonts_and_reject_damaged_values(self):
        for family, size, expected in (
                ('Yu Gothic', 18, ('Yu Gothic', 18)),
                ('', 0, DEFAULT_EDITOR_FONT),
                (None, True, DEFAULT_EDITOR_FONT),
                (['Yu Mincho'], '18', DEFAULT_EDITOR_FONT),
                ('Yu Gothic', 999999, ('Yu Gothic', DEFAULT_EDITOR_FONT[1]))):
            settings = Settings()
            data = json.dumps(dict(editor_font_family=family, editor_font_size=size))
            with patch('settings.os.path.exists', return_value=True), \
                    patch('builtins.open', mock_open(read_data=data)):
                settings.load('synthetic-settings.json')
            self.assertEqual((settings.get('editor_font_family'),
                              settings.get('editor_font_size')), expected)


class FontTkTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a = self.a
        a.root = self.root
        a.settings = Settings()
        for name in ('editor', 'result_view', '_quick_text'):
            w = tk.Text(self.root, font=DEFAULT_EDITOR_FONT, undo=True)
            w.insert('1.0', '😀本文\t資料\n次の行')
            w.tag_add('sel', '1.0+1c', '1.0+3c')
            w.mark_set('insert', '2.2')
            w.edit_reset()
            setattr(a, name, w)
        a._syncing = False
        a._overview_pad = {}
        a._overview = None
        a._layout_is_unified = lambda: True
        a._adjust_quick_size = Mock()
        a._set_ime_font = Mock()
        a._schedule_whitespace_paint = Mock()
        a._font_size_var = tk.IntVar(master=self.root, value=11)
        a.editor_gutter = types.SimpleNamespace(font=None, redraw=Mock())
        a.result_gutter = types.SimpleNamespace(font=None, redraw=Mock())

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self, 'a', 'root')

    def test_change_and_overview_restore_keeps_text_selection_and_quick_size(self):
        a = self.a
        family = tkfont.nametofont('TkFixedFont').actual('family')
        snapshots = [(w.get('1.0', 'end-1c'), tuple(map(str, w.tag_ranges('sel'))),
                      w.index('insert')) for w in a._whitespace_targets()]
        a._choose_editor_font(family, 18)
        self.root.update_idletasks()
        self.assertEqual(a._editor_font(), (family, 18))
        self.assertEqual(a.editor_gutter.font, (family, 18))
        self.assertEqual(a._font_size_var.get(), 18)
        quick_stops = a._quick_text.cget('tabs')
        a._overview_fonts(5)
        self.root.update_idletasks()
        self.assertEqual(tkfont.Font(font=a.editor.cget('font')).actual('size'), 5)
        self.assertEqual(tkfont.Font(font=a._quick_text.cget('font')).actual('size'), 18)
        self.assertEqual(a._quick_text.cget('tabs'), quick_stops)
        a._overview_fonts(None)
        self.root.update_idletasks()
        for w, before in zip(a._whitespace_targets(), snapshots):
            self.assertEqual(tkfont.Font(font=w.cget('font')).actual('size'), 18)
            self.assertEqual((w.get('1.0', 'end-1c'),
                              tuple(map(str, w.tag_ranges('sel'))),
                              w.index('insert')), before)
            with self.assertRaises(tk.TclError):
                w.edit_undo()
        a._choose_editor_font(*DEFAULT_EDITOR_FONT)
        self.root.update_idletasks()
        self.assertEqual(a._editor_font(), DEFAULT_EDITOR_FONT)
        self.assertEqual(tkfont.Font(font=a._quick_text.cget('font')).actual('size'),
                         DEFAULT_EDITOR_FONT[1])

    def test_font_dialog_can_apply_and_reopen_without_duplicate_window(self):
        self.a._place_dialog = Mock()
        self.a.open_font_dialog()
        first = self.a._font_dialog
        self.a.open_font_dialog()
        self.assertIs(self.a._font_dialog, first)
        first.destroy()
        self.a.open_font_dialog()
        self.assertIsNot(self.a._font_dialog, first)

    def test_pos_font_tags_apply_ceil_size_without_changing_text(self):
        from boundary_colors import BoundaryColors
        from pos_font import POS_FONT_TAGS
        a=self.a;w=a.editor
        w.delete('1.0','end');w.insert('1.0','😀資料は大きい。')
        text=w.get('1.0','end-1c')
        a.settings.set('pos_font_multipliers',{'名詞':1.1,'形容詞':1.1})
        a._ctrl_boundary_plans={text:((),((3,4),),
            (('名詞',1,3),('助詞',3,4),('形容詞',4,7),('記号',7,8)))}
        colors=BoundaryColors(a,w)
        colors._rows=[1]
        colors.paint_one()
        noun=POS_FONT_TAGS['名詞'];adjective=POS_FONT_TAGS['形容詞']
        particle=POS_FONT_TAGS['助詞']
        # Query by symbolic Python-character offsets: Tk's numeric ranges
        # report UTF-16 columns after supplementary characters.
        self.assertIn(noun,w.tag_names('1.0+1c'))
        self.assertIn(noun,w.tag_names('1.0+2c'))
        self.assertNotIn(noun,w.tag_names('1.0+3c'))
        self.assertIn(adjective,w.tag_names('1.0+4c'))
        self.assertIn(adjective,w.tag_names('1.0+6c'))
        self.assertNotIn(adjective,w.tag_names('1.0+7c'))
        self.assertFalse(w.tag_ranges(particle))
        self.assertEqual(tkfont.Font(root=self.root,
            font=w.tag_cget(noun,'font')).actual('size'),
            font_size(DEFAULT_EDITOR_FONT[1],1.1))
        self.assertFalse(colors._marker_indices)
        self.assertNotIn('ctrl_boundary_marker',w.tag_names('1.3'))
        self.assertEqual(w.get('1.0','end-1c'),text)

    def test_sahen_font_tag_is_independent_from_noun_size(self):
        from boundary_colors import BoundaryColors
        from pos_font import POS_FONT_TAGS
        a=self.a;w=a.editor
        w.delete('1.0','end');w.insert('1.0','資料勉強')
        text=w.get('1.0','end-1c')
        a.settings.set('pos_font_multipliers',{
            '名詞':1.5,'名詞（サ変）':1.2})
        a._ctrl_boundary_plans={text:((),(),
            (('名詞',0,2),('名詞（サ変）',2,4)))}
        colors=BoundaryColors(a,w)
        colors._rows=[1]
        colors.paint_one()
        noun=POS_FONT_TAGS['名詞']
        sahen=POS_FONT_TAGS['名詞（サ変）']
        self.assertIn(noun,w.tag_names('1.0'))
        self.assertIn(sahen,w.tag_names('1.0+2c'))
        self.assertEqual(tkfont.Font(root=self.root,
            font=w.tag_cget(noun,'font')).actual('size'),
            font_size(DEFAULT_EDITOR_FONT[1],1.5))
        self.assertEqual(tkfont.Font(root=self.root,
            font=w.tag_cget(sahen,'font')).actual('size'),
            font_size(DEFAULT_EDITOR_FONT[1],1.2))

    def test_pos_font_dialog_compacts_columns_and_offers_all_one(self):
        from pos_font import POS_CATEGORIES, POS_FONT_DEFAULTS
        a=self.a
        a._place_dialog=lambda dlg,width,height:dlg.geometry(
            f'{width}x{height}+0+0')
        a._choose_pos_font_multipliers=Mock()
        a.open_pos_font_dialog()
        dlg=a._pos_font_dialog
        try:
            self.root.deiconify()
            dlg.deiconify()
            dlg.update()

            def descendants(parent):
                found=[]
                for child in parent.winfo_children():
                    found.append(child)
                    found.extend(descendants(child))
                return found

            children=descendants(dlg)
            labels=[w for w in children if isinstance(w,tk.Label)]
            sahen=next(w for w in labels if w.cget('text')=='名詞（サ変）')
            form=sahen.master
            row=int(sahen.grid_info()['row'])
            spinbox=next(w for w in form.grid_slaves(row=row,column=1)
                         if isinstance(w,tk.Spinbox))
            gap=spinbox.winfo_x()-(sahen.winfo_x()+sahen.winfo_width())
            self.assertLessEqual(gap,8)

            buttons={w.cget('text'):w for w in children
                     if isinstance(w,tk.Button)}
            all_one=buttons['すべて1倍']
            reset=buttons['倍率を初期値']
            self.assertIn('色を初期化',buttons)
            button_gap=all_one.winfo_x()-(reset.winfo_x()+reset.winfo_width())
            self.assertGreaterEqual(button_gap,0)
            self.assertLessEqual(button_gap,8)
            all_one.invoke()
            values=a._choose_pos_font_multipliers.call_args.args[0]
            self.assertEqual(set(values),set(POS_CATEGORIES))
            self.assertTrue(all(value==1.0 for value in values.values()))
            a._choose_pos_font_multipliers.reset_mock()
            reset.invoke()
            values=a._choose_pos_font_multipliers.call_args.args[0]
            self.assertEqual(values,POS_FONT_DEFAULTS)
            self.assertTrue(any(w.cget('text')=='数詞' for w in labels))
            close=buttons['キャンセル']
            self.assertIn('OK',buttons)
            self.assertNotIn('適用',buttons);self.assertNotIn('閉じる',buttons)
            self.assertLessEqual(close.winfo_rooty()+close.winfo_height(),
                                 dlg.winfo_rooty()+dlg.winfo_height())

            from pos_font import PALETTE_ROWS
            chosen=[]
            palette=a._open_pos_color_palette(close,'',chosen.append)
            palette.update()
            swatches=[w for w in descendants(palette)
                      if isinstance(w,tk.Frame) and w.grid_info()]
            self.assertEqual(len(swatches),sum(map(len,PALETTE_ROWS)))
            self.assertFalse([w for w in descendants(palette)
                              if isinstance(w,tk.Label) and
                              w.cget('text') in ('テーマの色','標準の色')])
            target=PALETTE_ROWS[3][1]
            swatch=next(w for w in swatches if w.cget('bg')==target)
            self.assertEqual((int(swatch.grid_info()['row']),
                              int(swatch.grid_info()['column'])),(3,1))
            self.assertEqual(len(PALETTE_ROWS),7)
            swatch.event_generate('<ButtonRelease-1>')
            self.assertEqual(chosen,[target])
        finally:
            dlg.destroy()
            self.root.withdraw()

    def test_pos_font_dialog_applies_at_once_and_cancel_restores(self):
        from pos_font import (PALETTE_ROWS, POS_COLOR_DEFAULTS_LIGHT,
                              normalize_colors)
        a=self.a
        a._place_dialog=lambda dlg,width,height:dlg.geometry(
            f'{width}x{height}+0+0')
        a.settings.save=Mock();a._analyze=Mock()
        opened_sizes=dict(a.settings.get('pos_font_multipliers'))
        opened_colors=normalize_colors(a.settings.get('pos_font_colors_light'),False)
        dark_before=a.settings.get('pos_font_colors')
        a.open_pos_font_dialog()
        dlg=a._pos_font_dialog

        def wait(ms):
            done=[]
            self.root.after(ms,lambda:done.append(1))
            while not done:self.root.update()

        def descendants(parent):
            found=[]
            for child in parent.winfo_children():
                found.append(child)
                found.extend(descendants(child))
            return found

        def palette_cells():
            palette=a._pos_color_palette;palette.update()
            return palette,{w.cget('bg'):w for w in descendants(palette)
                            if isinstance(w,tk.Frame) and w.grid_info()}

        try:
            self.root.deiconify();dlg.deiconify();dlg.update()
            label=next(w for w in descendants(dlg) if isinstance(w,tk.Label)
                       and w.cget('text')=='名詞')
            form=label.master;row=int(label.grid_info()['row'])
            spinbox=form.grid_slaves(row=row,column=1)[0]
            swatch=form.grid_slaves(row=row,column=2)[0]
            # Size: no apply button, the text follows the box.
            spinbox.delete(0,'end');spinbox.insert(0,'1.7')
            wait(250)
            self.assertEqual(a.settings.get('pos_font_multipliers')['名詞'],1.7)
            self.assertTrue(a.settings.save.called)
            # Colour: hovering shows the colour without saving it.
            swatch.invoke();palette,cells=palette_cells()
            target=PALETTE_ROWS[2][6]
            # Light pane: the light colours are kept apart from the dark ones
            # and the swatch colour is kept as it is (2026-10-13).
            kept=target;noun=POS_COLOR_DEFAULTS_LIGHT['名詞']
            a.settings.save.reset_mock()
            cells[target].event_generate('<Enter>');self.root.update()
            self.assertEqual(a.settings.get('pos_font_colors_light')['名詞'],kept)
            self.assertFalse(a.settings.save.called)
            cells[target].event_generate('<Leave>');wait(150)
            self.assertEqual(a.settings.get('pos_font_colors_light')['名詞'],noun)
            # Closing the palette without a click also goes back.
            cells[target].event_generate('<Enter>');self.root.update()
            palette.destroy();self.root.update()
            self.assertEqual(a.settings.get('pos_font_colors_light')['名詞'],noun)
            self.assertFalse(a.settings.save.called)
            # A click keeps it.
            swatch.invoke();palette,cells=palette_cells()
            cells[target].event_generate('<Enter>');self.root.update()
            cells[target].event_generate('<ButtonRelease-1>');self.root.update()
            self.assertEqual(a.settings.get('pos_font_colors_light')['名詞'],kept)
            self.assertTrue(a.settings.save.called)
            buttons={w.cget('text'):w for w in descendants(dlg)
                     if isinstance(w,tk.Button)}
            # One button leaves every part of speech in the pane's colour.
            buttons['色をすべて変えない'].invoke();self.root.update()
            self.assertFalse(any(a.settings.get('pos_font_colors_light').values()))
            self.assertEqual(swatch.cget('text'),'変えない')
            # 色を初期化 puts back this mode's colours only.
            buttons['色を初期化'].invoke();self.root.update()
            self.assertEqual(a.settings.get('pos_font_colors_light'),POS_COLOR_DEFAULTS_LIGHT)
            self.assertEqual(a.settings.get('pos_font_colors'),dark_before)
            # Cancel puts back what was there when the dialog opened.
            buttons['キャンセル'].invoke();self.root.update()
            self.assertEqual(a.settings.get('pos_font_multipliers'),opened_sizes)
            self.assertEqual(a.settings.get('pos_font_colors_light'),opened_colors)
            self.assertEqual(opened_colors,POS_COLOR_DEFAULTS_LIGHT)
            self.assertEqual(a.settings.get('pos_font_colors'),dark_before)
            self.assertIsNone(a._pos_font_dialog)
        finally:
            if dlg.winfo_exists():dlg.destroy()
            self.root.withdraw()
