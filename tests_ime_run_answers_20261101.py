# -*- coding: utf-8 -*-
"""IME の答えを、解析の1回の間だけ行をまたいで使う（ime_session.run_activity・2026-11-01）。重い材料で、IME に
尋ねる回数が 1,708 → 1,371（答えは 56行とも同じ）。間が空いたら次の解析は IME に尋ね直す（IME の学びを見る）。"""
import unittest
from unittest.mock import patch

import ime_session as S


class RunAnswersTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.line = ['一行目']
        patches = (patch.object(S, 'monotonic', lambda: self.now[0]),
                   patch.object(S, '_current_line', lambda: self.line[0]))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        scope = S.line_answers_scope()
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)

    def correct(self, line, key, value=None):
        """1行の補正: 控えを引き、無ければ（IME に尋ねたことにして）書く。"""
        self.line[0] = line
        S.run_activity(True)
        store = S.line_answers()
        got = store.get(key)
        if got is None and value is not None:
            store.put(key, value)
        self.now[0] += 0.5
        S.run_activity(False)
        return got

    def test_another_row_of_the_same_run_reuses_the_answer(self):
        self.correct('会議の資料', ('morph', 1, 'しりょう'), '資料')
        self.assertEqual(self.correct('まったく別の文です', ('morph', 1, 'しりょう')), '資料')

    def test_a_pause_starts_a_new_run(self):
        self.correct('会議の資料', ('morph', 1, 'しりょう'), '資料')
        self.now[0] += S.RUN_IDLE + 1
        self.assertIsNone(self.correct('まったく別の文です', ('morph', 1, 'しりょう')))

    def test_a_long_row_keeps_its_run(self):
        self.line[0] = '会議の資料'
        S.run_activity(True)
        S.line_answers().put(('morph', 1, 'しりょう'), '資料')
        self.now[0] += 30                                   # 30秒かかる行
        S.run_activity(False)
        self.assertEqual(self.correct('まったく別の文です', ('morph', 1, 'しりょう')), '資料')

    def test_a_committed_reading_is_asked_again(self):
        self.correct('会議の資料', ('text', 8, 'しりょう'), '資料')
        S.forget_readings(['しりょう'])
        self.assertIsNone(self.correct('まったく別の文です', ('text', 8, 'しりょう')))

    def test_nothing_is_shared_outside_the_worker(self):
        S._LINE_STORES = None
        S.run_activity(True)
        self.assertIsNone(S._run_answers())


if __name__ == '__main__':
    unittest.main()
