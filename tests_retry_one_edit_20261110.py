"""correction_entry: 1打戻した行の通し直しでは、似た読みの探索を1手までにする（作った例）。"""
import unittest
from unittest import mock

import correction_entry as CE
import contextual_repair
import vocabulary


class RetryOneEditTests(unittest.TestCase):
    def test_installed(self):
        self.assertEqual(vocabulary.find_known_readings_flex.__qualname__, '_fkr_retry_one_edit')
        self.assertFalse(hasattr(vocabulary.find_known_readings_flex._cn_raw, '_cn_raw'))

    def test_one_edit_only_while_slip_reverted(self):
        seen = []

        def raw(typed, store, max_dist=1.6, max_edits=2, beam_width=600, input_method=None):
            seen.append(max_edits)
            return []
        with mock.patch.object(CE, '_FKR_RAW', raw):
            CE._fkr_retry_one_edit('かくにん', None, max_edits=2)
            tok = contextual_repair.SLIP_REVERTED.set(True)
            try:
                CE._fkr_retry_one_edit('かくにん', None, max_edits=2)
            finally:
                contextual_repair.SLIP_REVERTED.reset(tok)
        self.assertEqual(seen, [2, 1])


if __name__ == '__main__':
    unittest.main()
