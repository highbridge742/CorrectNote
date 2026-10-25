# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""used_keys（行が使った材料のキー・裏のタブの解析）の見張り。作った語だけ。"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import used_keys as UK


class UsedKeysTest(unittest.TestCase):
    def setUp(self):
        UK.install()
        from vocabulary import VocabularyStore
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = VocabularyStore(path=os.path.join(self.tmp.name, 'vocabulary.json'))

    def test_keyed_lookup_recorded(self):
        token, rec = UK.start()
        try:
            self.store.lookup('てすと')
            self.store.has_reading('かみ')
        finally:
            UK.stop(token)
        a = rec.answer()
        self.assertEqual((a['vocab'], a['whole'], a['recent']), (['かみ', 'てすと'], False, False))

    def test_whole_scan_marks_whole(self):
        token, rec = UK.start()
        try:
            list(self.store.all_readings())
        finally:
            UK.stop(token)
        self.assertTrue(rec.answer()['whole'])

    def test_loan_table_build_is_loan_only(self):
        # 外来語・英語の表を作る間の引きは loan だけ（表が先に作られていたかで whole やキーが揺れない）
        import loanword
        UK.install()
        token, rec = UK.start()
        try:
            loanword._english_vocabulary(self.store)
            loanword._katakana_vocabulary(self.store)
        finally:
            UK.stop(token)
        a = rec.answer()
        self.assertEqual((a['vocab'], a['whole'], a['loan']), ([], False, True))

    def test_whole_answer_drops_keys(self):
        # whole の行はキーを持たない（控えに当たってキーが減っても、同じ行の答えが回ごとに変わらない）
        token, rec = UK.start()
        try:
            self.store.lookup('てすと')
            list(self.store.all_readings())
        finally:
            UK.stop(token)
        a = rec.answer()
        self.assertEqual((a['vocab'], a['choice'], a['whole']), ([], [], True))

    def test_nothing_recorded_outside(self):
        self.store.lookup('てすと')
        self.assertIsNone(UK._ACTIVE.get())

    def test_recent_only_when_read(self):
        words = UK.RecentWords(('本', '机'))
        token, rec = UK.start()
        try:
            bool(words); len(words)
            self.assertFalse(rec.recent)
            '本' in words
        finally:
            UK.stop(token)
        self.assertTrue(rec.recent)

    def test_loan_table_check_is_not_whole(self):
        import loanword
        token, rec = UK.start()
        try:
            loanword._store_revision(self.store)
        finally:
            UK.stop(token)
        a = rec.answer()
        self.assertEqual((a['loan'], a['whole']), (True, False))

    def test_loan_change(self):
        self.assertTrue(UK.is_loan_change('ぺん', 'ペン'))
        self.assertTrue(UK.is_loan_change('en:pen', 'pen'))
        self.assertFalse(UK.is_loan_change('つくえ', '机'))


if __name__ == '__main__':
    unittest.main()
