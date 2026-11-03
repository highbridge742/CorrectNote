# -*- coding: utf-8 -*-
"""再入力変換: Ctrl の2回押しで語を読みに開き、スペースで変換し直す（作った例・2026-11-02）。"""
import time
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import reinput
from reinput import ReInput, TAG, START, END

STOPS = {'資料を作る': [0, 2, 3, 5], 'メモ abc を読む': [0, 2, 3, 6, 7, 8, 10]}


def key(name):
    return NS(keysym=name)


class Base(unittest.TestCase):
    TEXT = '資料を作る\n二行目です'

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.text = tk.Text(self.root, undo=True, autoseparators=True)
        self.text.pack()
        self.text.insert('1.0', self.TEXT)
        self.text.edit_reset()
        self.changes = []
        self.composing = False
        app = NS(_composing=lambda w: self.composing, _text_edge_column=self.edge, status=NS(config=lambda **k: None),
                 settings={}, _on_change=lambda: self.changes.append(1))
        self.app = app
        self.r = ReInput(app, self.text)
        patch.object(ReInput, 'reading_of', lambda s, row, col, surface: self.READ.get(surface, surface)).start()
        patch.object(ReInput, 'choices_for', lambda s, reading: self.CHOICES.get(reading, [reading])).start()
        patch.object(ReInput, '_owner', lambda s: 'tab').start()
        patch.object(ReInput, '_char_readings', lambda s, ch: []).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.root.destroy)

    READ = {'資料': 'しりょう', '作る': 'つくる'}
    CHOICES = {'しりょう': ['試料', '資料', 'しりょう']}

    def edge(self, widget, row, text, column, direction):
        stops = STOPS.get(text, [0, len(text)])
        if direction > 0:
            return next((n for n in stops if n > column), len(text))
        return next((n for n in reversed(stops) if n < column), 0)

    def line(self, row=1):
        return self.text.get(f'{row}.0', f'{row}.end')

    def tap(self, name='Control_L'):
        self.r.on_press(key(name)); self.r.on_release(key(name))

    def begin(self, at='1.1'):
        self.text.mark_set('insert', at)
        self.tap(); self.tap()
        self.assertIsNotNone(self.r.state)


class DoubleTap(Base):
    def test_two_taps_open_the_word(self):
        self.begin()
        self.assertEqual(self.line(), 'しりょうを作る')
        self.assertEqual(self.text.get(START, END), 'しりょう')
        self.assertEqual(self.text.index('insert'), self.text.index(END))
        self.assertTrue(self.text.tag_ranges(TAG))

    def test_one_tap_does_nothing(self):
        self.text.mark_set('insert', '1.1')
        self.tap()
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), '資料を作る')

    def test_too_slow(self):
        self.text.mark_set('insert', '1.1')
        self.tap()
        self.r._released_at -= 1000
        self.tap()
        self.assertIsNone(self.r.state)

    def test_a_key_or_the_mouse_between_does_not_count(self):
        for between in (lambda: self.r.on_press(key('c')), self.r.on_pointer):
            self.tap(); between(); self.tap()
            self.assertIsNone(self.r.state)
            self.r._forget_taps()

    def test_ctrl_c_is_not_a_tap(self):
        for _ in range(2):
            self.r.on_press(key('Control_L')); self.r.on_press(key('c')); self.r.on_release(key('c')); self.r.on_release(key('Control_L'))
        self.assertIsNone(self.r.state)

    def test_held_ctrl_is_not_a_tap(self):
        self.text.mark_set('insert', '1.1')
        self.r.on_press(key('Control_L')); self.r._down_at -= 1000; self.r.on_release(key('Control_L'))
        self.tap()
        self.assertIsNone(self.r.state)

    def test_not_while_composing(self):
        self.text.mark_set('insert', '1.1')
        self.composing = True
        self.tap(); self.tap()
        self.assertIsNone(self.r.state)


class Range(Base):
    def spans(self, at):
        return self.r.word_columns(1, '資料を作る', at)

    def test_rule(self):
        self.assertEqual(self.spans(0), (0, 2))     # 止まる位置: そこから次の止まる位置まで
        self.assertEqual(self.spans(2), (2, 3))
        self.assertEqual(self.spans(1), (0, 2))     # 語の中: 前後の止まる位置
        self.assertEqual(self.spans(4), (3, 5))
        self.assertEqual(self.spans(5), (3, 5))     # 行末: 今打ち終えた語
        self.assertIsNone(self.r.word_columns(1, '', 0))


class Keys(Base):
    def press(self, name):
        return self.r.on_press(key(name))

    def test_space_goes_through_the_choices(self):
        self.begin()
        self.assertEqual(self.press('space'), 'break')
        self.assertEqual(self.line(), '試料を作る')
        self.press('space')
        self.assertEqual(self.line(), '資料を作る')
        self.press('space'); self.press('space')
        self.assertEqual(self.line(), '試料を作る')

    def test_enter_keeps_and_ends_without_a_new_row(self):
        self.begin(); self.press('space')
        self.assertEqual(self.press('Return'), 'break')
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), '試料を作る')
        self.assertEqual(self.text.get('1.0', 'end-1c').count('\n'), 1)
        self.assertFalse(self.text.tag_ranges(TAG))

    def test_escape_restores(self):
        self.begin(); self.press('space')
        self.assertEqual(self.press('Escape'), 'break')
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), '資料を作る')

    def test_keys_are_the_imes_while_composing(self):
        self.begin()
        self.composing = True
        for name in ('space', 'Return', 'Escape'):
            self.assertIsNone(self.press(name))
        self.assertIsNotNone(self.r.state)

    def test_other_keys_pass(self):
        self.begin()
        self.assertIsNone(self.press('a'))

    def test_without_a_range_nothing_is_taken(self):
        for name in ('space', 'Return', 'Escape'):
            self.assertIsNone(self.press(name))

    def test_undo_once_goes_back_before_it(self):
        self.begin(); self.press('space'); self.press('space'); self.press('Return')
        self.text.edit_undo()
        self.assertEqual(self.text.get('1.0', 'end-1c'), self.TEXT)


class Follow(Base):
    def test_range_grows_and_shrinks_with_the_edits(self):
        self.begin()
        self.text.insert('insert', 'x'); self.r.settle()
        self.assertEqual(self.text.get(START, END), 'しりょうx')
        self.text.delete('insert-1c', 'insert'); self.text.delete('insert-1c', 'insert'); self.r.settle()
        self.assertEqual(self.text.get(START, END), 'しりょ')
        self.assertIsNotNone(self.r.state)
        self.text.mark_set('insert', START); self.text.insert('insert', 'y'); self.r.settle()
        self.assertEqual(self.text.get(START, END), 'yしりょ')

    def test_edit_then_space_reads_the_new_text(self):
        self.begin()
        seen = []
        with patch.object(ReInput, 'choices_for', lambda s, reading: seen.append(reading) or ['Z']):
            self.text.delete(START, END); self.text.insert(START, '作る'); self.text.mark_set('insert', END); self.r.settle()
            self.r.on_press(key('space'))
        self.assertEqual(seen, ['つくる'])
        self.assertEqual(self.line(), 'Zを作る')

    def leave_to(self, index='2.1', event=None):
        self.text.mark_set('insert', index)
        (event or (lambda: self.r.on_release(key('Next'))))()

    def test_leaving_without_an_edit_goes_back_to_the_original(self):
        for leave in (lambda: self.r.on_release(key('Left')), lambda: self.r.on_release(key('Prior')), self.r.on_pointer_release):
            self.begin()
            self.leave_to(event=leave)
            self.assertIsNone(self.r.state)
            self.assertEqual(self.line(), '資料を作る')
            self.assertEqual(self.text.index('insert'), '2.1')
            self.assertFalse(self.text.tag_ranges(TAG))

    def test_leaving_on_the_same_row_keeps_the_cursor_where_it_went(self):
        self.begin()
        self.text.mark_set('insert', 'cn_reinput_end+2c')
        self.r.on_release(key('Right'))
        self.assertEqual(self.line(), '資料を作る')
        self.assertEqual(self.text.index('insert'), '1.4')

    def test_leaving_after_an_edit_converts_all_of_the_range(self):
        seen = []
        self.begin()
        with patch.object(ReInput, 'reading_of', lambda s, row, col, surface: surface), \
             patch.object(ReInput, 'choices_for', lambda s, reading: seen.append(reading) or ['Z']):
            self.text.insert('insert', 'x'); self.r.settle()
            self.leave_to()
        self.assertEqual(seen, ['しりょうx'])
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), 'Zを作る')
        self.assertEqual(self.text.index('insert'), '2.1')

    def test_an_edit_and_the_leaving_in_one_step(self):
        seen = []
        self.begin()
        with patch.object(ReInput, 'reading_of', lambda s, row, col, surface: surface), \
             patch.object(ReInput, 'choices_for', lambda s, reading: seen.append(reading) or ['Z']):
            self.text.delete('insert-1c', 'insert')
            self.leave_to()
        self.assertEqual(seen, ['しりょ'])
        self.assertEqual(self.line(), 'Zを作る')

    def test_typing_and_taking_it_back_is_no_edit(self):
        self.begin()
        self.text.insert('insert', 'x'); self.r.settle()
        self.text.delete('insert-1c', 'insert'); self.r.settle()
        self.leave_to()
        self.assertEqual(self.line(), '資料を作る')

    def test_a_choice_being_made_is_kept_on_leaving(self):
        self.begin(); self.r.on_press(key('space')); self.r.on_press(key('space'))
        self.leave_to()
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), '資料を作る')

    def test_an_edit_after_a_choice_converts_again(self):
        self.begin(); self.r.on_press(key('space'))
        with patch.object(ReInput, 'reading_of', lambda s, row, col, surface: surface), \
             patch.object(ReInput, 'choices_for', lambda s, reading: ['Y']):
            self.text.insert('insert', 'x'); self.r.settle()
            self.leave_to()
        self.assertEqual(self.line(), 'Yを作る')

    def test_undo_while_open_just_ends_it(self):
        self.begin()
        self.text.edit_undo()
        self.r.settle()
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), '資料を作る')

    def test_undo_after_leaving_goes_before_it(self):
        self.begin(); self.r.on_press(key('space'))
        self.leave_to()
        self.text.edit_undo()
        self.assertEqual(self.text.get('1.0', 'end-1c'), self.TEXT)

    def test_leaving_the_range_ends_it_as_it_is(self):
        self.begin(); self.r.on_press(key('space'))
        self.text.mark_set('insert', 'end-1c')
        self.r.on_release(key('Right'))
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), '試料を作る')
        self.assertFalse(self.text.tag_ranges(TAG))

    def test_ime_space_that_came_in_as_a_character(self):
        self.begin()
        self.text.insert('insert', '　')
        self.r.on_release(key('space'))
        self.assertEqual(self.line(), '試料を作る')

    def test_a_space_seen_and_also_put_in_converts_once(self):
        self.begin()
        self.r.on_press(key('space'))
        self.assertEqual(self.line(), '試料を作る')
        self.text.insert('insert', '　')
        self.r.on_release(key('space'))
        self.assertEqual(self.line(), '試料を作る')

    def test_added_text_then_space_converts_all_of_the_range(self):
        self.begin()
        with patch.object(ReInput, 'reading_of', lambda s, row, col, surface: surface),              patch.object(ReInput, 'choices_for', lambda s, reading: [reading.upper() + '!']):
            self.text.insert('insert', 'a'); self.r.settle()
            self.r.on_press(key('space'))
        self.assertEqual(self.line(), 'しりょうA!を作る')

    def test_removing_all_of_it_ends(self):
        self.begin()
        self.text.delete(START, END); self.r.settle()
        self.assertIsNone(self.r.state)

    def test_another_tab_is_left_alone(self):
        self.begin()
        with patch.object(ReInput, '_owner', lambda s: 'other'):
            self.r.settle()
        self.assertIsNone(self.r.state)
        self.assertEqual(self.line(), 'しりょうを作る')

    def test_keeps_only_its_row(self):
        self.begin()
        self.assertTrue(self.r.keeps_row(1))
        self.assertFalse(self.r.keeps_row(2))
        self.r.finish()
        self.assertFalse(self.r.keeps_row(1))


class Chosen(Base):
    UNIT = dict(base='資料', prev='', next='を')

    def setUp(self):
        super().setUp()
        self.recorded = []
        self.moved = []
        self.app.choices = NS(record=lambda *a: self.recorded.append(a), save=lambda: None)
        self.app._choice_reading = lambda unit, cand: 'しりょう'
        self.app._invalidate_units_cache = lambda: None
        self.app._choices_moved = lambda: self.moved.append(1)
        self.app._units_cache = {('試料を作る', '資料を作る'): ('資料を作る', [dict(self.UNIT)])}

    def choose(self):
        self.begin(); self.r.on_press(key('space')); self.r.on_press(key('Return'))
        return self.line()

    def answer(self, *details, original='試料を作る'):
        return dict(original=original, corrected='資料を作る', details=list(details))

    def test_a_fix_of_the_chosen_word_is_recorded_as_a_choice(self):
        self.choose()
        self.r.on_answer(self.answer(('試料', '資料', 'かな入力')))
        self.assertEqual(self.recorded, [('資料', '試料', 'しりょう', '', 'を')])
        self.assertEqual(self.moved, [1])

    def test_once(self):
        self.choose()
        self.r.on_answer(self.answer(('試料', '資料', 'x')))
        self.r.on_answer(self.answer(('試料', '資料', 'x')))
        self.assertEqual(len(self.recorded), 1)

    def test_undo_back_before_it_forgets_the_choice(self):
        self.app.choices = NS(record=lambda *a: setattr(self.app.choices, '_readings', {'x': 1}), save=lambda: None, _readings={}, _units={}, _contexts={})
        self.choose()
        self.r.on_answer(self.answer(('試料', '資料', 'x')))
        self.assertEqual(self.app.choices._readings, {'x': 1})
        self.r.on_answer(dict(original='資料を作る', corrected='資料を作る', details=[]))
        self.assertEqual(self.app.choices._readings, {})
        self.assertEqual(self.moved, [1, 1])
        self.r.on_answer(self.answer(('試料', '資料', 'x')))      # redo
        self.assertEqual(self.app.choices._readings, {'x': 1})

    def test_fixes_elsewhere_stay(self):
        self.choose()
        self.r.on_answer(self.answer(('作る', '造る', 'x')))
        self.assertEqual(self.recorded, [])

    def test_only_on_the_row_as_it_was_chosen(self):
        self.choose()
        self.r.on_answer(self.answer(('試料', '資料', 'x'), original='別の行'))
        self.assertEqual(self.recorded, [])

    def test_opening_alone_chooses_nothing(self):
        self.begin(); self.r.on_press(key('Return'))
        self.r.on_answer(self.answer(('しりょう', '資料', 'x'), original='しりょうを作る'))
        self.assertEqual(self.recorded, [])

    def test_escape_chooses_nothing(self):
        self.begin(); self.r.on_press(key('space')); self.r.on_press(key('Escape'))
        self.r.on_answer(self.answer(('資料', '試料', 'x'), original='資料を作る'))
        self.assertEqual(self.recorded, [])

    def test_the_answer_already_there_counts(self):
        self.begin(); self.r.on_press(key('space'))
        self.app.line_results = [self.answer(('試料', '資料', 'x'))]
        self.r.on_press(key('Return'))
        self.assertEqual(len(self.recorded), 1)


class Caret(unittest.TestCase):
    READS = {'資': ['し'], '料': ['りょう'], '学': ['がく'], '校': ['こう'], '発': ['はつ'], '表': ['ひょう'], '作': ['つく', 'さく'], '人': ['ひと', 'じん', 'にん']}

    def at(self, original, reading, column):
        return reinput.caret_column(original, reading, column, lambda ch: self.READS.get(ch, ()))

    def test_between_kanji_by_each_kanjis_reading(self):
        self.assertEqual(self.at('資料', 'しりょう', 1), 1)
        self.assertEqual(self.at('資料を', 'しりょうを', 2), 4)
        self.assertEqual(self.at('資料を', 'しりょうを', 3), 5)

    def test_sound_changes_count(self):
        self.assertEqual(self.at('学校', 'がっこう', 1), 2)
        self.assertEqual(self.at('発表', 'はっぴょう', 1), 2)

    def test_kana_between(self):
        self.assertEqual(self.at('作り方', 'つくりかた', 2), 3)
        self.assertEqual(self.at('作り方', 'つくりかた', 1), 2)
        self.assertEqual(self.at('メモ帳', 'めもちょう', 1), 1)

    def test_unknown_kanji_goes_after_its_kana(self):
        self.assertEqual(self.at('丸々', 'まるまる', 1), 4)
        self.assertEqual(self.at('未知語を', 'みちごを', 1), 3)

    def test_nothing_matches_goes_to_the_end(self):
        self.assertEqual(self.at('資料を', 'しりょうが', 1), 5)

    def test_edges(self):
        self.assertEqual(self.at('資料', 'しりょう', 0), 0)
        self.assertEqual(self.at('資料', 'しりょう', 2), 4)

    def test_one_kanji_without_that_reading_takes_the_rest(self):
        reads = {'日': ['にち', 'に', 'ひ'], '程': ['ほど']}
        self.assertEqual(reinput.caret_column('日程', 'にってい', 1, lambda ch: reads[ch]), 2)
        self.assertEqual(reinput.cut_column('日程', 'にってい', 1, lambda ch: reads[ch]), 2)

    def test_two_unknown_kanji_are_not_guessed(self):
        self.assertIsNone(reinput.cut_column('甲乙', 'あいう', 1, lambda ch: ()))

    def test_two_ways_are_not_guessed(self):
        reads = {'甲': ['あ', 'ああ'], '乙': ['あ', 'ああ']}
        self.assertEqual(reinput.caret_column('甲乙', 'あああ', 1, lambda ch: reads[ch]), 3)


class CaretOpen(Base):
    TEXT = '資料を作る\n二行目です'

    def setUp(self):
        super().setUp()
        patch.object(ReInput, '_char_readings', lambda s, ch: {'資': ['し'], '料': ['りょう']}.get(ch, [])).start()

    def col(self):
        return self.text.index('insert')

    def test_opens_at_the_kana_of_the_caret(self):
        self.begin('1.1')
        self.assertEqual(self.col(), '1.1')
        self.assertEqual(self.text.get('1.0', 'insert'), 'し')

    def test_at_a_stop_with_no_purple_goes_to_the_head(self):
        self.begin('1.0')
        self.assertEqual(self.col(), '1.0')

    def test_at_a_stop_goes_to_the_first_purple(self):
        self.app.line_results = [dict(original='資料を作る', odd_spans=[(1, 2)])]
        self.begin('1.0')
        self.assertEqual(self.text.get('1.0', 'insert'), 'し')

    def test_purple_outside_the_range_does_not_count(self):
        self.app.line_results = [dict(original='資料を作る', odd_spans=[(3, 5)])]
        self.begin('1.0')
        self.assertEqual(self.col(), '1.0')

    def test_purple_of_another_text_does_not_count(self):
        self.app.line_results = [dict(original='別の行', odd_spans=[(1, 2)])]
        self.begin('1.0')
        self.assertEqual(self.col(), '1.0')

    def test_at_the_end_of_the_row_goes_after_the_word(self):
        self.begin('1.end')
        self.assertEqual(self.line(), '資料をつくる')
        self.assertEqual(self.col(), '1.6')

    def test_space_then_goes_to_the_end_of_the_word(self):
        self.begin('1.1'); self.r.on_press(key('space'))
        self.assertEqual(self.col(), self.text.index(END))


class Selected(Base):
    def setUp(self):
        super().setUp()
        self.closed = []
        self.app._close_dropdown = lambda: self.closed.append('list')
        self.app._clear_f2_target = lambda: self.closed.append('target')

    def test_the_reconvert_range_is_the_range(self):
        self.app._f2_focus_target = dict(widget=self.text, row=1, start=3, end=5, text='作る')
        self.tap(); self.tap()
        self.assertEqual(self.text.get(START, END), 'つくる')
        self.assertEqual(self.line(), '資料をつくる')
        self.assertEqual(self.closed, ['list', 'target'])
        self.assertEqual(self.r.state['original'], '作る')

    def test_a_reconvert_range_of_another_box_is_not_ours(self):
        self.app._f2_focus_target = dict(widget=object(), row=1, start=3, end=5, text='作る')
        self.text.mark_set('insert', '1.1')
        self.tap(); self.tap()
        self.assertEqual(self.r.state['original'], '資料')

    def test_a_selection_is_the_range(self):
        self.text.tag_add('sel', '1.3', '1.5')
        self.tap(); self.tap()
        self.assertEqual(self.r.state['original'], '作る')

    def test_a_selection_over_rows_is_not(self):
        self.text.tag_add('sel', '1.3', '2.1')
        self.text.mark_set('insert', '1.1')
        self.tap(); self.tap()
        self.assertEqual(self.r.state['original'], '資料')

    def test_list_open_without_a_range_does_nothing(self):
        self.app._dropdown = object()
        self.text.mark_set('insert', '1.1')
        self.tap(); self.tap()
        self.assertIsNone(self.r.state)


class Typed(Base):
    def setUp(self):
        super().setUp()
        self.f5 = []
        self.app._on_f2_candidates = lambda event: self.f5.append(self.text.get('sel.first', 'sel.last'))
        self.app._just_committed_range = lambda w: ('1.0', '1.5')
        self.text.mark_set('insert', '1.5')

    def answer(self, *odd, text='資料を作る'):
        self.app.line_results = [dict(original=text, odd_spans=list(odd))]

    def test_purple_in_what_was_typed_opens_there(self):
        self.answer((3, 5))
        self.tap(); self.tap()
        self.assertEqual(self.r.state['original'], '作る')
        self.assertEqual(self.f5, [])

    def test_first_purple_wins(self):
        self.answer((3, 5), (1, 2))
        self.tap(); self.tap()
        self.assertEqual(self.r.state['original'], '資料')

    def test_no_purple_selects_the_last_word_as_reconvert(self):
        self.answer()
        self.tap(); self.tap()
        self.assertIsNone(self.r.state)
        self.assertEqual(self.f5, ['作る'])

    def test_purple_outside_what_was_typed_does_not_count(self):
        self.app._just_committed_range = lambda w: ('1.3', '1.5')
        self.answer((0, 2))
        self.tap(); self.tap()
        self.assertEqual(self.f5, ['作る'])

    def test_waits_for_the_row_being_analysed(self):
        self.app.line_results = [dict(original='資料を作る', pending=True)]
        self.tap(); self.tap()
        self.assertIsNone(self.r.state)
        self.assertEqual(self.f5, [])
        self.answer((3, 5))
        end = time.monotonic() + 1
        while self.r.state is None and time.monotonic() < end:
            self.root.update(); time.sleep(.01)
        self.assertEqual(self.r.state['original'], '作る')

    def test_a_key_while_waiting_calls_it_off(self):
        self.app.line_results = [dict(original='資料を作る', pending=True)]
        self.tap(); self.tap()
        self.r.on_press(key('a'))
        self.answer((3, 5))
        end = time.monotonic() + .2
        while time.monotonic() < end:
            self.root.update(); time.sleep(.01)
        self.assertIsNone(self.r.state)

    def test_not_just_typed_is_the_word_at_the_cursor(self):
        self.app._just_committed_range = lambda w: None
        self.text.mark_set('insert', '1.1')
        self.tap(); self.tap()
        self.assertEqual(self.r.state['original'], '資料')


class Quick(Base):
    def setUp(self):
        super().setUp()
        self.r = ReInput(self.app, self.text, quick=True)

    def test_opens_converts_and_goes_back(self):
        self.begin('1.1')
        self.assertEqual(self.line(), 'しりょうを作る')
        self.r.on_press(key('space'))
        self.assertEqual(self.line(), '試料を作る')
        self.r.on_press(key('Escape'))
        self.assertEqual(self.line(), '資料を作る')

    def test_leaving_without_an_edit_goes_back(self):
        self.begin('1.1')
        self.text.mark_set('insert', '2.1'); self.r.on_release(key('Right'))
        self.assertEqual(self.line(), '資料を作る')

    def test_the_main_memos_results_are_not_its_own(self):
        self.app.line_results = [dict(original='資料を作る', odd_spans=[(1, 2)])]
        self.begin('1.0')
        self.assertEqual(self.text.index('insert'), '1.0')
        self.app._quick_results = [dict(original='しりょうを作る', odd_spans=[])]

    def test_its_own_results_count(self):
        patch.object(ReInput, '_char_readings', lambda s, ch: {'資': ['し'], '料': ['りょう']}.get(ch, [])).start()
        self.app._quick_results = [dict(original='資料を作る', odd_spans=[(1, 2)])]
        self.begin('1.0')
        self.assertEqual(self.text.get('1.0', 'insert'), 'し')

    def test_edits_do_not_call_the_main_memos_analysis(self):
        self.begin('1.1')
        self.assertEqual(self.changes, [])


class Merged(Base):
    """再変換の一覧のキー（一覧のふりをした物で）。"""
    def setUp(self):
        super().setUp()
        self.picks = []
        self.selected = (0,)
        self.app._f2_focus_target = dict(widget=self.text, row=1, start=3, end=5, text='作る')
        self.app._dropdown = object()
        self.app._dropdown_pick = lambda: self.picks.append(self.selected)
        self.app._close_dropdown = lambda: setattr(self.app, '_dropdown', None)
        self.app._clear_f2_target = lambda: setattr(self.app, '_f2_focus_target', None)
        self.app._reinput = self.r
        self.keys = reinput.ListKeys(self.app, NS(curselection=lambda: self.selected))
        self.keys.remember_first()

    def tap_on_list(self):
        self.keys.press(key('Control_L')); return self.keys.release(key('Control_L'))

    def test_space_before_moving_opens_the_range(self):
        self.assertEqual(self.keys.press(NS(keysym='space', char=' ')), 'break')
        self.assertEqual(self.r.state['original'], '作る')
        self.assertEqual(self.line(), '資料をつくる')
        self.assertEqual(self.picks, [])

    def test_ime_space_too(self):
        self.assertEqual(self.keys.press(NS(keysym='space', char='\u3000')), 'break')
        self.assertIsNotNone(self.r.state)

    def test_a_misread_key_is_not_a_space(self):
        self.assertIsNone(self.keys.press(NS(keysym='space', char='映')))
        self.assertIsNone(self.r.state)

    def test_space_after_moving_is_left_to_the_list(self):
        self.selected = (2,)
        self.assertIsNone(self.keys.press(NS(keysym='space', char=' ')))
        self.assertIsNone(self.r.state)

    def test_moving_back_is_not_moved(self):
        self.selected = (2,); self.selected = (0,)
        self.assertEqual(self.keys.press(NS(keysym='space', char=' ')), 'break')

    def test_ctrl_alone_after_moving_decides(self):
        self.selected = (2,)
        self.assertEqual(self.tap_on_list(), 'break')
        self.assertEqual(self.picks, [(2,)])
        self.assertIsNone(self.r.state)

    def test_ctrl_with_another_key_does_not_decide(self):
        self.selected = (2,)
        for other in (lambda: self.keys.press(key('Right')), lambda: self.keys.release(key('Right')), self.keys.pointer):
            self.keys.press(key('Control_L')); other(); self.keys.release(key('Control_L'))
        self.assertEqual(self.picks, [])

    def test_one_ctrl_before_moving_does_nothing(self):
        self.tap_on_list()
        self.assertEqual(self.picks, [])
        self.assertIsNone(self.r.state)

    def test_two_ctrl_before_moving_opens_the_range(self):
        self.tap_on_list(); self.tap_on_list()
        self.assertEqual(self.r.state['original'], '作る')
        self.assertEqual(self.picks, [])

    def test_a_list_for_another_box_is_left_alone(self):
        self.app._f2_focus_target = dict(widget=object(), row=1, start=3, end=5)
        self.assertIsNone(self.keys.press(NS(keysym='space', char=' ')))
        self.selected = (2,)
        self.assertIsNone(self.tap_on_list())
        self.assertEqual(self.picks, [])

    def test_the_range_with_no_list_open_opens_on_space(self):
        self.app._dropdown = None
        self.assertEqual(self.r.on_press(key('space')), 'break')
        self.assertEqual(self.r.state['original'], '作る')

    def test_quick_box_the_same(self):
        quick = ReInput(self.app, tk.Text(self.root), quick=True)
        quick.widget.insert('1.0', '資料を作る')
        self.app._quick_reinput = quick
        self.app._f2_focus_target = dict(widget=quick.widget, row=1, start=3, end=5, text='作る')
        self.keys.press(NS(keysym='space', char=' '))
        self.assertEqual(quick.state['original'], '作る')
        self.assertIsNone(self.r.state)


class Installed2(unittest.TestCase):
    def test_list_binding_is_first(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.addCleanup(root.destroy)
        listbox = tk.Listbox(root)
        reinput.install_on_list(NS(), listbox)
        self.assertTrue(listbox.bindtags()[0].startswith(reinput.LIST_TAG))


class SelectionSpace(Base):
    def setUp(self):
        super().setUp()
        patch.object(ReInput, '_char_readings', lambda s, ch: {'資': ['し'], '料': ['りょう']}.get(ch, [])).start()

    def space(self, **k):
        return self.r.on_press(NS(keysym='space', **k))

    def test_a_selection_opens_on_space(self):
        self.text.tag_add('sel', '1.0', '1.2')
        self.text.mark_set('insert', '1.0')
        self.assertEqual(self.space(), 'break')
        self.assertEqual(self.r.state['original'], '資料')
        self.assertEqual(self.line(), 'しりょうを作る')
        self.assertEqual(self.text.index('insert'), '1.0')

    def test_the_caret_goes_to_the_first_purple(self):
        self.app.line_results = [dict(original='資料を作る', odd_spans=[(1, 2)])]
        self.text.tag_add('sel', '1.0', '1.2')
        self.space()
        self.assertEqual(self.text.get('1.0', 'insert'), 'し')

    def test_no_purple_keeps_the_caret_where_it_was(self):
        self.text.tag_add('sel', '1.0', '1.2'); self.text.mark_set('insert', '1.2')
        self.space()
        self.assertEqual(self.text.get('1.0', 'insert'), 'しりょう')
        self.r.on_press(key('Escape'))
        self.text.tag_add('sel', '1.0', '1.2'); self.text.mark_set('insert', '1.1')
        self.space()
        self.assertEqual(self.text.get('1.0', 'insert'), 'し')

    def test_purple_comes_before_the_caret(self):
        self.app.line_results = [dict(original='資料を作る', odd_spans=[(1, 2)])]
        self.text.tag_add('sel', '1.0', '1.2'); self.text.mark_set('insert', '1.2')
        self.space()
        self.assertEqual(self.text.get('1.0', 'insert'), 'し')

    def test_the_imes_full_width_space(self):
        self.text.tag_add('sel', '1.0', '1.2')
        self.assertEqual(self.r.on_press(NS(keysym='??', char='\u3000')), 'break')
        self.assertIsNotNone(self.r.state)

    def test_only_spaces_selected_is_an_ordinary_space(self):
        self.text.insert('1.end', '  ')
        self.text.tag_add('sel', '1.5', '1.7')
        self.assertIsNone(self.space())
        self.assertIsNone(self.r.state)

    def test_quick_box_the_same(self):
        r = ReInput(self.app, self.text, quick=True)
        self.text.tag_add('sel', '1.0', '1.2'); self.text.mark_set('insert', '1.2')
        self.assertEqual(r.on_press(NS(keysym='space')), 'break')
        self.assertEqual(r.state['original'], '資料')

    def test_no_selection_is_an_ordinary_space(self):
        self.assertIsNone(self.space())
        self.assertIsNone(self.r.state)

    def test_over_rows_is_an_ordinary_space(self):
        self.text.tag_add('sel', '1.0', '2.1')
        self.assertIsNone(self.space())

    def test_with_shift_or_ctrl_is_ordinary(self):
        self.text.tag_add('sel', '1.0', '1.2')
        self.assertIsNone(self.space(state=1))
        self.assertIsNone(self.space(state=4))

    def test_a_misread_key_is_a_character(self):
        self.text.tag_add('sel', '1.0', '1.2')
        self.assertIsNone(self.space(char='映'))

    def test_while_composing_is_the_imes(self):
        self.text.tag_add('sel', '1.0', '1.2')
        self.composing = True
        self.assertIsNone(self.space())

    def test_undo_once_goes_back(self):
        self.text.tag_add('sel', '1.0', '1.2')
        self.space(); self.r.on_press(key('Return'))
        self.text.edit_undo()
        self.assertEqual(self.text.get('1.0', 'end-1c'), self.TEXT)


class Reading(unittest.TestCase):
    def reader(self, doc=(), remembered=None, reverse=None, tokens=None):
        app = NS(ime_readings=NS(readings_for=lambda s: (remembered or {}).get(s, ())), store=NS(_tokenize_fn=tokens))
        r = ReInput(app, NS(get=lambda *a: ''))
        patch.object(ReInput, '_committed', lambda s, row, col, surface: list(doc)).start()
        patch.object(ReInput, '_reverse', lambda s, text: (reverse or {}).get(text)).start()
        self.addCleanup(patch.stopall)
        return r

    def test_the_committed_reading_comes_first(self):
        r = self.reader(doc=[(0, 2, 'しりょう')], remembered={'資料': ('べつ',)})
        self.assertEqual(r.reading_of(1, 0, '資料'), 'しりょう')

    def test_then_remembered_then_reverse_then_tokens(self):
        self.assertEqual(self.reader(remembered={'資料': ('しりょう',)}, reverse={'資料': 'べつ'}).reading_of(1, 0, '資料'), 'しりょう')
        self.assertEqual(self.reader(reverse={'資料': 'シリョウ'}).reading_of(1, 0, '資料'), 'しりょう')
        tokens = lambda text: [NS(surface=text, reading='しりょう', has_reading=True)]
        self.assertEqual(self.reader(tokens=tokens).reading_of(1, 0, '資料'), 'しりょう')

    def test_katakana_and_letters(self):
        r = self.reader()
        self.assertEqual(r.reading_of(1, 0, 'メモ'), 'めも')
        self.assertEqual(r.reading_of(1, 0, 'abc'), 'abc')
        self.assertEqual(self.reader(reverse={'字': 'じ'}).reading_of(1, 0, 'abc字'), 'abcじ')

    def test_unread_stays(self):
        self.assertEqual(self.reader(tokens=lambda text: []).reading_of(1, 0, '資料'), '資料')

    def test_part_committed(self):
        r = self.reader(doc=[(0, 2, 'しりょう')], reverse={'を作': 'をさく'})
        self.assertEqual(r.reading_of(1, 0, '資料を作'), 'しりょうをさく')


class PartOfAWord(unittest.TestCase):
    READS = {'会': ['かい', 'あ'], '議': ['ぎ'], '資': ['し'], '料': ['りょう'], '変': ['へん'], '更': ['こう', 'さら']}

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.text = tk.Text(self.root)
        self.text.insert('1.0', '会議の資料を変更')
        self.words = [(0, 2, '会議', 'かいぎ'), (2, 3, 'の', 'の'), (3, 5, '資料', 'しりょう'), (5, 6, 'を', 'を'), (6, 8, '変更', 'へんこう')]
        def tokens(line):
            return [(w, 'x', r, s, e, True, '') for s, e, w, r in self.words]
        app = NS(store=NS(_tokenize_fn=tokens), ime_readings=NS(readings_for=lambda s: ()))
        self.r = ReInput(app, self.text)
        self.lone = {}
        for name, value in (('_char_readings', lambda s, ch: self.READS.get(ch, [])), ('_reverse', lambda s, t: self.lone.get(t)),
                            ('_committed_main', lambda s, row, col, surface: list(self.committed))):
            p = patch.object(ReInput, name, value); p.start(); self.addCleanup(p.stop)
        self.committed = []

    def read(self, first, last):
        return self.r.reading_of(1, first, self.text.get(f'1.{first}', f'1.{last}'))

    def test_second_kanji_with_what_follows_reads_from_the_word(self):
        self.lone = {'議の': 'はかりの'}      # 単独の読みは違う
        self.assertEqual(self.read(1, 3), 'ぎの')
        self.assertEqual(self.read(7, 8), 'こう')

    def test_first_kanji_too(self):
        self.lone = {'会': 'あ'}
        self.assertEqual(self.read(0, 1), 'かい')

    def test_across_two_words(self):
        self.assertEqual(self.read(1, 4), 'ぎのし')

    def test_on_word_boundaries_stays_as_it_was(self):
        self.lone = {'資料': 'べつ'}
        self.assertEqual(self.read(3, 5), 'べつ')

    def test_cannot_cut_falls_back_to_the_characters_alone(self):
        self.READS = {}
        self.lone = {'議': 'はかり'}
        self.assertEqual(self.read(1, 2), 'はかり')

    def test_a_commit_is_cut_at_the_characters(self):
        class Occ:
            start, end, surface, reading = 0, 2, '会議', 'カイギ'
        patch.stopall()
        for name, value in (('_char_readings', lambda s, ch: self.READS.get(ch, [])), ('_reverse', lambda s, t: None)):
            p = patch.object(ReInput, name, value); p.start(); self.addCleanup(p.stop)
        with patch('analysis_work_app.line_readings', return_value=[Occ]):
            self.assertEqual(self.r._committed_main(1, 1, '議の'), [(0, 1, 'ぎ')])

    def test_a_whole_commit_stays(self):
        class Occ:
            start, end, surface, reading = 0, 2, '会議', 'かいぎ'
        patch.stopall()
        with patch('analysis_work_app.line_readings', return_value=[Occ]):
            self.assertEqual(self.r._committed_main(1, 0, '会議の'), [(0, 2, 'かいぎ')])

    def test_a_commit_that_cannot_be_cut_is_not_used(self):
        class Occ:
            start, end, surface, reading = 0, 2, '会議', 'かいぎ'
        patch.stopall()
        p = patch.object(ReInput, '_char_readings', lambda s, ch: []); p.start(); self.addCleanup(p.stop)
        with patch('analysis_work_app.line_readings', return_value=[Occ]):
            self.assertEqual(self.r._committed_main(1, 1, '議の'), [])


class Installed(unittest.TestCase):
    def test_first_in_the_bindings(self):
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.addCleanup(root.destroy)
        text = tk.Text(root)
        reinput.install(NS(), text)
        self.assertEqual(text.bindtags()[0], reinput.BIND_TAG)


if __name__ == '__main__':
    unittest.main()
