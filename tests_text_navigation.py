# -*- coding: utf-8 -*-
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from text_navigation import block_edge
import app

class BlockNavigationTests(unittest.TestCase):
    def test_horizontal_edges_keep_punctuation_and_space_run_sides(self):
        from text_navigation import text_edge
        text = '最初、続き。次！本当？(括弧)「引用」 終わり\t\t　次'
        pieces = ['最初、', '続き。', '次！', '本当？', '(括弧', ')', '「引用', '」',
                  ' ', '終わり', '\t\t　', '次']
        expected = [0]
        for part in pieces:expected.append(expected[-1]+len(part))
        self.assertEqual(''.join(pieces),text)
        actual = [0]
        while actual[-1] < len(text):actual.append(text_edge(text,actual[-1],1))
        self.assertEqual(actual,expected)
        backward = [len(text)]
        while backward[-1]:backward.append(text_edge(text,backward[-1],-1))
        self.assertEqual(backward,list(reversed(expected)))
        for i in range(len(text)+1):
            self.assertEqual(text_edge(text,i,1),next((n for n in expected if n>i),len(text)))
            self.assertEqual(text_edge(text,i,-1),next((n for n in reversed(expected) if n<i),0))
        for text in ('', '連続した日本語ABC123', '😀絵文字', ' \t　'):
            self.assertEqual(text_edge(text,0,1),len(text))
            self.assertEqual(text_edge(text,len(text),-1),0)
        self.assertEqual(text_edge('a,b.c!d?e',0,1),2)

    def test_edges_blanks_and_document_ends_in_both_directions(self):
        lines=['','甲','乙','丙','','　','丁','戊','','']
        down=[1,3,3,6,6,6,7,9,9,9]
        up=[0,0,1,1,3,3,3,6,7,7]
        self.assertEqual([block_edge(lines,i,1) for i in range(10)],down)
        self.assertEqual([block_edge(lines,i,-1) for i in range(10)],up)
        self.assertEqual(block_edge([],0,1),0)
        self.assertEqual(block_edge([''],0,-1),0)
    def test_directional_symmetry_for_all_short_empty_filled_patterns(self):
        from itertools import product
        for length in range(1,8):
            for pattern in product(('', '文'),repeat=length):
                for row in range(length):
                    forward=block_edge(pattern,row,1)
                    backward=length-1-block_edge(list(reversed(pattern)),length-1-row,-1)
                    self.assertEqual(forward,backward,(pattern,row))
                    self.assertTrue(row<=forward<length)

class NavigationTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp);self.a.root=self.root
        self.a.editor=tk.Text(self.root);self.a.result_view=tk.Text(self.root)
        self.a.editor_gutter=Mock();self.a.result_gutter=Mock();self.a.status=Mock()
        self.a._close_dropdown=Mock();self.a._ime_first=lambda fn:fn
        self.a.bookmarks={2,5,8}
        for widget in (self.a.editor,self.a.result_view):
            widget.insert('1.0','始まり😀\n継続😀\n末尾😀\n\n次の塊\n短\n\n末尾\n')
    def tearDown(self):
        self.root.update_idletasks();self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')
    def test_native_text_cursor_selection_and_readonly_pane(self):
        for widget in (self.a.editor,self.a.result_view):
            if widget is self.a.result_view:widget.configure(state='disabled')
            widget.mark_set('insert','1.2')
            event=SimpleNamespace(widget=widget,state=4)
            self.assertEqual(self.a._move_block_edge(event,1),'break')
            self.assertEqual(widget.index('insert'),'3.2')
            self.a._move_block_edge(event,1);self.assertEqual(widget.index('insert'),'5.2')
            self.a._move_block_edge(event,1);self.assertEqual(widget.index('insert'),'6.1')
            self.a._move_block_edge(event,-1);self.assertEqual(widget.index('insert'),'5.1')
            widget.mark_set('insert','1.1')
            event.state=5;self.a._move_block_edge(event,1)
            self.assertEqual(widget.index('sel.first'),'1.1')
            self.assertEqual(widget.index('sel.last'),'3.1')
            self.a._move_block_edge(event,1);self.assertEqual(widget.index('sel.last'),'5.1')
            self.a._move_block_edge(event,-1);self.assertEqual(widget.index('sel.last'),'3.1')
    def test_installed_horizontal_keys_unicode_selection_and_readonly(self):
        from tests_tk_keys import deliver_key
        for w in (self.a.editor,self.a.result_view):
            w.delete('1.0','end')
            w.insert('1.0','甲😀、乙　　丙\t丁。\n\n次の行')
            self.a._bind_block_navigation(w)
            w.mark_set('insert','1.0')
            if w is self.a.result_view:w.configure(state='disabled')
            before=w.get('1.0','end-1c')
            for prefix in ('甲😀、','甲😀、乙','甲😀、乙　　','甲😀、乙　　丙',
                           '甲😀、乙　　丙\t','甲😀、乙　　丙\t丁。',
                           '甲😀、乙　　丙\t丁。\n','甲😀、乙　　丙\t丁。\n\n',before):
                deliver_key(w,'<Control-Right>','Right',39,state=4)
                self.assertEqual(w.get('1.0','insert'),prefix)
            deliver_key(w,'<Control-Right>','Right',39,state=4)
            self.assertEqual(w.get('1.0','insert'),before)
            deliver_key(w,'<Control-Left>','Left',37,state=4)
            self.assertEqual(w.index('insert'),'3.0')
            deliver_key(w,'<Control-Left>','Left',37,state=4)
            self.assertEqual(w.index('insert'),'2.0')
            deliver_key(w,'<Control-Left>','Left',37,state=4)
            self.assertEqual(w.index('insert'),w.index('1.end'))
            w.mark_set('insert','1.0')
            deliver_key(w,'<Control-Shift-Right>','Right',39,state=5)
            self.assertEqual(w.get('sel.first','sel.last'),'甲😀、')
            deliver_key(w,'<Control-Shift-Right>','Right',39,state=5)
            self.assertEqual(w.get('sel.first','sel.last'),'甲😀、乙')
            deliver_key(w,'<Control-Shift-Left>','Left',37,state=5)
            self.assertEqual(w.get('sel.first','sel.last'),'甲😀、')
            deliver_key(w,'<Control-Left>','Left',37,state=4)
            self.assertFalse(w.tag_ranges('sel'))
            self.assertEqual(w.index('insert'),'1.0')
            self.assertEqual(w.get('1.0','end-1c'),before)

    def test_bookmarks_use_the_focused_pane_and_wrap(self):
        self.a.editor.mark_set('insert','1.0');w=self.a.result_view;w.mark_set('insert','5.0')
        event=SimpleNamespace(widget=w)
        self.assertEqual(self.a._on_bookmark_navigation(event,True),'break')
        self.assertEqual(w.index('insert'),'8.0');self.assertEqual(self.a.editor.index('insert'),'8.0')
        self.a._on_bookmark_navigation(event,True);self.assertEqual(w.index('insert'),'2.0')
        self.a._on_bookmark_navigation(event,False);self.assertEqual(w.index('insert'),'8.0')
    def test_key_bindings_are_registered_on_each_text_widget(self):
        for widget in (self.a.editor,self.a.result_view):
            self.a._bind_block_navigation(widget)
            for sequence in ('<Control-Up>','<Control-Down>','<Control-Shift-Up>','<Control-Shift-Down>'):
                self.assertTrue(widget.bind(sequence),sequence)

if __name__=='__main__':unittest.main()