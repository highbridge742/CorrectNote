# -*- coding: utf-8 -*-
import tkinter as tk
import unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import Mock,patch
from boundary_colors import (install,BoundaryColors,plans,remember,
                              boundary_marker_spans,plan_for)
from editor_guides import FLASH_COLOR
from settings import Settings
from vocabulary import VocabularyStore
import app

class BoundaryColorTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('580x220+0+0')
        self.errors=[];self.root.report_callback_exception=lambda *a:self.errors.append(a)
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root=self.root
        self.a.settings=Settings();self.a.store=VocabularyStore()
        # 印は既定オン（設定の版に関係なく、ここでは明示する）。
        self.a.settings.set('show_ctrl_boundaries',True)
        # 印は Ctrl を押している間だけ出る。描き方の試験では押したままにする。
        self.a._ctrl_boundaries_held=True
        self.a._ime_first=lambda fn:fn;self.a._close_dropdown=Mock();self.a._analyze=Mock()
        for name in ('editor','result_view','_quick_text'):
            widget=tk.Text(self.root,undo=True,width=1,height=1,wrap='word',padx=14,pady=12,bd=2)
            widget.pack(side='left',fill='both',expand=True)
            widget.insert('1.0','😀私は、次へ！？進む。\nとはいえ、資料について確認する。')
            widget.edit_reset();widget.mark_set('insert','1.0');setattr(self.a,name,widget)
            self.a._bind_block_navigation(widget);install(self.a,widget)
        self.publish()
        self.root.update()
        self.a.show_ctrl_boundaries_var=tk.BooleanVar(master=self.root,value=True)
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def settle(self,ms=350):
        done=tk.BooleanVar(master=self.root,value=False)
        self.root.after(ms,lambda:done.set(True));self.root.wait_variable(done)
        self.root.update_idletasks()
    def publish(self):
        import corrector
        fn=getattr(self.a.store,'_tokenize_fn',None)
        if fn is None:fn=self.a.store._tokenize_fn=corrector.make_tokenizer(self.a.store)
        texts=[line for w in (self.a.editor,self.a.result_view,self.a._quick_text)
               for line in w.get('1.0','end-1c').split('\n')]
        remember(self.a,plans(texts,fn))
    def texts(self,w):
        colors=w._correctnote_boundary_colors
        return [w.get(f'{row}.0+{offset}c',f'{row}.0+{offset+1}c')
                for row in sorted(colors._marker_indices)
                for offset in colors._marker_indices[row]]
    def test_all_panes_native_pos_match_actual_navigation_and_readonly(self):
        self.a.result_view.configure(state='disabled');self.settle()
        from tests_tk_keys import deliver_key
        for w in (self.a.editor,self.a.result_view,self.a._quick_text):
            spans=self.texts(w)
            self.assertTrue(spans)
            self.assertTrue(all(len(value)==1 for value in spans),spans)
            expected=[]
            for row,text in enumerate(w.get('1.0','end-1c').split('\n'),1):
                value=plan_for(self.a,w,row,text)
                if value is not None:
                    expected.extend(text[a:z] for a,z in boundary_marker_spans(text,value[0]))
            self.assertEqual(spans,expected)
            colors=w._correctnote_boundary_colors
            self.assertTrue(colors.lines)
            # The tick is the underline of the character before the stop.
            self.assertEqual(set(colors._tick_ranges()),set(colors.lines))
            for (row,offset) in colors.lines:
                index=f'{row}.0+{offset}c'
                self.assertIn(BoundaryColors.TICK_TAG,w.tag_names(index))
                self.assertNotIn(BoundaryColors.TICK_TAG,w.tag_names(f'{index}+1c'))
                self.assertEqual(row,1)
            tag=BoundaryColors.TICK_TAG
            self.assertTrue(int(w.tag_cget(tag,'underline')))
            self.assertEqual(str(w.tag_cget(tag,'underlinefg')),colors._marker_color())
            self.assertNotEqual(str(w.tag_cget(tag,'underlinefg')),FLASH_COLOR)
            original=w.get('1.0','end-1c')
            for expected in ('😀私は、','😀私は、次へ！？','😀私は、次へ！？進む。'):
                deliver_key(w,'<Control-Right>','Right',39,state=4)
                self.assertEqual(w.get('1.0','insert'),expected)
            self.assertEqual(w.get('1.0','end-1c'),original)
        self.assertEqual(self.errors,[])
    def test_option_clears_each_pane_default_on_and_persists_off(self):
        self.assertTrue(Settings().get('show_ctrl_boundaries'))
        self.settle();self.assertTrue(self.a.settings.get('show_ctrl_boundaries'))
        self.a.show_ctrl_boundaries_var.set(False);self.a._on_toggle_ctrl_boundaries();self.settle()
        for w in (self.a.editor,self.a.result_view,self.a._quick_text):
            self.assertFalse(w._correctnote_boundary_colors._marker_indices)
            self.assertFalse(w._correctnote_boundary_colors.lines)
            self.assertIsNone(w._correctnote_boundary_colors._job)
        with tempfile.TemporaryDirectory(prefix='cn-boundary-') as d:
            p=str(Path(d)/'settings.json');self.a.settings.save(p)
            # オフにした人の設定は、次の起動でもオフのまま
            self.assertFalse(Settings(p).get('show_ctrl_boundaries'))
            Path(p).write_text(json.dumps({'show_ctrl_boundaries':False,
                                           'ctrl_boundaries_defaults':'3'}),encoding='utf8')
            self.assertFalse(Settings(p).get('show_ctrl_boundaries'))
        self.a.show_ctrl_boundaries_var.set(True);self.a._on_toggle_ctrl_boundaries();self.settle()
        with tempfile.TemporaryDirectory(prefix='cn-boundary-') as d:
            p=str(Path(d)/'settings.json');self.a.settings.save(p)
            self.assertTrue(Settings(p).get('show_ctrl_boundaries'))
        self.assertIn('、',self.texts(self.a.editor))
    def test_markers_follow_the_cursor_row_unless_all_rows_are_on(self):
        w=self.a.editor;self.settle()
        rows=lambda widget:{row for row,offset in widget._correctnote_boundary_colors.lines}
        self.assertEqual(rows(w),{1});self.assertEqual(rows(self.a.result_view),{1})
        w.mark_set('insert','2.3');self.settle(50)
        self.assertEqual(rows(w),{2});self.assertEqual(rows(self.a.result_view),{2})
        self.a.settings.set('ctrl_boundaries_cursor_row_only',False)
        w._correctnote_boundary_colors.queue_draw();self.settle(50)
        self.assertEqual(rows(w),{1,2})
        self.assertEqual(self.errors,[])
    def test_rows_without_stops_count_as_unanalyzed_for_the_gutter(self):
        w=self.a.editor;self.settle()
        self.assertFalse(self.a._row_navigation_missing(1))
        w.insert('1.end','まだ計算していない行')
        self.a._ctrl_boundary_plans.clear();w._correctnote_boundary_colors._painted.clear()
        w._correctnote_boundary_colors._last_plans.clear()
        self.assertTrue(self.a._row_navigation_missing(1))
        w.insert('end','\n　\n');self.assertFalse(self.a._row_navigation_missing(3))
        self.a.settings.set('show_ctrl_boundaries',False)
        self.a.settings.set('pos_font_multipliers',{k:1.0 for k in __import__('pos_font').POS_CATEGORIES})
        self.a.settings.set('pos_font_colors',{k:'' for k in __import__('pos_font').POS_CATEGORIES})
        self.a.settings.set('pos_font_colors_light',{k:'' for k in __import__('pos_font').POS_CATEGORIES})
        self.assertFalse(self.a._row_navigation_missing(1))
        self.publish();self.a.settings.set('show_ctrl_boundaries',True)
        self.assertFalse(self.a._row_navigation_missing(1))
    def test_gutter_redraws_only_when_an_awaited_row_arrives(self):
        w=self.a.editor;self.settle()
        calls=[];self.a._redraw_gutter_now=lambda:calls.append(1)
        self.a.editor_gutter=getattr(self.a,'editor_gutter',None) or object()
        from boundary_colors import remember
        remember(self.a,{'見えていない行':((),(),())});self.settle(100)
        self.assertEqual(calls,[])
        w.insert('1.end','まだ計算していない行');text=w.get('1.0','1.end')
        self.a._ctrl_boundary_plans.clear();w._correctnote_boundary_colors._painted.clear()
        w._correctnote_boundary_colors._last_plans.clear()
        self.assertTrue(self.a._row_navigation_missing(1))
        remember(self.a,{text:((),(),())});self.settle(100)
        self.assertEqual(calls,[1])
        remember(self.a,{text:((),(),())});self.settle(100)
        self.assertEqual(calls,[1])
    def test_typing_keeps_pos_sizes_until_the_new_plan_arrives(self):
        from pos_font import POS_FONT_TAGS
        self.a.settings.set('pos_font_multipliers',{'名詞':1.5})
        w=self.a.editor;colors=w._correctnote_boundary_colors
        colors.refresh_option();self.settle()
        tag=POS_FONT_TAGS['名詞']
        self.assertTrue(w.tag_nextrange(tag,'2.0','2.end'))
        w.insert('2.end','あ');self.settle()
        self.assertTrue(w.tag_nextrange(tag,'2.0','2.end'))
        self.publish();self.settle()
        self.assertTrue(w.tag_nextrange(tag,'2.0','2.end'))
        self.assertEqual(self.errors,[])
    def test_colour_preview_keeps_sizes_and_line_layout(self):
        # 色見本にマウスを乗せても行が動かない（大きさは掛け直さない）。うに 2026-10-13
        from pos_font import POS_FONT_TAGS,POS_COLOR_TAGS,POS_CATEGORIES
        self.a.settings.set('pos_font_multipliers',{'名詞':1.5})
        self.a.settings.set('pos_font_colors_light',{k:'' for k in POS_CATEGORIES})
        w=self.a.editor;colors=w._correctnote_boundary_colors
        colors.refresh_option();self.settle()
        size_tag=POS_FONT_TAGS['名詞']
        sized=str(w.tag_ranges(size_tag));font=str(w.tag_cget(size_tag,'font'))
        self.assertNotEqual(sized,'()')
        w.tk.call(w,'sync')
        repaint=Mock(side_effect=colors.refresh_option);colors.refresh_option=repaint
        for chosen in ({'名詞':'#cc3322'},{'名詞':'#2266cc','動詞':'#118833'},
                       {'動詞':'#aa22aa'},{}):
            self.a._choose_pos_font_colors(dict({k:'' for k in POS_CATEGORIES},**chosen),save=False)
            # Tk lays no line out again: nothing can move.
            self.assertEqual(w.tk.call(w,'pendingsync'),0,chosen)
            self.assertEqual(str(w.tag_ranges(size_tag)),sized)
            self.assertEqual(str(w.tag_cget(size_tag,'font')),font)
            for major in ('名詞','動詞'):
                tag=POS_COLOR_TAGS[major]
                self.assertEqual(bool(w.tag_ranges(tag)),major in chosen,(chosen,major))
                if major in chosen:
                    self.assertEqual(str(w.tag_cget(tag,'foreground')),chosen[major])
                    self.assertEqual(str(w.tag_cget(tag,'font')),'')
        repaint.assert_not_called()
        self.assertEqual(self.errors,[])
    def test_paint_keeps_text_selection_insert_and_existing_undo(self):
        self.a.settings.set('ctrl_boundaries_cursor_row_only',False)
        w=self.a.editor;w.insert('1.0','追加');w.edit_separator()
        w.tag_add('sel','1.2','1.7');w.mark_set('insert','1.8')
        original=w.get('1.0','end-1c');selected=tuple(w.tag_ranges('sel'));cursor=w.index('insert')
        self.settle()
        self.assertEqual(w.get('1.0','end-1c'),original)
        self.assertEqual(tuple(w.tag_ranges('sel')),selected);self.assertEqual(w.index('insert'),cursor)
        self.assertTrue(w._correctnote_boundary_colors.lines)
        w.edit_undo();self.assertNotIn('追加',w.get('1.0','end-1c'));self.settle()
        self.assertIn('、',self.texts(w));self.assertEqual(self.errors,[])
    def test_changed_tab_and_undo_clear_stale_ranges_then_repaint(self):
        w=self.a.editor;self.settle()
        w.delete('1.0','end');w.insert('1.0','（文章）次へ！？')
        self.assertFalse(w._correctnote_boundary_colors._marker_indices);self.publish();self.settle()
        self.assertIn('）',self.texts(w));self.assertNotIn('文章）',self.texts(w))
        w.delete('1.0','end');w.insert('1.0','\n \t　\n')
        self.settle();self.assertFalse(w._correctnote_boundary_colors._marker_indices)
    def test_hidden_clipped_long_and_link_only_rows_skip_tokenization(self):
        w=self.a.editor;self.a.settings.set('show_ctrl_boundaries',False)
        w.delete('1.0','end');w.insert('1.0','x'*4001+'\nhttps://example.test/\nC:\\資料\\メモ.txt\n \t　')
        fn=Mock(side_effect=AssertionError('literal row NLP'))
        self.a.store._tokenize_fn=fn
        self.a.settings.set('show_ctrl_boundaries',True);w._correctnote_boundary_colors.refresh_option();self.settle()
        fn.assert_not_called();self.assertFalse(w._correctnote_boundary_colors._marker_indices);self.assertEqual(self.errors,[])
    def test_scroll_wrap_resize_only_visible_rows_and_reuse_cached_tokens(self):
        w=self.a.editor;w.delete('1.0','end')
        w.insert('1.0','\n'.join('資料を確認する。'+str(i) for i in range(90)))
        import corrector
        actual=corrector.make_tokenizer(self.a.store);self.a.store._tokenize_fn=Mock(wraps=actual)
        self.publish();self.a.store._tokenize_fn.reset_mock()
        self.settle();fn=self.a.store._tokenize_fn;before=fn.call_count
        self.assertEqual(before,0)
        w._correctnote_boundary_colors.queue();self.settle();self.assertEqual(fn.call_count,before)
        w.yview_moveto(1);self.settle()
        # Every row is sized ahead of time; only rows in view get ticks.
        rows={row for row,offset in w._correctnote_boundary_colors.lines}
        self.assertTrue(rows)
        self.assertTrue(all(int(row)>60 for row in rows))
        self.assertIn(1,w._correctnote_boundary_colors._painted)
        self.root.geometry('700x280+0+0');self.settle();self.assertEqual(self.errors,[])
    def test_ime_preedit_defers_and_destroy_cancels_all_callbacks(self):
        w=self.a.editor;colors=w._correctnote_boundary_colors
        with patch('ime_watch.composition_active',return_value=True),patch('corrector.make_tokenizer',side_effect=AssertionError('preedit NLP')):
            colors.refresh_option();self.settle();self.assertFalse(colors._marker_indices)
        self.settle();self.assertIn('、',self.texts(w))
        w.destroy();self.assertTrue(colors._closed);self.assertIsNone(colors._job)
        self.assertNotIn(colors.changed,w._correctnote_observers.get('changed',[]))
        self.settle();self.assertEqual(self.errors,[])
    def test_correction_link_and_selection_colors_keep_priority(self):
        w=self.a.editor;self.settle()
        for tag,color in (('autofixed','#cc3322'),('autochosen','#008888'),('explicit_link','#065dcc')):
            w.tag_configure(tag,foreground=color);w.tag_add(tag,'1.2','1.4')
        w._correctnote_boundary_colors.queue();self.settle()
        self.assertNotIn('ctrl_boundary_marker',w.tag_names('1.3'))
        self.assertEqual(w.tag_cget('autofixed','foreground'),'#cc3322')
        self.assertEqual(w.tag_cget('explicit_link','foreground'),'#065dcc')
        self.assertTrue(w._correctnote_boundary_colors.lines)

    def test_marks_are_tags_not_windows_over_the_text(self):
        # 窓の印は Windows で行の移動・スクロールを大きく遅くした（2026-10-12）
        self.settle();w=self.a.editor
        colors=w._correctnote_boundary_colors
        self.assertTrue(colors.lines)
        for _ in range(3):
            colors.refresh_option();self.settle()
        self.assertEqual(w.winfo_children(),[])
        self.assertEqual(w.get('1.0','end-1c').count('😀'),1)
        self.assertEqual(self.errors,[])
    def test_user_underline_is_not_recoloured_by_a_tick(self):
        from text_format import STYLE_TAGS
        self.settle();w=self.a.editor
        colors=w._correctnote_boundary_colors
        (row,offset)=next(iter(colors.lines))
        index=f'{row}.0+{offset}c'
        w.tag_remove(BoundaryColors.TICK_TAG,'1.0','end')
        w.tag_add(STYLE_TAGS['underline'],index,f'{index}+1c')
        colors.queue_draw();self.settle()
        self.assertNotIn(BoundaryColors.TICK_TAG,w.tag_names(index))
        self.assertTrue(colors.lines)
        self.assertEqual(self.errors,[])
    def test_adjacent_closing_punctuation_stops_keep_independent_markers(self):
        w=self.a.editor;w.delete('1.0','end');w.insert('1.0','文）。」')
        self.publish();self.settle()
        self.assertEqual(self.texts(w),['）','。'])
        self.assertEqual(len(w._correctnote_boundary_colors.lines),2)
    def test_editing_one_row_keeps_other_rows_ticks(self):
        self.a.settings.set('ctrl_boundaries_cursor_row_only',False)
        w=self.a.editor;colors=w._correctnote_boundary_colors
        colors.queue_draw();self.settle()
        kept={index for index in colors.lines if index[0]==2}
        self.assertTrue(kept)
        w.insert('1.0','あ')
        self.assertTrue(kept<=set(colors.lines))
        self.assertTrue(kept<=set(colors._tick_ranges()))
        w.insert('1.end','\n新しい行');self.root.update_idletasks()
        moved={(3,offset) for row,offset in kept}
        self.assertTrue(moved<=set(colors.lines))
        self.assertTrue(moved<=set(colors._tick_ranges()))
        self.assertEqual(self.errors,[])
    def test_enter_moves_marks_with_the_text(self):
        # 改行で下の行が動くとき、印が元の場所に取り残されない（2026-10-12）
        self.a.settings.set('ctrl_boundaries_cursor_row_only',False)
        w=self.a.editor;colors=w._correctnote_boundary_colors
        colors.queue_draw();self.settle()
        below={offset for (row,offset) in colors._tick_ranges() if row==2}
        self.assertTrue(below)
        w.insert('1.end','\n新しい行')
        # Before any redraw: the marks are on the moved row, none on the new one.
        ticks=set(colors._tick_ranges())
        self.assertEqual({offset for row,offset in ticks if row==3},below)
        self.assertFalse({offset for row,offset in ticks if row==2})
        self.settle()
        self.assertTrue(colors.lines)
        self.assertEqual(self.errors,[])
    def test_scroll_keeps_ticks_on_their_characters(self):
        w=self.a.editor;colors=w._correctnote_boundary_colors
        w.delete('1.0','end');w.insert('1.0','\n'.join('資料を確認する。' for i in range(60)))
        w.mark_set('insert','1.0');self.publish();self.settle()
        before=set(colors._tick_ranges())
        self.assertTrue(before)
        w.yview_scroll(3,'units')
        self.assertEqual(set(colors._tick_ranges()),before)
        self.settle();self.assertEqual(self.errors,[])
    def test_rows_out_of_view_get_pos_sizes_ahead_of_scrolling(self):
        from pos_font import POS_FONT_TAGS
        self.a.settings.set('pos_font_multipliers',{'名詞':1.5})
        w=self.a.editor;colors=w._correctnote_boundary_colors
        w.delete('1.0','end');w.insert('1.0','\n'.join('資料を確認する。'+str(i) for i in range(120)))
        colors.refresh_option();self.publish();self.settle(800)
        tag=POS_FONT_TAGS['名詞']
        self.assertGreater(int(w.index('@0,'+str(w.winfo_height()-1)).split('.')[0]),1)
        self.assertLess(int(w.index('@0,'+str(w.winfo_height()-1)).split('.')[0]),100)
        self.assertTrue(w.tag_nextrange(tag,'110.0','110.end'))
        self.assertEqual(self.errors,[])
    def test_loaded_text_skips_clearing_untagged_rows_but_clears_stale_ones(self):
        from pos_font import POS_FONT_TAGS
        self.a.settings.set('pos_font_multipliers',{'名詞':1.5})
        w=self.a.editor;colors=w._correctnote_boundary_colors
        text='\n'.join('資料を確認する。'+str(i) for i in range(120))
        w.delete('1.0','end');w.insert('1.0',text)
        colors.refresh_option();self.publish();self.settle(800)
        tag=POS_FONT_TAGS['名詞']
        cleared=[];original=colors._clear_pos_tags
        def counted(*args,**kw):
            cleared.append(args);return original(*args,**kw)
        colors._clear_pos_tags=counted
        try:
            # A tab switch: the whole text is replaced and arrives untagged.
            w.delete('1.0','end');w.insert('1.0',text);self.settle(800)
            self.assertTrue(w.tag_nextrange(tag,'110.0','110.end'))
            self.assertLess(len(cleared),10)
            # A row that still carries an old range is cleared before painting.
            w.tag_add(tag,'50.0','50.end');colors._painted.pop(50,None)
            colors._schedule_sweep();self.settle(400)
        finally:
            colors._clear_pos_tags=original
        self.assertTrue(w.tag_nextrange(tag,'50.0','50.end'))
        self.assertNotIn(tag,w.tag_names('50.7'))
        self.assertEqual(self.errors,[])
    def test_sizing_rows_out_of_view_does_not_redraw_the_marks(self):
        self.a.settings.set('pos_font_multipliers',{'名詞':1.5})
        w=self.a.editor;colors=w._correctnote_boundary_colors
        text='\n'.join('資料を確認する。'+str(i) for i in range(300))
        w.delete('1.0','end');w.insert('1.0',text)
        colors.refresh_option();self.publish();self.settle(800)
        drawn=[];original=colors.draw_markers
        def counted():
            drawn.append(1);return original()
        colors.draw_markers=counted
        try:
            w.delete('1.0','end');w.insert('1.0',text);w.mark_set('insert','1.0')
            self.settle(1200)
        finally:
            colors.draw_markers=original
        self.assertTrue(colors._marker_indices.get(1))
        self.assertTrue(colors.lines)
        self.assertLessEqual(len(drawn),6)
        self.assertEqual(self.errors,[])
    def test_rows_without_a_plan_are_not_repainted_on_every_pass(self):
        import boundary_colors
        w=self.a.editor;colors=w._correctnote_boundary_colors
        w.delete('1.0','end');w.insert('1.0','\n'.join('計画なし'+str(i) for i in range(80)))
        self.settle(400)
        for i in range(80):self.a._ctrl_boundary_plans['計画なし'+str(i)]=None
        colors._schedule_sweep();self.settle(400)
        painted=[];original=colors.paint_row
        def counted(row,*args,**kw):
            painted.append(row);return original(row,*args,**kw)
        colors.paint_row=counted
        try:
            for _ in range(3):
                colors._schedule_sweep();self.settle(200)
        finally:
            colors.paint_row=original
        self.assertEqual(painted,[])
        self.assertEqual(self.errors,[])
    def test_tick_is_an_underline_between_text_and_background(self):
        w=self.a.editor;colors=w._correctnote_boundary_colors
        def rgb(color):return w.winfo_rgb(color)
        tag=BoundaryColors.TICK_TAG
        for bg,fg in (('#ffffff','#000000'),('#1e1e1e','#d4d4d4')):
            w.configure(background=bg,foreground=fg);colors.queue_draw();self.settle()
            self.assertTrue(colors.lines)
            self.assertTrue(int(w.tag_cget(tag,'underline')))
            color=rgb(str(w.tag_cget(tag,'underlinefg')));back=rgb(bg);front=rgb(fg)
            # Softer than the text but plainly visible, on both themes
            # (nearer the text: the faint underline was hard to see).
            to_back=sum(abs(c-b) for c,b in zip(color,back))
            to_text=sum(abs(c-f) for c,f in zip(color,front))
            self.assertGreater(to_text,0);self.assertLess(to_text,to_back)
        self.assertEqual(self.errors,[])
    def test_marks_show_only_while_ctrl_is_held(self):
        from tests_tk_keys import deliver_key
        self.a._ctrl_boundaries_held=False
        self.a.settings.set('ctrl_boundaries_cursor_row_only',False)
        panes=(self.a.editor,self.a.result_view,self.a._quick_text)
        for w in panes:w._correctnote_boundary_colors.queue_draw()
        self.settle()
        for w in panes:
            self.assertFalse(w._correctnote_boundary_colors.lines)
            self.assertFalse(w.tag_ranges(BoundaryColors.TICK_TAG))
            self.assertTrue(w._correctnote_boundary_colors._marker_indices)
        w=self.a.editor;w.focus_force();self.root.update()
        deliver_key(w,'<KeyPress-Control_L>','Control_L',17)
        # At once, in every pane, without waiting for a redraw.
        for pane in panes:
            self.assertTrue(pane._correctnote_boundary_colors.lines)
            self.assertTrue(pane.tag_ranges(BoundaryColors.TICK_TAG))
        deliver_key(w,'<Control-Right>','Right',39,state=4)
        self.settle();self.assertTrue(w._correctnote_boundary_colors.lines)
        deliver_key(w,'<KeyRelease-Control_L>','Control_L',17,state=4,event_type=3)
        for pane in panes:
            self.assertFalse(pane._correctnote_boundary_colors.lines)
            self.assertFalse(pane.tag_ranges(BoundaryColors.TICK_TAG))
        self.settle()
        for pane in panes:self.assertFalse(pane.tag_ranges(BoundaryColors.TICK_TAG))
        deliver_key(w,'<KeyPress-Control_R>','Control_R',17)
        self.assertTrue(w.tag_ranges(BoundaryColors.TICK_TAG))
        # A release that went elsewhere: the next plain key hides the marks.
        deliver_key(w,'<KeyPress>','a',65,char='a')
        self.assertFalse(w.tag_ranges(BoundaryColors.TICK_TAG))
        deliver_key(w,'<KeyPress-Control_L>','Control_L',17)
        self.assertTrue(w.tag_ranges(BoundaryColors.TICK_TAG))
        w._correctnote_boundary_colors.ctrl_up()   # as on <FocusOut>
        self.assertFalse(w.tag_ranges(BoundaryColors.TICK_TAG))
        self.assertEqual(self.errors,[])
    def test_row_end_has_no_tick(self):
        w=self.a.editor;w.delete('1.0','end');w.insert('1.0','資料を確認する。')
        self.publish();self.settle()
        text=w.get('1.0','1.end')
        self.assertTrue(self.texts(w))
        self.assertTrue(all(offset<len(text)-1 for row,offset in w._correctnote_boundary_colors.lines))
        self.assertEqual(self.errors,[])
    def test_option_restores_visible_plan_after_bounded_cache_eviction(self):
        self.settle();w=self.a.editor
        before=self.texts(w);self.assertTrue(before)
        from boundary_colors import PLAN_CACHE_ROWS
        remember(self.a,{str(i):((0,1),()) for i in range(PLAN_CACHE_ROWS+20)})
        self.assertNotIn(w.get('1.0','1.end'),self.a._ctrl_boundary_plans)
        self.a.show_ctrl_boundaries_var.set(False);self.a._on_toggle_ctrl_boundaries();self.settle()
        self.assertFalse(self.texts(w))
        self.a.show_ctrl_boundaries_var.set(True);self.a._on_toggle_ctrl_boundaries();self.settle()
        self.assertEqual(self.texts(w),before);self.assertEqual(self.errors,[])

if __name__=='__main__':unittest.main()
