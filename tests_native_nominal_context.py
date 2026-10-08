# -*- coding: utf-8 -*-
"""Original native nouns and their cases must agree across completion paths."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import corrector as C
from tests_native_phrase_context import tokens


def entries(surface):
    return {
        'おみやげ': (('名詞,一般,*,*','*','おみやげ','おみやげ'),),
        '引っ張りだこ': (('名詞,一般,*,*','*','引っ張りだこ','ひっぱりだこ'),),
        'やや': (('名詞,一般,*,*','*','やや','やや'),),
        'もも': (('名詞,一般,*,*','*','もも','もも'),),
        'ささ': (('名詞,一般,*,*','*','ささ','ささ'),),
        '同じ': (('名詞,形容動詞語幹,*,*','*','同じ','おなじ'),),
    }.get(surface, ())


class NativeNominalContextTests(unittest.TestCase):
    def test_written_modifier_retains_the_same_supported_compound_head(self):
        import semantic_roles as S
        for modifier in ('新しい','古い','正しい','小さな'):
            text=modifier+'読み入力'
            with self.subTest(text=text):
                self.assertEqual(R.native_surface_nominal_heads(text),('読み入力',))
                self.assertEqual(S.nominal_roles('読み入力'),frozenset({'process'}))
                self.assertTrue(R.native_object_predicate_proof(text+'を確認します',len(text)+1,('読み入力',)))
        source='新しい読み入力';parts=M.tokenize(source)
        self.assertEqual(R._native_written_modifier_nominal_heads(source,parts),('読み入力',))
        with patch.object(R,'native_adnominal_modifier_parts',return_value=()):
            self.assertFalse(R._native_written_modifier_nominal_heads(source,parts))
        with patch.object(S,'nominal_roles',return_value=frozenset()):
            self.assertFalse(R._native_written_modifier_nominal_heads(source,parts))
        def altered(**changes):
            values={key:getattr(parts[0],key) for key in M.Token.__slots__}
            values.update(changes)
            return M.Token(**values)
        for first in (altered(reading='ふるい'),altered(start=1),altered(infl_form='連用形')):
            with self.subTest(first=first):
                self.assertFalse(R._native_written_modifier_nominal_heads(source,[first,*parts[1:]]))
        for text in ('新しい読み処方','新しい読みぽね','ぽねな読み入力',
                     '新しい太郎','新しい読みにゅう','新しい読み\t入力'):
            with self.subTest(unproved=text):self.assertFalse(R.native_surface_nominal_heads(text))
        self.assertFalse(R.native_object_predicate_proof('新しい読み入力を使います',8,('読み入力',)))

    def test_modified_compound_repair_keeps_its_own_meaning_and_common_gate(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        def run(source):
            a=initial()
            return app.correct_line(source,a.store,dict_index=a.dict_index,decisions=a.decisions,
                                    context_vec=None,input_method='kana')
        try:
            for source in ('古い読み乳力を確認します。','正しい読み乳力を調べます。'):
                with self.subTest(source=source):
                    result=run(source)
                    self.assertEqual(result['corrected'],source.replace('乳力','入力'))
                    self.assertFalse(result['odd_spans'])
                    self.assertEqual(result['analysis_status'],'complete')
            source='古い読み乳力を確認します。'
            with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
                self.assertEqual(run(source)['corrected'],source)
            for source in ('古い読み入力を確認します。','新しい読み手を紹介します。',
                           '「古い読み乳力」と入力します。','新しい読み\t乳力を確認します。'):
                with self.subTest(control=source):self.assertEqual(run(source)['corrected'],source)
        finally:set_active(None)

    def setUp(self):
        M._native_nominal_case_entry.cache_clear()

    def tearDown(self):
        M._native_nominal_case_entry.cache_clear()

    def check_context(self, text, start, end, parts):
        with patch.object(M,'dictionary_inflections',side_effect=entries):
            return R.native_nominal_context(text,start,end,lambda _:parts)

    def test_known_noun_with_compound_functional_tail(self):
        text='おみやげについては'
        parts=tokens([('おみやげ','名詞:一般','おみやげ'),
                      ('について','助詞:格助詞:連語','について'),
                      ('は','助詞:係助詞','は')])
        self.assertTrue(self.check_context(text,0,len(text),parts))

    def test_mixed_script_noun_is_checked_in_original_coordinates(self):
        text='引っ張りだこについて'
        parts=tokens([('引っ張りだこ','名詞:一般','ひっぱりだこ'),
                      ('について','助詞:格助詞:連語','について')])
        self.assertTrue(self.check_context(text,3,len(text),parts))
        self.assertFalse(self.check_context(text,7,len(text),parts))

    def test_genitive_requires_its_original_known_nominal_head(self):
        text='説明のおみやげについて'
        parts=tokens([('説明','名詞:サ変接続','せつめい'),
                      ('の','助詞:連体化','の'),('おみやげ','名詞:一般','おみやげ'),
                      ('について','助詞:格助詞:連語','について')])
        self.assertTrue(self.check_context(text,2,len(text),parts))
        wrong=[parts[0][:5]+(False,)+parts[0][6:]]+parts[1:]
        self.assertFalse(self.check_context(text,2,len(text),wrong))

    def test_dictionary_reading_and_ordinary_noun_are_both_required(self):
        for head in (('おみやげ','名詞:一般','おみやけ'),
                     ('おみやげ','名詞:固有名詞','おみやげ'),
                     ('おみやげ','名詞:接尾:一般','おみやげ'),
                     ('おみやげ','名詞:一般','おみやげ','',False)):
            with self.subTest(head=head):
                self.assertFalse(self.check_context('おみやげ',0,4,tokens([head])))
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertFalse(R.native_nominal_context('おみやげ',0,4,
                             lambda _:tokens([('おみやげ','名詞:一般','おみやげ')])))

    def test_last_noun_of_larger_compound_does_not_prove_whole_phrase(self):
        parts=tokens([('特製','名詞:一般','とくせい'),('おみやげ','名詞:一般','おみやげ')])
        self.assertFalse(self.check_context('特製おみやげ',2,6,parts))

    def test_content_word_or_broken_tail_is_not_functional_grammar(self):
        for tail in ([('資料','名詞:一般','しりょう')],
                     [('を','助詞:格助詞','を'),('を','助詞:格助詞','を')],
                     [('ヌォ','名詞:一般','ぬぉ','',False)]):
            parts=tokens([('おみやげ','名詞:一般','おみやげ')]+tail)
            text=''.join(t[0] for t in parts)
            with self.subTest(text=text):
                self.assertFalse(self.check_context(text,0,len(text),parts))

    def test_cut_particle_and_outside_coordinates_are_rejected(self):
        parts=tokens([('おみやげ','名詞:一般','おみやげ'),
                      ('について','助詞:格助詞:連語','について')])
        for start,end in ((0,5),(-1,8),(0,9),(8,8)):
            self.assertFalse(self.check_context('おみやげについて',start,end,parts))

    def test_copula_or_verbal_tail_is_not_proof_of_a_nominal_phrase(self):
        for tail in ([('だ','助動詞','だ','基本形')],
                     [('が','助詞:格助詞:一般','が'),('し','動詞:自立','し','連用形')]):
            parts=tokens([('おみやげ','名詞:一般','おみやげ')]+tail)
            text=''.join(t[0] for t in parts)
            self.assertFalse(self.check_context(text,0,len(text),parts))

    def test_existing_case_anomaly_is_not_overridden_by_functional_spelling(self):
        parts=tokens([('おみやげ','名詞:一般','おみやげ'),
                      ('より','助詞:格助詞:一般','より'),('が','助詞:格助詞:一般','が')])
        self.assertFalse(self.check_context('おみやげよりが',0,7,parts))

    def test_legitimate_compound_case_and_topic_continue_to_work(self):
        for tail in ([('から','助詞:格助詞:一般','から'),('が','助詞:格助詞:一般','が')],
                     [('について','助詞:格助詞:連語','について'),('は','助詞:係助詞','は')],
                     [('の','助詞:連体化','の')]):
            parts=tokens([('おみやげ','名詞:一般','おみやげ')]+tail)
            text=''.join(t[0] for t in parts)
            self.assertTrue(self.check_context(text,0,len(text),parts))

    def transform(self, parts):
        with patch.object(M,'dictionary_inflections',side_effect=entries):
            return M._contextualize_nominal_cases(parts)

    def test_nominal_homograph_before_case_preserves_source_fields(self):
        a=M.Token('やや','副詞','やや','やや',3,5,True,'一般')
        b=M.Token('が','助詞','が','が',5,6,True,'格助詞:一般')
        result=self.transform([a,b])
        self.assertEqual(result[0].pos,'名詞')
        for name in ('surface','reading','start','end','has_reading'):
            self.assertEqual(getattr(result[0],name),getattr(a,name))
        self.assertEqual(a.pos,'副詞')
        self.assertEqual(self.transform(result),result)

    def test_adverb_before_predicate_and_other_readings_stay_adverbial(self):
        a=M.Token('やや','副詞','やや','やや',0,2,True,'一般')
        predicate=M.Token('寒い','形容詞','寒い','さむい',2,4,True,'自立','基本形')
        case=M.Token('が','助詞','が','が',2,3,True,'格助詞:一般')
        wrong=M.Token('やや','副詞','やや','やー',0,2,True,'一般')
        unknown=M.Token('やや','副詞','やや','やや',0,2,False,'一般')
        for parts in ([a,predicate],[wrong,case],[unknown,case]):
            self.assertEqual(self.transform(parts),parts)

    def test_gap_unknown_particle_and_noncase_do_not_select_noun_sense(self):
        a=M.Token('やや','副詞','やや','やや',0,2,True,'一般')
        for b in (M.Token('が','助詞','が','が',3,4,True,'格助詞:一般'),
                  M.Token('が','助詞','が','が',2,3,False,'格助詞:一般'),
                  M.Token('て','助詞','て','て',2,3,True,'接続助詞')):
            self.assertEqual(self.transform([a,b]),[a,b])

    def test_repeated_characters_inside_native_noun_are_not_two_particles(self):
        text='ややがありました'
        parts=tokens([('やや','名詞:一般','やや'),('が','助詞:格助詞:一般','が'),
                      ('あり','動詞:自立','あり','連用形'),('ました','助動詞','ました')])
        with patch.object(M,'dictionary_inflections',side_effect=entries):
            self.assertTrue(C._doubled_is_word_boundary(text,0,lambda _:parts))

    def test_original_verbal_form_is_not_reinterpreted_as_homographic_noun(self):
        text='表示さされる'
        parts=tokens([('表示','名詞:サ変接続','ひょうじ'),('ささ','動詞:自立','ささ','未然形'),
                      ('れる','助動詞','れる','基本形')])
        token=C._CORRECTION_SOURCE.set(text)
        try:
            with patch.object(M,'dictionary_inflections',side_effect=entries):
                self.assertFalse(C._doubled_is_word_boundary('さされる',0,lambda _:parts))
        finally:
            C._CORRECTION_SOURCE.reset(token)

    def test_other_repetition_does_not_enable_deleting_a_native_noun_character(self):
        text='ももににして'
        parts=tokens([('もも','名詞:一般','もも'),('に','助詞:格助詞:一般','に'),
                      ('に','助詞:格助詞:一般','に'),('し','動詞:自立','し','連用形'),
                      ('て','助詞:接続助詞','て')])
        with patch.object(M,'dictionary_inflections',side_effect=entries), \
             patch.object(C,'_chunk_is_intact',return_value=False), \
             patch.object(C,'_is_functional_strict',return_value=True):
            import os
            with patch.dict(os.environ,{'CN_NO_DUP':'0'}):
                self.assertEqual(C._fix_functional_run(text,tokenize_fn=lambda _:parts),'ももにして')
            with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
                self.assertIsNone(C._fix_functional_run(text,tokenize_fn=lambda _:parts))

    def test_six_field_particles_remain_valid_without_inventing_verb_inflection(self):
        particle=('が','助詞:格助詞:一般','が',0,1,True)
        self.assertTrue(R._native_nominal_functional_tail([particle]))
        verb=('ある','動詞:自立','ある',1,3,True)
        self.assertFalse(R._native_nominal_functional_tail([particle,verb]))

    def test_functional_predicate_must_be_complete_and_not_another_content_word(self):
        particle=('が','助詞:格助詞:一般','が',0,1,True,'')
        for tail in (('し','動詞:自立','し',1,2,True,'連用形'),
                     ('走る','動詞:自立','はしる',1,3,True,'基本形'),
                     ('資料','名詞:一般','しりょう',1,3,True,'')):
            self.assertFalse(R._native_nominal_functional_tail([particle,tail]))

    def test_adnominal_homograph_uses_native_noun_sense_only_before_case(self):
        a=M.Token('同じ','連体詞','同じ','おなじ',0,2,True,'')
        case=M.Token('を','助詞','を','を',2,3,True,'格助詞:一般')
        noun=M.Token('字','名詞','字','じ',2,3,True,'一般')
        result=self.transform([a,case])
        self.assertEqual(result[0].pos,'名詞')
        self.assertEqual(result[0].pos_sub,'形容動詞語幹')
        self.assertEqual(result[0].reading,'おなじ')
        self.assertEqual(self.transform([a,noun]),[a,noun])

    def test_adnominal_without_same_reading_native_noun_stays_adnominal(self):
        case=M.Token('を','助詞','を','を',2,3,True,'格助詞:一般')
        for a in (M.Token('この','連体詞','この','この',0,2,True,''),
                  M.Token('同じ','連体詞','同じ','どうじ',0,2,True,'')):
            self.assertEqual(self.transform([a,case]),[a,case])

    def test_failed_tokenizer_does_not_invent_native_word_proof(self):
        def broken(_):
            raise RuntimeError('unavailable tokenizer')
        self.assertFalse(C._doubled_is_word_boundary('ももがありました',0,broken))

    def test_dangling_final_particle_does_not_prove_the_next_word_boundary(self):
        parts=tokens([('これ','名詞:代名詞:一般','これ'),('は','助詞:係助詞','は'),
                      ('わ','助詞:終助詞','わ'),('もも','名詞:一般','もも')])
        self.assertFalse(self.check_context('これはわもも',4,6,parts))
        self.assertFalse(self.check_context('わもも',1,3,tokens([
            ('わ','助詞:終助詞','わ'),('もも','名詞:一般','もも')])))

    def test_completed_utterance_and_a_real_gap_preserve_next_native_word(self):
        parts=tokens([('そう','副詞:助詞類接続','そう'),('だ','助動詞','だ','基本形'),
                      ('ね','助詞:終助詞','ね'),('もも','名詞:一般','もも')])
        self.assertTrue(self.check_context('そうだねもも',4,6,parts))
        parts=tokens([('私','名詞:代名詞:一般','わたし'),('は','助詞:係助詞','は'),
                      ('ね','助詞:終助詞','ね'),('、','記号:読点','、'),
                      ('もも','名詞:一般','もも')])
        self.assertTrue(self.check_context('私はね、もも',4,6,parts))


if __name__=='__main__':
    unittest.main()
