# -*- coding: utf-8 -*-
"""Exact source context supplies only readings at attested word boundaries."""
import unittest
import morphology
from unittest.mock import patch,MagicMock
import ime_inverse_gate as I
import contextual_repair as R

class SourceContextIMEContractTests(unittest.TestCase):
    def slice(self,matched=True,start=1,end=3):
        source='前誤字後'
        morph=('まえすきにんあと',((0,1,0,2,100,3),(1,3,2,6,100,3),(3,4,6,8,100,3)))
        cache={('morph',source):morph,('first_match',source):matched}
        token=I._CORRECTION_CACHE.set(cache)
        try:
            with patch('ime_language.JapaneseIME') as provider:
                result=I.exact_context_reading(source,start,end)
                provider.return_value.__enter__.return_value.reverse_words.assert_not_called()
                return result
        finally:I._CORRECTION_CACHE.reset(token)

    def test_exact_whole_context_supplies_local_small_kana_reading(self):
        self.assertEqual(self.slice(),('すきにん',((0,2,'すきにん','ime_context_word'),)))

    def test_unmatched_whole_context_supplies_no_reading(self):
        self.assertIsNone(self.slice(matched=False))

    def test_inside_word_boundary_cannot_guess_a_partial_reading(self):
        self.assertIsNone(self.slice(start=2))

    def test_context_roundtrip_does_not_erase_attested_dictionary_readings(self):
        source='原文を誤字しました'
        target=R.RepairTarget(source,3,5,0,len(source),(('誤','字',3,5),),True,'しました')
        native=lambda text: [('誤字','名詞:一般','じしょ',3,5,True,'')] if text==source else [('誤字','名詞:一般','じしょ',0,2,True,'')]
        with patch('analysis_work.occurrence_readings',return_value=()), \
                patch('kanji_guess.ime_readings_for',return_value=[]), \
                patch('inflected_lexicon.dictionary_readings',return_value=('じしょ',)), \
                patch('kanji_guess.reading_combos_with_evidence',return_value=[]), \
                patch('ime_language.JapaneseIME') as source_ime, \
                patch('ime_native_reading.source_roundtrips',return_value=()), \
                patch.object(I,'exact_context_reading',return_value=('すきにん',((0,2,'すきにん','ime_context_word'),))):
            source_ime.return_value.__enter__.return_value.available=False
            rows=R.reading_evidence(target,native,None)
        self.assertEqual({r.text for r in rows},{'すきにん','じしょ'})
        self.assertEqual(R._reading_strength(R.Reading('すきにん','ime_context_roundtrip',0))[0],
                         R._reading_strength(R.Reading('じしょ','token_sequence',0))[0])

    def test_duplicate_native_reading_keeps_its_existing_candidate_evidence(self):
        context=R.Reading('きろくまして','ime_context_roundtrip',0)
        native=R.Reading('きろくまして','contextual_token_sequence',0,
                         ((0,2,'きろく','analyzed_word'),(2,5,'まして','literal_kana')))
        self.assertTrue(R.needs_ime_context_projection(context))
        merged=R.merge_readings((context,native))[0]
        # Known component words retain argument evidence, not completion
        # of the whole malformed IME phrase or its candidate spelling route.
        self.assertTrue(R.needs_ime_context_projection(merged))
        self.assertFalse(R.needs_source_argument_proof(merged))
        guessed=R.Reading('きろくまして','token_sequence',0,
                          ((0,2,'きろく','character_guess'),(2,5,'まして','literal_kana')))
        self.assertTrue(R.needs_ime_context_projection(R.merge_readings((context,guessed))[0]))
        self.assertTrue(R.needs_source_argument_proof(R.merge_readings((context,guessed))[0]))

    def test_context_query_never_uses_other_columns(self):
        context='原文を誤字しました';source='入力の説明\t'+context+'\t右端の正解'
        lo=source.index(context);start=lo+3;end=start+2
        t=R.RepairTarget(source,start,end,lo,lo+len(context),(('誤','字',start,end),),True,'しました')
        with patch('analysis_work.occurrence_readings',return_value=()), \
                patch('kanji_guess.ime_readings_for',return_value=[]), \
                patch('ime_language.JapaneseIME') as live, \
                patch.object(I,'exact_context_reading',return_value=('すきにん',((0,2,'すきにん','ime_context_word'),))) as query:
            live.return_value.__enter__.return_value.available=False
            rows=R.reading_evidence(t,lambda text:[],None)
        query.assert_called_once_with(context,3,5)
        self.assertEqual(rows[0].source,'ime_context_roundtrip')

    def test_first_roundtrip_retains_independent_native_reading(self):
        source='誤字';target=R.RepairTarget(source,0,2,0,2,(('IME逆読み','異様',0,2),),True,'')
        native=lambda text:[('誤字','名詞:一般','じしょ',0,2,True,'')]
        token=I._CORRECTION_CACHE.set({('phonetic',source):'すきにん',('first_match',source):True})
        try:
            with patch('analysis_work.occurrence_readings',return_value=()), \
                 patch('kanji_guess.ime_readings_for',return_value=[]), \
                 patch('inflected_lexicon.dictionary_readings',return_value=('じしょ',)), \
                 patch('kanji_guess.reading_combos_with_evidence',return_value=[]) as guesses:
                rows=R.reading_evidence(target,native,None)
            self.assertEqual({r.text for r in rows},{'すきにん','じしょ'})
            guesses.assert_not_called()
        finally:I._CORRECTION_CACHE.reset(token)

    @unittest.skipUnless(morphology.HAS_JANOME,'native word boundaries')
    def test_actual_whole_commit_can_attest_an_independent_native_word(self):
        from analysis_work import Document,current_input,occurrence_readings
        source='書くこと蚊あります';doc=Document('test',source)
        self.assertTrue(doc.remember(0,len(source),source,'かくことかあります'))
        with current_input(source,doc.occurrences):
            self.assertEqual(occurrence_readings(source,4,5),('か',))
            self.assertEqual(occurrence_readings(source,0,1),())
            self.assertEqual(occurrence_readings('別の本文',0,1),())
        wrong=Document('test',source);wrong.remember(0,len(source),source,'よむことかあります')
        with current_input(source,wrong.occurrences):
            self.assertEqual(occurrence_readings(source,4,5),())

    @unittest.skipUnless(morphology.HAS_JANOME,'native word boundaries')
    def test_observed_question_key_does_not_override_a_correct_written_case(self):
        from analysis_work import Document,current_input
        from particle_frames import nominalized_existential_case_frames
        source='書くことがあります';doc=Document('test',source)
        doc.remember(0,len(source),source,'かくことかあります')
        with current_input(source,doc.occurrences):
            self.assertEqual(nominalized_existential_case_frames(source),())

    @unittest.skipUnless(morphology.HAS_JANOME,'native source and candidate proof')
    def test_observed_whole_commit_uses_argument_meaning_without_marking_normal_text(self):
        import app
        from analysis_work import Document
        from tests_analysis_async import initial
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('native Japanese IME unavailable')
        state=initial();revision=state.store.revision()
        cases=(('海上を読奥して','かいじょうをよおくして','会場を予約して'),
               ('会場を予約しました。','かいじょうをよやくしました。','会場を予約しました。'),
               ('海上を航行しました。','かいじょうをこうこうしました。','海上を航行しました。'))
        for source,reading,expected in cases:
            with self.subTest(source=source):
                doc=Document('synthetic',source)
                # IMM readings exclude punctuation when committing words.
                face=source.rstrip('。');rd=reading.rstrip('。')
                self.assertTrue(doc.remember(0,len(face),face,rd))
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,
                    occurrence_readings=doc.occurrences)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
        self.assertEqual(state.store.revision(),revision)

    @unittest.skipUnless(morphology.HAS_JANOME,'native candidate ranking')
    def test_joint_rank_keeps_common_context_and_native_usage_evidence(self):
        import app
        from tests_analysis_async import initial
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('native Japanese IME unavailable')
        state=initial();revision=state.store.revision()
        cases=(('有線して補正','優先して補正'),
               ('行けいません。','行けてません。'),
               ('必要な部分だけを点刷してください。','必要な部分だけを印刷してください。'),
               ('必要な部分だけを位寸刷してください。','必要な部分だけを印刷してください。'),
               ('結果を切ろまして資料を閉じます。','結果を記録して資料を閉じます。'),
               ('尻わょうを整理してください。','資料を整理してください。'),
               ('音楽を聴けまして感動しました。','音楽を聴けまして感動しました。'))
        for source,expected in cases:
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
        self.assertEqual(state.store.revision(),revision)

    def test_weak_character_path_shares_argument_proof_without_an_ime_route(self):
        weak=R.Reading('きろく','contextual_token_sequence',0,
                       ((0,2,'きろく','unrecognized_ime_sequence'),))
        native=R.Reading('きろく','token_sequence',0,((0,2,'きろく','dictionary_word'),))
        self.assertTrue(R.needs_source_argument_proof(weak))
        for rows in ((weak,native),(native,weak)):
            self.assertFalse(R.needs_source_argument_proof(R.merge_readings(rows)[0]))
        self.assertFalse(R.needs_source_argument_proof(R.Reading('きろく','current_ime_occurrence',0)))


    @unittest.skipUnless(morphology.HAS_JANOME,'native IME word forms')
    def test_ime_colloquial_head_respects_native_tail_and_other_errors(self):
        import app
        from tests_analysis_async import initial
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('native Japanese IME unavailable')
        state=initial();revision=state.store.revision()
        normal=('ググってから確認します。','てんぱっても落ち着きます。',
                'ググりますので待ってください。','ググってから書類を作成しました。')
        unresolved=('ググっます。','てんぱっで落ち着きます。',
                    'てんぱっても落ち着きまぇ。','ググってから資料乳力します。')
        def analyze(source):
            return app.correct_line(source,state.store,input_method='kana',
                dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
        for source in normal:
            with self.subTest(source=source):
                result=analyze(source)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans'])
        for source in unresolved:
            with self.subTest(source=source):
                result=analyze(source)
                self.assertEqual(result['corrected'],source)
                self.assertTrue(result['odd_spans'])
        first=analyze(normal[0])
        analyze('メモってから確認します。')
        self.assertEqual(analyze(normal[0])['odd_spans'],first['odd_spans'])
        self.assertEqual(state.store.revision(),revision)

    @unittest.skipUnless(morphology.HAS_JANOME,'native IME word offsets')
    def test_medial_colloquial_word_uses_only_its_original_wdd_range(self):
        import app,corrector
        from tests_analysis_async import initial
        from ime_colloquial import source_tokenizer
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('native Japanese IME unavailable')
        state=initial();revision=state.store.revision()
        analyze=lambda source:app.correct_line(source,state.store,input_method='kana',
            dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
        for source in ('資料をググってから確認します。','私はググってから確認します。',
                       '私がてんぱっても落ち着きます。','後でググります。',
                       '「ググってから確認します。」'):
            with self.subTest(source=source):
                result=analyze(source)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans'])
        later='資料をググってから資料乳力します。'
        result=analyze(later)
        self.assertEqual(result['corrected'],later)
        self.assertTrue(result['odd_spans'])
        self.assertTrue(all(start>=9 for start,end in result['odd_spans']))
        fn=corrector.make_tokenizer(state.store)
        fake=lambda text: []
        fake.analysis_backend='mock'
        self.assertIs(source_tokenizer('ググってから確認します。',fake),fake)
        self.assertIs(source_tokenizer('😀ググってから確認します。',fn),fn)
        with patch('ime_language.JapaneseIME',side_effect=OSError):
            self.assertIs(source_tokenizer('資料をググってから確認します。',fn),fn)
        self.assertIs(source_tokenizer('ググってから確認します。	右列',fn),fn)
        self.assertEqual(state.store.revision(),revision)

    @unittest.skipUnless(morphology.HAS_JANOME,'independent native IME words')
    def test_repeated_colloquial_words_keep_their_own_source_proof(self):
        import app,corrector
        from tests_analysis_async import initial
        from ime_colloquial import source_tokenizer
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('native Japanese IME unavailable')
        state=initial();revision=state.store.revision()
        normal=('ググってからググります。',
                '資料をググって、もう一度ググります。',
                'てんぱってもググります。',
                'てんぱってもてんぱらずに確認します。')
        for source in normal:
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans'])
        mixed='ググって資料乳力してからググります。'
        result=app.correct_line(mixed,state.store,input_method='kana',
            dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],mixed)
        self.assertTrue(result['odd_spans'])
        fn=corrector.make_tokenizer(state.store)
        for malformed in ('ググってもググっで確認します。',
                          'ググりますググります。',
                          'てんぱりますググります。'):
            with self.subTest(malformed=malformed):
                self.assertIs(source_tokenizer(malformed,fn),fn)
        self.assertEqual(state.store.revision(),revision)

    @unittest.skipUnless(morphology.HAS_JANOME,'public lexical lemma with IME source range')
    def test_seed_attested_colloquial_lemma_preserves_original_inflection(self):
        import app,corrector
        from tests_analysis_async import initial
        from ime_colloquial import source_tokenizer
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('native Japanese IME unavailable')
        state=initial();revision=state.store.revision()
        fn=corrector.make_tokenizer(state.store)
        for source in ('メモります。','バグります。','メモりました。',
                       'バグらない。','メモってから確認します。',
                       'メモる資料','メモりますので確認します。'):
            with self.subTest(source=source):
                self.assertIsNot(source_tokenizer(source,fn),fn)
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans'])
        for malformed in ('資料ります。','メモっます。','メモらます。',
                          'メモろます。','バグっで確認します。',
                          'メモるを調べます。',
                          'オチります。','カケります。','ハゲります。',
                          'メモります猫','メモりました資料','メモるです'):
            with self.subTest(malformed=malformed):
                self.assertIs(source_tokenizer(malformed,fn),fn)
        scoped=source_tokenizer('メモります。',fn)
        self.assertEqual(scoped('目盛ります。'),fn('目盛ります。'))
        with patch('seed_japanese.is_unit',return_value=None):
            self.assertIs(source_tokenizer('メモります。',fn),fn)
        self.assertEqual(state.store.revision(),revision)

    @unittest.skipUnless(morphology.HAS_JANOME,'native IME relative clause')
    def test_native_plain_relative_is_not_reopened_by_inverse_ime(self):
        import app
        from tests_analysis_async import initial
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('native Japanese IME unavailable')
        state=initial()
        for source in ('取る手段','取る辞書'):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result['odd_spans'])

    @unittest.skipUnless(morphology.HAS_JANOME,'native kana correction')
    def test_reported_kana_typo_does_not_invent_small_ya_shift(self):
        import app,kana_layout
        from tests_analysis_async import initial
        self.assertEqual(kana_layout.kana_key_distance('に','ゃ'),kana_layout.FAR)
        state=initial()
        for source,expected in (('すきにん','確認'),('すきにん。','確認。')):
            result=app.correct_line(source,state.store,input_method='kana',
                dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result['odd_spans'])

if __name__=='__main__':unittest.main()