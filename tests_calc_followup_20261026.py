# -*- coding: utf-8 -*-
"""Calculation mode, carried on (2026-10-26 うにさん).

12:57Z「計算モードで計算の答えが出た直後に限り、さらに答えを使った計算式を組んだ場合、再計算する。また、
数字が書かれているところに、頭にイコールをつけて計算式にした場合も、答えに変換する。」
13:14Z「計算モードの答えは、小数点第4位までとし、第5位からは切り捨てる」

- Right after an answer (12+3 → 15), an operator and a number typed onto it and Enter work it out from the
  answer as shown: 15*2 → 30 (not 12+3*2). Moving the cursor away first forgets the answer.
- = typed in front of a formula already written (=100*1.08) and Enter: 108, as = typed before a new formula.
  Dates, telephone numbers and = before words are left alone.
- Answers keep 4 decimal places, cut toward zero; carrying on uses the answer as shown.
- One undo takes back the carried-on part (the earlier answer stands again).
"""
import types
import unittest
from unittest.mock import patch

from quote_calculator import (calculate, continuation, continued_calculation, clean_calculations, evaluate,
                              written_formula)


class FourPlacesTests(unittest.TestCase):
    def test_cut_not_rounded(self):
        for expression, answer in (('10/3', '3.3333'), ('2/3', '0.6666'), ('-2/3', '-0.6666'), ('1/8', '0.125'),
                                   ('0.1+0.2', '0.3'), ('7*3', '21'), ('1.50+1', '2.5'), ('-0.00001', '0'),
                                   ('1/3*3', '0.9999'), ('5.99999', '5.9999')):
            with self.subTest(expression=expression):
                self.assertEqual(calculate(expression), answer)


class CarryOnTests(unittest.TestCase):
    def test_evaluate_from_the_answer(self):
        self.assertEqual(evaluate('12+3*2', (4,)), '30')            # (12+3)*2, not 18
        self.assertEqual(evaluate('12+3*2+1', (4, 6)), '31')
        self.assertEqual(evaluate('10/3*3', (4,)), '9.9999')        # the answer as shown: 3.3333*3
        self.assertEqual(evaluate('2-5*2', (3,)), '-6')             # -3*2
        self.assertIsNone(evaluate('12+32', (4,)))                  # what follows must start with an operator
        self.assertIsNone(evaluate('12+3', (9,)))

    def test_continuation(self):
        for text in ('*2', ' + 3', '÷4', '－1.5', '*(1+1)'):
            self.assertTrue(continuation(text), text)
        for text in ('', '2', '*', '円', '*2円', '\n*2'):
            self.assertFalse(continuation(text), text)

    def test_continued_calculation(self):
        from analysis_work import Calculation
        source = '値12+3*2です'
        calcs = (Calculation(1, 5, '12+3', '15'),)
        self.assertEqual(continued_calculation(source, calcs, 5, 7), (1, '12+3*2', (4,)))
        # digits typed straight onto the answer stay one formula as before
        self.assertEqual(continued_calculation('値12+32です', calcs, 5, 6), (1, '12+32', ()))

    def test_saved_records_keep_the_splits(self):
        text = '12+3*2'
        kept = clean_calculations(text, [dict(start=0, end=6, surface=text, splits=[4])])
        self.assertEqual(kept, [dict(start=0, end=6, surface=text, splits=[4])])
        self.assertEqual(clean_calculations(text, [dict(start=0, end=6, surface=text, splits=[9])]), [])
        self.assertEqual(clean_calculations(text, [dict(start=0, end=6, surface=text)]),
                         [dict(start=0, end=6, surface=text)])

    def test_undo_of_the_carried_part_brings_back_the_earlier_answer(self):
        from analysis_work import Document
        doc = Document('t', '12+3*2')
        self.assertTrue(doc.remember_calculation(0, 6, '12+3*2', '30', (4,)))
        doc.update('12+3')
        self.assertEqual([(c.start, c.end, c.surface, c.result) for c in doc.calculations],
                         [(0, 4, '12+3', '15')])


class WrittenFormulaTests(unittest.TestCase):
    def test_formula_at_the_start(self):
        self.assertEqual(written_formula('100*1.08'), '100*1.08')
        self.assertEqual(written_formula('100*1.08円です'), '100*1.08')
        self.assertEqual(written_formula('１２＋３ は'), '１２＋３')

    def test_not_formulas(self):
        for text in ('2026-10-26', '03-1234-5678', '2026/10/26', '100', '円は100', 'abc', '', '1+', '10:30'):
            self.assertEqual(written_formula(text), '', text)


class CalcFollowupTkTests(unittest.TestCase):
    """The real app's Enter handling, on the editor of a bare app (as tests_gui_editing)."""

    def setUp(self):
        from tests_gui_editing import QuoteEnterCommandTests
        self.fixture = QuoteEnterCommandTests('setUp')
        self.fixture.setUp()
        self.a = self.fixture.a
        self.a._calc_followup = None
        self.a.result_view.bind('<KeyPress>', self.a._on_pick_mode_keypress)

    def tearDown(self):
        self.a = None           # the fixture checks that nothing keeps its Tk root
        self.fixture.tearDown()

    def source(self, text):
        return self.fixture._command_source(text)

    def type(self, widget, text):
        self.fixture._type_quote_expression(widget, text)

    def enter(self, widget):
        return self.fixture._enter_quote_expression(widget)

    def shown(self):
        return self.fixture._calculated_text()

    def equals(self, widget):
        self.a._on_equal_key(types.SimpleNamespace(widget=widget, char='=', keysym='equal', state=0))

    def calculate_typed(self, text, expression):
        w = self.source(text)
        w.mark_set('insert', '1.end')
        self.equals(w)
        self.type(w, expression)
        self.enter(w)
        return w

    def test_answer_then_operator_and_enter(self):
        w = self.calculate_typed('値は', '12+3')
        self.assertEqual(self.shown(), '値は15')
        self.assertIsNone(self.a._pick_mode)
        self.type(w, '*2')
        self.assertEqual(self.enter(w), 'break')
        self.assertEqual(self.shown(), '値は30')
        self.type(w, '/4')
        self.enter(w)
        self.assertEqual(self.shown(), '値は7.5')
        self.assertEqual(len(self.a._input_document.calculations), 1)

    def test_answers_cut_at_four_places_carry_on_as_shown(self):
        w = self.calculate_typed('', '10/3')
        self.assertEqual(self.shown(), '3.3333')
        self.type(w, '*3')
        self.enter(w)
        self.assertEqual(self.shown(), '9.9999')

    def test_moving_away_forgets_the_answer(self):
        w = self.calculate_typed('値は', '12+3')
        self.a._on_pick_mode_keypress(types.SimpleNamespace(widget=w, keysym='Left', char='', state=0))
        self.a._on_pick_mode_keypress(types.SimpleNamespace(widget=w, keysym='Right', char='', state=0))
        self.type(w, '*2')
        self.assertIsNone(self.enter(w))        # a plain Enter again
        self.assertEqual(self.shown(), '値は15*2')

    def test_plain_text_after_an_answer_is_not_touched(self):
        w = self.calculate_typed('値は', '12+3')
        self.type(w, '円')
        self.assertIsNone(self.enter(w))
        self.assertEqual(self.shown(), '値は15円')

    def test_undo_takes_back_the_carried_part(self):
        w = self.calculate_typed('値は', '12+3')
        w.edit_separator()
        self.type(w, '*2')
        self.enter(w)
        self.assertEqual(self.shown(), '値は30')
        w.edit_undo()
        self.assertEqual(w.get('1.0', 'end-1c'), '値は12+3')
        import analysis_work_app as work
        work.select_document(self.a, self.a.editor_source_text())
        self.assertEqual(self.shown(), '値は15')

    def test_equals_in_front_of_a_written_formula(self):
        w = self.source('税込は100*1.08円')
        w.mark_set('insert', '1.3')
        self.equals(w)
        self.assertEqual(self.a._pick_mode, 'equals')
        self.enter(w)
        self.assertIsNone(self.a._pick_mode)
        self.assertEqual(w.get('1.0', 'end-1c'), '税込は100*1.08円')     # the = is gone
        self.assertEqual(self.shown(), '税込は108円')
        # right after it, carrying on works too
        self.assertEqual(w.index('insert'), '1.11')
        self.type(w, '*2')
        self.enter(w)
        self.assertEqual(self.shown(), '税込は216円')

    def test_equals_in_front_of_unrelated_text_does_nothing(self):
        for text, at in (('日付は2026-10-26です', 3), ('電話03-1234-5678', 2), ('名前は田中', 3)):
            with self.subTest(text=text):
                w = self.source(text)
                w.mark_set('insert', '1.%d' % at)
                self.equals(w)
                self.enter(w)
                self.assertFalse(self.a._input_document.calculations)
                self.assertTrue(self.shown().replace('=', '').startswith(text[:at]))
                self.assertIn(text[at:], self.shown())

    def test_text_without_equals_is_left_alone(self):
        for text in ('日付は2026-10-26です', '電話03-1234-5678', '100*1.08円'):
            w = self.source(text)
            w.mark_set('insert', '1.end')
            self.assertIsNone(self.enter(w))
            self.assertEqual(self.shown(), text)


if __name__ == '__main__':
    unittest.main()
