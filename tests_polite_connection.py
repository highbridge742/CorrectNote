# -*- coding: utf-8 -*-
"""Auxiliary attachment, dictionary alternatives, and original repair boundaries."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import morphology as M
import oddness as O
import contextual_repair as R


def pair(surface, pos, form='', start=0, auxiliary='ます'):
    end=start+len(surface)
    return ((surface,pos,surface,start,end,True,form),
            (auxiliary,'助動詞',auxiliary,end,end+len(auxiliary),True,'基本形'))


class PoliteConnectionTests(unittest.TestCase):
    def test_pure_noun_cannot_attach_to_polite_auxiliary(self):
        with patch.object(M,'dictionary_inflections',return_value=(('名詞,サ変接続,*,*','*','記録','きろく'),)):
            self.assertTrue(O.polite_aux_mismatch(*pair('記録','名詞:サ変接続')))

    def test_verb_continuative_and_dictionary_alternative_are_valid(self):
        with patch.object(M,'dictionary_inflections',return_value=(('動詞,自立,*,*','連用形','楽しむ','たのしみ'),)):
            self.assertFalse(O.polite_aux_mismatch(*pair('楽しみ','名詞:一般')))
            self.assertFalse(O.polite_aux_mismatch(*pair('楽しみ','動詞:自立','連用形')))

    def test_sahen_shi_retains_its_continuative_when_dictionary_has_only_irrealis(self):
        with patch.object(M,'dictionary_inflections',return_value=((
                '動詞,自立,*,*','未然形','ろくする','ろくし'),)):
            self.assertFalse(O.polite_aux_mismatch(*pair('ろくし','動詞:自立','未然形')))
        with patch.object(M,'dictionary_inflections',return_value=((
                '動詞,自立,*,*','未然形','書く','かか'),)):
            self.assertTrue(O.polite_aux_mismatch(*pair('書か','動詞:自立','未然形')))

    def test_dictionary_base_and_euphonic_forms_do_not_license_masu(self):
        for surface,form in (('読む','基本形'),('読ん','連用タ接続'),('美しく','連用テ接続')):
            with self.subTest(surface=surface),patch.object(M,'dictionary_inflections',return_value=((
                    '形容詞,自立,*,*' if surface=='美しく' else '動詞,自立,*,*',form,surface,surface),)):
                self.assertTrue(O.polite_aux_mismatch(*pair(surface,'形容詞' if surface=='美しく' else '動詞:自立',form)))

    def test_passive_causative_auxiliaries_can_continue_to_masu(self):
        for base in ('れる','られる','せる','させる'):
            surface=base[:-1]
            with self.subTest(base=base),patch.object(M,'dictionary_inflections',return_value=((
                    '助動詞,*,*,*','連用形',base,surface),)):
                self.assertFalse(O.polite_aux_mismatch(*pair(surface,'助動詞','連用形')))

    def test_past_or_copula_is_not_a_passive_auxiliary(self):
        for surface,base,form in (('た','た','基本形'),('でし','です','連用形')):
            with self.subTest(surface=surface),patch.object(M,'dictionary_inflections',return_value=((
                    '助動詞,*,*,*',form,base,surface),)):
                self.assertTrue(O.polite_aux_mismatch(*pair(surface,'助動詞',form)))

    def test_unknown_and_missing_dictionary_are_not_grammar_proof(self):
        a,b=pair('未知','名詞:一般')
        with patch.object(M,'dictionary_inflections',return_value=None):
            self.assertFalse(O.polite_aux_mismatch(a,b))
        self.assertFalse(O.polite_aux_mismatch(a[:5]+(False,a[6]),b))

    def test_spaces_and_independent_words_are_not_auxiliary_attachment(self):
        a,b=pair('名詞','名詞:一般')
        self.assertFalse(O.polite_aux_mismatch(a,b[:3]+(b[3]+1,b[4]+1)+b[5:]))
        self.assertFalse(O.polite_aux_mismatch(a,(b[0],'名詞:一般')+b[2:]))

    def test_invalid_auxiliary_has_extended_scope_but_preserves_valid_action_first(self):
        parts=[('記録','名詞:サ変接続','きろく',0,2,True,''),
               ('まし','助動詞','まし',2,4,True,'連用形'),
               ('て','助詞:接続助詞','て',4,5,True,'')]
        with patch.object(O,'is_odd_run',return_value=[('記録','まし',0,4)]), \
             patch.object(O,'polite_aux_mismatch',return_value=True):
            targets=R.targets_for_line('記録まして',lambda s:parts,None,None)
        self.assertEqual([(t.text,t.following,t.preserved_head) for t in targets],
                         [('記録まして','','記録'),('記録','まして','')])

    def test_composed_surface_uses_native_action_and_grammatical_ending(self):
        dictionary=SimpleNamespace(surfaces_for_reading=lambda rd,**kw:['記録'] if rd=='きろく' else [],
                                   inflected_surfaces_for_reading=lambda rd:[])
        store=SimpleNamespace(lookup=lambda rd:[])
        entries={'記録':(('名詞,サ変接続,*,*','*','記録','きろく'),),
                 'し':(('動詞,自立,*,*','連用形','する','し'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda sf:entries.get(sf,())), \
             patch.object(R,'_productive_predicate',return_value=True), \
             patch.object(R,'_grammatical_suffix',side_effect=lambda tail,state:tail=='て' and state=='R'):
            self.assertEqual(R._surfaces('きろくして',store,dictionary,compose=True),['記録して'])
            self.assertEqual(R._surfaces('きろくまして',store,dictionary,compose=True),[])
            self.assertEqual(R._surfaces('きろくして',store,dictionary),[])

    def test_action_scope_rejects_changed_head_before_other_checks(self):
        target=R.RepairTarget('記録まして',0,5,0,5,(),True,'','auxiliary_connection','記録')
        self.assertEqual(R.validate(target,'広くまして',None,None,None,None),
                         (False,'known_action_changed'))

    def test_adverb_mashite_after_an_object_action_has_auxiliary_boundaries(self):
        ts=[M.Token('を','助詞','を','を',0,1,True,'格助詞:一般'),
            M.Token('記録','名詞','記録','きろく',1,3,True,'サ変接続'),
            M.Token('まして','副詞','まして','まして',3,6,True,'一般')]
        restored=M._restore_polite_aux_boundaries(ts)
        self.assertEqual([(t.surface,t.pos,t.start,t.end) for t in restored[-2:]],
                         [('まし','助動詞',3,5),('て','助詞',5,6)])
        self.assertEqual(''.join(t.surface for t in restored),'を記録まして')

    def test_independent_comparative_adverb_stays_intact(self):
        ts=[M.Token('大人','名詞','大人','おとな',0,2,True,'一般'),
            M.Token('まして','副詞','まして','まして',2,5,True,'一般')]
        self.assertEqual(M._restore_polite_aux_boundaries(ts),ts)

    def test_repair_keeps_a_possible_adverbial_head_until_original_span_was_tested(self):
        line='位寸刷します'
        parts=[('位','名詞:副詞可能','くらい',0,1,True,''),
               ('寸','名詞:一般','すん',1,2,True,''),
               ('刷','名詞:一般','すり',2,3,True,''),
               ('し','動詞:自立','し',3,4,True,'連用形'),
               ('ます','助動詞','ます',4,6,True,'基本形')]
        with patch.object(O,'is_odd_run',return_value=[('刷','し',2,4)]):
            targets=R.targets_for_line(line,lambda s:parts,None,None)
        self.assertEqual([t.text for t in targets],['位寸刷','寸刷'])

    def test_original_polite_attachment_cannot_be_evaded_by_adverb_reanalysis(self):
        target=R.RepairTarget('切ろまして資料',0,2,0,7,(('切ろ','まし',0,4),),True,'まして資料')
        def tk(s):
            if s=='切ろまして資料':
                return [('切ろ','動詞:自立','きろ',0,2,True,'未然ウ接続'),
                        ('まし','助動詞','まし',2,4,True,'連用形'),
                        ('て','助詞:接続助詞','て',4,5,True,''),
                        ('資料','名詞:一般','しりょう',5,7,True,'')]
            if s=='帰路まして資料':
                return [('帰路','名詞:一般','きろ',0,2,True,''),
                        ('まして','副詞:一般','まして',2,5,True,''),
                        ('資料','名詞:一般','しりょう',5,7,True,'')]
            return [('帰路','名詞:一般','きろ',0,2,True,'')]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch.object(O,'is_odd_run',return_value=[]):
            self.assertEqual(R.validate(target,'帰路',engine,tk,None,None),
                             (False,'polite_auxiliary_slot'))

    def test_existing_tail_repair_is_rechecked_over_the_entire_original_anomaly(self):
        target=R.RepairTarget('泳ぎのました',0,2,0,6,(('泳ぎ','のました',0,6),),True,'のました')
        with patch.object(R,'validate',return_value=(True,'accepted')) as check:
            self.assertTrue(R._legacy_resolves_anomaly(target,[(2,3,'')],None,None,None,None,None))
        wide,surface=check.call_args.args[:2]
        self.assertEqual((wide.text,surface),('泳ぎのました','泳ぎました'))
        with patch.object(R,'validate',return_value=(False,'context_still_anomalous')):
            self.assertFalse(R._legacy_resolves_anomaly(target,[(2,3,'')],None,None,None,None,None))

    def test_existing_change_inside_the_lexical_head_still_competes_with_new_candidates(self):
        target=R.RepairTarget('泳ぎのました',0,2,0,6,(('泳ぎ','のました',0,6),),True,'のました')
        with patch.object(R,'validate') as check:
            self.assertFalse(R._legacy_resolves_anomaly(target,[(0,2,'及び')],None,None,None,None,None))
            self.assertFalse(R._legacy_resolves_anomaly(target,[(7,7,'。')],None,None,None,None,None))
        check.assert_not_called()

    def test_causative_selects_the_auxiliary_for_the_original_conjugation(self):
        cases=(('並べ','一段','未然形','並べる','せ',True),
               ('並べ','一段','未然形','並べる','させ',False),
               ('読ま','五段・マ行','未然形','読む','せ',False),
               ('読み','五段・マ行','連用形','読む','せ',True),
               ('来','カ変・クル','未然形','来る','させ',False),
               ('来','カ変・クル','未然形','来る','せ',True),
               ('さ','サ変・スル','未然レル接続','する','せ',False))
        for sf,kind,form,base,aux,bad in cases:
            entries={sf:(('動詞,自立,*,*',kind,form,base,sf),),
                     aux:(('動詞,接尾,*,*','一段','連用形',aux+'る',aux),)}
            a,b=pair(sf,'動詞:自立',form,auxiliary=aux)
            b=(b[0],'動詞:接尾')+b[2:]
            with self.subTest(surface=sf,aux=aux),patch.object(M,'dictionary_paradigms',side_effect=lambda x:entries.get(x,())):
                self.assertEqual(O.causative_aux_mismatch(a,b),bad)

    def test_missing_conjugation_evidence_does_not_invent_an_anomaly(self):
        a,b=pair('未知','動詞:自立',auxiliary='せ')
        b=(b[0],'動詞:接尾')+b[2:]
        with patch.object(M,'dictionary_paradigms',return_value=None):
            self.assertFalse(O.causative_aux_mismatch(a,b))

    def test_generated_tail_may_not_hide_a_final_particle_before_a_new_verb(self):
        good=[M.Token('記録','名詞','記録','きろく',0,2,True,'サ変接続'),
              M.Token('し','動詞','する','し',2,3,True,'自立','連用形'),
              M.Token('て','助詞','て','て',3,4,True,'接続助詞')]
        bad=[M.Token('詰め','動詞','詰める','つめ',0,2,True,'自立','連用形'),
             M.Token('ぜ','助詞','ぜ','ぜ',2,3,True,'終助詞'),
             M.Token('き','動詞','くる','き',3,4,True,'自立','連用形')]
        R._productive_predicate.cache_clear()
        with patch.object(M,'tokenize',return_value=good):
            self.assertTrue(R._productive_predicate('記録して','記録'))
        with patch.object(M,'tokenize',return_value=bad):
            self.assertFalse(R._productive_predicate('詰めぜき','詰め'))
        R._productive_predicate.cache_clear()

    def test_auxiliary_iru_needs_the_te_connection_but_compounds_are_kept(self):
        a,b=pair('並べ','動詞:自立','連用形',auxiliary='い')
        b=(b[0],'動詞:非自立')+b[2:]
        entries={'い':(('動詞,非自立,*,*','連用形','いる','い'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda x:entries.get(x,())):
            self.assertTrue(O.auxiliary_te_mismatch(a,b))
            te=('て','助詞:接続助詞','て',a[3],a[4],True,'')
            self.assertFalse(O.auxiliary_te_mismatch(te,b))
            self.assertFalse(O.auxiliary_te_mismatch(a,(b[0],'動詞:自立')+b[2:]))
        entries[a[0]+b[0]]=(('動詞,自立,*,*','連用形','複合動詞',a[0]+b[0]),)
        with patch.object(M,'dictionary_inflections',side_effect=lambda x:entries.get(x,())):
            self.assertFalse(O.auxiliary_te_mismatch(a,b))

    def test_standalone_sokuon_after_case_particle_is_not_a_verbal_stem(self):
        previous=('を','助詞:格助詞:一般','を',0,1,True,'')
        a=('っ','動詞:非自立','っ',1,2,True,'連用タ接続')
        b=('買い','動詞:自立','かい',2,4,True,'連用形')
        self.assertTrue(O.orphan_sokuon_mismatch(a,b,previous))
        self.assertFalse(O.orphan_sokuon_mismatch(a,b,None))
        self.assertFalse(O.orphan_sokuon_mismatch(a,b,('あ','感動詞','あ',0,1,True,'')))
        self.assertFalse(O.orphan_sokuon_mismatch(a,('！','記号','！',2,3,True,''),previous))
        self.assertFalse(O.orphan_sokuon_mismatch(a,('て','助詞:接続助詞','て',2,3,True,''),previous))
        self.assertFalse(O.orphan_sokuon_mismatch(a,b[:3]+(3,5)+b[5:],previous))

    def test_passive_uses_irrealis_and_conjugation_type_with_colloquial_alternatives(self):
        cases=(('書か','五段・カ行イ音便','未然形','書く','れ',False),
               ('書き','五段・カ行イ音便','連用形','書く','れ',True),
               ('読み','五段・マ行','連用形','読む','られ',True),
               ('食べ','一段','未然形','食べる','られ',False),
               ('食べ','一段','未然形','食べる','れ',False),
               ('来','カ変・クル','未然形','来る','れ',False),
               ('さ','サ変・スル','未然レル接続','する','れ',False),
               ('し','サ変・スル','未然形','する','れ',True),
               ('論ぜ','サ変・−ズル','未然形','論ずる','られ',False))
        for sf,kind,form,base,aux,bad in cases:
            entries={sf:(('動詞,自立,*,*',kind,form,base,sf),),
                     aux:(('動詞,接尾,*,*','一段','連用形',aux+'る',aux),)}
            a,b=pair(sf,'動詞:自立',form,auxiliary=aux)
            b=(b[0],'動詞:接尾')+b[2:]
            with self.subTest(surface=sf,aux=aux),patch.object(M,'dictionary_paradigms',side_effect=lambda x:entries.get(x,())):
                self.assertEqual(O.passive_aux_mismatch(a,b),bad)

    def test_unknown_dictionary_and_separated_passive_are_not_new_anomalies(self):
        a,b=pair('書き','動詞:自立','連用形',auxiliary='れ')
        b=(b[0],'動詞:接尾')+b[2:]
        with patch.object(M,'dictionary_paradigms',return_value=None):
            self.assertFalse(O.passive_aux_mismatch(a,b))
        self.assertFalse(O.passive_aux_mismatch(a,b[:3]+(b[3]+1,b[4]+1)+b[5:]))

    def test_intrusion_can_use_the_next_unedited_particle_key(self):
        ordinary={r.reading for r in R.key_repairs('かたづけい')}
        contextual={r.reading:r for r in R.key_repairs('かたづけい',after='て')}
        self.assertNotIn('かたづけ',ordinary)
        self.assertIn('かたづけ',contextual)
        self.assertEqual(contextual['かたづけ'].operation,'adjacent_intrusion')
        self.assertEqual(contextual['かたづけ'].pressed,'い')
        self.assertEqual(contextual['かたづけ'].intended,'')
        self.assertNotIn('かたづけ',{r.reading for r in R.key_repairs('かたづけい',after='ほ')})

    def test_intrusion_can_use_the_preceding_key_without_editing_it(self):
        self.assertNotIn('きろく',{r.reading for r in R.key_repairs('いきろく')})
        self.assertIn('きろく',{r.reading for r in R.key_repairs('いきろく',before='て')})

    def test_homographic_imperative_does_not_replace_the_parsed_potential_base(self):
        entries=(('動詞,自立,*,*','命令ｅ','読む','よめ'),
                 ('動詞,自立,*,*','連用形','読める','よめ'))
        tk=lambda s:[('読め','動詞:自立','よめ',0,2,True,'連用形')]
        with patch.object(M,'dictionary_inflections',return_value=entries), \
             patch('inflected_lexicon.dictionary_readings',side_effect=lambda s:('よめる',) if s=='読める' else ('よむ',)):
            bases=R._candidate_verb_bases('読め',tk)
        self.assertIn(('surface','読める'),bases)
        self.assertIn(('reading','よめる'),bases)
        self.assertNotIn(('surface','読む'),bases)
        self.assertNotIn(('reading','よむ'),bases)

    def test_known_nominal_reading_is_not_an_invalid_aspect_auxiliary(self):
        a,b=pair('かけ','動詞:自立','連用形',auxiliary='い')
        b=(b[0],'動詞:非自立')+b[2:]
        entries={'い':(('動詞,非自立,*,*','連用形','いる','い'),)}
        O._kana_nominal_alternative.cache_clear()
        with patch.object(M,'dictionary_inflections',side_effect=lambda s:entries.get(s,())), \
             patch('corrector.table_surfaces_for_reading',return_value=['家計']), \
             patch.object(M,'dictionary_base_pos',return_value=('名詞,一般,*,*',)):
            self.assertFalse(O.auxiliary_te_mismatch(a,b))
        O._kana_nominal_alternative.cache_clear()

    def test_kana_verb_fragment_requires_an_explicit_predicate_ending(self):
        a=('とい','動詞:自立','とい',0,2,True,'連用タ接続')
        b=('れ','動詞:接尾','れ',2,3,True,'連用形')
        with patch.object(O,'polite_aux_mismatch',return_value=False), \
             patch.object(O,'causative_aux_mismatch',return_value=False), \
             patch.object(O,'passive_aux_mismatch',return_value=True):
            self.assertFalse(R._kana_grammar_boundary([a,b],0,3))
            c=('て','助詞:接続助詞','て',3,4,True,'')
            self.assertTrue(R._kana_grammar_boundary([a,b,c],0,3))

    def test_generated_te_ta_follow_the_native_euphonic_form(self):
        cases=(('置き','おき','五段・カ行イ音便','連用形','置く','て',False),
               ('置い','おい','五段・カ行イ音便','連用タ接続','置く','て',True),
               ('泳い','およい','五段・ガ行','連用タ接続','泳ぐ','で',True),
               ('泳い','およい','五段・ガ行','連用タ接続','泳ぐ','て',False),
               ('読ん','よん','五段・マ行','連用タ接続','読む','だ',True),
               ('話し','はなし','五段・サ行','連用形','話す','て',True),
               ('食べ','たべ','一段','連用形','食べる','た',True),
               ('問う','とう','五段・ワ行ウ音便','連用タ接続','問う','て',True),
               ('ろくし','ろくし','サ変・−スル','未然形','ろくする','て',True),
               ('来','き','カ変・来ル','連用形','来る','て',True),
               ('なさい','なさい','五段・ラ行特殊','連用形','なさる','て',False))
        for sf,rd,kind,form,base,aux,allowed in cases:
            R._modern_te_allowed.cache_clear()
            with self.subTest(surface=sf,aux=aux),patch.object(M,'dictionary_paradigms',
                    return_value=(('動詞,自立,*,*',kind,form,base,rd),)):
                self.assertIs(R._modern_te_allowed(sf,rd,aux),allowed)
        R._modern_te_allowed.cache_clear()

    def test_generated_connection_does_not_borrow_another_reading_or_invent_unknown_paradigm(self):
        R._modern_te_allowed.cache_clear()
        with patch.object(M,'dictionary_paradigms',return_value=(
                ('動詞,自立,*,*','カ変・来ル','連用形','来る','き'),)):
            self.assertIsNone(R._modern_te_allowed('来','く','て'))
        with patch.object(M,'dictionary_paradigms',return_value=None):
            self.assertIsNone(R._modern_te_allowed('未知','みち','て'))
        with patch.object(M,'dictionary_paradigms',return_value=(
                ('動詞,自立,*,*','文語・四段','連用形','語る','かたり'),)):
            self.assertIsNone(R._modern_te_allowed('語り','かたり','て'))
        R._modern_te_allowed.cache_clear()

    def test_single_nominal_glyph_with_bad_polite_auxiliary_has_a_scope(self):
        parts=[('語','名詞:一般','ご',0,1,True,''),('ます','助動詞','ます',1,3,True,'基本形')]
        with patch.object(O,'is_odd_run',return_value=[('語','ます',0,3)]), \
             patch.object(O,'polite_aux_mismatch',return_value=True):
            targets=R.targets_for_line('語ます',lambda s:parts,None,None)
        self.assertIn(('語ます','auxiliary_connection'),[(t.text,t.boundary_kind) for t in targets])

    def test_broken_polite_scope_can_reconsider_a_false_case_boundary(self):
        line='場所へ語ます'
        parts=[('場所','名詞:一般','ばしょ',0,2,True,''),('へ','助詞:格助詞:一般','へ',2,3,True,''),
               ('語','名詞:一般','ご',3,4,True,''),('ます','助動詞','ます',4,6,True,'基本形')]
        with patch.object(O,'is_odd_run',return_value=[('語','ます',3,6)]), \
             patch.object(O,'polite_aux_mismatch',side_effect=lambda a,b:b[0]=='ます'):
            targets=R.targets_for_line(line,lambda s:parts,None,None)
        self.assertEqual(targets[0].text,line)
        self.assertEqual(targets[0].boundary_kind,'auxiliary_connection')
        self.assertTrue(all(t.source[t.start:t.end]==t.text for t in targets))

    def test_aspect_generation_does_not_attach_iru_to_an_imperative(self):
        a=('均せ','動詞:自立','ならせ',0,2,True,'命令ｅ')
        b=('い','動詞:非自立','い',2,3,True,'連用形')
        entries={'い':(('動詞,非自立,*,*','連用形','いる','い'),)}
        with patch.object(M,'dictionary_inflections',side_effect=lambda sf:entries.get(sf,())):
            self.assertTrue(O.aspect_auxiliary_needs_te(a,b))
            self.assertFalse(O.auxiliary_te_mismatch(a,b))

    def test_space_keeps_the_comparative_adverb_separate(self):
        ts=[M.Token('記録','名詞','記録','きろく',0,2,True,'サ変接続'),
            M.Token('まして','副詞','まして','まして',3,6,True,'一般')]
        self.assertEqual(M._restore_polite_aux_boundaries(ts),ts)


    def test_terminal_imperative_emphasis_keeps_source_and_dictionary_form(self):
        a=M.Token('行け','動詞','行ける','いけ',4,6,True,'自立','連用形')
        b=M.Token('い','動詞','いる','い',6,7,True,'非自立','連用形')
        stop=M.Token('。','記号','。','。',7,8,True,'句点')
        forms=(('動詞,自立,*,*','命令ｅ','行く','いけ'),)
        with patch.object(M,'dictionary_inflections',return_value=forms):
            got=M._restore_imperative_emphasis([a,b,stop])
        self.assertEqual(got[0].infl_form,'命令ｅ')
        self.assertEqual(got[1].pos_sub,'終助詞')
        self.assertEqual([(t.surface,t.start,t.end) for t in got],[(t.surface,t.start,t.end) for t in (a,b,stop)])
        aux=M.Token('ます','助動詞','ます','ます',7,9,True,'','基本形')
        with patch.object(M,'dictionary_inflections',return_value=forms):
            self.assertEqual(M._restore_imperative_emphasis([a,b,aux]),[a,b,aux])
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertEqual(M._restore_imperative_emphasis([a,b,stop]),[a,b,stop])


    def test_euphonic_generation_uses_the_same_native_voicing_as_validation(self):
        cases=(('買っ','かっ','買う','て','TSU'),('読ん','よん','読む','で','N'),
               ('書い','かい','書く','て','TSU'),('泳い','およい','泳ぐ','で','N'))
        for sf,rd,base,particle,state in cases:
            forms=(('動詞,自立,*,*','連用タ接続',base,rd),)
            with self.subTest(surface=sf),patch.object(R,'_modern_te_allowed',side_effect=lambda s,r,p:p==particle), \
                 patch.object(R,'_grammatical_suffix',side_effect=lambda tail,st:st==state and tail==particle) as check:
                self.assertTrue(R._allows_grammatical_tail(forms,particle,rd,sf))
                check.assert_called_once_with(particle,state)
            with patch.object(R,'_modern_te_allowed',return_value=None):
                self.assertFalse(R._allows_grammatical_tail(forms,particle,rd,sf))



    def test_completed_contraction_needs_a_verb_not_a_case_particle(self):
        a=('に','助詞:格助詞','に',0,1,True,'')
        b=('じまう','動詞:非自立','じまう',1,4,True,'基本形')
        forms=(('動詞,非自立,*,*','基本形','じまう','じまう'),)
        with patch.object(M,'dictionary_inflections',return_value=forms):
            self.assertTrue(O.contracted_aux_mismatch(a,b))
            self.assertFalse(O.contracted_aux_mismatch(('飛ん','動詞:自立','とん',0,1,True,'連用タ接続'),b))
            self.assertFalse(O.contracted_aux_mismatch(('と','助詞:格助詞','と',0,1,True,''),b))
        with patch.object(M,'dictionary_inflections',return_value=forms+(('動詞,自立,*,*','基本形','しまう','しまう'),)):
            self.assertFalse(O.contracted_aux_mismatch(a,b))

    def test_a_whole_kana_noun_is_not_split_into_a_polite_auxiliary(self):
        a,b=pair('名の読み','名詞:一般')
        with patch.object(O,'_kana_nominal_alternative',return_value=True):
            self.assertFalse(O.polite_aux_mismatch(a,b))
            a,b=pair('かな語','動詞:自立','体言接続特殊２')
            self.assertFalse(O.polite_aux_mismatch(a,b))



    def test_common_intact_gate_keeps_native_imperative_emphasis_in_original_context(self):
        import corrector as C
        from contextvars import ContextVar
        source=ContextVar('test_command_source',default='次へ進めい。')
        tokens=[('次','名詞:一般','つぎ',0,1,True,''),('へ','助詞:格助詞','へ',1,2,True,''),
                ('進め','動詞:自立','すすめ',2,4,True,'命令ｅ'),('い','助詞:終助詞','い',4,5,True,''),
                ('。','記号:句点','。',5,6,True,'')]
        with patch.object(C,'_CORRECTION_SOURCE',source):
            self.assertTrue(C._chunk_is_intact('進めい',lambda s:tokens))
            # The same substring in a nonterminal auxiliary chain is not protected.
            tokens[2]=('進め','動詞:自立','すすめ',2,4,True,'連用形')
            tokens[3]=('い','動詞:非自立','い',4,5,True,'連用形')
            self.assertFalse(C._chunk_is_intact('進めい',lambda s:tokens,context_only=True))


if __name__=='__main__':unittest.main()
