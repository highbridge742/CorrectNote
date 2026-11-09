# -*- coding: utf-8 -*-
"""2026-11-05 長い行で紫の所の読み直し（odd_respell）が終わらない: 上限の秒を過ぎたら読み直さず前の答えのまま。"""
import time
import unittest

import correction_entry as C


class DeadlineTests(unittest.TestCase):
    def test_wrapped_run_stops_after_limit(self):
        calls = []
        run = C._deadline_run(lambda t: calls.append(t) or {'corrected': t}, sec=0.05)
        run('あ')
        time.sleep(0.08)
        with self.assertRaises(C._RespellTimeout):
            run('い')
        self.assertEqual(calls, ['あ'])

    def test_timeout_keeps_previous_result(self):
        import odd_respell
        orig = odd_respell.repair_line

        def slow(line, result, run, *a, **k):
            while True:
                try:
                    run(line)
                except Exception:
                    pass
                time.sleep(0.01)
        odd_respell.repair_line = slow
        old = C.ODD_RESPELL_SEC
        C.ODD_RESPELL_SEC = 0.05
        try:
            res = {'corrected': '作った行', 'odd_spans': [(0, 1)]}
            out = C._odd_respell('作った行', res, lambda t: {'corrected': t}, None, None, None, (), 'kana')
            self.assertIs(out, res)
        finally:
            odd_respell.repair_line = orig
            C.ODD_RESPELL_SEC = old


if __name__ == '__main__':
    unittest.main()
