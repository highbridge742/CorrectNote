# -*- coding: utf-8 -*-
"""Process transport matches the application entry on isolated initial stores."""
import time,unittest
from types import SimpleNamespace
from unittest.mock import Mock
import analysis_worker,analysis_async,analysis_work_app
from analysis_work import Document


def initial():
    from vocabulary import VocabularyStore
    from seed_vocabulary import load_seed
    from decisions import DecisionStore
    from last_choice import LastChoiceStore,set_active
    from ime_readings import IMEReadings
    from dict_index import DictIndex
    from context_vec import ContextVectorStore
    import kanji_guess
    store=VocabularyStore();load_seed(store)
    index=DictIndex();index.ensure_built()
    cv=ContextVectorStore();cv.ensure_seeded()
    choices=LastChoiceStore();choices.bind(store,index);set_active(choices)
    ime=IMEReadings();kanji_guess.set_ime_readings_provider(ime.readings_for)
    return SimpleNamespace(store=store,dict_index=index,choices=choices,decisions=DecisionStore(),
        ime_readings=ime,context_vec=cv,settings={'input_method':'kana'})


def wait(worker,identifier):
    end=time.monotonic()+90
    while time.monotonic()<end:
        value=worker.poll(identifier)
        if value is not None:return value
        time.sleep(.01)
    raise AssertionError('Worker timed out')


class EngineProcessTests(unittest.TestCase):
    def test_initial_results_and_decision_updates_match_original_entry(self):
        import app
        from vocabulary import build_context_vocab_cached
        a=initial();worker=analysis_worker.Worker()
        lines=['寒ぃ日だ。','よいでしょぅか。','今日も良い天気です。','書類を作成しました。',
               '作業が官僚しました。','もんじにゅうりょく','今日は😀晴れです。','']
        try:
            expected_context=build_context_vocab_cached(lines,a.store,{})
            prepared=wait(worker,worker.submit(dict(kind='prepare',lines=lines),analysis_worker.snapshot(a)))
            self.assertEqual(prepared['context'],expected_context)
            for line in lines:
                with self.subTest(line=line):
                    expected=app.correct_line(line,a.store,context_vocab=expected_context,decisions=a.decisions,
                        input_method='kana',context_vec=a.context_vec,dict_index=a.dict_index)
                    value=wait(worker,worker.submit(dict(kind='line',line=line,context=expected_context,
                        input_method='kana',attested=prepared['attested'])))
                    self.assertEqual(value['result'],expected)
            a.decisions.protect('寒ぃ')
            a._analysis_state_revision=1
            value=wait(worker,worker.submit(dict(kind='line',line=lines[0],context=expected_context,
                input_method='kana',attested=prepared['attested']),analysis_worker.snapshot(a)))
            expected=app.correct_line(lines[0],a.store,context_vocab=expected_context,decisions=a.decisions,
                input_method='kana',context_vec=a.context_vec,dict_index=a.dict_index)
            self.assertEqual(value['result'],expected)
            self.assertEqual(value['result']['corrected'],lines[0])
        finally:
            worker.close()
        self.assertFalse(worker.process.is_alive())

    def test_unit_rebuild_preserves_results_without_correction(self):
        from unittest.mock import patch
        import app
        a=initial();runtime=analysis_worker.Runtime();runtime.set_state(analysis_worker.snapshot(a))
        result=app.correct_line('寒ぃ日だ。',a.store,dict_index=a.dict_index,decisions=a.decisions)
        with patch.object(app,'correct_line',side_effect=AssertionError('Cache restore reran correction')):
            value=runtime.execute(dict(kind='units',result=result,lines=['寒ぃ日だ。']))
        self.assertIs(value['result'],result)
        self.assertTrue(value['corrected_units'][1])


class AsyncIdentityTests(unittest.TestCase):
    def test_old_a_b_a_result_is_never_applied(self):
        a=SimpleNamespace(settings={'input_method':'kana'},_work_epoch=1)
        work=analysis_work_app.token(a)
        a._analyze_work=work;a._analyze_dependencies=analysis_worker.state_key(a)
        a._analyze_todo=[0];a._analyze_pos=0;a._prev_lines=['元の文'];a.line_results=[{'original':'元の文'}]
        a._correction_worker=Mock();a._correction_worker.poll.return_value={'result':{'corrected':'古い答え'}}
        a._work_epoch+=2  # A→B→A, same string, different generation.
        analysis_async.line_step(a,1)
        self.assertEqual(a.line_results,[{'original':'元の文'}])
        a._correction_worker.poll.assert_not_called()

    def test_changed_dependencies_restart_plan(self):
        a=SimpleNamespace(settings={'input_method':'kana'},_work_epoch=1,_analyze=Mock())
        a._analyze_work=analysis_work_app.token(a);a._analyze_dependencies=analysis_worker.state_key(a)
        a._analysis_state_revision=1
        analysis_async.line_step(a,1)
        a._analyze.assert_called_once()

if __name__=='__main__':unittest.main()