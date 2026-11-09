"""pos_seq_odd: を＋サ変の名詞で終わる行（メモ・見出し）に紫を付けない（作った例）。"""
import os
import unittest

import pos_seq_odd as P


def _odd(t):
    return P.mark_line(t, {'original': t, 'corrected': t, 'changed': False}).get('odd_spans')


class WoSahenTest(unittest.TestCase):
    def test_note_kept(self):
        self.assertFalse(_odd('表の誤記を修正。'))

    def test_general_noun_still_marked(self):
        self.assertTrue(_odd('絵を民'))

    def test_switch_off(self):
        os.environ['CN_POS_SEQ_WO_SAHEN'] = '0'
        try:
            self.assertTrue(_odd('表の誤記を修正。'))
        finally:
            del os.environ['CN_POS_SEQ_WO_SAHEN']


if __name__ == '__main__':
    unittest.main()
