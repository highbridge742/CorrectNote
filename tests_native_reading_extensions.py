# -*- coding: utf-8 -*-
"""Native auxiliary boundaries and resultative clauses share source evidence."""
from tests_spelling_reference import assert_reviewed_result_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
from unittest.mock import patch
import morphology as M,oddness as O,reading_segments as R,semantic_roles as S
try:
    from janome.tokenizer import Tokenizer
    NATIVE=True
except ImportError:
    NATIVE=False

class NativeReadingExtensionsTests(unittest.TestCase):
    def tearDown(self):
        O._native_derivational_reading_boundary.cache_clear()
        S.resultative_adjective_roles.cache_clear()
        S._resultative_adjective_readings.cache_clear()
        R.native_resultative_reading.cache_clear()
        S._short_role_noun_readings.cache_clear()

    def test_same_kana_can_supply_a_different_native_irrealis_boundary(self):
        entries={
            'し':(('動詞,自立,*,*','サ変・スル','未然形','する','し'),),
            'られ':(('動詞,接尾,*,*','一段','連用形','られる','られ'),),
            'しら':(('動詞,自立,*,*','五段・ラ行','未然形','しる','しら'),),
            'れ':(('動詞,接尾,*,*','一段','連用形','れる','れ'),)}
        a=('し','動詞:自立','し',3,4,True,'未然形')
        b=('られ','動詞:接尾','られ',4,6,True,'連用形')
        with patch.object(M,'dictionary_paradigms',side_effect=lambda text:entries.get(text,())):
            self.assertFalse(O.passive_aux_mismatch(a,b))
            self.assertTrue(O._native_derivational_reading_boundary('しられ',1,'passive'))

    def test_alternative_requires_exact_reading_and_a_modern_verb_paradigm(self):
        right=(('動詞,接尾,*,*','一段','連用形','れる','れ'),)
        for left in ((('名詞,一般,*,*','*','*','しら','しら'),),
                     (('動詞,自立,*,*','五段・ラ行','未然形','しる','しり'),),
                     (('動詞,自立,*,*','文語・ラ行変格','未然形','しる','しら'),),()):
            O._native_derivational_reading_boundary.cache_clear()
            entries={'しら':left,'れ':right}
            with patch.object(M,'dictionary_paradigms',side_effect=lambda text:entries.get(text,())):
                self.assertFalse(O._native_derivational_reading_boundary('しられ',1,'passive'))
        self.assertFalse(O._native_derivational_reading_boundary('知りられ',2,'passive'))

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_resultative_requires_object_property_and_a_complete_suru(self):
        for text,faces in [('ちいさくします',('音',)),('あかるくして',('部屋',)),
                           ('みじかくした',('説明',)),('つめたくします',('水',))]:
            with self.subTest(text=text):self.assertTrue(R.native_resultative_reading(text,faces,True))
        for text,faces in [('ちいさくし',('音',)),('ちいさくでした',('音',)),
                           ('つめたくします',('意味',)),('おいしくします',('音',)),
                           ('ちいさくします',('未分類の対象',)),('ちいさくしられます',('音',))]:
            with self.subTest(text=text):self.assertFalse(R.native_resultative_reading(text,faces,True))

    def test_short_noun_requires_an_existing_role_and_exact_native_one_kana_reading(self):
        entries={
            '絵':(('名詞,一般,*,*','*','絵','え'),),
            '手':(('名詞,一般,*,*','*','手','て'),),
            '偽':(('名詞,一般,*,*','*','偽','にせ'),),
            '姓':(('名詞,固有名詞,人名,姓','*','姓','せ'),),
            '尾':(('名詞,接尾,一般,*','*','尾','び'),),
            '違':(('名詞,一般,*,*','*','別','い'),),
            '未分類':(('名詞,一般,*,*','*','未分類','む'),)}
        with patch.object(S,'NOUN_ROLES',{key:() for key in entries if key!='未分類'}), \
             patch.object(M,'dictionary_inflections',side_effect=lambda text:entries.get(text,())):
            self.assertEqual(S.short_role_noun_faces('え'),('絵',))
            self.assertEqual(S.short_role_noun_faces('て'),('手',))
            for reading in ('にせ','せ','び','い','む',''):
                self.assertEqual(S.short_role_noun_faces(reading),())

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_short_noun_proof_stays_inside_a_complete_case_frame(self):
        # 48-AMP: exact one-kana nouns share the index; complete case proof remains below.
        self.assertIn('絵',R._native_nominal_reading_faces('え'))
        for text in ('えをかきます。','てをあらいます。','えにかきます。',
                     'やまをえにかきます。','まどのそとにみえるやまをえにかきます。'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,require_nominal=True,require_object_fit=True))
        for text in ('えをのみます。','えがはしります。','えにたべます。',
                     'えかきます。','えをかき','えと','え'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_clause(text,require_nominal=True,require_object_fit=True))

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_complete_source_links_and_adjacent_repairs_keep_kana(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        cases=[
            ('えをかいてからともだちにみせます。','えをかいてからともだちにみせます。'),
            ('やまにのぼってそらをみあげます。','やまにのぼってそらをみあげます。'),
            ('「ちいちく」は入力例です。へやをあかりるくします。','「ちいちく」は入力例です。へやをあかるくします。'),
            ('まどのそとにみえるやまをえにかきます。','まどのそとにみえるやまをえにかきます。'),
            ('ひろくしられているほんです。','ひろくしられているほんです。'),
            ('おとをちいさくしてからどうがをさいせいします。','おとをちいさくしてからどうがをさいせいします。'),
            ('へやをあかりるくします。','へやをあかるくします。'),
            ('おとをちいさきくします。','おとをちいさくします。'),
            ('せつめいをみじえかくします。','せつめいをみじかくします。')]
        for text,expected in cases:
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,context_vec=a.context_vec,
                                        decisions=a.decisions,input_method='kana')
                assert_reviewed_result_spelling(self, result, expected)
                self.assertEqual(result.get('odd_spans'),[])

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_modified_noun_retains_all_exact_native_reading_faces(self):
        self.assertIn('茶',R.native_nominal_phrase_faces('あついおちゃ'))
        self.assertIn('ちゃ',R.native_nominal_phrase_faces('あついおちゃ'))
        self.assertTrue(R.intact_native_reading('あついおちゃをさましてからのみます。'))
        # Kana evidence does not reinterpret an already written homophone.
        self.assertEqual(R.native_nominal_phrase_faces('あついお茶'),())
        for text in ('このはこ','そのはこ','あのひと','このは','そのは','あのは'):
            with self.subTest(text=text):self.assertTrue(R.native_adnominal_reading_parts(text))
        # The one-kana reading は is the attested ordinary noun 葉.
        # A matching particle spelling does not erase its nominal reading.
        self.assertIn('葉',R.native_nominal_phrase_faces('そのは'))
        self.assertEqual(R.native_adnominal_reading_parts('そのは')[1][4],'は')
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('このはをみます。','そのはをみます。','あのはをみます。'):
            result=app.correct_line(text,a.store,dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions,input_method='kana')
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('その','そのを','きのこ'):
            with self.subTest(text=text):self.assertFalse(R.native_adnominal_reading_parts(text))

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_receiving_auxiliary_supplies_the_agent_case(self):
        cases=[('はこん','連用タ接続','はこん','でもらいました','に'),
               ('よん','連用タ接続','よん','でもらいます','に'),
               ('なおし','連用形','なおし','ていただきます','から')]
        for args in cases:
            with self.subTest(args=args):self.assertEqual(S.native_benefactive_case_roles(*args),frozenset(('person',)))
        for text in ('ともだちににもつをはこんでもらいました',
                     'こどもにほんをよんでもらいます'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_clause(text,True,True,True))
        self.assertFalse(R.completed_native_reading_clause('ものにほんをよんでもらいます',True,True,True))

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_reflexive_manner_is_a_boundary_not_a_free_case_or_completed_tail(self):
        for text in ('じぶんで','じしんで','自分で','自身で'):
            self.assertTrue(R.native_reflexive_manner_prefix(text),text)
        for text in ('せんせいで','たにんで','みずで','じぶんに','じぶんの','ぷねらで'):
            self.assertFalse(R.native_reflexive_manner_prefix(text),text)
        for text in ('じぶんでためしてみます','じぶんでえほんをよみます',
                     'せつめいをきいてからじぶんでためしてみます'):
            self.assertTrue(R.intact_native_reading(text),text)
        for text in ('じぶんでしりょうをおきります','じぶんでよみますです',
                     'じぶんでありた','じぶんでぷねらます'):
            self.assertFalse(R.native_adverbial_predicate_reading(text,allow_open_tail=False),text)

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_native_te_auxiliaries_share_tail_and_argument_proof(self):
        import contextual_repair as C
        import morphology as M
        for face,reading,tail in (('よん','よん','であげます'),('読ん','よん','であげます'),
                ('なおし','なおし','てくれます'),('はこん','はこん','でいただきました'),
                ('読ん','よん','であげてくれます'),('書い','かい','てあげません')):
            forms=M.dictionary_inflections(face)
            self.assertTrue(C._allows_grammatical_tail(forms,tail,reading,face),(face,tail))
            self.assertTrue(C._productive_predicate(face+tail,face),(face,tail))
        for face,reading,tail in (('読ん','よん','てあげます'),('読む','よむ','であげます'),
                ('書い','かい','であげます'),('読ん','よん','でぷねらます'),
                ('読ん','よん','であげります'),('読ん','よん','であげますです')):
            forms=M.dictionary_inflections(face)
            self.assertFalse(C._allows_grammatical_tail(forms,tail,reading,face)
                and C._productive_predicate(face+tail,face),(face,tail))
        for tail in ('であげます','でくれます','でやります','でさしあげます'):
            self.assertEqual(S.native_benefactive_case_roles('よん','連用タ接続','よん',tail,'に'),frozenset(('person',)),tail)
            self.assertFalse(S.native_benefactive_case_roles('よん','連用タ接続','よん',tail,'から'),tail)
        for text in ('こどもにえほんをよんであげます','ともだちにほんをよんでくれます',
                     'ともだちにほんをよんでもらいます'):
            self.assertTrue(R.completed_native_reading_clause(text,True,True,True),text)
        for text in ('みずにえほんをよんであげます','こどもにみずをよんであげます'):
            self.assertFalse(R.completed_native_reading_clause(text,True,True,True),text)

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_receiving_role_requires_exact_attachment_and_a_completed_auxiliary(self):
        cases=[('よん','連用タ接続','よん','てもらいます','に'),
               ('よむ','基本形','よむ','もらいます','に'),
               ('はこん','連用タ接続','はこん','でもらい','に'),
               ('はこん','連用タ接続','はこん','で','に'),
               ('はこん','連用タ接続','はこん','でもらいました','と'),
               ('はこん','連用形','はこん','でもらいました','に'),
               ('はこん','連用タ接続','はこび','でもらいました','に')]
        for args in cases:
            with self.subTest(args=args):self.assertFalse(S.native_benefactive_case_roles(*args))

    @unittest.skipUnless(NATIVE,'requires the native dictionary')
    def test_source_argument_extensions_preserve_text_and_restore_adjacent_keys(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        cases=[('あついおちゃをさましてからのみます。','あついおちゃをさましてからのみます。'),
               ('ともだちににもつをはこんでもらいました。','ともだちににもつをはこんでもらいました。'),
               ('あついおちゃをはましてからのみます。','あついおちゃをさましてからのみます。'),
               ('あついおちゃをさのましてからのみます。','あついおちゃをさましてからのみます。')]
        for text,expected in cases:
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,context_vec=None,
                                        decisions=a.decisions,input_method='kana')
                assert_reviewed_result_spelling(self, result, expected)
                self.assertEqual(result.get('odd_spans'),[])

    def test_inflection_tail_keeps_the_original_cross_boundary_anomaly(self):
        import morphology as M
        if not M.HAS_JANOME:self.skipTest('requires native Janome dictionary')
        import app
        from tests_analysis_async import initial
        a=initial()
        # The shorter tail has a different adverb/predicate parse; it cannot
        # erase the original preceding verb and its established anomaly.
        self.assertTrue(R.intact_native_reading('ゆうになる',allow_incomplete=False))
        self.assertFalse(R.intact_native_reading('分かるゆうになる',allow_incomplete=False))
        for source,expected in (('分かるゆうになる','分かるようになる'),
                                ('見つかるよわぅになる','見つかるようになる'),
                                ('読むようらなる','読むようになる')):
            result=app.correct_line(source,a.store,dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions,input_method='kana')
            self.assertIn(result['corrected'],expected if isinstance(expected,tuple) else (expected,),source)
            self.assertFalse(result.get('odd_spans'),source)
        tok=__import__('corrector').make_tokenizer(a.store)
        for source in ('やみづきがありました。','あんじんしました。',
                       'せつめをよみなおしてりかいしました。'):
            self.assertFalse(__import__('corrector')._inflection_tail_fixes(
                source,tok,'kana',a.dict_index,a.store),source)
        for source,expected in (('みちがこんでいたためすこしおくれ゛ました。','みちがこんでいたためすこしおくれ゛ました。'),
                ('せつめをよみなおしてりかいしました。','説明をよみなおしてりかいしました。')):
            result=app.correct_line(source,a.store,dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions,input_method='kana')
            self.assertIn(result['corrected'],expected if isinstance(expected,tuple) else (expected,),source)
            self.assertFalse(result.get('diagnostic_cycle'),source)
        result=app.correct_line('やみづきがありました。',a.store,dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions,input_method='kana')
        self.assertFalse(result.get('diagnostic_cycle'))
        for source in ('分かるようになる','読むようになる','分かる夕になる','見るはずだった'):
            result=app.correct_line(source,a.store,dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions,input_method='kana')
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'),source)


    def test_nonadjacent_voicing_is_not_an_intrusion(self):
        from contextual_repair import key_repairs
        for source,unsupported in (('あんじん','あんしん'),('けいじき','けいしき'),('ぴっぐるす','ぴっくるす')):
            self.assertFalse(any(r.reading==unsupported for r in key_repairs(source)),source)
        # This does not claim those intended words were successfully fixed.
        # Other surviving readings may be ambiguous without more context.

if __name__=='__main__':unittest.main()
