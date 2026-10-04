# -*- coding: utf-8 -*-
"""Existing semantic units need their own native readings, including compounds."""
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('日光'),'requires native dictionary')
class ClassifiedNominalReadingTests(unittest.TestCase):
    def test_existing_general_words_share_exact_readings_without_new_entries(self):
        import general_words as G
        import reading_segments as R
        import oddness as O
        before={word:M.dictionary_inflections(word) for word in ('アイコン','クリップボード','綾鷹')}
        for face,reading in (('アイコン','あいこん'),('クリップボード','くりっぷぼーど'),
                             ('タップ','たっぷ'),('プレビュー','ぷれびゅー')):
            self.assertTrue(G.general_katakana_noun_reading(face,reading))
            self.assertTrue(R.native_common_noun_reading(face,reading))
            self.assertEqual(R.native_katakana_nominal_face(reading),face)
            self.assertIn(face,R.native_lexical_reading_faces(reading))
            self.assertTrue(R.intact_native_reading(reading),reading)
        for face,reading in (('アイコン','あいこ'),('綾鷹','あやたか'),
                             ('プネラ','ぷねら'),('アイコンます','あいこんます')):
            self.assertFalse(G.general_katakana_noun_reading(face,reading))
        self.assertEqual(before,{word:M.dictionary_inflections(word) for word in before})
        self.assertTrue(O.changed_auxiliary_chain_allowed('あいこん',0,4,original='あいこゃ'))
        self.assertFalse(R.completed_native_reading('あいこんます'))

    def test_sourced_unread_nouns_share_analysis_without_forging_native_entries(self):
        import general_words as G
        before={word:M.dictionary_inflections(word) for word in ('プロジェクション','ソリューション','和英','薬袋')}
        for word,reading in (('プロジェクション','ぷろじぇくしょん'),('ソリューション','そりゅーしょん')):
            parts=M.tokenize(word)
            self.assertEqual([(t.surface,t.reading,t.has_reading,t.pos) for t in parts],[(word,reading,True,'名詞')])
            self.assertTrue(G.sourced_common_noun_evidence(word,reading))
            self.assertTrue(R.native_common_noun_reading(word,reading))
            self.assertFalse(R.native_common_noun_reading(word,reading+'あ'))
            self.assertFalse(S.support(word,'食べる'))
        for word in ('プロジェクションプネラ','プネラソリューション'):
            parts=M.tokenize(word)
            self.assertTrue(any(not t.has_reading for t in parts))
            self.assertFalse(any(t.surface in ('プロジェクション','ソリューション') for t in parts))
        self.assertEqual(before,{word:M.dictionary_inflections(word) for word in before})
        self.assertTrue(any(t.reading=='かずひで' for t in M.tokenize('和英')))
        self.assertTrue(any(t.reading=='みない' for t in M.tokenize('薬袋')))

    def test_sourced_web_reading_is_an_ordinary_information_noun(self):
        import general_words as G
        import app
        from tests_analysis_async import initial
        self.assertTrue(G.sourced_common_noun_evidence('ウェブ','うぇぶ'))
        self.assertFalse(G.sourced_common_noun_evidence('ウェブ','うえぶ'))
        self.assertIn('ウェブ',R._native_nominal_reading_faces('うぇぶ'))
        self.assertFalse(R._native_nominal_reading_faces('うぇぶます'))
        self.assertTrue(S.support('ウェブ','見る'))
        self.assertFalse(S.support('ウェブ','食べる'))
        for text in ('うぇぶを食べる','うぇぶを見','うぇぶを食','うぇぶをしらゆほます'):
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)
        a=initial();revision=a.store.revision()
        for text,expected in (('うぇぶを見る。','ウェブを見る。'),
                              ('ウェブを見る。','ウェブを見る。'),
                              ('うぇぶをみます。','ウェブをみます。')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], expected)
            self.assertFalse(result['odd_spans'])
        self.assertEqual(a.store.revision(),revision)

    def test_multiple_external_readings_do_not_choose_an_unknown_parse(self):
        import general_words as G
        from unittest.mock import patch
        with patch.dict(G.SOURCES,{'fixture':'unit-test-only'}),patch.dict(G.SOURCED_COMMON_NOUNS,{'プネラ':(('ぷねら','fixture'),('ぷねろ','fixture'))}):
            self.assertTrue(any(not t.has_reading for t in M.tokenize('プネラ')))

    def test_exact_native_common_sense_survives_best_parse_proper_name(self):
        self.assertIn('直射日光',R._native_nominal_reading_faces('ちょくしゃにっこう'))
        self.assertTrue(R.native_common_noun_reading('直射日光','ちょくしゃにっこう'))
        self.assertFalse(R.native_common_noun_reading('直射日光','ちょくしゃひかり'))
        self.assertFalse(R.native_common_noun_reading('直射日光','ちょくしゃにこう'))
        self.assertNotIn('資料日光',R._native_nominal_reading_faces('しりょうにっこう'))
        self.assertNotIn('読んで日光',R._native_nominal_reading_faces('よんでにっこう'))

    def test_classified_single_nouns_share_the_existing_usage_index(self):
        from kango_tier import _explicit_reading_faces
        for word,reading in (('蓼','たで'),('筆','ふで'),('湿気','しっけ')):
            with self.subTest(word=word):
                self.assertIn(word,_explicit_reading_faces().get(reading,()))
                self.assertIn(word,R.native_nominal_phrase_faces(reading))

    def test_physical_plant_sense_does_not_invent_edibility_or_a_verb_role(self):
        for word in ('植物','草','葉','茎','根','枝','苗','蓼'):
            with self.subTest(word=word):
                self.assertTrue(S.support(word,'洗う'))
                self.assertTrue(S.support(word,'並べる'))
                self.assertFalse(S.support(word,'食べる'))
                self.assertFalse(S.support(word,'読む'))
        self.assertFalse(S.support('たでる','洗う'))

    def test_initial_application_keeps_real_alternative_nouns_and_compounds(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('たでをにほんあらいます。','はをにまいあらいます。',
                     'くきをさんぼんあらいます。','なえをならべます。',
                     'ちょくしゃにっこうをさけます。',
                     'ちょくしゃにっこうをさけてほかんします。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], text)
                self.assertEqual(result.get('odd_spans'),[])


    def test_sourced_common_readings_do_not_forge_native_dictionary_rows(self):
        from general_words import sourced_common_noun_evidence
        for word,reading in (('和英','わえい'),('薬袋','やくたい'),('薬袋','くすりぶくろ')):
            self.assertIn(word,R.native_nominal_phrase_faces(reading))
            self.assertTrue(R.native_common_noun_reading(word,reading))
            evidence=sourced_common_noun_evidence(word,reading)
            self.assertTrue(evidence and evidence[0]['source'] and evidence[0]['version'])
            self.assertFalse(any(row[-1]==reading for row in M.dictionary_inflections(word) or ()))
        self.assertFalse(sourced_common_noun_evidence('薬袋','みない'))
        self.assertFalse(sourced_common_noun_evidence('和英','かずひで'))
        self.assertFalse(sourced_common_noun_evidence('未登録の薬袋'))
        self.assertTrue(any(row[-1]=='かずひで' for row in M.dictionary_inflections('和英')))
        self.assertTrue(any(row[-1]=='みない' for row in M.dictionary_inflections('薬袋')))

    def test_sourced_nominals_share_scope_but_not_contents_or_inflected_endings(self):
        self.assertTrue(R._native_written_nominal_faces('和英辞典'))
        self.assertTrue(R._native_written_nominal_faces('薬袋'))
        self.assertFalse(R._native_written_nominal_faces('薬袋さん'))
        for text in ('わえいじてんをよみます','くすりぶくろをはこびます'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True))
        for text in ('わえいじてんをよみま','くすりぶくろをはこびますです',
                     'くすりぶくろをのみます','くすりぶくろをたべます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        self.assertFalse(S.support('薬袋','飲む'))
        self.assertFalse(S.support('薬袋','食べる'))

    def test_complete_bare_nominal_is_a_source_proof_not_a_predicate(self):
        import app
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('くすりぶくろ','りんごばこ','かみばこ','ふうけいのしゃしん'):
            self.assertTrue(R.intact_native_reading(text),text)
            self.assertTrue(C._chunk_is_intact(text,tokenize),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'),text)
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        # AMO: an unfinished polite prefix is source-only, not a completed candidate.
        self.assertTrue(R.intact_native_reading('くすりぶくろをはこびま'))
        self.assertFalse(R.completed_native_reading_clause('くすりぶくろをはこびま',require_object_fit=True))
        for text in ('くすりぶくろをはこびますです',
                     'くすりぶくろをのみます','ぬょぶくろ','せいどばこ','のくすりぶくろ'):
            self.assertFalse(R.intact_native_reading(text),text)

    def test_one_kana_common_nouns_keep_their_exact_reading_and_actual_case(self):
        for face,reading in (('絵','え'),('手','て'),('葉','は'),('根','ね'),('図','ず'),('戸','と')):
            with self.subTest(face=face):
                self.assertIn(face,R._classified_nominal_readings().get(reading,()))
                self.assertTrue(R.native_common_noun_reading(face,reading))
                self.assertIn(face,R.native_nominal_phrase_faces(reading))
        self.assertEqual(R.native_coordinated_nominal_parts('えとかみ'),('え','かみ'))
        self.assertTrue(R.completed_native_reading_clause('えをかきます',require_object_fit=True))
        self.assertFalse(R.completed_native_reading_clause('えをかきますです',require_object_fit=True))
        self.assertFalse(R.completed_native_reading_clause('えをたべます',require_object_fit=True))
        for reading in ('かずひで','みない'):
            self.assertFalse(R._classified_nominal_readings().get(reading,()))
        self.assertFalse(R.native_coordinated_nominal_parts('まとがい'))

if __name__=='__main__':unittest.main()
