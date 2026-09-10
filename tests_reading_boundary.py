# -*- coding: utf-8 -*-
import unittest
from unittest.mock import Mock, patch
import corrector as C
import morphology as M
from reading_segments import short_nominal_reading

class ReadingBoundaryTests(unittest.TestCase):
    def tearDown(self):
        short_nominal_reading.cache_clear()

    def tokens(self, broken=True):
        return [M.Token('かな','名詞','かな','かな',0,2,True,'一般'),
                M.Token('に','助詞','に','に',2,3,True,'格助詞:一般'),
                M.Token('ゅうりょく','名詞','ゅうりょく','ゅうりょく',3,8,not broken,'一般')]

    def test_verbal_continuative_head_recovers_boundary(self):
        head=M.Token('よみこみ','動詞','よみこむ','よみこみ',0,4,True,'自立','連用形')
        tokens=[head,M.Token('に','助詞','に','に',4,5),
                M.Token('ゅうりょく','名詞','ゅうりょく','ゅうりょく',5,10,False)]
        with patch('morphology._tokenize_janome',return_value=tokens), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,サ変接続,*,*'}), \
             patch('corrector.table_surfaces_for_reading',side_effect=lambda r,limit=6:['入力'] if r=='にゅうりょく' else []):
            self.assertEqual(short_nominal_reading('よみこみにゅうりょく'),('よみこみ','にゅうりょく','','入力'))
            restored=M._restore_nominal_readings('よみこみにゅうりょく',tokens)
            self.assertIs(restored[0],head)
            self.assertEqual(restored[0].infl_form,'連用形')
            self.assertEqual([(t.surface,t.start,t.end) for t in restored],[('よみこみ',0,4),('にゅうりょく',4,10)])

    def test_nominalized_verb_genitive_survives_wrong_token_boundary(self):
        from reading_segments import continuative_reading_prefix
        head=M.Token('おわり','動詞','おわる','おわり',0,3,True,'自立','連用形')
        wrong=M.Token('のく','動詞','のく','のく',3,5,True,'自立','基本形')
        continuative_reading_prefix.cache_clear()
        with patch('morphology._tokenize_janome',return_value=[head,wrong]), \
             patch('corrector.table_surfaces_for_reading',side_effect=lambda r,limit=6:['句点'] if r=='くてん' else []), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*'}):
            self.assertIsNone(continuative_reading_prefix('おわりのくてん'))
        continuative_reading_prefix.cache_clear()

    def test_readable_particle_connection_is_not_compound_tail(self):
        from reading_segments import continuative_reading_prefix
        head=M.Token('おわり','動詞','おわる','おわり',0,3,True,'自立','連用形')
        particle=M.Token('の','助詞','の','の',3,4,True,'連体化')
        tail=M.Token('くてん','名詞','くてん','くてん',4,7,True,'一般')
        continuative_reading_prefix.cache_clear()
        with patch('morphology._tokenize_janome',return_value=[head,particle,tail]):
            self.assertIsNone(continuative_reading_prefix('おわりのくてん'))
        continuative_reading_prefix.cache_clear()

    def test_other_conjugations_do_not_supply_nominal_head(self):
        for form in ('基本形','未然形','仮定形','連用タ接続',''):
            short_nominal_reading.cache_clear()
            tokens=[M.Token('よみこみ','動詞','よみこむ','よみこみ',0,4,True,'自立',form),
                    M.Token('ゅうりょく','名詞','ゅうりょく','ゅうりょく',5,10,False)]
            with patch('morphology._tokenize_janome',return_value=tokens):
                self.assertIsNone(short_nominal_reading('よみこみにゅうりょく'),form)

    def test_dictionary_reading_recovers_mora_boundary(self):
        with patch('morphology._tokenize_janome',return_value=self.tokens()), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*'}), \
             patch('corrector.table_surfaces_for_reading',side_effect=lambda r,limit=6: ['入力'] if r=='にゅうりょく' else []):
            self.assertEqual(short_nominal_reading('かなにゅうりょく'),('かな','にゅうりょく','','入力'))

    def test_readable_tokens_are_not_resegmented(self):
        with patch('morphology._tokenize_janome',return_value=self.tokens(False)), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*'}), \
             patch('corrector.table_surfaces_for_reading',return_value=['入力']):
            self.assertIsNone(short_nominal_reading('かなにゅうりょく'))

    def test_name_only_is_not_noun_evidence(self):
        with patch('morphology._tokenize_janome',return_value=self.tokens()), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,固有名詞,人名,名'}):
            self.assertIsNone(short_nominal_reading('かなにゅうりょく'))

    def test_unknown_tail_stays_unknown(self):
        with patch('morphology._tokenize_janome',return_value=self.tokens()), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,一般,*,*'}), \
             patch('corrector.table_surfaces_for_reading',return_value=[]):
            self.assertIsNone(short_nominal_reading('かなにゅうりょく'))

    def test_restored_tokens_preserve_source_offsets(self):
        source='かなにゅうりょく'
        with patch('reading_segments.short_nominal_reading',return_value=('かな','にゅうりょく','','入力')), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,サ変接続,*,*'}):
            result=M._restore_nominal_readings(source,self.tokens())
        self.assertEqual([(t.surface,t.start,t.end) for t in result],[('かな',0,2),('にゅうりょく',2,8)])
        self.assertEqual(''.join(t.surface for t in result),source)
        self.assertEqual(result[1].pos_sub,'サ変接続')

    def test_noun_suffix_requires_noun_connection(self):
        import pos_grammar as PG
        for suffix in ('です','ではありません','なら','を','の'):
            self.assertTrue(PG.explain_kana_run(suffix,no_words=True,initial_state='Bw'),suffix)
        for suffix in ('ます','ました'):
            self.assertFalse(PG.explain_kana_run(suffix,no_words=True,initial_state='Bw'),suffix)
        self.assertTrue(PG.explain_kana_run('します',no_words=True,initial_state='Bw'))

    def test_shifted_restoration_preserves_surrounding_tokens(self):
        source='「かなにゅうりょく」を'
        original=[M.Token('「','記号','「','「',0,1,True,'括弧開')]
        original.extend(M.Token(t.surface,t.pos,t.base_form,t.reading,t.start+1,t.end+1,
                                t.has_reading,t.pos_sub) for t in self.tokens())
        original.extend([M.Token('」','記号','」','」',9,10,True,'括弧閉'),
                         M.Token('を','助詞','を','を',10,11,True,'格助詞:一般')])
        with patch('reading_segments.short_nominal_reading',return_value=('かな','にゅうりょく','','入力')), \
             patch('morphology.dictionary_base_pos',return_value={'名詞,サ変接続,*,*'}):
            result=M._restore_nominal_readings(source,original)
        self.assertEqual(''.join(t.surface for t in result),source)
        for token in result:self.assertEqual(source[token.start:token.end],token.surface)
        self.assertIs(result[0],original[0])
        self.assertIs(result[-1],original[-1])

class IntrudedStrokeTests(unittest.TestCase):
    def test_whole_anomaly_can_reach_unknown_tail(self):
        index=Mock();index.is_world_reading.return_value=False
        store=Mock();store.has_reading.return_value=False
        with patch.object(C,'_kana_run_is_odd_by_grammar',side_effect=lambda run,*_:run=='全体'), \
             patch('morphology._tokenize_janome',return_value=[Mock(has_reading=False)]):
            self.assertTrue(C._intrusion_tail_is_odd('全体','残り',index,store,True))
            self.assertFalse(C._intrusion_tail_is_odd('全体','残り',index,store,False))
            self.assertFalse(C._intrusion_tail_is_odd('正常','残り',index,store,True))

    def test_known_or_readable_tail_is_not_overridden(self):
        index=Mock();index.is_world_reading.return_value=False
        store=Mock();store.has_reading.return_value=False
        with patch.object(C,'_kana_run_is_odd_by_grammar',side_effect=lambda run,*_:run=='全体'), \
             patch('morphology._tokenize_janome',return_value=[Mock(has_reading=True)]):
            self.assertFalse(C._intrusion_tail_is_odd('全体','残り',index,store,True))
        index.is_world_reading.return_value=True
        with patch.object(C,'_kana_run_is_odd_by_grammar',side_effect=lambda run,*_:run=='全体'), \
             patch('morphology._tokenize_janome',return_value=[Mock(has_reading=False)]):
            self.assertFalse(C._intrusion_tail_is_odd('全体','残り',index,store,True))
        index.is_world_reading.return_value=False;store.has_reading.return_value=True
        with patch.object(C,'_kana_run_is_odd_by_grammar',side_effect=lambda run,*_:run=='全体'), \
             patch('morphology._tokenize_janome',return_value=[Mock(has_reading=False)]):
            self.assertFalse(C._intrusion_tail_is_odd('全体','残り',index,store,True))

    def test_base_key_of_voiced_neighbor_is_used(self):
        self.assertTrue(C._intruded_keystroke('す','が','ぞ'))
        self.assertIn('がぞう',C._typo_repairs_intruded('がすぞう'))

    def test_two_strokes_are_not_one_intrusion(self):
        self.assertFalse(C._intruded_keystroke('が','か','す'))

    def test_distant_keys_do_not_allow_deletion(self):
        self.assertFalse(C._intruded_keystroke('と','ん','ひ'))
        self.assertNotIn('ほぞんひょうじ',C._typo_repairs_intruded('ほぞんとひょうじ'))

    def test_last_letter_is_not_an_internal_intrusion(self):
        self.assertNotIn('けいさん',C._typo_repairs_intruded('けいさんき'))

    def test_edges_require_physical_adjacency(self):
        self.assertNotIn('がぞう', C._typo_repairs_intruded('すがぞう'))
        self.assertIn('がぞう', C._typo_repairs_intruded('すがぞう', include_edges=True))
        self.assertIn('にもつ', C._typo_repairs_intruded('のにもつ', include_edges=True))
        self.assertIn('たぶ', C._typo_repairs_intruded('たぶせ', include_edges=True))
        self.assertNotIn('がぞう', C._typo_repairs_intruded('ぬがぞう', include_edges=True))

    def test_edge_does_not_bypass_duplicate_or_stroke_count(self):
        for text in ('ががぞう', 'がぞうう'):
            self.assertNotIn('がぞう', C._typo_repairs_intruded(text, include_edges=True))
        self.assertNotIn('はつどう', C._typo_repairs_intruded('ぎはつどう', include_edges=True))

    def test_fallback_ranking_does_not_depend_on_generation_order(self):
        tokens = [('も', '助詞', 'も', 0, 1, True),
                  ('水戸', '名詞', 'みと', 1, 3, True),
                  ('に戻ります', '動詞', 'にもどります', 3, 8, True)]
        store = Mock(); store.lookup.return_value = []
        for candidates in (['みとにもどります', 'もとにもどります'],
                           ['もとにもどります', 'みとにもどります']):
            fixes = Mock(return_value=candidates)
            fixes.costs = {reading: 1.0 for reading in candidates}
            with patch.object(C, '_table_cost', return_value=100), \
                 patch.object(C, '_kana_run_explained', return_value=True), \
                 patch.object(C, '_is_whole_proper_noun', side_effect=lambda text, _: text == 'みと'), \
                 patch.object(C, '_yomi_prior_bucket', return_value=0), \
                 patch('oddness.is_odd_run', return_value=False):
                result = C._po_replace_odd_span('も水戸に戻ります', [('も', '水戸')],
                                               'もみとにもどります', fixes,
                                               lambda _: tokens, store, None)
            self.assertEqual(result, 'もとに戻ります')

    def test_fallback_ranking_keeps_physical_cost_before_word_prior(self):
        tokens = [('も', '助詞', 'も', 0, 1, True),
                  ('水戸', '名詞', 'みと', 1, 3, True),
                  ('に戻ります', '動詞', 'にもどります', 3, 8, True)]
        fixes = Mock(return_value=['もとにもどります', 'みとにもどります'])
        fixes.costs = {'もとにもどります': 2.6, 'みとにもどります': 1.0}
        store = Mock(); store.lookup.return_value = []
        with patch.object(C, '_table_cost', return_value=100), \
             patch.object(C, '_kana_run_explained', return_value=True), \
             patch.object(C, '_is_whole_proper_noun', side_effect=lambda text, _: text == 'みと'), \
             patch.object(C, '_yomi_prior_bucket', return_value=0), \
             patch('oddness.is_odd_run', return_value=False):
            result = C._po_replace_odd_span('も水戸に戻ります', [('も', '水戸')],
                                           'もみとにもどります', fixes,
                                           lambda _: tokens, store, None)
        self.assertEqual(result, 'みとに戻ります')

    def test_identical_repeat_is_not_intrusion(self):
        self.assertNotIn('がぞう',C._typo_repairs_intruded('がぞぞう'))

if __name__=='__main__':unittest.main()
