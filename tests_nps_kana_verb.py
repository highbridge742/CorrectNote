"""no_particle_slip: 送り仮名の無い漢字1字を用言と見ない（作った例）。"""
import os
import unittest

import no_particle_slip as N


class NpsKanaVerbTest(unittest.TestCase):
    def test_prefix_noun_kept(self):
        self.assertEqual(N.propose('本・棚などの誤配送を減らす。'), [])

    def test_still_fixes(self):
        self.assertEqual(N.propose('本などのしたばあい'), [(3, 4, 'に')])

    def test_switch_off(self):
        os.environ['CN_NPS_KANA_VERB'] = '0'
        try:
            self.assertEqual(N.propose('本・棚などの誤配送を減らす。'), [(5, 6, 'に')])
        finally:
            del os.environ['CN_NPS_KANA_VERB']


if __name__ == '__main__':
    unittest.main()
