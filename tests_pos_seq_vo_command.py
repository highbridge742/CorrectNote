"""pos_seq_odd: 動詞の終止形＋を の後ろが項目を選ぶ・押す動詞なら紫を付けない（作った例）。"""
import os
import unittest

import pos_seq_odd as P


def _odd(t):
    return P.mark_line(t, {'original': t, 'corrected': t, 'changed': False}).get('odd_spans')


class VoCommandTest(unittest.TestCase):
    def test_command_name_kept(self):
        self.assertFalse(_odd('一覧から消すを選びます。'))

    def test_switch_off(self):
        os.environ['CN_POS_SEQ_VO_COMMAND'] = '0'
        try:
            self.assertTrue(_odd('一覧から消すを選びます。'))
        finally:
            del os.environ['CN_POS_SEQ_VO_COMMAND']


if __name__ == '__main__':
    unittest.main()
