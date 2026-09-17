"""Shared source coordinates, reading evidence and physical-key contracts."""
import os
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch
import contextual_repair as R


def token(surface, reading, pos='名詞:一般', start=0, form=''):
    return (surface,pos,reading,start,start+len(surface),True,form)


class ContextualRepairTests(unittest.TestCase):
    def target(self, text, after=''):
        return R.RepairTarget(text+after,0,len(text),0,len(text+after),
                              (('異','様',0,len(text)),),True,after)

    def test_source_coordinates_do_not_move_with_replacement_length(self):
        t=R.RepairTarget('前\t対象です。後',2,4,2,7,(),True,'です')
        self.assertEqual(t.substitute('候補文字'),'候補文字です。')
        self.assertEqual(t.text,'対象')
        with self.assertRaises(FrozenInstanceError):t.start=0

    def test_physical_mark_is_one_substitution(self):
        with patch.dict(os.environ,{'CN_MARK_SLIP':'1'}):
            candidate=next(r for r in R.key_repairs('たふせ') if r.reading=='たぶ')
        self.assertEqual((candidate.operation,candidate.pressed,candidate.intended),
                         ('adjacent_substitution','せ','゛'))

    def test_mark_setting_is_checked_even_after_cached_neighbor_lookup(self):
        with patch.dict(os.environ,{'CN_MARK_SLIP':'1'}):R.key_repairs('たふせ')
        with patch.dict(os.environ,{'CN_MARK_SLIP':'0'}):
            self.assertNotIn('たぶ',[r.reading for r in R.key_repairs('たふせ')])

    def test_intrusion_must_be_a_physical_neighbor(self):
        candidates=R.key_repairs('もみと')
        self.assertTrue(any(r.reading=='もと' and r.operation=='adjacent_intrusion' for r in candidates))
        self.assertFalse(any(r.reading=='すぞう' and r.operation=='adjacent_intrusion'
                             for r in R.key_repairs('すなぞう')))

    def test_duplicate_default_and_override(self):
        with patch.dict(os.environ,{'CN_NO_DUP':'1'}):
            self.assertNotIn('か',[r.reading for r in R.key_repairs('かか')])
        with patch.dict(os.environ,{'CN_NO_DUP':'0'}):
            self.assertIn('か',[r.reading for r in R.key_repairs('かか')])

    def test_no_missing_key_is_added_by_the_one_stroke_stage(self):
        import kana_layout as K
        for reading in ('もみと','たふせ','かか','がぞう','しゅうりょ'):
            n=sum(len(K.keystrokes(c)) for c in reading)
            for row in R.key_repairs(reading):
                self.assertLessEqual(sum(len(K.keystrokes(c)) for c in row.reading),n)

    def test_chained_intrusion_uses_original_geometry_and_shift_identity(self):
        remote=R.KeyRepair('もじ','adjacent_intrusion',1,'ん','',1.0)
        shifted=R.KeyRepair('ちょう','adjacent_intrusion',2,'ょ','',1.0)
        adjacent=R.KeyRepair('もと','adjacent_intrusion',1,'み','',1.0)
        self.assertFalse(R._original_intrusion_allowed('もんじ',remote))
        self.assertFalse(R._original_intrusion_allowed('ちよょう',shifted))
        self.assertTrue(R._original_intrusion_allowed('もみと',adjacent))

    def test_lazy_search_cutoff_is_not_candidate_exhaustion(self):
        @R._with_search_report
        def search():
            while R._search_step('clause_key_tails',2):pass
            return None,dict(status='no_candidate')
        result,diagnostic=search()
        self.assertIsNone(result)
        self.assertEqual(diagnostic['status'],'unexplored_no_valid_candidate')
        self.assertEqual(diagnostic['search']['state'],'truncated')
        self.assertEqual(diagnostic['search']['limits']['clause_key_tails']['examined'],2)

    def test_known_inflection_is_not_split_into_character_guesses(self):
        t=self.target('読み直し')
        tk=lambda s:[token(s,'よみなおし','動詞:自立',form='連用形')]
        with patch('kanji_guess.ime_readings_for',return_value=[]), \
             patch('inflected_lexicon.dictionary_readings',return_value=('よみなおし',)), \
             patch('kanji_guess.reading_combos_with_evidence') as guessed:
            readings=R.reading_evidence(t,tk,None)
        self.assertEqual(readings[0].text,'よみなおし')
        guessed.assert_not_called()

    def test_saved_ime_pair_precedes_dictionary_reading(self):
        with patch('kanji_guess.ime_readings_for',return_value=['いめ']), \
             patch('inflected_lexicon.dictionary_readings',return_value=('じしょ',)):
            rows=R.reading_evidence(self.target('文字'),lambda s:[token(s,'じしょ')],None)
        self.assertEqual((rows[0].text,rows[0].source),('いめ','saved_ime_pair'))

    def test_candidate_reading_must_survive_in_context(self):
        target=self.target('異字','に戻る')
        def tk(s):
            if s=='看取に戻る':return [token('看取','かんしゅ'),token('に','に','助詞:格助詞',2),token('戻る','もどる','動詞:自立',3)]
            return [token(s,'かんしゅ')]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]):
            ok,why=R.validate(target,'看取',engine,tk,None,None,expected_reading='みと')
        self.assertFalse(ok);self.assertEqual(why,'reading_changed_in_context')

    def test_legacy_candidate_is_checked_in_the_original_context(self):
        target=self.target('異字','うを保存')
        seen=[]
        def odd(text,*a,**kw):
            seen.append(text);return [('画像','う',0,3)]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',side_effect=odd):
            ok,why=R.validate(target,'画像',engine,lambda s:[],None,None)
        self.assertFalse(ok);self.assertEqual(why,'context_still_anomalous')
        self.assertEqual(seen,['画像うを保存'])

    def test_absence_of_anomaly_does_not_start_reading_search(self):
        with patch('oddness.is_odd_run',return_value=[]):
            self.assertEqual(R.targets_for_line('自然な文章',lambda s:[],None,None),[])

    def test_disjoint_edits_and_empty_replacement(self):
        self.assertEqual(R._apply('あいうえお',[(1,2,''),(3,5,'後')]),'あう後')
        with self.assertRaises(ValueError):R._apply('あいうえお',[(1,4,''),(2,5,'後')])

    def test_joint_validation_tries_the_next_candidate(self):
        source='甲、乙'
        targets=[R.RepairTarget(source,a,a+1,0,3,(),True,'') for a in (0,2)]
        diagnostics=[dict(start=a,end=a+1,candidates=[
            dict(surface=sf,repair=dict(reading='よみ')) for sf in choices])
            for a,choices in ((0,('A','AA')),(2,('B','BB')))]
        def check(target,surface,*args):
            companions=args[-1]
            return (not (surface=='B' and any(c[2]=='A' for c in companions)), 'joint_connection')
        with patch.object(R,'validate',side_effect=check):
            got=R._validate_joint_choices([(0,1,'A'),(2,3,'B')],[],targets,diagnostics,
                                          None,None,None,None,None)
        self.assertEqual(R._apply(source,got),'A、BB')
        self.assertEqual(diagnostics[1]['status'],'selected_after_joint_validation')

    def test_joint_validation_keeps_the_selected_owner_at_same_coordinates(self):
        first=self.target('甲');second=R.RepairTarget('甲',0,1,0,1,(),True,'','kana_predicate')
        diagnostics=[dict(start=0,end=1,candidates=[dict(surface='A',repair=dict(reading=reading))])
                     for reading in ('first','second')]
        seen=[]
        def check(target,surface,*args):
            seen.append((target,args[-2]));return True,''
        owner={(0,1,'A'):(first,diagnostics[0])}
        with patch.object(R,'validate',side_effect=check):
            got=R._validate_joint_choices([(0,1,'A')],[],[first,second],diagnostics,
                                          None,None,None,None,None,owner)
        self.assertEqual(got,[(0,1,'A')])
        self.assertEqual(seen,[(first,'first')])

    def test_unknown_ime_sequence_can_use_kun_without_written_okurigana(self):
        t=self.target('未知')
        tk=lambda s:[(s,'名詞:一般',s,0,len(s),False,'')]
        with patch('kanji_guess.ime_readings_for',return_value=[]), \
             patch('inflected_lexicon.dictionary_readings',return_value=()), \
             patch('kanji_guess.reading_combos_with_evidence',return_value=[dict(reading='おん',rank=0)]), \
             patch('kanji_guess.readings_for_char',side_effect=lambda c,d:['く'] if c=='未' else ['ん']):
            rows=R.reading_evidence(t,tk,None)
        self.assertIn('くん',[r.text for r in rows])

    def test_pos_must_be_the_one_in_context_not_the_isolated_word(self):
        t=self.target('悪けれ','ではない')
        def tk(s):
            if s=='分けれではない':
                return [token('分けれ','わけれ','動詞:自立',form='仮定形'),
                        token('で','で','助動詞',3,form='連用形'),token('は','は','助詞:係助詞',4),
                        token('ない','ない','助動詞',5)]
            return [token(s,'わけれ','動詞:自立',form='連用形')]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]):
            ok,why=R.validate(t,'分けれ',engine,tk,None,None,expected_reading='わけれ')
        self.assertFalse(ok);self.assertEqual(why,'conditional_slot')

    def test_inflected_index_does_not_change_the_normal_candidate_pool(self):
        from dict_index import DictIndex
        import dict_index as D
        entries=[('読み直し','よみなおし','動詞','自立','*',7002),
                 ('保存','ほぞん','名詞','サ変接続','*',1000),
                 ('架空人名','かくうじんめい','名詞','固有名詞','人名',1000)]
        index=DictIndex()
        with patch.object(D,'iter_janome_entries',return_value=iter(entries)):
            index._build()
        self.assertEqual(index.surfaces_for_reading('よみなおし'),[])
        self.assertEqual(index.inflected_surfaces_for_reading('よみなおし'),('読み直し',))
        self.assertEqual(index.inflected_surfaces_for_reading('かくうじんめい'),())
        self.assertIn('保存',index.surfaces_for_reading('ほぞん'))

    def test_first_run_vocabulary_and_dictionary_share_the_candidate_pool(self):
        store=SimpleNamespace(lookup=lambda r:[dict(surface='記録')])
        dictionary=SimpleNamespace(surfaces_for_reading=lambda *a,**kw:[],
                                   inflected_surfaces_for_reading=lambda r:())
        self.assertEqual(R._surfaces('きろく',store,dictionary),['記録'])


    def test_unknown_kana_does_not_swallow_its_particle_and_known_context(self):
        line='昨日ぴっぐるすを見ました。'
        parts=[token('昨日','きのう','名詞:副詞可能'),
               ('ぴっぐるすを','名詞:一般','ぴっぐるすを',2,8,False,''),
               token('見','み','動詞:自立',8,form='連用形'),
               token('まし','まし','助動詞',9),token('た','た','助動詞',11)]
        with patch('oddness.is_odd_run',return_value=[('昨日','ぴっぐるすを',0,8)]):
            targets=R.targets_for_line(line,lambda s:parts,None,None)
        self.assertEqual(targets,[])  # 読みが見える本文へIME逆変換を重ねない

    def test_polite_auxiliary_cannot_follow_a_noun_candidate(self):
        target=self.target('に行き','ます')
        def tk(s):
            if s=='人気ます':return [token('人気','にんき'),token('ます','ます','助動詞',2)]
            return [token(s,'にんき')]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]):
            ok,why=R.validate(target,'人気',engine,tk,None,None,expected_reading='にんき')
        self.assertFalse(ok);self.assertEqual(why,'polite_auxiliary_slot')


    def test_adjectival_noun_needs_a_particle_before_suru(self):
        target=self.target('旧明井','します')
        def tk(s):
            if s=='不快します':return [token('不快','ふかい','名詞:形容動詞語幹'),
                                      token('し','し','動詞:自立',2,'連用形'),token('ます','ます','助動詞',3)]
            return [token(s,'ふかい','名詞:形容動詞語幹')]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]):
            ok,why=R.validate(target,'不快',engine,tk,None,None,expected_reading='ふかい')
        self.assertFalse(ok);self.assertEqual(why,'suru_slot')

    def test_unfinished_inflection_cannot_be_rescued_by_noun_fragments(self):
        target=self.target('早かろ','を確認する')
        def tk(s):
            if s=='はかろ':return [token(s,s,'動詞:自立',form='未然ウ接続')]
            if s=='はかろを確認する':return [token('はか','はか'),token('ろ','ろ',start=2),
                    token('を','を','助詞:格助詞',3),token('確認','かくにん','名詞:サ変接続',4)]
            return [token(s,s)]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]), \
             patch('inflected_lexicon.has_nominal_entry',return_value=False):
            ok,why=R.validate(target,'はかろ',engine,tk,None,None,expected_reading='はかろ')
        self.assertFalse(ok);self.assertEqual(why,'incomplete_inflection_before_nominal_particle')

    def test_real_nominal_dictionary_alternative_survives(self):
        target=self.target('未知字','を確認する')
        def tk(s):
            if s=='候補':return [token(s,'こうほ','動詞:自立',form='仮定形')]
            if s=='候補を確認する':return [token('候補','こうほ'),token('を','を','助詞:格助詞',2)]
            return [token(s,s)]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]), \
             patch('inflected_lexicon.has_nominal_entry',return_value=True):
            ok,_=R.validate(target,'候補',engine,tk,None,None,expected_reading='こうほ')
        self.assertTrue(ok)

    def test_unambiguous_polite_tail_is_context_even_after_a_mistyped_noun(self):
        line='移歯ます'
        parts=[token('移','い'),token('歯','は',start=1),token('ます','ます','助動詞',2)]
        with patch('oddness.is_odd_run',return_value=[('歯','ます',1,4)]), \
             patch('morphology.dictionary_inflections',return_value=None):
            targets=R.targets_for_line(line,lambda s:parts,None,None)
        # 構造的に異様な漢字2字も読み直す。正しい語尾は文脈に残す。
        self.assertEqual([(t.text,t.following,t.structural) for t in targets],
                         [('移歯','ます',True)])

    def test_context_material_uses_distance_not_sentence_order(self):
        line='遠語を近語に対象を後語する。'
        target=R.RepairTarget(line,6,8,0,len(line),(),True,line[8:])
        parts=[token('遠語','えんご',start=0),token('近語','きんご',start=3),
               token('対象','たいしょう',start=6),token('後語','ごご',start=9)]
        self.assertEqual(R.context_material(target,lambda s:parts),('近語','後語','遠語'))
        # 文中の別区画でも、文脈座標を原文座標へ取り違えない。
        shifted=R.RepairTarget('別欄\t'+line,9,11,3,3+len(line),(),True,line[8:])
        self.assertEqual(R.context_material(shifted,lambda s:parts),('近語','後語','遠語'))

    def test_nominal_suffix_resplit_keeps_absolute_source_coordinates(self):
        import morphology as M
        parts=[M.Token('透','名詞','透','とう',5,6,True,'一般'),
               M.Token('明度','名詞','明度','めいど',6,8,True,'一般')]
        with patch.object(M,'_nominal_suffix_parts',return_value=('透明','とうめい','一般','','度','ど')):
            got=M._restore_nominal_suffix_boundaries(parts)
        self.assertEqual([(t.surface,t.reading,t.start,t.end,t.pos_sub) for t in got],
                         [('透明','とうめい',5,7,'一般'),('度','ど',7,8,'接尾:一般')])
        self.assertEqual(''.join(t.surface for t in got),'透明度')

    def test_suffix_resplit_does_not_cross_spaces_or_reclassify_names(self):
        import morphology as M
        a=M.Token('透','名詞','透','とう',0,1,True,'一般')
        gap=M.Token('明度','名詞','明度','めいど',2,4,True,'一般')
        name=M.Token('明度','名詞','明度','めいど',1,3,True,'固有名詞:人名:名')
        with patch.object(M,'_nominal_suffix_parts') as split:
            self.assertEqual(M._restore_nominal_suffix_boundaries([a,gap]),[a,gap])
            self.assertEqual(M._restore_nominal_suffix_boundaries([a,name]),[a,name])
        split.assert_not_called()

    def test_suffix_resplit_requires_a_single_registered_nominal_root(self):
        import morphology as M
        M._nominal_suffix_parts.cache_clear()
        entries=(('名詞,接尾,一般,*','*','度','ど'),)
        root=M.Token('透明','名詞','透明','とうめい',0,2,True,'一般')
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'dictionary_inflections',return_value=entries), \
             patch.object(M,'_tokenize_janome',return_value=[root]):
            self.assertEqual(M._nominal_suffix_parts('透明度')[1],'とうめい')
        M._nominal_suffix_parts.cache_clear()
        with patch.object(M,'HAS_JANOME',True),patch.object(M,'dictionary_inflections',return_value=entries), \
             patch.object(M,'_tokenize_janome',return_value=[]):
            self.assertIsNone(M._nominal_suffix_parts('透明度'))
        M._nominal_suffix_parts.cache_clear()


    def test_two_repairs_of_one_connection_are_not_composed(self):
        source='甲ぼて、乙'
        target=R.RepairTarget(source,0,2,0,len(source),(('甲ぼ','て',0,3),),True,'て、乙')
        old=[(0,1,'かな'),(2,3,'う'),(4,5,'丙')]
        selected=[(0,2,'甲べ')]
        kept=R._retain_independent_changes(old,selected,[target])
        self.assertEqual(kept,[(4,5,'丙')])
        self.assertEqual(R._apply(source,kept+selected),'甲べて、丙')

    def test_no_new_candidate_keeps_independent_legacy_changes(self):
        target=self.target('対象')
        old=[(0,1,'甲')]
        self.assertEqual(R._retain_independent_changes(old,[],[target]),old)


    def test_explicit_polite_predicate_cannot_turn_into_a_bare_noun(self):
        source='語を旧ます'
        target=R.RepairTarget(source,2,5,0,5,(('旧','ます',2,5),),True,'','auxiliary_connection')
        def tk(s):
            if s in ('語を旧ます','語を候補'):
                return [token('語','ご'),token('を','を','助詞:格助詞',1),token(s[2:],s[2:],start=2)]
            if s=='旧ます':return [token('旧','きゅう'),token('ます','ます','助動詞',1)]
            return [token(s,s)]
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]),patch('oddness.polite_aux_mismatch',return_value=True):
            self.assertEqual(R.validate(target,'候補',engine,tk,None,None),(False,'predicate_replaced_with_noun'))


    def test_reading_keeps_the_inflection_found_in_original_context(self):
        line='本を貸さって帰る'
        t=R.RepairTarget(line,2,6,0,len(line),(('貸さ','って',2,6),),True,line[6:],'auxiliary_connection')
        full=[token('本','ほん'),token('を','を','助詞:格助詞',1),
              token('貸さ','かさ','動詞:自立',2,'未然形'),token('って','って','助詞:格助詞',4),
              token('帰る','かえる','動詞:自立',6,'基本形')]
        cut=[token('貸','かし'),token('さ','さ',start=1),token('って','って','助詞:格助詞',2)]
        with patch('kanji_guess.ime_readings_for',return_value=[]), \
             patch('inflected_lexicon.dictionary_readings',return_value=()):
            readings=R.reading_evidence(t,lambda x:full if x==line else cut,None)
        self.assertEqual(readings[0].text,'かさって')
        self.assertEqual(readings[0].source,'contextual_token_sequence')
        self.assertEqual(readings[0].segments[0][:2],(0,2))

    def test_in_context_reading_does_not_override_a_saved_whole_ime_pair(self):
        t=self.target('漢字')
        tk=lambda s:[token(s,'かんじ')]
        with patch('kanji_guess.ime_readings_for',side_effect=lambda s:['かんし'] if s=='漢字' else []), \
             patch('inflected_lexicon.dictionary_readings',return_value=()):
            rows=R.reading_evidence(t,tk,None)
        self.assertEqual((rows[0].text,rows[0].source),('かんし','saved_ime_pair'))
        self.assertIn('かんじ',[r.text for r in rows])



    def test_completed_word_ranks_before_an_unfinished_auxiliary_without_banning_it(self):
        def tk(s):
            if s=='候補て尾':return [token('候補','こうほ','動詞:自立',form='連用形'),
                token('て','て','助詞:接続助詞',2),token('尾','お','動詞:非自立',3,'連用形')]
            if s=='ます':return [token('ます','ます','助動詞')]
            if s=='、':return [token('、','、','記号:読点')]
            return [token(s,s)]
        self.assertTrue(R._terminal_auxiliary_fragment('候補て尾','',tk))
        self.assertFalse(R._terminal_auxiliary_fragment('候補て尾','ます',tk))
        self.assertFalse(R._terminal_auxiliary_fragment('候補て尾','、',tk))
        self.assertFalse(R._terminal_auxiliary_fragment('完成語','',tk))


    def suffix_candidate(self,surface,pos,form,after='て',new_suffix_pos='助詞:接続助詞',allowed=True,in_context_pos=None):
        target=self.target('誤字',after)
        def tk(text):
            if text=='誤字'+after:
                return [token('誤字','ごじ'),token(after,after,'助詞:接続助詞',2)]
            if text==surface:
                return [token(surface,surface,pos,form=form)]
            if text==surface+after:
                return [token(surface,surface,in_context_pos or pos,form=form),
                        token(after,after,new_suffix_pos,len(surface))]
            return []
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        with patch('oddness.is_odd_run',return_value=[]), \
             patch('oddness.preserves_bound_verb',return_value=True), \
             patch.object(R,'_modern_te_allowed',return_value=allowed) as proof:
            return R.validate(target,surface,engine,tk,None,None),proof

    def test_unchanged_connective_checks_the_candidate_native_euphony(self):
        result,proof=self.suffix_candidate('漕ぎ','動詞:自立','連用形',allowed=False)
        self.assertEqual(result,(False,'euphonic_following_slot'))
        proof.assert_called_with('漕ぎ','漕ぎ','て')

    def test_original_connective_does_not_turn_into_nominal_case_for_new_noun(self):
        result,proof=self.suffix_candidate('ブギ','名詞:一般','',
            new_suffix_pos='助詞:格助詞:連語')
        self.assertEqual(result,(False,'continuative_following_slot'))
        proof.assert_not_called()

    def test_grammatical_continuative_and_unclassified_modern_form_are_not_rejected(self):
        for allowed in (True,None):
            result,_=self.suffix_candidate('書い','動詞:自立','連用タ接続',allowed=allowed)
            self.assertEqual(result,(True,'accepted'))

    def test_conditional_auxiliary_has_its_own_connection_but_native_role_is_required(self):
        rows=(('助動詞,*,*,*','仮定形','た','たら'),)
        with patch('morphology.dictionary_inflections',return_value=rows):
            self.assertTrue(R._self_contained_conditional(token('たら','たら','助動詞',form='仮定形')))
            self.assertFalse(R._self_contained_conditional(token('たら','たら','名詞:一般',form='仮定形')))
            self.assertFalse(R._self_contained_conditional(token('たら','別読み','助動詞',form='仮定形')))
        with patch('morphology.dictionary_inflections',return_value=(('動詞,自立,*,*','仮定形','たる','たら'),)):
            self.assertFalse(R._self_contained_conditional(token('たら','たら','助動詞',form='仮定形')))


    def test_native_verbal_homograph_takes_its_role_in_the_changed_clause(self):
        result,proof=self.suffix_candidate('調べ','名詞:一般','連用形',
            in_context_pos='動詞:自立')
        self.assertEqual(result,(True,'accepted'))
        proof.assert_called_with('調べ','調べ','て')

    def interjection_candidate(self,native=True,original_interjection=False):
        source='読んであうげます';surface='あかげます';changed='読んで'+surface
        target=R.RepairTarget(source,3,8,0,8,(('げ','ます',5,8),),True,'','auxiliary_connection')
        prefix=[token('読ん','よん','動詞:自立',0,'連用タ接続'),token('で','で','助詞:接続助詞',2)]
        original=prefix+[token('あう','あう','動詞:非自立',3,'基本形'),
                         token('げ','げ','名詞:接尾:一般',5),token('ます','ます','助動詞',6,'基本形')]
        cut=[token('あ','あ','フィラー'),token('う','う','形容詞:自立',1,'ガル接続'),
             token('げ','げ','名詞:接尾:一般',2),token('ます','ます','助動詞',3,'基本形')]
        cand=[token('あ','あ','フィラー'),token('かげ','かげ','動詞:自立',1,'連用形'),
              token('ます','ます','助動詞',3,'基本形')]
        if original_interjection:
            original=prefix+[t[:3]+(t[3]+3,t[4]+3)+t[5:] for t in cut]
        actual=prefix+[t[:3]+(t[3]+3,t[4]+3)+t[5:] for t in cand]
        def tk(text):
            return {source:original,changed:actual,'あうげます':cut,surface:cand}.get(text,[])
        engine=SimpleNamespace(_check_replacement=lambda source,c,*a,**kw:(c,None))
        entries=(('動詞,非自立,*,*','基本形','あう','あう'),) if native else ()
        with patch('oddness.is_odd_run',return_value=[]), \
             patch('oddness.preserves_completed_modifier',return_value=True), \
             patch('oddness.preserves_bound_verb',return_value=True), \
             patch('morphology.dictionary_inflections',return_value=entries):
            return R.validate(target,surface,engine,tk,None,None)

    def test_original_context_predicate_cannot_become_a_new_interjection(self):
        self.assertEqual(self.interjection_candidate(),(False,'predicate_replaced_with_interjection'))

    def test_existing_interjection_does_not_acquire_a_new_predicate_constraint(self):
        self.assertEqual(self.interjection_candidate(original_interjection=True),(True,'accepted'))

    def test_unproven_original_predicate_is_not_a_new_negative_judgement(self):
        self.assertEqual(self.interjection_candidate(native=False),(True,'accepted'))


if __name__=='__main__':unittest.main()
