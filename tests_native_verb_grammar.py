# -*- coding: utf-8 -*-
"""Kana explanations must not invent a known verb's inflectional family."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
from unittest.mock import patch
import morphology as M
import pos_grammar as P


@unittest.skipUnless(M.dictionary_inflections('起きる'),'requires native dictionary')
class NativeVerbGrammarTests(unittest.TestCase):
    def test_kahen_causative_and_passive_source_keeps_complete_forms(self):
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for text in ('こさせます。','こさせました。','こさせない。',
                     'こさせなかった。','こさせられる。','こさせられました。',
                     'こられます。','こられました。','こさせた。'):
            with self.subTest(normal=text):
                result=app.correct_line(text,a.store,input_method='kana',
                    dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])
        for text in ('こさせう。','こさせますです。','こさせましたねこ。'):
            with self.subTest(invalid=text):
                result=app.correct_line(text,a.store,input_method='kana',
                    dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertTrue(result.get('odd_spans'))
        self.assertEqual(a.store.revision(),revision)

    def test_actual_ichidan_and_godan_forms_and_homographs(self):
        for text in ('おきます','おくります','あびます','のびます','たべます',
                     'かえります','かえます','きります','きます','くります',
                     'きました','おきれます','おきられます','おきよう'):
            self.assertTrue(P.explain_kana_run(text,before_kanji=False,bare_head=True),text)
        for text in ('おきります','あびります','のびります'):
            self.assertFalse(P.explain_kana_run(text,before_kanji=False,bare_head=True),text)

    def test_native_potential_meaning_keeps_the_same_godan_origin(self):
        import semantic_roles as S
        for surface,form,reading,origin,yomi in (
                ('ひらけ','連用形','ひらけ','ひらく','ひらく'),
                ('読め','連用形','よめ','読む','よむ'),
                ('書ける','基本形','かける','書く','かく')):
            with self.subTest(surface=surface):
                self.assertIn((origin,yomi),M.native_potential_origins(surface,form,reading))
                self.assertTrue(S.native_verb_roles(surface,form,reading) & S.predicate_roles(origin))
        self.assertIn('text',S.native_verb_roles('ひらけ','連用形','ひらけ',tail='ます'))
        self.assertFalse(S.native_verb_roles('ひらけ','連用形','ひらけ',tail='かった'))
        self.assertFalse(M.native_potential_origins('食べ','連用形','たべ'))
        self.assertFalse(M.native_potential_origins('読め','未然形','よみ'))
        self.assertFalse(M.native_potential_origins('ぷねれ','連用形','ぷねれ'))

    def test_page_potential_uses_positive_object_roles(self):
        import app,reading_segments as R
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for text in ('もくてきのぺーじをひらけます','じしょをひらけます',
                     'ほんをよめます','てがみをかけます'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result['odd_spans'],text)
        for text in ('りんごをよめます','てがみをのめます','ぺーじをひらけきます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        self.assertEqual(a.store.revision(),revision)

    def test_unknown_dictionary_evidence_does_not_reject_the_fallback(self):
        with patch.object(M,'dictionary_paradigms',return_value=None):
            self.assertTrue(P.explain_kana_run('おきります',before_kanji=False,bare_head=True))

    def test_long_reading_uses_the_same_actual_inflection(self):
        from tests_analysis_async import initial
        a=initial()
        for text in ('しりょうをせんせいにおきります',
                     'あさにつくったしりょうをせんせいにおきります'):
            self.assertTrue(P.odd_kana_spans(text,a.dict_index,a.store),text)
            normal=text.replace('おきります','おくります')
            self.assertEqual(P.odd_kana_spans(normal,a.dict_index,a.store),[],normal)

    def test_normal_and_quoted_source_is_not_rewritten(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('あさにおきます。','ふくをきます。','かみをきります。',
                     'じかんをかえます。','いえにかえります。',
                     'あしたははやくおきれます。',
                     '「おきります」という文字列を検索します。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertEqual(result.get('odd_spans'),[],text)


    def test_native_request_prefix_and_stem_keep_the_completed_boundary(self):
        import reading_segments as R
        for text in ('おきりください','およみください','おまちください','おかえりください',
                     'ごかくにんください','ごそうだんください','およみくださいね'):
            self.assertTrue(R.native_honorific_request_heads(text),text)
        for text in ('おきり','およみ','おまち','ごかくにん'):
            self.assertTrue(R.native_honorific_request_heads(text,allow_open=True),text)
            self.assertFalse(R.native_honorific_request_heads(text),text)
        for text in ('おきります','おきりました','おきるください','ごたべください',
                     'おぷねらください','ごしおりください','おきりです','おきりまし'):
            self.assertFalse(R.native_honorific_request_heads(text,allow_open=True),text)

    def test_request_meaning_and_open_source_do_not_certify_a_candidate(self):
        import reading_segments as R
        self.assertTrue(R.completed_native_reading_clause('しりょうをおよみください',require_object_fit=True))
        self.assertTrue(R.completed_native_reading_clause('しりょうをごかくにんください',require_object_fit=True))
        for text in ('しりょうをおよみ','しりょうをおのみください','みずをおよみください'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        self.assertTrue(R.intact_native_reading('しりょうをおよみ'))
        self.assertFalse(R.native_object_predicate_proof('しりょうをおよみ',5,('資料',)))

    def test_honorific_source_and_typing_fragments_have_no_false_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('しりょうをおきり','しりょうをおきりください。','しりょうをおよみください。',
                     'しりょうをごかくにんください。','せんせいにしりょうをおきり',
                     '資料をお切りください。','おまちください。','おまちくださいませ。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertEqual(result.get('odd_spans'),[],text)

    def test_reported_input_preserves_text_and_anomalies_outside_the_quote(self):
        from tests_analysis_async import initial
        import app
        a=initial()
        source='「おきります」を入力しました。先生に資料をおきります。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertTrue(result['corrected'].startswith('「おきります」を入力しました。'))
        self.assertFalse(any(start<6 and 1<end for start,end in result.get('odd_spans',[])))
        # The rest of the line is neither masked nor cleared by the report.
        if result['corrected'].endswith('先生に資料をおきります。'):
            self.assertTrue(any(start>=source.index('先生') for start,end in result.get('odd_spans',[])))
        else:
            self.assertTrue(result['corrected'].endswith('先生に資料を送ります。'))



    def test_finite_content_verb_uses_the_same_proof_at_the_reading_entry(self):
        import reading_segments as R
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('かききる','かききった','よみえる','よみうる','かきつづける','ほしていく'):
            self.assertTrue(R.completed_native_verb_reading(text,allow_nonpolite=True,finite_only=True),text)
            self.assertTrue(R.completed_native_reading(text),text)
            result=app.correct_line(text+'。',a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text+'。')
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('かくつづける','ほせいく','ほんます','ぷねらきる','たべま'):
            self.assertFalse(R.completed_native_verb_reading(text,allow_nonpolite=True,finite_only=True),text)
        self.assertTrue(R.completed_native_verb_reading('たべて',allow_nonpolite=True))
        self.assertFalse(R.completed_native_verb_reading('たべて',allow_nonpolite=True,finite_only=True))
        self.assertFalse(R.completed_native_verb_reading('たべて',allow_nonpolite=True,require_roles=False,finite_only=True))
        self.assertFalse(R.completed_native_verb_reading('およみください',allow_nonpolite=True,require_roles=False,finite_only=True))

    def test_negative_auxiliary_uses_actual_irrealis_alternatives(self):
        import reading_segments as R
        import oddness as O
        import contextual_repair as X
        for text in ('かかない','たべない','しない','せぬ','しらん','ありません',
                     'かききらない','よみえない','のみきらない','たべませんでした'):
            self.assertTrue(R.completed_native_verb_reading(text,True,require_roles=False,finite_only=True),text)
            self.assertTrue(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)
        for text in ('たべるない','かきない','かききるない','へんんん'):
            self.assertFalse(R.completed_native_verb_reading(text,True,require_roles=False,finite_only=True),text)
            self.assertFalse(X._productive_predicate(text,M.tokenize(text)[0].surface),text)
        for text in ('たかくない','きれいではない','するんです','あいひん'):
            parts=M.tokenize(text)
            legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
            self.assertFalse(any(O.negative_aux_mismatch(a,b) for a,b in zip(legacy,legacy[1:])),text)

    def test_exact_native_verb_reading_owns_its_whole_unchanged_head(self):
        import reading_segments as R
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('のみきる','のみきった','のみきるよ','よみえた','よみえたね',
                     'よみうる','のみつづける'):
            self.assertTrue(R.completed_native_verb_reading(text,True,finite_only=True),text)
            result=app.correct_line(text+'。',a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text+'。')
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('のむきる','よむえた','のまきる','ぷねらきる','のみきるです',
                     'のみつづけるです','よみえましたです','ほせいく'):
            self.assertFalse(R.completed_native_verb_reading(text,True,finite_only=True),text)
            self.assertFalse(R.completed_native_verb_reading(text,True,require_roles=False,finite_only=True),text)

    def test_finite_bound_verb_keeps_particles_but_not_an_unlicensed_copula(self):
        import reading_segments as R
        import contextual_repair as X
        import oddness as O
        for text in ('かききるよ','かききったね','はしりきるぞ','よみえるよ',
                     'かきつづけるね','ほしていくよ'):
            self.assertTrue(R.completed_native_verb_reading(text,True,finite_only=True),text)
            self.assertTrue(R.intact_native_reading(text),text)
        for text in ('かききるです','たべるだ','かくつづけるよ','ほせいくね'):
            self.assertFalse(R.completed_native_verb_reading(text,True,finite_only=True),text)
            self.assertFalse(X._productive_predicate(text,M.tokenize(text)[0].surface),text)
        for text in ('たべるなら','たべるだろう','うれしいです','たべないです',
                     'たべるのです','たべるんです'):
            self.assertTrue(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)
        for text in ('たべるです','かききるです','たべるだ','たべましたです','たべませんでしたです'):
            self.assertFalse(O.changed_auxiliary_chain_allowed(text,0,len(text)),text)
        self.assertTrue(R.native_linked_reading_boundaries('たべませんでしつれいしました',allow_unclassified=True))
        self.assertFalse(R.native_linked_reading_boundaries('たべませんでしたです',allow_unclassified=True))
        import app
        from tests_analysis_async import initial
        a=initial();source='「たべるです」と入力しました。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],source)
        self.assertFalse(result.get('odd_spans'))

    def test_final_auxiliary_check_keeps_independent_word_boundaries(self):
        import oddness as O
        pairs=(('昨日せれぐしょんを見ました。','昨日せれくしょんを見ました。'),
               ('すげるつぉを確認しました。','すけるつぉを確認しました。'),
               ('昨日すれかっらしを見ました。','昨日すれっからしを見ました。'),
               ('かせいいちを確認しました。','せかいいちを確認しました。'),
               ('こかしん','こかいん'),
               ('昨日のせれぐしょんを見ました。','昨日のせれくしょんを見ました。'))
        from difflib import SequenceMatcher
        for source,changed in pairs:
            edits=[(c,d) for tag,a,b,c,d in SequenceMatcher(None,source,changed,autojunk=False).get_opcodes() if tag!='equal']
            for start,end in ((0,len(changed)),(min(a for a,b in edits),max(b for a,b in edits))):
                self.assertTrue(O.changed_auxiliary_chain_allowed(changed,start,end,original=source),changed)
        for source,changed in (('ほせまし','ほせいく'),
                               ('たへますです','たべますです'),
                               ('せれぐしょんます','せれくしょんます'),
                               ('昨日せれくししょんを見ました。','昨日せれくししょきを見ました。'),
                               ('昨日れせくしょんを見ました。','昨日れせくしょきを見ました。')):
            self.assertFalse(O.changed_auxiliary_chain_allowed(changed,0,len(changed),original=source),changed)

    def test_native_bound_verb_keeps_the_same_preceding_inflection(self):
        import contextual_repair as X
        import reading_segments as R
        import corrector as C
        from tests_analysis_async import initial
        for text in ('ほせいく','ほせいくし','書く続けます'):
            parts=M.tokenize(text)
            self.assertFalse(X._productive_predicate(text,parts[0].surface),text)
        for text in ('干していく','干していきます','書き続けます','書き切る'):
            parts=M.tokenize(text)
            self.assertTrue(X._productive_predicate(text,parts[0].surface),text)
        self.assertFalse(R.completed_native_source_sequence('ゆうせんしてほせいくし'))
        a=initial();source='ゆうせんしてほせいまし'
        candidate,reason=C._check_replacement(source,(0,len(source),'ゆうせんしてほせいくし','かな入力'),
            a.store,C.make_tokenizer(a.store),a.dict_index,a.decisions)
        self.assertIsNone(candidate)

    def test_incomplete_polite_evidence_does_not_borrow_lexical_masu(self):
        import reading_segments as R
        # 増す is an independent verb; this completed adverb reading does
        # not prove a polite auxiliary immediately after the particle も.
        self.assertTrue(R.native_adverbial_predicate_reading('こうもますまい',allow_open_tail=False))
        self.assertFalse(R.native_incomplete_polite_reading('こうもま'))
        for text in ('こうもふえま','たべま','ごじをしゅうせいしま',
                     'にゅうりょくちゅうもほぞんしま','きじつにしりょうをほぞんしま',
                     'ほぞんしたらばほんをよみま'):
            self.assertTrue(R.native_incomplete_polite_reading(text),text)

    def test_in_progress_polite_prefix_is_not_an_anomaly_or_completed_candidate(self):
        import reading_segments as R
        import app
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('たべま','たべまし','たべませ','たべましょ','たべれま',
                     'まてがいをたべま','りんごをたべま','ぶんしょうをかきま',
                     'ごじをしゅうせいしま','くすりぶくろをはこびま'):
            self.assertTrue(R.native_incomplete_polite_reading(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'),text)
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('たべます','たべました','たべません','たべまい','たべん','くるま',
                     'たべまうす','たべるま','ぷねらま','せいどをたべま'):
            self.assertFalse(R.native_incomplete_polite_reading(text),text)
        source='まてがいをたべま'
        for replacement in ((5,8,'たべん','かな入力'),(5,8,'たべます','かな入力')):
            candidate,reason=C._check_replacement(source,replacement,a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNone(candidate)
            self.assertEqual(reason,'incomplete_original_source')
        self.assertTrue(R.preserves_native_incomplete_source(source+'。誤字',source+'。文字'))

    def test_unfinished_polite_clause_keeps_its_proved_adverb_or_conditional(self):
        import reading_segments as R
        import app
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('しめきりまでにしりょうをほぞんしま',
                     'きじつにしりょうをほぞんしま',
                     'あしたまでにしりょうをほぞんしま',
                     'にゅうりょくちゅうもほぞんしま',
                     'ほんをよんだらほぞんしま','ほぞんしたらばねま'):
            self.assertTrue(R.native_incomplete_polite_reading(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            # Same-reading spelling remains allowed in an unfinished source;
            # its auxiliary may not be completed or otherwise rewritten.
            spelling=text.replace('しりょう','資料').replace('きじつ','期日')
            self.assertIn(result['corrected'],(text,spelling))
            self.assertFalse(result.get('odd_spans'),text)
            self.assertFalse(R.completed_native_source_sequence(text),text)
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
            proposal=(len(text)-1,len(text),'ます','かな入力')
            candidate,reason=C._check_replacement(text,proposal,a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNone(candidate)
            self.assertEqual(reason,'incomplete_original_source')
        for text in ('ぷねらまでにしりょうをほぞんしま','しめきりまでにぷねらをほぞんしま',
                     'ほんをよみたらほぞんしま','ほんをよんだらぷねらま',
                     'あしたまでにしりょうをほぞんしまうす'):
            self.assertFalse(R.native_incomplete_polite_reading(text),text)

    def test_incomplete_proof_belongs_to_original_clause_not_nominal_cut(self):
        import reading_segments as R
        import corrector as C
        import app
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        source='しゃしまをならべておおきさをかえます。'
        self.assertTrue(R.native_incomplete_polite_reading('しゃしま'))
        self.assertFalse(R.intact_native_reading('しゃしま',allow_incomplete=False))
        token=C._CORRECTION_SOURCE.set(source)
        try:self.assertFalse(C._chunk_is_intact('しゃしま',tokenize))
        finally:C._CORRECTION_SOURCE.reset(token)
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        # ma -> n is an excluded diagonal in the user's revised layout.
        import kana_layout as K
        self.assertGreater(K._base_distance('ま','ん'),1.0)
        self.assertEqual(result['corrected'],source)
        self.assertTrue(result.get('odd_spans'))
        for source in ('たべま','りんごをたべま。','「まてがいをたべま」と書きます。'):
            token=C._CORRECTION_SOURCE.set(source)
            try:self.assertTrue(C._chunk_is_intact('たべま',tokenize),source)
            finally:C._CORRECTION_SOURCE.reset(token)
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], source)
            self.assertFalse(result.get('odd_spans'),source)

    def test_original_punctuation_owns_anomaly_before_target_cut(self):
        import app,corrector as C,contextual_repair as X,oddness
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        source='しりょうをほぞんしたます。'
        original=oddness.is_odd_run(source,tokenize,with_spans=True,
            store=a.store,dict_index=a.dict_index,complete_line=True)
        self.assertTrue(any(start==9 and end==12 for _,_,start,end in original))
        targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
        self.assertTrue(any(t.text=='ほぞんしたます' and t.boundary_kind=='kana_predicate'
                            and t.start==5 and t.context_start==0 for t in targets))
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, 'しりょうを保存してます。')
        self.assertFalse(result.get('odd_spans'))

    def test_original_anomaly_coordinates_survive_preceding_sentence_and_quotes(self):
        import app,corrector as C,contextual_repair as X
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        prefix='本を読みます。'
        source=prefix+'しりょうをほぞんしたます。'
        targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
        self.assertTrue(any(t.text=='ほぞんしたます' and t.start==len(prefix)+5
                            and t.context_start==len(prefix) for t in targets))
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, prefix+'しりょうを保存してます。')
        self.assertFalse(result.get('odd_spans'))
        for source in ('まうす。','あらいまうす。','しりょうをほぞんしてます。',
                       '「しりょうをほぞんしたます。」を入力します。','りんごをたべま。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], source)
            self.assertFalse(result.get('odd_spans'),source)

    def test_source_final_nominal_case_is_unfinished_not_a_candidate(self):
        import reading_segments as R
        for text in ('にゅうりょくちゅうに','さぎょうちゅうは','にゅうりょくちゅうも',
                     'ほんを','がめんが','きょうから','くすりぶくろへ','入力中に','画面は'):
            self.assertTrue(R.native_incomplete_nominal_reading(text),text)
            self.assertTrue(R.intact_native_reading(text),text)
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('ぷねらを','まとがいを','しゃしまを','にゅうりょくちゅうにぷねら',
                     'にゅうりょくちゅうにほんをよみるます'):
            self.assertFalse(R.native_incomplete_nominal_reading(text),text)

    def test_incomplete_case_protection_comes_from_the_actual_clause_end(self):
        import reading_segments as R
        self.assertEqual(R.native_incomplete_source_ranges('にゅうりょくちゅうに。誤字'),((0,10),))
        self.assertTrue(R.preserves_native_incomplete_source('にゅうりょくちゅうに。誤字',
                                                            'にゅうりょくちゅうに。文字'))
        self.assertFalse(R.preserves_native_incomplete_source('にゅうりょくちゅうに','入力中止'))
        self.assertFalse(R.native_incomplete_source_ranges('にゅうりょくちゅうにほんをよみるます。'))
        self.assertFalse(R.native_incomplete_source_ranges('しゃしまをならべておおきさをかえます。'))

    def test_application_keeps_open_nominal_case_body_and_mark_separate(self):
        import app,corrector
        from tests_analysis_async import initial
        a=initial();tokenize=corrector.make_tokenizer(a.store)
        for text in ('にゅうりょくちゅうに','さぎょうちゅうは','にゅうりょくちゅうも','ほんを'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'),text)
        accepted,reason=corrector._check_replacement('にゅうりょくちゅうに',(0,10,'入力中止','かな入力'),
            a.store,tokenize,a.dict_index,a.decisions)
        self.assertIsNone(accepted)
        self.assertEqual(reason,'incomplete_original_source')

    def test_original_object_exposes_swallowed_predicate_with_same_grammar(self):
        import oddness as O,corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='あしたまでにぶんしょうをなおすします。'
        for strict in (False,True):
            reasons={}
            rows=O.is_odd_run(text,tokenize,with_spans=True,store=a.store,
                dict_index=a.dict_index,skip_join=strict,complete_line=True,reading_reasons_out=reasons)
            self.assertIn(('なおす','し',12,16),rows)
            self.assertIn((12,16),reasons)
        for text in ('あしたまでにぶんしょうをなおします。','あしたまでにぶんしょうをなおす。',
                     'あしたまでにぶんしょうをぷねら。','あしたまでにぷねらをなおすします。',
                     'あしたまでにぶんしょうをなおしま','にゅうりょくちゅうに'):
            self.assertFalse(O._source_object_predicate_spans(text,tokenize(text),
                tokenize,a.store,a.dict_index),text)

    def test_open_native_nominal_alternative_does_not_require_an_unwritten_predicate(self):
        import reading_segments as R,app
        from tests_analysis_async import initial
        a=initial()
        for text in ('くすりぶくろが','くすりぶくろから'):
            self.assertTrue(R.native_incomplete_nominal_reading(text),text)
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('くすりぶくろからぷねら','しゃしまを','ぷねらが','たべるに'):
            self.assertFalse(R.native_incomplete_nominal_reading(text),text)

    def test_native_imperative_closes_only_its_attested_verb_chain(self):
        import reading_segments as R,contextual_repair as X,app
        from tests_analysis_async import initial
        a=initial()
        for text in ('かききれ','のみきれ','かききれよ','のみきれよ'):
            self.assertTrue(R.completed_native_verb_reading(text,True,False,True),text)
            result=app.correct_line(text+'。',a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text+'。')
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('よめ','かけ','よみきれ'):
            self.assertTrue(X._native_imperative_completion(M.tokenize(text)),text)
        for text in ('たべるきれ','かききれです','のみきれです','よみかけ','かきぷね',
                     'ぷねらきれ','かききれなら','かききれまうす'):
            self.assertFalse(R.completed_native_verb_reading(text,True,False,True),text)

    def test_perfective_auxiliary_shares_continuative_after_an_auxiliary(self):
        import reading_segments as R,contextual_repair as X,oddness as O
        for text in ('病みきつ','止みきつ','読みきつ'):
            parts=M.tokenize(text)
            self.assertFalse(X._productive_predicate(text,parts[0].surface),text)
            self.assertFalse(R._completed_native_verb_surface(text,True,False,True),text)
        for text in ('書きつ','読みつ','書かれつ'):
            parts=M.tokenize(text)
            self.assertTrue(X._productive_predicate(text,parts[0].surface),text)
        parts=M.tokenize('病みきつ')
        a,b=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
              t.start,t.end,t.has_reading,t.infl_form) for t in parts[-2:]]
        self.assertTrue(O.completed_tsu_aux_mismatch(a,b))
        self.assertFalse(O.completed_tsu_source_mismatch(a,b))

    def test_dependent_amount_noun_is_not_a_free_command_modifier(self):
        import reading_segments as R,semantic_roles as S,app
        from tests_analysis_async import initial
        self.assertTrue(S.adverbial_reading_needs_host('分','ぶん'))
        self.assertFalse(R._native_adverbial_faces('ぶん'))
        self.assertFalse(R.native_adverbial_predicate_reading('ぶんしょえ'))
        self.assertTrue(R.native_nominal_phrase_faces('ぶん'))
        for text in ('じゅうぶん','はんぶん'):
            self.assertTrue(R._native_adverbial_faces(text),text)
        a=initial()
        for text in ('ぶん','ぶんをかきます。','じゅうぶんよみます。','半分食べます。',
                     '働いた分だけ休みます。','三分待ちます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)

    def test_attested_historical_auxiliary_is_source_only_and_uses_actual_continuative(self):
        import reading_segments as R,corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('ほんをよみまうす','ほんをよみまをす','しりょうをほぞんしまうす',
                     'にゅうりょくまちなのでほんをよみまうす','とうちゃくまちだからほんをよみまうす'):
            with self.subTest(text=text):
                self.assertTrue(R.intact_native_reading(text))
                self.assertIn((0,len(text)),R.attested_historical_auxiliary_ranges(text))
                self.assertFalse(R.native_incomplete_polite_reading(text))
                self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True))
                ending='まをす' if text.endswith('まをす') else 'まうす'
                changed=text[:-len(ending)]+'ます'
                self.assertFalse(R.preserves_attested_historical_auxiliary(text,changed))
                candidate,reason=C._check_replacement(text,(len(text)-3,len(text),'ます','かな入力'),
                    a.store,tokenize,a.dict_index,a.decisions)
                self.assertIsNone(candidate)
                self.assertEqual(reason,'nonadjacent_original_key_deletion'
                    if ending=='まをす' else 'attested_historical_auxiliary')
        for text in ('たべるまうす','よむまうす','ほんまうす','ぷねらまうす',
                     'まうす','ごまをすります','たべてまうす','ほんをよみまうすを使う'):
            self.assertFalse(R.attested_historical_auxiliary_ranges(text),text)
        source='ほんをたべまうす'
        self.assertFalse(R.intact_native_reading(source))
        self.assertEqual(R.attested_historical_auxiliary_ranges(source),((5,8),))
        self.assertFalse(R.preserves_attested_historical_auxiliary(source,'ほんをたべます'))
        self.assertTrue(R.preserves_attested_historical_auxiliary(source,'りんごをたべまうす'))
        self.assertTrue(R.preserves_attested_historical_auxiliary('ほんをよみまうす。誤字','ほんをよみまうす。文字'))

    def test_historical_auxiliary_keeps_normal_source_and_independent_typo(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source in ('ほんをよみまうす。','ほんをよみまをす。','ばねをかいまうす。',
                       'とうちゃくまちだからほんをよみまうす。',
                       '承認待ちだから資料をほぞんしまうす。','買いまうす。','ごまをすります。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], source)
            self.assertFalse(result.get('odd_spans'),source)
        source='ほんをよみまうす。しりょうをほぞんしたます。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, 'ほんをよみまうす。しりょうを保存してます。')
        self.assertFalse(result.get('odd_spans'))


    def test_known_te_auxiliary_requires_its_actual_connection(self):
        import contextual_repair as Q,reading_segments as R
        for source,head in (('仕事せいきます','仕事'),('読めきます','読め'),('書けきます','書け')):
            self.assertFalse(Q._productive_predicate(source,head),source)
        for source,head in (('仕事してきます','仕事'),('読んできました','読ん'),('書いていきます','書い')):
            self.assertTrue(Q._productive_predicate(source,head),source)
        self.assertFalse(R.completed_native_reading_clause('しごとせいきます',require_object_fit=True))

    def test_original_kana_lemma_keeps_its_object_and_polite_tail(self):
        import app,corrector as C,contextual_repair as Q
        from tests_analysis_async import initial
        a=initial();tok=C.make_tokenizer(a.store);revision=a.store.revision()
        for source,expected in (('このほんだけをよむます。','この本だけを読めます。'),
                                ('しりょうだけをよむます。','資料だけを読めます。')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result['odd_spans'])
            for target in Q.targets_for_line(source,tok,a.store,a.dict_index):
                if target.text=='よむます':
                    self.assertFalse(Q.validate(target,'分けます',C,tok,a.store,a.dict_index,a.decisions,
                        expected_reading='わけます')[0])
        self.assertEqual(a.store.revision(),revision)

if __name__=='__main__':unittest.main()


class NativeNegativeSourceTests(unittest.TestCase):
    def legacy(self,text):
        return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]

    def test_source_negative_reuses_exact_native_irrealis_attachment(self):
        import oddness as O
        for text in ('保存したない','読んだない','読むない','食べますない'):
            parts=self.legacy(text)
            self.assertTrue(any(O.negative_aux_mismatch(a,b,include_adjective=True) for a,b in zip(parts,parts[1:])),text)
        for text in ('保存しない','読まない','来ない','ありません','食べませんでした',
                     '保存したくない','保存したくなかった','読まなくない','らしくない','学生でない',
                     '高くない','きれいではない','仕方ない','知らない','読んだ本はない','読むな'):
            parts=self.legacy(text)
            self.assertFalse(any(O.negative_aux_mismatch(a,b,include_adjective=True) for a,b in zip(parts,parts[1:])),text)

    def test_written_malformed_negative_uses_validated_repair_or_source_mark(self):
        import app
        from tests_analysis_async import initial
        for source,corrected in (('資料を保存したない','資料を保存したいな'),('本を読んだない','本を読んだない')):
            with self.subTest(source=source):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],corrected,source)
                self.assertEqual(bool(r['odd_spans']),source==corrected,source)
                self.assertEqual(r['analysis_status'],'complete',source)
        # The first correction swaps only the final adjacent な/い. Native
        # predicate morphology is checked independently of the engine output.
        import contextual_repair as X
        self.assertTrue(X._productive_predicate('保存したいな','保存'))

    def test_native_negative_source_keeps_valid_text_and_literal_reporting(self):
        import app
        from tests_analysis_async import initial
        for source in ('資料を保存しない','資料を保存したくない','資料を保存したくなかった',
                       '本を読まない','本を読んだ人は来ない','読んだ本はない','高くない',
                       '綺麗ではない','学生でない','「資料を保存したない」という入力例'):
            with self.subTest(source=source):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],source,source)
                self.assertFalse(r['odd_spans'],source)



class DefiniteNegativeSourceTests(unittest.TestCase):
    def test_nasal_and_nominalized_parses_do_not_declare_source_negative_error(self):
        import oddness as O
        for text in ('着こんで','読むんで','読まんで','知らん','書かぬ'):
            parts=M.tokenize(text)
            legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
            self.assertFalse(any(O.negative_source_mismatch(a,b) for a,b in zip(legacy,legacy[1:])),text)

    def test_real_frozen_regression_cannot_turn_verb_into_unrelated_person_noun(self):
        import app
        from tests_analysis_async import initial
        a=initial();source='荷物を着こんでから休みます。'
        r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        # This existing unresolved input may eventually reach 運ぶ. Do not
        # freeze today's unchanged text as permanent source protection.
        self.assertNotEqual(r['corrected'],'荷物を娘んでから休みます。')
        self.assertEqual(r['analysis_status'],'complete')

