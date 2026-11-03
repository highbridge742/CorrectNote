# -*- coding: utf-8 -*-
"""起動時の英単語の覚え直しを、準備のスレッドで語彙の写しに済ませ、Tk の側は同じ足し方をなぞるだけにする
（2026-10-31・主スレッドが 6〜9 秒止まっていた）。なぞった語彙は、その場で覚え直した語彙と同じ。"""
import unittest

import loanword
from vocabulary import VocabularyStore


def store_with(words):
    store = VocabularyStore()
    for reading, surface in words:
        store.add(reading, surface, '名詞')
    store.add(loanword.english_reading('olddword'), 'olddword', '英語')      # thrown away by the relearn
    return store


class EnglishRelearnThreadTests(unittest.TestCase):
    TEXTS = ['Planetarium Planetarium Planetarium のプラネタリウム\nPlanetariumm と lanetarium も書いた',
             'tkinter tkinter で callout を作る。callout は便利\nhello world']

    def test_replaying_the_record_gives_the_same_vocabulary(self):
        base = [('しりょう', '資料'), ('かいぎ', '会議')]
        direct = store_with(base)
        learned = loanword.relearn_english_from_texts(self.TEXTS, direct)
        real = store_with(base)
        scratch = loanword.scratch_store(real)
        self.assertEqual(scratch.revision(), real.revision())
        record = []
        loanword.relearn_english_from_texts(self.TEXTS, scratch, record=record)
        self.assertEqual(loanword.apply_english_relearn(real, record), learned)
        self.assertEqual(real.to_list(), direct.to_list())
        self.assertEqual(loanword._english_vocabulary(real), loanword._english_vocabulary(direct))
        self.assertNotIn('olddword', loanword._english_vocabulary(real).values())

    def test_the_scratch_copy_leaves_the_real_store_alone(self):
        real = store_with([('しりょう', '資料')])
        before = real.to_list()
        scratch = loanword.scratch_store(real)
        loanword.relearn_english_from_texts(self.TEXTS, scratch, record=[])
        self.assertEqual(real.to_list(), before)


class WorkerRelearnTests(unittest.TestCase):
    TEXTS = EnglishRelearnThreadTests.TEXTS

    def test_the_worker_task_returns_the_same_record(self):
        # analysis_worker.Runtime の english_relearn（本体の語彙の写し・最後の選択の写しつき）
        import analysis_worker
        base = [('しりょう', '資料')]
        direct = store_with(base)
        record_direct = []
        loanword.relearn_english_from_texts(self.TEXTS, direct, record=record_direct)
        real = store_with(base)
        runtime = analysis_worker.Runtime()
        value = runtime.execute(dict(kind='english_relearn', texts=self.TEXTS,
                                     entries=[dict(e) for e in real.to_list()], revision=real.revision(),
                                     choices={'_readings': {}, '_units': {}}, choice_revision=0))
        self.assertEqual(value['record'], record_direct)
        loanword.apply_english_relearn(real, value['record'])
        self.assertEqual(real.to_list(), direct.to_list())

    def test_waiting_takes_the_answer_and_closes_a_temporary_worker(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import app
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        worker = SimpleNamespace(poll=Mock(side_effect=[None, {'record': [('en:x', 'x', 1)]}]), close=Mock())
        plan = dict(job=7, worker=worker, temporary=True, since=__import__('time').monotonic(), record=None)
        self.assertTrue(a._english_relearn_waiting(plan))          # not yet
        self.assertFalse(a._english_relearn_waiting(plan))         # the answer came
        self.assertEqual(plan['record'], [('en:x', 'x', 1)])
        worker.close.assert_called_once()
        broken = SimpleNamespace(poll=Mock(side_effect=RuntimeError('exited')), close=Mock())
        plan = dict(job=1, worker=broken, temporary=False, since=0, record=None)
        self.assertFalse(a._english_relearn_waiting(plan))         # gives up: the main thread relearns
        self.assertTrue(plan['given_up'])
        broken.close.assert_not_called()                            # a kept worker is not closed


if __name__ == '__main__':
    unittest.main()
