# -*- coding: utf-8 -*-
"""Contextual anomaly boundaries; real dictionary integration lives in ci_smoke_test."""
import unittest
from unittest.mock import patch
import oddness as O
import corrector as C


def tokens(*parts):
    out=[]
    start=0
    for surface,pos,reading in parts:
        out.append((surface,pos,reading,start,start+len(surface),True,''))
        start+=len(surface)
    return out


class ContextualTailTests(unittest.TestCase):
    def negative(self, tail='李', reading='り'):
        return tokens(('いけ','動詞:非自立','いけ'),
                      ('なかっ','助動詞','なかっ'),('た','助動詞','た'),
                      (tail,'名詞:固有名詞:人名:姓',reading))

    def test_negative_tail_uses_reading_and_inflection(self):
        # The rule depends on the reading, not a table of surnames or typo answers.
        for tail in ('李','理','利'):
            text='いけなかった'+tail
            self.assertEqual(O.past_tail_kanji_spans(text,self.negative(tail)),[(5,6,7,'り')])
        self.assertEqual(O.past_tail_kanji_spans('いけなかった里',self.negative('里','さと')),[])

    def test_name_context_is_preserved(self):
        for after in ('さん','氏','君','先生','が来た','の話','へ連絡する',' 太郎'):
            with self.subTest(after=after):
                self.assertEqual(O.past_tail_kanji_spans('いけなかった李'+after,self.negative()),[])
        spaced=self.negative();last=spaced[-1]
        spaced[-1]=last[:3]+(7,8)+last[5:]
        self.assertEqual(O.past_tail_kanji_spans('いけなかった 李',spaced),[])

    def test_positive_past_is_not_enough(self):
        ts=tokens(('読ん','動詞:自立','よん'),('だ','助動詞','だ'),('李','名詞:一般','り'))
        self.assertEqual(O.past_tail_kanji_spans('読んだ李',ts),[])

    def test_parallel_evidence_must_be_in_same_clause(self):
        head=[('読ん','動詞:自立','よん'),('だり','助詞:並立助詞','だり')]
        tail=[('書い','動詞:自立','かい'),('た','助動詞','た'),('李','名詞:一般','り')]
        for separator in ('','、','。','	','  ','　','\n'):
            ts=tokens(*(head+([(separator,'記号','')] if separator else [])+tail))
            text=''.join(t[0] for t in ts)
            with self.subTest(separator=separator):
                self.assertEqual(bool(O.past_tail_kanji_spans(text,ts)),separator in ('','、'))

    def test_columns_do_not_supply_the_answer(self):
        for suffix in ('	無関係','  いけなかったり','。','、できなかった李'):
            self.assertEqual(O.past_tail_kanji_spans('いけなかった李'+suffix,self.negative()),[(5,6,7,'り')])

    def test_local_repair_can_leave_an_unrelated_anomaly(self):
        text='いけなかった李、別の異様'
        opened='いけなかったり、別の異様'
        tk=lambda s:[('たり','助詞:並立助詞','たり',5,7,True,'')]
        with patch.object(O,'odd_spans',return_value=[(9,12)]):
            self.assertIsNone(C._open_one_kana(text,6,'り',tk,O))
            self.assertEqual(C._open_one_kana(text,6,'り',tk,O,scope=(5,7)),(6,7,'り','かな入力'))
        with patch.object(O,'odd_spans',return_value=[(5,7)]):
            self.assertIsNone(C._open_one_kana(text,6,'り',tk,O,scope=(5,7)))

    def test_opened_character_must_merge_into_function_word(self):
        tk=lambda s:[('り','名詞:一般','り',6,7,True,'')]
        with patch.object(O,'odd_spans',return_value=[]):
            self.assertIsNone(C._open_one_kana('いけなかった李',6,'り',tk,O,scope=(5,7)))


    def test_user_protection_covers_partial_edits_and_all_occurrences(self):
        from decisions import DecisionStore
        d=DecisionStore();d.protect('保持対象')
        seen=[]
        def engine(line,*args,**kwargs):
            seen.append(line)
            return dict(corrected=line.replace('対象','補正').replace('後','あと'),
                        odd_spans=[],unsure_spans=[],odd_reasons=[])
        source='前保持対象、保持対象後'
        r=C._with_literal_examples(engine)(source,decisions=d)
        self.assertEqual(seen,['前    、    後'])
        self.assertEqual(r['corrected'],'前保持対象、保持対象あと')
        r=C._with_literal_examples(engine)(source,None,None,None,1.6,None,d)
        self.assertEqual(r['corrected'],'前保持対象、保持対象あと')

    def test_overlapping_protected_words_are_merged(self):
        from decisions import DecisionStore
        d=DecisionStore();d.protect('あいう');d.protect('うえお')
        seen=[]
        def engine(line,**kwargs):seen.append(line);return dict(corrected=line)
        r=C._with_literal_examples(engine)('あいうえお',decisions=d)
        self.assertEqual(seen,['     '])
        self.assertEqual(r['corrected'],'あいうえお')

    def test_odd_only_setting_does_not_mask_input(self):
        from decisions import DecisionStore
        d=DecisionStore();d.leave_odd_alone('保持対象')
        def engine(line,**kwargs):return dict(corrected=line.replace('対象','補正'))
        r=C._with_literal_examples(engine)('保持対象',decisions=d)
        self.assertEqual(r['corrected'],'保持補正')



class BareModifierTests(unittest.TestCase):
    def check(self,head='タフ',tail='背',pos='名詞:一般',reading='せ'):
        ts=tokens((head,'名詞:一般','たふ'),(tail,pos,reading))
        return O.bare_katakana_modifier_spans(head+tail,ts)

    def test_dictionary_alternate_pos_can_expose_bare_modifier(self):
        with patch('morphology.dictionary_base_pos',return_value=('名詞,形容動詞語幹,*,*',)),patch.object(O,'_run_is_word',return_value=False),patch.object(O,'can_join',return_value=False):
            self.assertEqual(self.check(),[('タフ','背',0,3)])
            self.assertEqual(self.check(pos='名詞:接尾:一般'),[])
            self.assertEqual(self.check(pos='名詞:固有名詞:人名:姓'),[])
            self.assertEqual(self.check(reading='せなか'),[])
            self.assertEqual(self.check(head='ソフト'),[])

    def test_known_word_and_licensed_connection_take_priority(self):
        with patch('morphology.dictionary_base_pos',return_value=('名詞,形容動詞語幹,*,*',)),patch.object(O,'_run_is_word',return_value=True),patch.object(O,'can_join',return_value=False):
            self.assertEqual(self.check(),[])
        with patch('morphology.dictionary_base_pos',return_value=('名詞,形容動詞語幹,*,*',)),patch.object(O,'_run_is_word',return_value=False),patch.object(O,'can_join',return_value=True):
            self.assertEqual(self.check(),[])
        with patch('morphology.dictionary_base_pos',return_value=('名詞,一般,*,*',)):
            self.assertEqual(self.check(),[])


class LayoutPositionTests(unittest.TestCase):
    def test_single_character_layout_noun_accepts_existing_position_class(self):
        for left in O._LAYOUT_KANJI:
            for right in O._POSITION_TAIL2:
                with self.subTest(left=left,right=right):
                    self.assertTrue(O.can_join(left,'名詞:一般',right,'名詞:一般'))

    def test_complete_layout_phrase_stops_all_reconstruction_at_shared_gate(self):
        src=tokens(('欄','名詞:一般','らん'),('下部','名詞:一般','かぶ'))
        self.assertTrue(C._chunk_is_intact('欄下部',lambda _:src))
        self.assertTrue(C._chunk_is_intact('欄下部',lambda _:src,context_only=True))
        with patch.object(C,'compose_suffix_surface') as compose:
            self.assertIsNone(C.compose_from_intruded('欄下部',['らんかぶ'],None,None,lambda _:src))
            compose.assert_not_called()

    def test_short_other_noun_is_not_promoted_by_position_rule(self):
        # 他の証拠を除き、この追加条件が1字名詞すべてを許さないことを確認。
        with patch.object(O,'_load',return_value=set()),patch.object(O,'_RIGHT',{}),patch.object(O,'_PAIR',set()):
            self.assertFalse(O.can_join('夢','名詞:一般','末尾','名詞:一般'))


class WrittenErrorActionTests(unittest.TestCase):
    def test_known_result_noun_can_describe_action_in_colloquial_use(self):
        import morphology as M
        for noun in ('誤字','脱字','衍字','脱文'):
            a=M.Token(noun,'名詞',noun,'ごじ',0,2,True,'一般')
            b=M.Token('し','動詞','する','し',2,3,True,'自立','連用形')
            with patch.object(M,'dictionary_base_pos',return_value={'名詞,一般,*,*'}):
                out=M._contextualize_written_error_actions([a,b])
            self.assertEqual(out[0].pos_sub,'サ変接続')
            self.assertEqual((out[0].surface,out[0].reading,out[0].start,out[0].end),
                             (noun,'ごじ',0,2))

    def test_word_formation_alone_does_not_approve_unknown_words(self):
        import morphology as M
        a=M.Token('誤語','名詞','誤語','ごご',0,2,True,'一般')
        b=M.Token('し','動詞','する','し',2,3,True,'自立','連用形')
        with patch.object(M,'dictionary_base_pos',return_value=None):
            self.assertEqual(M._contextualize_written_error_actions([a,b]),[a,b])

    def test_other_nouns_or_non_action_context_keep_original_pos(self):
        import morphology as M
        for noun,pos,base,start,known in (
                ('有線','動詞','する',2,True),('誤差','動詞','する',2,True),
                ('誤字','動詞','する',3,True),('誤字','動詞','知る',2,True),
                ('誤字','助詞','する',2,True),('誤字','動詞','する',2,False)):
            a=M.Token(noun,'名詞',noun,'ごじ',0,2,True,'一般')
            b=M.Token('し',pos,base,'し',start,start+1,known,'自立','連用形')
            with patch.object(M,'dictionary_base_pos',return_value={'名詞,一般,*,*'}):
                self.assertEqual(M._contextualize_written_error_actions([a,b]),[a,b])


class SahenHomophoneTests(unittest.TestCase):
    def evaluate(self,odd=True,intact=False,ime=(),reject=False):
        from types import SimpleNamespace
        src=tokens(('有線','名詞:一般','ゆうせん'),('し','動詞:自立','し'))
        idx=SimpleNamespace(surfaces_for_reading=lambda reading,**kw:
                            ['融資'] if reading=='ゆうし' else ['有線','郵船','優先'])
        def judge(text,*args,**kw):
            return [('有線','し',0,3)] if text=='有線し' and odd else ([('x','y',0,3)] if reject else [])
        def pos(face):
            return {'名詞,サ変接続,*,*'} if face in ('優先','融資') else {'名詞,一般,*,*'}
        with patch.object(O,'is_odd_run',side_effect=judge),patch.object(C,'_chunk_is_intact',return_value=intact), \
             patch('morphology.dictionary_base_pos',side_effect=pos),patch('kanji_guess.ime_readings_for',return_value=list(ime)):
            return C._sahen_homophone_fixes('有線し',lambda _:src,None,idx)

    def test_only_verbal_noun_same_reading_is_selected(self):
        self.assertEqual(self.evaluate(),[(0,2,'優先','その他')])

    def test_requires_original_anomaly_and_common_gate(self):
        self.assertEqual(self.evaluate(odd=False),[])
        self.assertEqual(self.evaluate(intact=True),[])
        self.assertEqual(self.evaluate(reject=True),[])

    def test_ime_reading_precedes_dictionary_inference(self):
        self.assertEqual(self.evaluate(ime=('ユウシ',)),[(0,2,'融資','その他')])


if __name__=='__main__':unittest.main()
