# -*- coding: utf-8 -*-
"""Each file tab keeps its own Undo/Redo: the one Text gives a tab's steps back when the tab returns."""
import tkinter as tk
import unittest
from types import SimpleNamespace

import tab_undo
import undo_feedback


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.text = tk.Text(self.root, undo=True, autoseparators=True)
        self.feedback = undo_feedback.install(self.text, lambda: '', lambda: '#b65000')
        self.tabs = [dict(name='a'), dict(name='b'), dict(name='c')]
        self.app = SimpleNamespace(editor=self.text, session=SimpleNamespace(tabs=self.tabs), root=self.root, _closing=False)
        self.keeper = tab_undo.TabUndo(self.app, self.feedback)
        self.body = {'a': '一行目\n二行目\n三行目\n', 'b': 'ほかのタブ\n', 'c': '三つ目\n'}
        self.current = None
        self.show(self.tabs[0])

    def tearDown(self):
        self.root.destroy()

    def get(self):
        return self.text.get('1.0', 'end-1c')

    def show(self, tab):
        # the order of _load_active_tab_core
        self.keeper.leave()
        if self.current is not None:
            self.body[self.current['name']] = self.get()
        self.text.configure(undo=False)
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', self.body[tab['name']])
        self.text.configure(undo=True)
        self.text.edit_reset()
        self.keeper.enter(tab)
        self.current = tab

    def undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass


class Keeps(Base):
    def test_cut_comes_back_after_other_tabs(self):
        self.text.delete('2.0', '3.0')
        cut = self.get()
        self.show(self.tabs[1])
        self.show(self.tabs[2])
        self.show(self.tabs[1])
        self.show(self.tabs[0])
        self.assertEqual(self.get(), cut)
        self.undo()
        self.assertEqual(self.get(), '一行目\n二行目\n三行目\n')

    def test_redo_after_coming_back(self):
        self.text.delete('2.0', '3.0')
        cut = self.get()
        self.show(self.tabs[1])
        self.show(self.tabs[0])
        self.undo()
        self.text.edit_redo()
        self.assertEqual(self.get(), cut)
        self.undo()
        self.assertEqual(self.get(), '一行目\n二行目\n三行目\n')

    def test_redo_kept_over_a_switch(self):
        self.text.delete('2.0', '3.0')
        cut = self.get()
        self.undo()
        self.show(self.tabs[1])
        self.show(self.tabs[0])
        self.text.edit_redo()
        self.assertEqual(self.get(), cut)
        self.undo()
        self.assertEqual(self.get(), '一行目\n二行目\n三行目\n')

    def test_steps_in_order_with_new_ones_on_top(self):
        self.text.edit_separator()
        self.text.insert('1.0', 'A')
        self.text.edit_separator()
        self.text.insert('2.0', 'B')
        self.text.edit_separator()
        self.show(self.tabs[1])
        self.show(self.tabs[0])
        self.text.insert('3.0', 'C')
        self.text.edit_separator()
        self.undo()
        self.assertEqual(self.get(), 'A一行目\nB二行目\n三行目\n')
        self.undo()
        self.assertEqual(self.get(), 'A一行目\n二行目\n三行目\n')
        self.undo()
        self.assertEqual(self.get(), '一行目\n二行目\n三行目\n')

    def test_each_tab_only_its_own(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.text.insert('1.0', 'x')
        self.text.edit_separator()
        self.undo()
        self.assertEqual(self.get(), 'ほかのタブ\n')
        self.show(self.tabs[0])
        self.assertEqual(self.get(), '一行目\n三行目\n')
        self.show(self.tabs[1])
        self.assertEqual(self.get(), 'ほかのタブ\n')

    def test_emoji_before_the_step(self):
        self.body['c'] = '絵😀文字\n次😀の行\n'
        self.show(self.tabs[2])
        before = self.get()
        self.text.delete('2.0', '2.end')
        self.show(self.tabs[1])
        self.show(self.tabs[2])
        self.undo()
        self.assertEqual(self.get(), before)

    def test_text_changed_while_away_drops_the_steps(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.current = None
        self.body['a'] = '読み直した本文\n'
        self.show(self.tabs[0])
        self.undo()
        self.assertEqual(self.get(), '読み直した本文\n')

    def test_step_that_does_not_fit_changes_nothing(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.show(self.tabs[0])
        self.feedback.parked[-1][2][0] = (0, '合わない', '合わない字')
        now = self.get()
        self.undo()
        self.assertEqual(self.get(), now)

    def test_closed_tab_is_forgotten(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.assertEqual(len(self.keeper.kept), 1)
        del self.tabs[0]
        self.show(self.tabs[1])
        self.assertEqual(self.keeper.kept, [])

    def test_reset_of_this_tab_forgets_its_steps(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.show(self.tabs[0])
        self.text.edit_reset()      # a file opened into the tab
        now = self.get()
        self.undo()
        self.assertEqual(self.get(), now)


class Underline(Base):
    def marked(self):
        self.root.update_idletasks()
        self.root.update()
        ranges = self.text.tag_ranges('undo_feedback')
        return [self.text.get(a, b) for a, b in zip(ranges[::2], ranges[1::2])]

    def test_what_a_cut_gave_back_is_marked(self):
        self.text.delete('2.0', '3.0')
        self.undo()
        self.assertEqual(self.marked(), ['二行目\n'])

    def test_after_coming_back_too(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.show(self.tabs[0])
        self.undo()
        self.assertEqual(self.marked(), ['二行目\n'])

    def test_a_word_replaced_marks_the_old_word(self):
        self.text.edit_separator()
        self.text.replace('1.0', '1.2', '別')
        self.text.edit_separator()
        self.undo()
        self.assertEqual(self.marked(), ['一行'])

    def test_typing_undone_marks_the_step_before(self):
        self.text.edit_separator()
        self.text.insert('1.0', '甲')
        self.text.edit_separator()
        self.text.insert('2.0', '乙')
        self.text.edit_separator()
        self.undo()
        self.assertEqual(self.marked(), ['甲'])

    def test_the_key_goes_the_same_way(self):
        self.root.deiconify()
        self.text.pack()
        self.text.delete('2.0', '3.0')
        self.text.focus_force()
        self.root.update()
        self.text.event_generate('<Control-Key-z>')
        self.assertEqual(self.get(), '一行目\n二行目\n三行目\n')
        self.assertEqual(self.marked(), ['二行目\n'])


class Limits(Base):
    def test_newest_kept_within_the_limit(self):
        for i in range(5):
            self.text.edit_separator()
            self.text.insert('1.0', 'あ' * 400000)
        self.text.edit_separator()
        snapshot = self.feedback.take()
        self.assertLessEqual(sum(map(tab_undo._chars, snapshot['undo'])), undo_feedback.LOG_CHARS)
        self.assertGreaterEqual(len(snapshot['undo']), 2)

    def test_one_step_over_the_limit_is_kept(self):
        entries = [(1, [], [(0, '', 'あ' * 10)])]
        tab_undo._trim(entries, 5)
        self.assertEqual(len(entries), 1)

    def test_all_tabs_limit_takes_the_oldest(self):
        small = lambda seq, n: (seq, [], [(0, '', 'あ' * n)])
        self.keeper.kept = [dict(tab=self.tabs[0], text=0, undo=[small(1, tab_undo.ALL_CHARS), small(4, 10)], redo=[]),
                            dict(tab=self.tabs[1], text=0, undo=[small(2, 10), small(3, 10)], redo=[])]
        self.keeper._trim_all()
        self.assertEqual([e[0] for e in self.keeper.kept[0]['undo']], [4])
        self.assertEqual([e[0] for e in self.keeper.kept[1]['undo']], [2, 3])


class Elsewhere(Base):
    def setUp(self):
        super().setUp()
        self.switched = []
        self.changed = []
        self.app._switch_tab = lambda i: (self.switched.append(i), self.show(self.tabs[i]))
        self.app._on_change = lambda: self.changed.append(1)

    def settle(self):
        self.root.update_idletasks()
        self.root.update()

    def test_nothing_here_goes_to_the_last_edit(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.show(self.tabs[2])
        self.undo()
        self.settle()
        self.assertEqual(self.switched, [0])
        self.assertIs(self.current, self.tabs[0])
        self.assertEqual(self.get(), '一行目\n二行目\n三行目\n')
        self.assertEqual(self.text.index('insert').split('.')[0], '3')     # Tk: the end of what came back
        self.assertTrue(self.changed)

    def test_own_step_first(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.text.insert('1.0', 'x')
        self.text.edit_separator()
        self.undo()
        self.settle()
        self.assertEqual(self.switched, [])
        self.assertEqual(self.get(), 'ほかのタブ\n')

    def test_the_newest_of_several_tabs(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.text.insert('1.0', 'x')
        self.text.edit_separator()
        self.show(self.tabs[2])
        self.undo()
        self.settle()
        self.assertEqual(self.switched, [1])
        self.assertEqual(self.get(), 'ほかのタブ\n')

    def test_no_history_anywhere_stays(self):
        self.show(self.tabs[1])
        self.undo()
        self.settle()
        self.assertEqual(self.switched, [])
        self.assertIs(self.current, self.tabs[1])

    def test_other_tab_text_untouched_until_there(self):
        self.text.delete('2.0', '3.0')
        cut = self.get()
        self.show(self.tabs[1])
        self.assertEqual(self.body['a'], cut)

    def redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass

    def test_newest_edit_first_though_this_tab_has_its_own(self):
        # B has an older edit, A the newest: the cut comes back first, in A
        self.show(self.tabs[1])
        self.text.insert('1.0', 'B古')
        self.text.edit_separator()
        b_old = self.get()
        self.show(self.tabs[0])
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.assertEqual(self.get(), b_old)
        self.undo()
        self.settle()
        self.assertIs(self.current, self.tabs[0])
        self.assertEqual(self.get(), '一行目\n二行目\n三行目\n')
        self.assertEqual(self.body['b'], b_old)
        self.undo()
        self.settle()
        self.assertIs(self.current, self.tabs[1])
        self.assertEqual(self.get(), 'ほかのタブ\n')

    def test_redo_goes_the_same_way_back(self):
        self.show(self.tabs[1])
        self.text.insert('1.0', 'B古')
        self.text.edit_separator()
        b_old = self.get()
        self.show(self.tabs[0])
        self.text.delete('2.0', '3.0')
        cut = self.get()
        self.show(self.tabs[2])
        self.undo()
        self.settle()
        self.undo()
        self.settle()
        self.assertIs(self.current, self.tabs[1])
        self.assertEqual(self.get(), 'ほかのタブ\n')
        self.redo()
        self.settle()
        self.assertIs(self.current, self.tabs[1])
        self.assertEqual(self.get(), b_old)
        self.redo()
        self.settle()
        self.assertIs(self.current, self.tabs[0])
        self.assertEqual(self.get(), cut)

    def test_newer_own_step_stays_here(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.text.insert('1.0', 'B新')
        self.text.edit_separator()
        self.undo()
        self.settle()
        self.assertEqual(self.switched, [])
        self.assertEqual(self.get(), 'ほかのタブ\n')

    def test_the_key_and_the_virtual_event_take_the_same_way(self):
        self.root.deiconify()
        self.text.pack()
        for event in ('<Control-Key-z>', '<<Undo>>'):
            self.switched.clear()
            self.show(self.tabs[1])
            self.text.insert('1.0', 'B古')
            self.text.edit_separator()
            self.show(self.tabs[0])
            self.text.delete('1.0', '2.0')
            before_b = self.body['b']
            self.show(self.tabs[1])
            self.text.focus_force()
            self.root.update()
            self.text.event_generate(event)
            self.settle()
            self.assertEqual(self.switched, [0], event)
            self.assertEqual(self.body['b'], before_b, event)
            self.assertTrue(self.get().startswith('一行目'), event)
            self.text.focus_force()
            self.root.update()
            self.text.event_generate(event)     # the older edit, in B
            self.settle()
            self.assertIs(self.current, self.tabs[1], event)
            self.assertEqual(self.get(), 'ほかのタブ\n', event)

    def test_two_quick_presses(self):
        self.show(self.tabs[1])
        self.text.insert('1.0', 'B古')
        self.text.edit_separator()
        self.show(self.tabs[0])
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[2])
        self.undo()
        self.undo()
        self.settle()
        self.assertEqual(self.body['a'] if self.current is not self.tabs[0] else self.get(), '一行目\n二行目\n三行目\n')
        self.assertEqual(self.get() if self.current is self.tabs[1] else self.body['b'], 'ほかのタブ\n')


class StyleSteps:
    """A step that is not text, as the bold, the ruler and a re-choice keep theirs."""
    def __init__(self, text):
        self.widget = text
        self.history, self.redo = [], []
        self.applied = []
        text._correctnote_observers.setdefault('undo_hooks', []).append(self.undo_step)

    def make(self, name, place=None):
        from analysis_work import next_step_seq
        self.history.append((self.widget.get('1.0', 'end-1c'), name, next_step_seq(self.widget), place))
        self.applied.append(name)

    def due_step_seq(self, kind):
        from analysis_work import same_step_text
        stack = self.history if kind == 'undo' else self.redo
        if not stack or not same_step_text(stack[-1][0], self.widget.get('1.0', 'end-1c')):
            return None
        return stack[-1][2]

    def step_top(self, kind):
        stack = self.history if kind == 'undo' else self.redo
        return (stack[-1][2], stack[-1][0], None) if stack else None

    def step_drop(self, kind):
        (self.history if kind == 'undo' else self.redo).pop()

    def undo_step(self, kind):
        if self.due_step_seq(kind) is None:
            return False
        stack, other = (self.history, self.redo) if kind == 'undo' else (self.redo, self.history)
        entry = stack.pop()
        other.append(entry)
        self.applied.remove(entry[1]) if kind == 'undo' else self.applied.append(entry[1])
        self.last_place = entry[3]
        return True


class OneHistory(Elsewhere):
    def setUp(self):
        super().setUp()
        self.steps = StyleSteps(self.text)
        # the text of a tab shown or left, as _capture_session keeps it
        for tab in self.tabs:
            tab['text'] = self.body[tab['name']]
        real = self.show

        def show(tab):
            if self.current is not None:
                self.current['text'] = self.get()
            real(tab)
        self.show = show

    def long_text(self):
        self.root.deiconify()
        self.text.configure(height=10)
        self.text.pack()
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', chr(10).join('行%d' % i for i in range(1, 201)))
        self.text.edit_reset()
        self.text.mark_set('insert', '1.0')
        self.text.yview('1.0')
        self.root.update()

    def test_same_tab_a_place_out_of_view_shows(self):
        self.long_text()
        self.steps.make('太字', '120.0')
        self.text.mark_set('insert', '3.0')
        self.text.yview('1.0')
        self.root.update()
        self.assertIsNone(self.text.bbox('120.0'))
        self.undo()
        self.root.update()
        self.assertEqual(self.steps.applied, [])
        self.assertEqual(self.text.index('insert'), '120.0')
        self.assertIsNotNone(self.text.bbox('120.0'))
        self.assertEqual(self.switched, [])

    def test_same_tab_redo_shows_too(self):
        self.long_text()
        self.steps.make('太字', '120.0')
        self.undo()
        self.root.update()
        self.text.mark_set('insert', '3.0')
        self.text.yview('1.0')
        self.root.update()
        self.redo()
        self.root.update()
        self.assertEqual(self.steps.applied, ['太字'])
        self.assertIsNotNone(self.text.bbox('120.0'))

    def test_same_tab_a_place_in_view_leaves_the_cursor(self):
        self.long_text()
        self.steps.make('太字', '5.0')
        self.text.mark_set('insert', '3.0')
        self.text.yview('1.0')
        self.root.update()
        self.undo()
        self.root.update()
        self.assertEqual(self.steps.applied, [])
        self.assertEqual(self.text.index('insert'), '3.0')
        self.assertEqual(self.text.index('@0,0').split('.')[0], '1')

    def test_cut_then_style_in_another_tab(self):
        cut_before = self.get()
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.steps.make('太字B')
        self.show(self.tabs[0])
        self.undo()
        self.settle()
        self.assertIs(self.current, self.tabs[1])
        self.assertEqual(self.steps.applied, [])
        self.assertEqual(self.body['a'], '一行目\n三行目\n')
        self.undo()
        self.settle()
        self.assertIs(self.current, self.tabs[0])
        self.assertEqual(self.get(), cut_before)

    def test_style_then_cut_in_another_tab(self):
        self.show(self.tabs[1])
        self.steps.make('太字B')
        self.show(self.tabs[0])
        before = self.get()
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.undo()
        self.settle()
        self.assertIs(self.current, self.tabs[0])
        self.assertEqual(self.get(), before)
        self.assertEqual(self.steps.applied, ['太字B'])
        self.undo()
        self.settle()
        self.assertIs(self.current, self.tabs[1])
        self.assertEqual(self.steps.applied, [])

    def test_redo_the_same_way_back(self):
        before = self.get()
        self.text.delete('2.0', '3.0')
        cut = self.get()
        self.show(self.tabs[1])
        self.steps.make('太字B')
        self.show(self.tabs[2])
        self.undo()
        self.settle()
        self.undo()
        self.settle()
        self.assertEqual(self.get(), before)
        self.redo()
        self.settle()
        self.assertIs(self.current, self.tabs[0])
        self.assertEqual(self.get(), cut)
        self.redo()
        self.settle()
        self.assertIs(self.current, self.tabs[1])
        self.assertEqual(self.steps.applied, ['太字B'])

    def test_a_step_whose_text_is_gone_does_not_block(self):
        self.show(self.tabs[1])
        self.steps.make('太字B')
        self.tabs[1]['text'] = '読み直した本文\n'
        self.body['b'] = '読み直した本文\n'
        self.current = None
        self.show(self.tabs[2])
        self.undo()
        self.settle()
        self.assertEqual(self.steps.history, [])
        self.assertEqual(self.switched, [])

    def test_a_button_of_this_tab_stays_in_this_tab(self):
        self.text.delete('2.0', '3.0')
        self.show(self.tabs[1])
        self.text.insert('1.0', '手')
        self.text.edit_separator()
        self.show(self.tabs[0])
        self.text.insert('1.0', '新')
        self.text.edit_separator()
        self.undo()
        self.settle()
        self.show(self.tabs[2])
        self.text._correctnote_undo_here = True
        self.undo()
        self.text._correctnote_undo_here = False
        self.settle()
        self.assertEqual(self.switched, [])


if __name__ == '__main__':
    unittest.main()
