"""Actual native histories on owned synthetic Tk widgets, not trial replay in use."""
import tkinter as tk
import unittest
from analysis_work import observe_text
from text_edit import undo_group
from undo_feedback import install,inserted_ranges


class UndoFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw();self.root.update_idletasks()
        self.widget=tk.Text(self.root,undo=True)
        self.widget.insert('1.0','base');self.widget.edit_reset()
        self.edits=[]
        observe_text(self.widget,on_edit=lambda *args:self.edits.append(args))
        self.feedback=install(self.widget,lambda:'#d6edf5')

    def tearDown(self):self.root.update_idletasks();self.root.destroy()

    def marked(self):
        self.root.update_idletasks()
        w=self.widget;text=w.get('1.0','end-1c')
        return ''.join(char for i,char in enumerate(text)
                       if self.feedback.TAG in w.tag_names(f'1.0+{i}c'))

    def group(self,text):
        with undo_group(self.widget):self.widget.insert('end-1c',text)

    def test_undo_marks_next_removal_and_redo_marks_restored_text(self):
        w=self.widget;self.group('ABC');self.group('XYZ')
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'baseABC')
        self.assertEqual(self.marked(),'ABC')
        undo_style=tuple(w.tag_cget(self.feedback.TAG,key) for key in ('background','underline','underlinefg'))
        self.assertEqual(undo_style,('','1','#b65000'))
        w.edit_redo();self.assertEqual(self.marked(),'XYZ')
        self.assertEqual(tuple(w.tag_cget(self.feedback.TAG,key) for key in ('background','underline','underlinefg')),undo_style)
        w.edit_undo();self.assertEqual(self.marked(),'ABC')
        w.edit_undo();self.assertEqual(self.marked(),'')
        self.assertEqual(w.get('1.0','end-1c'),'base')

    def test_contiguous_native_typing_keeps_native_grouping(self):
        w=self.widget;w.insert('end-1c','AB');w.insert('end-1c','CD')
        w.edit_separator();w.insert('end-1c','Z')
        w.edit_undo();self.assertEqual(self.marked(),'ABCD')
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'base')

    def test_deletion_group_does_not_color_unrelated_surviving_letters(self):
        w=self.widget;self.group('ABC');w.delete('1.5');w.edit_separator();w.insert('end-1c','Z')
        w.edit_undo();self.assertEqual(self.marked(),'')
        w.edit_undo();self.assertEqual(self.marked(),'ABC')
        w.edit_redo();self.assertEqual(self.marked(),'')

    def test_replace_and_mixed_group_keep_multiple_exact_surviving_ranges(self):
        w=self.widget
        with undo_group(w):
            w.insert('1.1','XY');w.delete('1.2');w.insert('end-1c','PQ')
        self.group('Z');w.edit_undo()
        self.assertEqual(self.marked(),'XPQ')
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'base')
        w.edit_redo();self.assertEqual(self.marked(),'XPQ')
        w.edit_separator();w.replace('1.1','1.3','UV')
        w.edit_separator();w.insert('end-1c','Z');w.edit_undo()
        self.assertEqual(self.marked(),'UV')

    def test_emoji_multiline_and_combining_marks_use_real_replay_positions(self):
        w=self.widget;self.group('😀\nか\u3099');self.group('終')
        w.edit_undo();self.assertEqual(self.marked(),'😀\nか\u3099')
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'base')
        w.edit_redo();self.assertEqual(self.marked(),'😀\nか\u3099')

    def test_new_edit_reset_disabled_widget_and_stale_paint_do_not_leak(self):
        w=self.widget;self.group('ABC');self.group('XYZ');w.edit_undo()
        self.assertIsNotNone(self.feedback.job)
        w.insert('end-1c','Q');self.assertEqual(self.marked(),'')
        self.assertFalse(w.edit('canredo'))
        w.edit_reset();self.assertFalse(self.feedback.undo)
        self.group('ABC');self.group('XYZ');w.edit_undo()
        self.assertEqual(self.marked(),'ABC')
        w.configure(state='disabled');w.insert('end','ignored')
        self.assertEqual(self.marked(),'ABC')
        w.configure(state='normal');w.edit_reset()
        self.assertEqual(self.marked(),'')

    def test_unknown_multiple_delete_fails_closed_but_native_undo_is_preserved(self):
        w=self.widget;self.group('ABC')
        w.tk.call(w._w,'delete','1.0','1.1','1.3','1.4')
        self.assertFalse(self.feedback.undo)
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'baseABC')
        self.assertEqual(self.marked(),'')
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'base')
        self.assertEqual(self.marked(),'')

    def test_native_errors_and_empty_history_still_raise(self):
        w=self.widget
        with self.assertRaises(tk.TclError):w.edit_undo()
        with self.assertRaises(tk.TclError):w.insert('not-an-index','ABC')
        self.assertEqual(w.get('1.0','end-1c'),'base')
        self.assertEqual(self.marked(),'')

    def test_metadata_contains_positions_and_lengths_only(self):
        self.group('XYZ');self.group('ABC')
        self.assertTrue(all(isinstance(value,int) for group in self.feedback.undo
                            for operation in group for value in operation))
        self.assertEqual(inserted_ranges([(2,0,4),(3,2,0),(8,0,2)]),[(2,4),(8,10)])

    def test_native_clamped_indices_and_reversed_ranges_keep_real_lengths(self):
        w=self.widget
        with undo_group(w):w.insert('end','XYZ')
        self.group('Q');w.edit_undo();self.assertEqual(self.marked(),'XYZ')
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'base')
        w.edit_separator();w.delete('1.3','1.1')
        self.assertEqual(w.get('1.0','end-1c'),'base')
        w.edit_separator();w.replace('1.2','end','UV')
        self.group('Q');w.edit_undo();self.assertEqual(self.marked(),'UV')
        w.edit_undo();self.assertEqual(w.get('1.0','end-1c'),'base')
        # Bypass the older outer edit observer's own malformed-call handling.
        with self.assertRaises(tk.TclError):
            self.feedback.invoke(('insert',),lambda:self.feedback._call('insert'))


if __name__=='__main__':unittest.main()
