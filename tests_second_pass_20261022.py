"""直した行をもう1度通した直しを、元の行の位置に写して足す（2026-10-22・1行に誤字が2つの行から。例は作った文）"""
import unittest
from correction_entry import _merge_second_pass


class SecondPassMergeTests(unittest.TestCase):
    def test_second_fix_is_mapped_to_original_line(self):
        # 元の行 こみれから宿題に鳥かかる。 1回目で こみれ→これ、2回目で 鳥かかる→取りかかる
        line = 'こみれから宿題に鳥かかる。'
        first = dict(changed=True, corrected='これから宿題に鳥かかる。', details=['a'],
                     spans=[(0, 2)], original_spans=[(0, 3)], odd_spans=[(7, 11)], unsure_spans=[])
        second = dict(changed=True, corrected='これから宿題に取りかかる。', details=['b'],
                      spans=[(7, 12)], original_spans=[(7, 11)], odd_spans=[], unsure_spans=[])
        got = _merge_second_pass(line, first, second)
        self.assertEqual(got['corrected'], 'これから宿題に取りかかる。')
        self.assertEqual(got['details'], ['a', 'b'])
        self.assertEqual(got['spans'], [(0, 2), (7, 12)])
        self.assertEqual(got['original_spans'], [(0, 3), (8, 12)])
        self.assertEqual(line[8:12], '鳥かかる')
        self.assertEqual(got['odd_spans'], [])

    def test_overlapping_second_fix_is_dropped(self):
        # 2回目が1回目の直しに重なるなら、1回目のままにする
        line = 'こみれから宿題をする。'
        first = dict(changed=True, corrected='これから宿題をする。', details=['a'],
                     spans=[(0, 2)], original_spans=[(0, 3)])
        second = dict(changed=True, corrected='ここから宿題をする。', details=['b'],
                      spans=[(0, 2)], original_spans=[(0, 2)])
        self.assertIs(_merge_second_pass(line, first, second), first)


if __name__ == '__main__':
    unittest.main()
