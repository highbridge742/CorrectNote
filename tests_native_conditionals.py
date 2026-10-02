# -*- coding: utf-8 -*-
"""Unchanged conditional clauses share native inflection and nominal proof."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R


@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NativeConditionalTests(unittest.TestCase):
    def test_conditional_connection_requires_the_whole_unchanged_native_predicate(self):
        for text in ('ぶんしょうをなおしたら','りんごをたべたら','ほんをよんだら',
                     'ほぞんしたら','なおしたら','あめなら','がくせいなら',
                     'がくせいだったら','がくせいでしたら','ほんをよむなら',
                     'ほんをよんだなら','およいだなら','がくせいだったなら',
                     'ほんをよむよなら'):
            with self.subTest(text=text):
                self.assertTrue(R.completed_native_reading_link(text,allow_unclassified=True))
        for text in ('たら','なら','ぶんしょうをなおすたら','ほんをよみたら',
                     'ほんをよんたら','りんごをたべだら','ぷねらをたべたら',
                     'ほんをよむぞなら','ほんをよむぜなら','ほんをよむよねなら',
                     'ほぞんしますなら','あめだなら','ほんをよんだだなら'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_link(text,allow_unclassified=True))

    def test_relative_time_noun_keeps_its_attested_reading_before_conditional(self):
        # よ has the independently attested noun 夜. The original relative
        # clause may retain that noun; it is not forced into final-particle よ.
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ほんをよむよなら','ほんをよむひなら'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        # The relative clause already owns its object 本; an unrelated
        # following 絵 is not supplied with a second reading-object role.
        self.assertFalse(R.completed_native_reading_link('ほんをよむえなら',allow_unclassified=True))

    def test_finite_link_keeps_the_original_written_object_constraint(self):
        constraint=('しりょう',('資料',))
        for prefix in ('しりょうをほぞんした','しりょうをほぞんしました',
                       'しりょうをかくにんした'):
            for link in ('が','ので','から'):
                with self.subTest(prefix=prefix,link=link):
                    self.assertTrue(R.completed_native_reading_link(prefix+link,
                        require_nominal=True,nominal_constraint=constraint))
        self.assertTrue(R.completed_native_reading_link('しりょうをほぞんしてから',
            require_nominal=True,nominal_constraint=constraint))
        for text in ('しりょうをほぞんしてが','しりょうをほぞんしてので',
                     'しりょうをほぞんしが','しりょうをほぞんしので'):
            self.assertFalse(R.completed_native_reading_link(text),text)
            self.assertFalse(R.completed_native_reading_link(text,
                require_nominal=True,nominal_constraint=constraint),text)
        self.assertFalse(R.completed_native_reading_link('かんじゃをほぞんしたが',
            require_nominal=True,nominal_constraint=('かんじゃ',('患者',))))
        self.assertTrue(R.native_object_predicate_proof('資料を保存したが話しました',3,('資料',)))
        self.assertFalse(R.native_object_predicate_proof('資料を保存したが話ました',3,('資料',)))

    def test_optional_ba_belongs_to_the_attested_conditional(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ほぞんしたらば','ほんをよんだらば','がくせいならば'):
            self.assertTrue(R.completed_native_reading_link(text,allow_unclassified=True),text)
            self.assertIn((0,len(text)),R.native_context_ranges(text),text)
        for text in ('たらば','ならば','たらばがに','ほんをよみたらば','あめだならば'):
            self.assertFalse(R.completed_native_reading_link(text,allow_unclassified=True),text)
        for text in ('ほぞんしたらばねます。','ほんをよんだらばねます。',
                     'がくせいならばほんをよみます。','ほぞんしたらばばななをかいます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)

    def test_short_complete_clauses_and_adverbs_use_the_same_source_proof(self):
        for text in ('みたらねる','よんだらねる','あめならねる','みてねる',
                     'ぶんしょうをなおしたらほぞんします',
                     'あしたまでにぶんしょうをなおしたらほぞんします'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_source_sequence(text))
        for text in ('みたねる','たらねる','ほんをよみたらねる','みたらぷねら',
                     'ぷねらをなおしたらほぞんします'):
            with self.subTest(text=text):self.assertFalse(R.completed_native_source_sequence(text))

    def test_normal_conditionals_keep_literal_text_and_no_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ぶんしょうをなおしたらほぞんします。',
                     'あしたまでにぶんしょうをなおしたらほぞんします。',
                     'ほんをよんだらねます。','みたらねる。','あめならねる。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result.get('odd_spans'),text)


    def test_nominal_conditional_uses_the_same_whole_noun_as_its_copula(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for head in ('にゅうりょくまち','にゅうりょくちゅう','しゅっぱつまえ','へんじまち'):
            self.assertTrue(R.completed_native_nominal_predicate(head+'だ'),head)
            for ending in ('なら','ならば'):
                link=head+ending
                self.assertTrue(R.completed_native_reading_link(link,allow_unclassified=True),link)
                self.assertFalse(R.completed_native_nominal_predicate(link),link)
        for text in ('にゅうりょくまちならほんをよみます。',
                     'にゅうりょくまちならばほんをよみます。',
                     'にゅうりょくまちなのでしりょうをほぞんしま'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        for text in ('ぷねらなら','にゅうりょくまちだなら','にゅうりょくまちなだ'):
            self.assertFalse(R.completed_native_reading_link(text,allow_unclassified=True),text)


    def test_swallowed_conditional_uses_exact_native_form_and_the_whole_source_clause(self):
        constraint=('しりょう',('資料',))
        for text in ('しりょうをほぞんしたら','しりょうをほぞんしたらば',
                     'しりょうをほぞんするなら','しりょうをほぞんするならば',
                     'しりょうをかくにんしたなら','しりょうをかくにんしたならば'):
            self.assertTrue(R.completed_native_reading_link(text),text)
            self.assertTrue(R.completed_native_reading_link(text,
                require_nominal=True,nominal_constraint=constraint),text)
            self.assertTrue(R.completed_native_source_sequence(text+'れんらくします'),text)
        for text in ('しりょうをほぞんしてなら','しりょうをほぞんしてならば',
                     'しりょうをほぞんしますなら','しりょうをほぞんしら',
                     'しりょうをほぞんするたら','しりょうをほぞんしだら',
                     'ほんをよみたら','ほんをよみたらば','ぷねらをほぞんしたら',
                     'しりょうをぷねらしたら','しりょうをほぞんしたらばね',
                     'たらばがに','さよなら'):
            self.assertFalse(R.completed_native_reading_link(text),text)
        self.assertFalse(R.completed_native_reading_link('かんじゃをほぞんしたら',
            require_nominal=True,nominal_constraint=('かんじゃ',('患者',))))
        self.assertFalse(R.completed_native_reading_link('しりょうをほぞんしたら',
            require_nominal=True,nominal_constraint=('しりょう',('患者',))))

    def test_swallowed_conditionals_keep_source_and_clear_only_proved_normal_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('しりょうをほぞんしたられんらくします。',
                     'しりょうをほぞんしたらばれんらくします。',
                     'しりょうをほぞんするなられんらくします。',
                     'しりょうをほぞんするならばれんらくします。',
                     'しりょうをかくにんしたなられんらくします。',
                     'しりょうをほぞんしたら','しりょうをほぞんするなら'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)

    def test_proved_finite_action_and_adverb_clause_survive_unknown_native_parse(self):
        for text in ('にゅうりょくします','にゅうりょくしました',
                     'まだとちゅうです','ゆっくりにゅうりょくします',
                     'まだしりょうがあります'):
            self.assertTrue(R.completed_native_link_clause(text),text)
        for text in ('にゅうりょくして','にゅうりょくし','まだにゅうりょくして',
                     'ゆっくりにゅうりょくして','まだとちゅうで',
                     'しりょうをほぞんして'):
            self.assertFalse(R.completed_native_link_clause(text),text)
        for text in ('しりょうをほぞんしてが','しりょうをほぞんしてので'):
            self.assertFalse(R.completed_native_reading_link(text),text)
        self.assertTrue(R.completed_native_reading_sequence('おなじもじをつづけてにゅうりょくします'))
        self.assertTrue(R.completed_native_source_sequence('ぶんしょうをほぞんしましたがまだとちゅうです'))

    def test_independent_slips_and_normal_progress_clause_keep_existing_contracts(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (
                ('おなじもじをさづけてにゅうせょくします。','おなじもじをつづけてにゅうりょくします。'),
                ('おなじもじをつさづけてにゅうありょくします。','おなじもじをつづけてにゅうりょくします。'),
                ('ぶんしょうをほぞんしましたがまだとちゅうです。','ぶんしょうをほぞんしましたがまだとちゅうです。')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, expected)
            self.assertFalse(result.get('odd_spans'),text)

    def test_linked_unfinished_predicate_is_source_only(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('しりょうをほぞんしたられんらくし',
                     'しりょうをほぞんしたらばれんらくし',
                     'しりょうをほぞんするなられんらくし',
                     'しりょうをほぞんしたのでれんらくし',
                     'しりょうをほぞんしたらほんをよみ',
                     'しりょうをほぞんしたられんらくしてほぞんし'):
            with self.subTest(text=text):
                self.assertTrue(R.native_incomplete_linked_reading(text))
                self.assertTrue(R.intact_native_reading(text))
                self.assertFalse(R.native_linked_reading_boundaries(text))
                self.assertFalse(R.completed_native_reading_sequence(text))
                self.assertIn((0,len(text)),R.native_incomplete_source_ranges(text))
                self.assertFalse(R.preserves_native_incomplete_source(text,text+'ます'))
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result.get('odd_spans'))

    def test_open_link_does_not_certify_unknown_or_malformed_clauses(self):
        for text in ('しりょうをほぞんするたられんらくし',
                     'しりょうをほぞんしだられんらくし',
                     'しりょうをほぞんしてがれんらくし',
                     'かんじゃをほぞんしたられんらくし',
                     'ぷねらをほぞんしたられんらくし',
                     'しりょうをほぞんしたらぷねら',
                     'しりょうをほぞんしたらぷねらし',
                     'しりょうをほぞんしたられんらくすます',
                     'しりょうをほぞんしたらばね'):
            self.assertFalse(R.native_incomplete_linked_reading(text),text)
        self.assertFalse(R.completed_native_reading_clause('れんらくし',allow_nonpolite=True))
        self.assertTrue(R.completed_native_reading_clause('れんらくし',allow_nonpolite=True,
            allow_open_tail=True))

    def test_source_continuative_keeps_each_original_nominal_case(self):
        for left,right in (('ぶんしょうをにゅうりょくし','ないようをかくにんします'),
                           ('しりょうをほぞんし','ぺーじをひらきます'),
                           ('でーたをあんごうかし','しりょうをほぞんします')):
            text=left+right
            self.assertIn(len(left),R.native_continuative_source_boundaries(text),text)
            self.assertTrue(R.completed_native_source_sequence(text),text)
        for text in ('りんごをにゅうりょくしないようをかくにんします',
                     'ぷねらをにゅうりょくしないようをかくにんします',
                     'ぶんしょうをにゅうりょくしぷねらをかくにんします',
                     'ぶんしょうをにゅうりょくしないようをかくにんまし',
                     'ぶんしょうをにゅうりょくしたないようをかくにんします',
                     'ぶんしょうをにゅうりょくさないようをかくにんします',
                     'ぶんしょうをかいないようをかくにんします'):
            self.assertFalse(R.native_continuative_source_boundaries(text),text)
        self.assertFalse(R.completed_native_reading_sequence(
            'ぶんしょうをにゅうりょくしないようをかくにんします'))

    def test_source_continuative_preserves_text_and_purple_separately(self):
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for text in ('ぶんしょうをにゅうりょくしないようをかくにんします。',
                     'しりょうをほぞんしぺーじをひらきます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result.get('odd_spans'),text)
        self.assertEqual(a.store.revision(),revision)

if __name__=='__main__':unittest.main()
