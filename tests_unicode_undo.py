# -*- coding: utf-8 -*-
"""Native history replay preserves supplementary characters and their neighbors."""
import tkinter as tk
import unittest
from analysis_work import observe_text
from text_edit import undo_group

class UnicodeUndoTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.editor=tk.Text(self.root,undo=True);self.edits=[]
        observe_text(self.editor,lambda *args:self.edits.append(args))
    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'editor','root','edits')
    def text(self):return self.editor.get('1.0','end-1c')
    def reset(self,text):
        self.editor.delete('1.0','end');self.editor.insert('1.0',text);self.editor.edit_reset()
    def test_insert_undo_redo_preserves_following_characters(self):
        for glyph in ('😀','𠮷','👨‍👩‍👧‍👦','が','a'):
            with self.subTest(glyph=glyph):
                self.reset('先頭😀続き')
                self.editor.insert('1.2','追加'+glyph)
                changed=self.text();self.editor.edit_undo()
                self.assertEqual(self.text(),'先頭😀続き')
                self.editor.edit_redo();self.assertEqual(self.text(),changed)
    def test_replacement_and_deletion_after_supplementary_prefix(self):
        w=self.editor
        for operation in ('replace','delete'):
            with self.subTest(operation=operation):
                before='😀先頭𠮷続き\n次の行😀';self.reset(before)
                with undo_group(w):
                    if operation=='replace':w.replace('1.2','1.4','別😀')
                    else:w.delete('1.2','1.4')
                changed=self.text();w.edit_undo();self.assertEqual(self.text(),before)
                w.edit_redo();self.assertEqual(self.text(),changed)
    def test_multiline_history_keeps_typing_paste_and_replace_separate(self):
        w=self.editor;before='先頭の文😀\n次の文\n';self.reset(before)
        w.mark_set('insert','2.end');w.insert('insert','追加した文');typed=self.text()
        self.root.tk.call('rename','::tk::GetSelection','::tk::GetSelectionSaved')
        self.root.tk.call('proc','::tk::GetSelection','args','return $::test_unicode_paste')
        self.root.tk.setvar('::test_unicode_paste','置いた文😀\n貼り付け')
        w.tag_add('sel','1.0','1.2');w.mark_set('insert','1.0');w.event_generate('<<Paste>>')
        pasted=self.text();replaced=pasted.replace('次の文','置換後')
        with undo_group(w):w.replace('1.0','end-1c',replaced)
        for expected in (pasted,typed,before):
            w.event_generate('<<Undo>>');self.assertEqual(self.text(),expected)
            self.assertEqual(self.edits[-1][0],expected)
        for expected in (typed,pasted,replaced):
            w.event_generate('<<Redo>>');self.assertEqual(self.text(),expected)
            self.assertEqual(self.edits[-1][0],expected)
    def test_callback_free_quick_entry_shares_history_handling(self):
        extra=tk.Text(self.root,undo=True)
        try:
            observe_text(extra);extra.insert('1.0','元の文');extra.edit_reset()
            extra.insert('1.1','😀');extra.edit_undo()
            self.assertEqual(extra.get('1.0','end-1c'),'元の文')
            extra.edit_redo();self.assertEqual(extra.get('1.0','end-1c'),'元😀の文')
        finally:extra.destroy()
    def test_errors_and_empty_history_keep_native_behavior(self):
        self.reset('元の文')
        with self.assertRaises(tk.TclError):self.editor.edit_undo()
        with self.assertRaises(tk.TclError):self.editor.cget('not-an-option')
        self.editor.insert('1.1','😀');self.editor.edit_undo()
        self.assertEqual(self.text(),'元の文')
        self.editor.configure(state='disabled');self.editor.insert('1.0','追加')
        self.assertEqual(self.text(),'元の文')
    def test_unaffected_runtime_path_keeps_native_ascii_undo(self):
        self.root._correctnote_legacy_unicode_undo=False
        extra=tk.Text(self.root,undo=True)
        try:
            observe_text(extra);extra.insert('1.0','abcd');extra.edit_reset()
            extra.insert('1.2','X');extra.edit_undo()
            self.assertEqual(extra.get('1.0','end-1c'),'abcd')
        finally:extra.destroy()

if __name__=='__main__':unittest.main()
