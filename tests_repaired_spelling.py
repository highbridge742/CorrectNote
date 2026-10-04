# -*- coding: utf-8 -*-
"""Accepted reading repairs gain native written forms, without wider rewriting."""
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
from unittest.mock import patch

class RepairedSpellingFrameTests(unittest.TestCase):
    def test_trimmed_edit_recovers_only_the_surviving_lexical_frame(self):
        import corrector as E
        from repaired_spelling import retained_frames
        source='しゅうありょうが'
        legacy=dict(corrected='しゅうりょうが',original_spans=[(0,7)],spans=[(0,6)])
        self.assertEqual(retained_frames(source,legacy,[(3,4,'')],[],E),[(0,7,'しゅうりょう','')])
        self.assertEqual(retained_frames(source,legacy,[],[],E),[])
        self.assertEqual(retained_frames(source,legacy,[(3,4,'')],[(0,3,'別')],E),[(3,4,'','')])
        self.assertEqual(retained_frames(source,legacy,[(3,4,'い')],[],E),[(3,4,'い','')])

class RepairedSpellingNativeTests(unittest.TestCase):
    def test_reported_counter_and_columns_reach_worker_display_without_answers(self):
        import analysis_worker as W
        from tests_analysis_async import initial
        from last_choice import set_active
        self.assertEqual([ord(c) for c in '4ば゜位'],[0x34,0x3070,0x309c,0x4f4d])
        cases=(('4ば゜位','4倍'),('4ば゜位\t','4倍\t'),
               ('平ん仮名\tひらんがな ⇒ ','平仮名\t平仮名 ⇒ '),
               ('資料を\tひらんがな ⇒ ','資料を\t平仮名 ⇒ '),
               ('補正付き','補正付き'),
               ('他のアプリを使っている最中でも、ちょっとしたメモを補正付きで書ける',
                '他のアプリを使っている最中でも、ちょっとしたメモを補正付きで書ける'))
        try:
            for source,expected in cases:
                with self.subTest(source=source):
                    a=initial();runtime=W.Runtime();runtime.set_state(W.snapshot(a))
                    prepared=runtime.prepare([source])
                    value=runtime.execute(dict(kind='line',line=source,input_method='kana',
                        context=prepared['context'],attested=prepared['attested']))
                    self.assertEqual(value['result']['corrected'],expected)
                    self.assertEqual(value['corrected_units'][0],expected)
                    self.assertEqual(value['result']['odd_spans'],[])
                    self.assertEqual(value['result']['analysis_status'],'complete')
        finally:set_active(None)

    def test_rare_negative_case_evidence_stays_in_its_source_column(self):
        import reading_segments as R
        for text in ('平ん仮名\tひらんがな ⇒ ','資料を\tひらんがな ⇒ ',
                     '資料を ⇒ ひらんがな','資料を\nひらんがな'):
            with self.subTest(text=text):
                self.assertEqual(R.native_negative_auxiliary_chains(text),())
        for text in ('屁をひらん','知らんがな','資料を読まん'):
            with self.subTest(text=text):
                self.assertTrue(R.native_negative_auxiliary_chains(text))

    def test_numeric_counter_proof_does_not_release_unrelated_adverbs(self):
        import morphology as M
        self.assertTrue(M.preserves_native_adverbial_word('4ば゜位','4倍'))
        for source,changed in (('4ば゜位','4貝'),('4ば゜位','5倍'),
                               ('今は洗います','居間は洗います'),
                               ('4ば゜位\t今は洗います','4倍\t居間は洗います')):
            with self.subTest(source=source,changed=changed):
                self.assertFalse(M.preserves_native_adverbial_word(source,changed))

    def test_attached_noun_has_source_proof_in_shared_final_check(self):
        import corrector as E,reading_segments as R
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=E.make_tokenizer(a.store)
        try:
            for source in ('補正付き','メモを補正付きで書ける',
                           '他のアプリを使っている最中でも、ちょっとしたメモを補正付きで書ける'):
                start=source.index('補正')
                for end,face in ((start+2,'方正'),(start+4,'方正付き')):
                    with self.subTest(source=source,face=face):
                        self.assertEqual(E._check_replacement(source,(start,end,face,'かな入力'),
                            a.store,tok,a.dict_index,a.decisions),(None,'completed_written_derivation'))
            for word in ('朝食付き','保証付き','説明付き'):
                with self.subTest(word=word):
                    self.assertEqual(R.native_written_derived_nominal_faces(word),(word,))
            for word in ('ぷね付き','朝食付きます','読ん付き'):
                with self.subTest(word=word):
                    self.assertEqual(R.native_written_derived_nominal_faces(word),())
        finally:set_active(None)

    def test_attached_noun_keeps_independent_neighbor_repair(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        try:
            for source,expected in (('朝食付き\tいれります。','朝食付き\t入れます。'),
                                   ('保証付き','保証付き'),('説明付き','説明付き'),
                                   ('4位','4位'),('8ぷん','8ぷん'),('3ぼん','3ぼん'),
                                   ('4パイ','4パイ'),('4π','4π'),('4パン','4パン'),
                                   ('「4ぱい」と書く','「4ぱい」と書く')):
                with self.subTest(source=source):
                    r=app.correct_line(source,a.store,input_method='kana',
                        dict_index=a.dict_index,decisions=a.decisions)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r['odd_spans'],[])
        finally:set_active(None)

    def test_initial_states_finish_accepted_repairs_and_original_readings(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        from last_choice import set_active
        for phase in ('seed','fresh'):
            a=initial();a.context_vec=None
            if phase=='fresh':import_from_janome(a.store)
            revision=a.store.revision()
            def run(text):return app.correct_line(text,a.store,dict_index=a.dict_index,decisions=a.decisions)
            try:
                for text,expected in (
                    # 48-APK: preserve valid 用船; the open field stays literal.
                    ('ようせんしてほせい','優先して補正'),
                    ('のひっています','残っています'),
                    ('しゅうありょうが','終了が'),
                    ('4ぱ゛位','4倍'),
                    ('ようせんしてほせい\t⇒ゆうせんしてほせい\t優先して補正','優先して補正\t⇒優先して補正\t優先して補正'),
                    ('のひっています\t⇒のこっています\t残っています','残っています\t⇒残っています\t残っています'),
                    ('しゅうありょうが\t⇒しゅうりょうが\t終了が','終了が\t⇒終了が\t終了が'),
                    ('4ぱ゛位\t4ばい\t4倍','4倍\t4倍\t4倍'),
                    ('子どもに絵本を読んであうげます。','子どもに絵本を読んであげます。'),
                    ('こどもにえほんをよんであうげます。','子供に絵本を読んであげます。'),
                    ('いんすと゛る','いんすどる'),
                    ('しゅう゛い','しゅゔい'),
                    ('か゛そる','がそる'),
                ):
                    with self.subTest(phase=phase,text=text):
                        result=run(text)
                        self.assertIn(result['corrected'],expected if isinstance(expected,tuple) else (expected,))
                        self.assertEqual(result.get('odd_spans'),[])
                        self.assertNotIn('_repair_surfaces',result)
                # 48-APC: original intended kana also receive normal spelling.
                for text,expected in (('ゆうせんしてほせい','優先して補正'),('のこっています','残っています'),
                                      ('しゅうりょうが','終了が'),('4ばい','4倍'),
                                      ('もんじにゅうりょく','もんじ入力'),('差し込み゛手、','差し込みで、'),('さしこみ゛て、','差し込みで、')):
                    with self.subTest(phase=phase,spelling=text):assert_reviewed_source_spelling(self, run(text+'\t')['corrected'], expected+'\t')
                for text in ('したあと','残っています','終了が','4倍','故人の遺した作品',
                             '保存してください','「のひっています」と入力します。','してみて','ほせいがきかない','今日は😀晴れです。'):
                    with self.subTest(phase=phase,keep=text):assert_reviewed_source_spelling(self, run(text)['corrected'], text)
                a.decisions.protect('のひっています')
                self.assertEqual(run('のひっています')['corrected'],'のひっています')
                self.assertEqual(a.store.revision(),revision)
            finally:set_active(None)

    def test_case_particle_without_a_host_does_not_spell_the_verb(self):
        import app
        from tests_analysis_async import initial
        state=initial();state.context_vec=None
        for source,expected in (('か゛そる','がそる'),):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,
                    context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))

    def test_unfinished_legacy_fragments_do_not_acquire_partial_kanji(self):
        import corrector as E
        from repaired_spelling import finish
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=E.make_tokenizer(a.store)
        cases=(('「とうけけつ」と書きました。','「とうけつけ」と書きました。',(2,6,'うけつけ','')),
               ('じっょうがありました。','じしょうがありました。',(0,3,'じしょ','')),
               ('昨日かふぶんを見ました。','昨日かたぶんを見ました。',(3,6,'たぶん','')),
               ('じっょしうがありました。','じしょしうがありました。',(0,3,'じしょ','')))
        try:
            for source,approved,frame in cases:
                with self.subTest(source=source):
                    result=finish(source,dict(corrected=approved,_repair_surfaces=[frame]),a.store,tok,a.dict_index,a.decisions)
                    self.assertEqual(result['corrected'],approved)
        finally:set_active(None)

    def test_explicit_kana_choice_and_final_rejection_are_preserved(self):
        import corrector as E
        from repaired_spelling import finish
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=E.make_tokenizer(a.store)
        def result():return dict(corrected='ゆうせんしてほせい',_repair_surfaces=[(0,4,'ゆうせん','kana_action_note')])
        try:
            with patch('last_choice.surface_for_reading',return_value='ゆうせん'):
                self.assertEqual(finish('ようせんしてほせい',result(),a.store,tok,a.dict_index,a.decisions)['corrected'],'ゆうせんしてほせい')
            with patch.object(E,'_check_replacement',return_value=(None,'blocked')):
                self.assertEqual(finish('ようせんしてほせい',result(),a.store,tok,a.dict_index,a.decisions)['corrected'],'ゆうせんしてほせい')
        finally:set_active(None)

if __name__=='__main__':unittest.main()
