"""September UI regressions, actual Tk widgets and synthetic text only."""
import tkinter as tk
import tkinter.font as tkfont
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import app, corrector, tests_gui_file_format, tests_gui_fonts
from session import new_tab
from text_navigation import text_edge
from vocabulary import VocabularyStore


class NavigationDetailsTests(unittest.TestCase):
    def test_conjunctions_use_existing_pos_not_substring_matching(self):
        fn=corrector.make_tokenizer(VocabularyStore())
        for text,pieces in (
            ('しかし次へ進む',['しかし','次へ','進む']),
            ('とはいえ進む',['とはいえ','進む']),
            ('甲そして乙',['甲そして','乙']),
            ('そこでもう一度',['そこで','もう一度']),
            ('またぐ道',['またぐ道'])):
            with self.subTest(text=text):
                tokens=fn(text);ends=[0]
                while ends[-1]<len(text):ends.append(text_edge(text,ends[-1],1,tokens))
                self.assertEqual([text[a:b] for a,b in zip(ends,ends[1:])],pieces)
                for a,b in zip(ends,ends[1:]):self.assertEqual(text_edge(text,b,-1,tokens),a)

    def test_particle_edges_keep_following_punctuation_runs(self):
        fn=corrector.make_tokenizer(VocabularyStore())
        examples=[
            ('私は本を読む。次へ進む！',['私は','本を','読む。','次へ','進む！']),
            ('ここには、何もない。',['ここに','は、','何も','ない。']),
            ('読むから、分かるよ！次へ。',['読むから、','分かるよ！','次へ。']),
            ('しかし、私は進む。',['しかし、','私は','進む。']),
            ('はさみと橋',['はさみと','橋']),
            ('😀私は、次へ！？進む。',['😀私は、','次へ！？','進む。']),
            ('私は  次へ',['私は','  ','次へ']),
        ]
        for run in ('、','。','！？','!?','……','‥','。。、、!!??…','，．,.'):
            examples.append(('私も'+run+'次へ',['私も'+run,'次へ']))
        for text,pieces in examples:
            with self.subTest(text=text):
                tokens=fn(text);expected=[0]
                for piece in pieces:expected.append(expected[-1]+len(piece))
                self.assertEqual(''.join(pieces),text)
                for column in range(len(text)+1):
                    self.assertEqual(text_edge(text,column,1,tokens),
                        next((i for i in expected if i>column),len(text)))
                    self.assertEqual(text_edge(text,column,-1,tokens),
                        next((i for i in reversed(expected) if i<column),0))

    def test_punctuation_runs_and_bracket_sides(self):
        for text,pieces in (
            ('あ……！？次',['あ……！？','次']),
            ('あ。。、、!!??次',['あ。。、、!!??','次']),
            ('call()next',['call()','next']),
            ('call(  )next',['call','(  )','next']),
            ('前「中」後',['前','「中」','後']),
            ('前（中）後',['前','（中）','後']),
            ('前[]後',['前[]','後']),
            ('😀…後',['😀…','後'])):
            # Whitespace-only brackets retain the separate whitespace edges.
            if text=='call(  )next':
                self.assertEqual(text_edge(text,0,1),5)
                continue
            ends=[0]
            while ends[-1]<len(text):ends.append(text_edge(text,ends[-1],1))
            self.assertEqual([text[a:b] for a,b in zip(ends,ends[1:])],pieces)
            for a,b in zip(ends,ends[1:]):self.assertEqual(text_edge(text,b,-1),a)


class FontDialogDetailsTests(unittest.TestCase):
    setUp=tests_gui_fonts.FontTkTests.setUp
    tearDown=tests_gui_fonts.FontTkTests.tearDown

    def test_size_only_and_default_buttons_accept_windows_font_alias(self):
        a=self.a;a._place_dialog=Mock()
        with patch('tkinter.font.families',return_value=('游明朝','Arial')):
            a.open_font_dialog()
        dlg=a._font_dialog
        descendants=[]
        def walk(w):
            for c in w.winfo_children():descendants.append(c);walk(c)
        walk(dlg)
        size=next(w for w in descendants if isinstance(w,tk.Spinbox))
        buttons={w.cget('text'):w for w in descendants if isinstance(w,tk.Button)}
        size.delete(0,'end');size.insert(0,'24');buttons['適用'].invoke()
        self.assertEqual(a._editor_font(),('Yu Mincho',24))
        buttons['初期設定'].invoke();self.assertEqual(a._editor_font(),app.EDITOR_FONT)
        size.delete(0,'end');size.insert(0,'28');buttons['OK'].invoke()
        self.assertEqual(a._editor_font(),('Yu Mincho',28))
        self.assertIsNone(a._font_dialog)

    def test_end_rule_keeps_row_height_and_caret_at_large_font(self):
        a=self.a
        self.root.attributes('-alpha',0);self.root.deiconify();self.root.geometry('640x850+0+0')
        for w in (a.editor,a.result_view):
            w.pack(side='left',fill='both',expand=True)
            w.delete('1.0','end');w.insert('1.0','本文\n\n\n後半\n\n\n')
            w.configure(font=('Yu Mincho',28),spacing1=2,spacing3=4,width=1,height=1)
        self.root.update()
        a._configure_end_rule_tag();a._paint_end_rule();self.root.update_idletasks()
        for w in (a.editor,a.result_view):
            heights=[w.dlineinfo(f'{row}.0')[3] for row in (5,6,7)]
            self.assertEqual(len(set(heights)),1)
            w.mark_set('insert','5.0');a._paint_end_rule()
            self.assertEqual(w.dlineinfo('5.0')[3],heights[0])
            self.assertEqual(w._end_rule_line.winfo_height(),1)


    def test_different_wrapping_keeps_following_rows_aligned_after_font_change(self):
        from text_layout import align_rows
        a=self.a;self.root.attributes('-alpha',0);self.root.geometry('640x850+0+0');self.root.deiconify()
        a.editor.delete('1.0','end');a.result_view.delete('1.0','end')
        a.editor.insert('1.0','長い元の文章です。'*6+'\n次の段落\n最後\n')
        a.result_view.insert('1.0','短い補正結果\n次の段落\n最後\n')
        for w in (a.editor,a.result_view):w.configure(width=1,height=1);w.pack(side='left',fill='both',expand=True)
        for size in (28,18,11,28):
            for w in (a.editor,a.result_view):w.configure(font=('Yu Mincho',size))
            self.root.update()
            align_rows(a.editor,a.result_view);self.root.update()
            self.assertEqual(a.editor.dlineinfo('2.0')[1],a.result_view.dlineinfo('2.0')[1])
            self.assertEqual(a.editor.dlineinfo('3.0')[1],a.result_view.dlineinfo('3.0')[1])
            self.assertFalse(align_rows(a.editor,a.result_view))
        align_rows(a.editor,a.result_view,enabled=False);self.root.update()
        self.assertFalse(any(t.startswith('paired_row_pad_') for t in a.result_view.tag_names('1.0')))

class SharedGutterTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        a=self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);a.root=self.root
        a.editor=tk.Text(self.root,font=('Yu Mincho',28))
        a.result_view=tk.Text(self.root,font=('Yu Mincho',28))
        for name,w in (('editor_gutter',a.editor),('result_gutter',a.result_view)):
            w.insert('1.0','\n'.join('本文' for _ in range(105)))
            g=app.LineNumberGutter(self.root,w,on_cursor_row=a._sync_cursor_line,
                active_row=lambda:getattr(a,'_active_cursor_row',1))
            setattr(a,name,g)
        self.root.update_idletasks()
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def test_both_panes_follow_active_cursor_and_tab_restore(self):
        a=self.a
        a.editor.mark_set('insert','22.0');self.root.update_idletasks()
        self.assertEqual((a.editor_gutter._cursor_row,a.result_gutter._cursor_row),('22','22'))
        with patch.object(self.root,'focus_get',return_value=a.result_view):
            a.result_view.mark_set('insert','30.0');self.root.update_idletasks()
        self.assertEqual((a.editor_gutter._cursor_row,a.result_gutter._cursor_row),('30','30'))
        self.assertEqual(a.editor.index('insert'),'22.0')
        a.editor.mark_set('insert','4.0');a._sync_cursor_line(a.editor,force=True)
        self.root.update_idletasks()
        self.assertEqual((a.editor_gutter._cursor_row,a.result_gutter._cursor_row),('4','4'))
    def test_result_click_updates_both_gutters_before_idle(self):
        a=self.a
        a._close_dropdown=Mock();a._scroll_cursor_restore=Mock()
        self.root.attributes('-alpha',0);self.root.geometry('640x500+0+0');self.root.deiconify()
        for w in (a.editor,a.result_view):
            w.configure(width=1,height=1);w.pack(side='left',fill='both',expand=True)
            w.yview_moveto(0)
        self.root.update()
        info=a.result_view.dlineinfo('3.0');self.assertIsNotNone(info)
        a._on_result_press(SimpleNamespace(num=1,x=10,y=info[1]+5))
        self.assertEqual(a._active_cursor_row,3)
        self.assertEqual((a.editor_gutter._cursor_row,a.result_gutter._cursor_row),('3','3'))

    def test_large_three_digit_number_fits_without_changing_text_font(self):
        a=self.a;g=a.editor_gutter
        font=g._number_font(100,48)
        item=g.create_text(38,20,anchor='e',text='100',font=font)
        self.assertGreaterEqual(g.bbox(item)[0],0)
        self.assertEqual(tkfont.Font(font=a.editor.cget('font')).actual('size'),28)
        self.assertLess(font.actual('size'),28)


class SavedStateTests(unittest.TestCase):
    setUp=tests_gui_file_format.FileFormatApplicationTests.setUp
    tearDown=tests_gui_file_format.FileFormatApplicationTests.tearDown
    def test_closing_inactive_tab_releases_only_its_analysis(self):
        import analysis_work_app as work
        a=self.a
        a.session.tabs=[new_tab(text='本文',saved=True),new_tab(text='別の文書',saved=True)]
        a.session.active=0;a.editor.delete('1.0','end');a.editor.insert('1.0','本文')
        live=work.owner_for_tab(a,a.session.tabs[0])
        closed=work.owner_for_tab(a,a.session.tabs[1])
        for name in ('_completed_tabs','_fg_parked','_bg_parked','_input_documents'):
            setattr(a,name,{live:object(),closed:object()})
        a._load_active_tab=Mock();a._refresh_tab_bar=Mock()
        a._close_tab(1)
        self.assertEqual(a.session.active,0)
        self.assertEqual(len(a.session.tabs),1)
        for name in ('_completed_tabs','_fg_parked','_bg_parked','_input_documents'):
            self.assertEqual(set(getattr(a,name)),{live})
        a._load_active_tab.assert_not_called()
        a._refresh_tab_bar.assert_called_once()

    def test_key_release_after_save_does_not_mark_dirty_or_prompt_on_close(self):
        a=self.a
        for method in ('save_file','save_file_as'):
            a.session.tabs=[new_tab(text='本文',saved=False)]
            a.session.active=0;a.editor.delete('1.0','end');a.editor.insert('1.0','本文\n\n')
            a._dirty=True;a.current_file=str(self.directory/(method+'.txt'))
            a._ask_save_path=lambda:a.current_file
            getattr(a,method)()
            for name in ('_sz_check_shrink','_design33_watch','_schedule_whitespace_paint',
                         '_auto_detect_input_method','_maybe_start_pick_from_equals'):
                setattr(a,name,Mock())
            a._after_id=None;a._gutter_after_id=None
            for key in ('s','Control_L','Right'):
                a._on_change(SimpleNamespace(keysym=key))
                self.assertFalse(a._dirty,(method,key))
            a.ask_yes_no=Mock(return_value=False);a._load_active_tab=Mock()
            a._refresh_tab_bar=Mock();a._close_tab()
            a.ask_yes_no.assert_not_called()
            # Real edits still set dirty and keep the close warning.
            a.editor.insert('1.0','追記');a._on_change()
            self.assertTrue(a._dirty)
            a._close_tab();a.ask_yes_no.assert_called_once()

if __name__=='__main__':unittest.main()
