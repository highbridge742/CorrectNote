import unittest, shift_slip as S

class ShiftSlipTest(unittest.TestCase):
    def test_shift_release_does_not_eat_pending_press(self):
        c = S.ShiftStrokeClock(lambda k: {56: '8', 68: 'd'}.get(k))
        c.press(229, 0.0); c.release(68, 50.0)
        c.press(16, 100.0); c.press(229, 150.0); c.release(16, 200.0); c.release(56, 220.0)
        strokes, shifts = c.take()
        self.assertEqual(strokes, [('d', 0.0), ('8', 150.0)])
        self.assertEqual(shifts, [(100.0, 200.0)])
        self.assertEqual(S.empty_shifts(strokes, shifts), [])

    def test_late_shift_makes_previous_key_small(self):
        strokes = [('s', 0.0), ('j', 100.0), ('z', 200.0), ('q', 400.0)]   # と ま つ た
        shifts = [(210.0, 330.0)]                                            # つ を押した後のシフト（中身なし）
        rel = {2: 260.0}
        got = S.repair_shift('とまつた', strokes, shifts, lambda rd: 1.0 if 'った' in rd else 0.0, rel.get)
        self.assertEqual(got[:2], ('とまった', 'fix'))

    def test_no_empty_shift_no_change(self):
        strokes = [('s', 0.0), ('j', 100.0), ('z', 200.0), ('q', 400.0)]
        self.assertEqual(S.repair_shift('とまつた', strokes, [(150.0, 250.0)], lambda rd: 0.0)[1], None)

if __name__ == '__main__':
    unittest.main()
