# -*- coding: utf-8 -*-
"""General argument roles rank candidates only after a grammatical repair exists."""
import unittest
from unittest.mock import patch
import morphology as M
import semantic_roles as S


class SemanticRoleTests(unittest.TestCase):
    @unittest.skipUnless(M.HAS_JANOME,'native lexical and potential meanings')
    def test_lexical_ichidan_meaning_precedes_possible_godan_derivation(self):
        for surface in ('あけ','開け'):
            roles=S.native_verb_roles(surface,'連用形','あけ',tail='て')
            self.assertIn('physical_opening',roles)
            self.assertNotIn('text',roles)
        self.assertIn('text',S.native_verb_roles('ひらい','連用タ接続','ひらい',tail='て'))
        self.assertIn('text',S.native_verb_roles('読め','連用形','よめ',tail='ます'))

    def test_drawing_and_borrowed_venues_keep_distinct_positive_senses(self):
        for noun in ('線','曲線','平行線'):
            self.assertTrue(S.support(noun,'引く'),noun)
            self.assertFalse(S.support(noun,'借りる'),noun)
        for noun in ('会議室','体育館','講堂'):
            self.assertTrue(S.support(noun,'借りる'),noun)
            self.assertFalse(S.support(noun,'引く'),noun)
        self.assertFalse(S.support('海上','借りる'))
        self.assertFalse(S.support('会場','食べる'))



    def test_schedule_inspection_does_not_supply_physical_object_roles(self):
        for noun in ('予定','日程','計画','期日','待ち合わせ'):
            self.assertTrue(S.support(noun,'見る'),noun)
            self.assertFalse(S.support(noun,'食べる'),noun)
            self.assertFalse(S.support(noun,'飲む'),noun)


    def test_input_and_output_share_information_not_food_meaning(self):
        for noun in ('入力','出力'):
            self.assertIn('information',S.nominal_roles(noun))
            for verb in ('使う','読む','保存'):
                self.assertTrue(S.support(noun,verb),(noun,verb))
            self.assertFalse(S.support(noun,'食べる'),noun)


    @unittest.skipUnless(M.HAS_JANOME,'native action noun meaning')
    def test_investigation_accepts_processes_without_making_them_edible(self):
        import reading_segments as R
        for noun in ('確認','保存','作業'):
            self.assertTrue(S.support(noun,'調べる'),noun)
            self.assertFalse(S.support(noun,'食べる'),noun)
        self.assertTrue(R.native_object_predicate_proof('資料確認を調べます',5,('確認',)))


    @unittest.skipUnless(M.HAS_JANOME,'native focus particles and case boundaries')
    def test_focus_particle_keeps_the_same_original_argument(self):
        def tok(text):
            return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,
                     t.has_reading,t.infl_form) for t in M.tokenize(text)]
        for text,noun in (('箱だけを起きます','箱'),('資料だけを読む','資料'),
                ('図面ばかりを確認する','図面'),('手紙のみを読む','手紙')):
            with self.subTest(text=text):
                self.assertEqual(S.object_before(text,text.index('を')+1,tok),noun)
        for text in ('未知語ぷねだけを起きます','を起きます','だけを起きます'):
            self.assertFalse(S.object_before(text,text.index('を')+1,tok),text)
        text='図書館だけで資料だけを読む'
        self.assertEqual(S.object_before(text,text.index('読む'),tok),'資料')
        self.assertEqual(S.case_argument_before(text,text.index('読む'),tok,True),('図書館','で'))
        parts=tok('箱だけを起きます')
        focus=next(i for i,p in enumerate(parts) if p[0]=='だけ')
        parts[focus]=parts[focus][:5]+(False,)+parts[focus][6:]
        self.assertFalse(S.object_before('箱だけを起きます',4,lambda _:parts))

    @unittest.skipUnless(M.HAS_JANOME,'native focus-particle correction')
    def test_focus_particle_reaches_existing_conflict_and_final_validation(self):
        import app
        from tests_analysis_async import initial
        state=initial()
        for source,expected in (
                ('小さな箱だけを起きます。','小さな箱だけを置きます。'),
                ('荷物だけを起きます。','荷物だけを置きます。'),
                ('荷物だけを置きます。','荷物だけを置きます。'),
                ('資料だけを読みます。','資料だけを読みます。'),
                ('朝だけ起きます。','朝だけ起きます。')):
            result=app.correct_line(source,state.store,input_method='kana',
                dict_index=state.dict_index,decisions=state.decisions,context_vec=None)
            with self.subTest(source=source):
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')


    @unittest.skipUnless(M.HAS_JANOME,'native issue and suru predicate')
    def test_issue_resolution_proves_the_actual_accusative(self):
        for noun in ('問題','課題','不具合','矛盾'):
            with self.subTest(noun=noun):
                proof=S.candidate_evidence(noun,'解決し','ます',before=noun+'を')
                self.assertIn('issue',proof['shared_roles'])
        for noun in ('石','人','資料'):
            with self.subTest(noun=noun):
                proof=S.candidate_evidence(noun,'解決し','ます',before=noun+'を')
                self.assertFalse(proof and proof['shared_roles'])
        self.assertIsNone(S.candidate_evidence('未知ぷねら','解決し','ます',before='未知ぷねらを'))
        proof=S.candidate_evidence('問題','解決し','ます',before='問題に',case='に')
        self.assertFalse(proof and proof['shared_roles'])


    @unittest.skipUnless(M.HAS_JANOME,'native table-field predicate boundaries')
    def test_terminal_action_owns_only_its_tab_or_arrow_field(self):
        def conflicts(text):
            tokens=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,
                     t.has_reading,t.infl_form) for t in M.tokenize(text)]
            return S.conflicting_object_predicates(text,tokens)
        for text in ('いとをさして','\t\tいとをさして⇒\t\t',
                     '意図をさして⇒説明','意図をさして\t資料を確認します'):
            with self.subTest(text=text):
                self.assertTrue(conflicts(text))
        for text in ('意図をさしている人','意図をさして、発言します',
                     '針をさして⇒説明','未知ぷねらをさして⇒説明'):
            with self.subTest(text=text):
                self.assertFalse(conflicts(text))

    @unittest.skipUnless(M.HAS_JANOME,'native focus spelling evidence')
    def test_focus_argument_is_shared_with_final_nominal_spelling(self):
        for noun,tail in (('物','だけを置きます'),('資料','のみを読みます'),
                          ('手紙','ばかりを読みます')):
            with self.subTest(noun=noun,tail=tail):
                proof=S.candidate_object_evidence(noun,tail)
                self.assertTrue(proof and proof['shared_roles'])
                self.assertTrue(S.candidate_nominal_spelling_evidence('',noun,tail))
        for noun,tail in (('者','だけを置きます'),('ぷねら','だけを置きます'),
                          ('物','だけでを置きます'),('物','だけ')):
            with self.subTest(noun=noun,tail=tail):
                proof=S.candidate_object_evidence(noun,tail)
                self.assertFalse(proof and proof['shared_roles'])

    def tearDown(self):
        S._action_head.cache_clear()
        S.predicate_roles.cache_clear()
        S.native_verb_roles.cache_clear()

    @unittest.skipUnless(M.HAS_JANOME,'native argument boundaries')
    def test_internal_argument_uses_the_same_written_noun_roles(self):
        proof=S.candidate_internal_argument_evidence('食器を洗って','')
        self.assertTrue(proof and proof['shared_roles'])
        self.assertEqual(proof['object'],'食器')
        self.assertEqual(proof['source'],'candidate_internal_argument')
        self.assertIsNone(S.candidate_internal_argument_evidence('式を洗って',''))
        self.assertIsNone(S.candidate_internal_argument_evidence('洗って','',before='食器を'))
        self.assertIsNone(S.candidate_internal_argument_evidence('食器','を洗って'))
        self.assertIsNone(S.candidate_internal_argument_evidence('食器を','洗って'))

    @unittest.skipUnless(M.HAS_JANOME,'native reference nouns and predicates')
    def test_opening_reference_material_keeps_original_spelling_and_case(self):
        import app,reading_segments as R
        from tests_analysis_async import initial
        a=initial()
        for noun in ('辞書','辞典','索引','史料'):
            for verb in ('開く','閉じる'):
                self.assertTrue(S.support(noun,verb),(noun,verb))
            self.assertFalse(S.support(noun,'食べる'),noun)
        # じてん can mean 辞典 or 事典; the context does not distinguish them.
        for text in ('じしょをひらく。','じてんをひらきます。','さくいんをとじます。',
                     '辞書を開きます。','辞典を閉じます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            expected={'じしょをひらく。':'辞書を開く。','さくいんをとじます。':'索引を閉じます。'}.get(text,text)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result.get('odd_spans'),text)
        self.assertFalse(R.completed_native_reading_clause('じしょをのむ',require_object_fit=True))
        self.assertFalse(R.completed_native_reading_clause('じしょをひら',require_object_fit=True))

    def test_roles_supply_positive_evidence_without_declaring_other_senses_invalid(self):
        self.assertTrue(S.support('理由','説明'))
        self.assertTrue(S.support('結果','記録'))
        self.assertTrue(S.support('本','再版'))
        self.assertTrue(S.support('資金','寄付'))
        self.assertFalse(S.support('理由','再版'))
        self.assertFalse(S.support('未知','説明'))
        self.assertFalse(S.support('理由','未知'))

    @unittest.skipUnless(M.dictionary_inflections('食器'),'requires native dictionary')
    def test_original_kana_accusative_shares_native_noun_evidence(self):
        for noun in ('食器','しょっき'):
            proof=S.candidate_evidence(noun,'あらってたなにもどします','',before=noun+'を')
            self.assertTrue(proof and proof['shared_roles'],noun)
            self.assertIsNone(S.candidate_evidence(noun,'ふらっとたなにもどします','',before=noun+'を'))
        for noun in ('布施','ふせ','しらゆほ'):
            proof=S.candidate_evidence(noun,'あらいます','',before=noun+'を')
            self.assertFalse(proof and proof['shared_roles'],noun)
        self.assertFalse(S.candidate_evidence('水','食べます','')['shared_roles'])

    @unittest.skipUnless(M.dictionary_inflections('食器'),'requires native dictionary')
    def test_kana_object_evidence_reaches_candidate_rank(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text,expected in (
            ('しょっきをふらってたなにもどします。','食器を洗って棚に戻します。'),
            ('しょっきをあらってたなにもどします。','食器を洗って棚に戻します。'),
            ('しょっきをあらってはたなにもどします。','食器を洗っては棚に戻します。')):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertIn(result['corrected'],expected if isinstance(expected,tuple) else (expected,),text)
            self.assertEqual(result.get('odd_spans'),[],text)

    @unittest.skipUnless(M.dictionary_inflections('保存'),'requires native dictionary')
    def test_kana_and_written_suru_actions_share_the_same_object_proof(self):
        for noun in ('データ','でーた'):
            written=S.candidate_evidence(noun,'保存','します',before=noun+'を')
            kana=S.candidate_evidence(noun,'ほぞん','します',before=noun+'を')
            self.assertTrue(written and written['shared_roles'])
            self.assertTrue(kana and kana['shared_roles'])
            self.assertEqual(kana['shared_roles'],written['shared_roles'])
        for action in ('せいり','整理'):
            self.assertTrue(S.candidate_evidence('しりょう',action,'してください')['shared_roles'])
        for noun,action,tail in (('野菜','ほぞん','しますです'),('野菜','せいり','のため'),
                                 ('資料','にく','します'),('資料','せいり','し')):
            proof=S.candidate_evidence(noun,action,tail)
            self.assertFalse(proof and proof['shared_roles'],(noun,action,tail))

    def test_food_drink_and_medicine_do_not_share_every_action(self):
        self.assertTrue(S.support('野菜','調理'))
        self.assertTrue(S.support('薬','服用'))
        for obj,verb in (('野菜','飲む'),('水','食べる'),('薬','食べる'),('人','キス')):
            with self.subTest(obj=obj,verb=verb):
                self.assertFalse(S.support(obj,verb))

    def test_explicit_accusative_head_keeps_original_boundary(self):
        ts=[('理由','名詞:一般','りゆう',0,2,True,''),
            ('を','助詞:格助詞:一般','を',2,3,True,'')]
        self.assertEqual(S.object_before('理由を説明',3,lambda s:ts),'理由')
        self.assertEqual(S.object_before('理由を 説明',4,lambda s:ts),'')
        self.assertEqual(S.object_before('理由を説明',2,lambda s:ts),'')
        self.assertEqual(S.object_before('理由に説明',3,lambda s:[ts[0],('に',)+ts[1][1:]]),'')

    def test_names_unknowns_suffixes_and_gaps_do_not_become_argument_evidence(self):
        p=('を','助詞:格助詞:一般','を',2,3,True,'')
        # A separately classified ordinary sense survives a proper-name
        # best parse; an unclassified name supplies no argument evidence.
        self.assertEqual(S.object_before('架名を説明',3,lambda s:[
            ('架名','名詞:固有名詞:人名','かめい',0,2,True,''),p]),'')
        self.assertEqual(S.object_before('理由を説明',3,lambda s:[
            ('理由','名詞:固有名詞:人名','りゆう',0,2,True,''),p]),'理由')
        for n in (('理由','名詞:一般','りゆう',0,2,False,''),
                  ('理由','名詞:接尾:一般','りゆう',0,2,True,''),
                  ('理由','名詞:一般','りゆう',0,1,True,'')):
            self.assertEqual(S.object_before('理由を説明',3,lambda s:[n,p]),'')

    def test_nominal_role_requires_the_actual_suru_connection(self):
        noun=M.Token('説明','名詞','説明','せつめい',0,2,True,'サ変接続')
        suru=M.Token('し','動詞','する','し',0,1,True,'自立','連用形')
        no=M.Token('の','助詞','の','の',0,1,True,'連体化')
        def native(text):
            if text=='説明':return [noun]
            if text=='説明します':return [noun,M.Token('し','動詞','する','し',2,3,True,'自立','連用形')]
            if text=='説明のため':return [noun,M.Token('の','助詞','の','の',2,3,True,'連体化')]
            return [suru] if text=='します' else [no]
        with patch.object(M,'tokenize',side_effect=native), \
             patch.object(M,'native_suru_form',side_effect=lambda sf,form,rd,*args:(sf,form,rd)==('し','連用形','し')):
            self.assertTrue(S.candidate_support('理由','説明','します'))
            self.assertFalse(S.candidate_support('理由','説明','のため'))
        self.assertFalse(S.candidate_support('未知','説明','します'))

    def test_inflected_predicate_uses_its_native_base_and_reading(self):
        verb=M.Token('並べ','動詞','並べる','ならべ',0,2,True,'自立','連用形')
        entries=(('動詞,自立,*,*','連用形','並べる','ならべ'),
                 ('動詞,自立,*,*','命令ｅ','別の原形','べつ'))
        with patch.object(M,'tokenize',return_value=[verb]),patch.object(M,'dictionary_inflections',return_value=entries):
            self.assertTrue(S.candidate_support('書類','並べました',''))
            self.assertFalse(S.candidate_support('理由','並べました',''))

    def test_homographic_noun_uses_the_verb_role_in_its_actual_te_context(self):
        noun=M.Token('片付け','名詞','片付け','かたづけ',0,3,True,'一般')
        verb=M.Token('片付け','動詞','片付ける','かたづけ',0,3,True,'自立','連用形')
        te=M.Token('て','助詞','て','て',3,4,True,'接続助詞')
        forms=(('動詞,自立,*,*','連用形','片付ける','かたづけ'),)
        S.native_verb_roles.cache_clear()
        with patch.object(M,'tokenize',side_effect=lambda text:[verb,te] if text=='片付けて' else [noun]), \
             patch.object(M,'dictionary_inflections',return_value=forms):
            self.assertTrue(S.candidate_support('道具','片付け','て'))
            self.assertFalse(S.predicate_roles('片付け'))

    def test_actual_left_context_keeps_homographic_verb_reading(self):
        verb=M.Token('並べ','動詞','並べる','ならべ',3,5,True,'自立','連用形')
        adverb=M.Token('並べて','副詞','並べて','なべて',0,3,True,'一般')
        entries=(('動詞,自立,*,*','連用形','並べる','ならべ'),)
        with patch.object(M,'tokenize',side_effect=lambda text:[verb] if text.startswith('荷物を') else [adverb]), \
             patch.object(M,'dictionary_inflections',return_value=entries):
            self.assertIsNone(S.candidate_evidence('荷物','並べ','てから'))
            e=S.candidate_evidence('荷物','並べ','てから',before='荷物を')
            self.assertEqual(e['shared_roles'],['object'])

    def test_candidate_compound_needs_an_operation_or_lexical_relation(self):
        with patch('seed_japanese.is_unit',return_value=False):
            for left,right in (('自動','入力'),('簡易','入力'),('右','スクロール'),('かな','入力'),('カタカナ','入力'),('本人','確認'),('巨人','確認')):
                self.assertTrue(S.nominal_compound_support(left,right),(left,right))
            for left,right in (('意味','ストール'),('文書','乳力'),('右','インストール'),('本人','飲む'),('巨人','服用')):
                self.assertFalse(S.nominal_compound_support(left,right),(left,right))

    @unittest.skipUnless(M.HAS_JANOME,'native common noun boundaries')
    def test_compound_content_relation_is_shared_by_source_and_candidate(self):
        import app,oddness,reading_segments as R
        from tests_analysis_async import initial
        for left,right in (('炭酸','湯'),('温泉','湯'),('薬草','湯'),
                           ('香草','湯'),('構文','木'),('系統','木')):
            self.assertTrue(S.nominal_compound_support(left,right),(left,right))
            self.assertTrue(oddness.can_join(left,'名詞:一般',right,'名詞:一般'))
        for left,right in (('構文','湯'),('炭酸','木'),('資料','湯'),
                           ('引き','月'),('画面','繁栄'),('未知','湯')):
            self.assertFalse(S.nominal_compound_support(left,right),(left,right))
        self.assertFalse(S.nominal_compound_support('資料','乳力'))
        a=initial();revision=a.store.revision()
        for head in ('炭酸湯','温泉湯','薬草湯','清涼炭酸湯','無香料炭酸湯',
                     '構文木','系統木'):
            for tail in ('','の話です','を確認します'):
                text=head+tail
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result.get('odd_spans'),text)
        self.assertEqual(a.store.revision(),revision)

    @unittest.skipUnless(M.HAS_JANOME,'native humble action construction')
    def test_humble_action_keeps_native_head_tail_and_object_meaning(self):
        import app,reading_segments as R
        from tests_analysis_async import initial
        for text,head in (('おかけいたしました','かけ'),('およみいたします','よみ'),
                          ('おわたしいたしました','わたし'),('ごあんないいたします','案内')):
            self.assertIn(head,R.native_humble_action_heads(text),text)
        for text in ('おかけいたしまし','おかけいたすます','おかくいたします',
                     'おしらゆほいたします','ごしらゆほいたします','およみいたしますう'):
            self.assertFalse(R.native_humble_action_heads(text),text)
        a=initial();revision=a.store.revision()
        for source in ('お手数をおかけいたしました。','おてすうをおかけいたしました。',
                       '手間をかけました。','ご迷惑をおかけいたしました。',
                       '資料をおよみいたします。','にもつをおわたしいたします。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            expected={'手間をかけました。':'手間を掛けました。','にもつをおわたしいたします。':'荷物をお渡しいたします。'}.get(source,source)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result.get('odd_spans'),source)
        self.assertFalse(R.completed_native_reading_clause('りんごをおよみいたします',require_object_fit=True))
        self.assertEqual(a.store.revision(),revision)

    def test_unknown_argument_needs_no_predicate_analysis(self):
        with patch.object(S,'_action_head') as analyze:
            self.assertIsNone(S.candidate_evidence('未知','説明','します'))
        analyze.assert_not_called()

    def test_diagnostics_identify_roles_and_knowledge_version(self):
        with patch.object(S,'_action_head',return_value='説明'):
            e=S.candidate_evidence('理由','説明','します')
        self.assertEqual(e['object'],'理由')
        self.assertEqual(e['predicate'],'説明')
        self.assertEqual(e['shared_roles'],['information'])
        self.assertEqual(e['version'],S.KNOWLEDGE_VERSION)


    def test_dative_argument_does_not_hide_the_explicit_object(self):
        ts=[('本','名詞:一般','ほん',0,1,True,''),('を','助詞:格助詞','を',1,2,True,''),
            ('友人','名詞:一般','ゆうじん',2,4,True,''),('に','助詞:格助詞','に',4,5,True,'')]
        self.assertEqual(S.object_before('本を友人に貸す',5,lambda s:ts),'本')
        self.assertEqual(S.object_before('本を友人に 貸す',6,lambda s:ts),'')
        self.assertTrue(S.support('本','貸す'))
        self.assertFalse(S.support('理由','貸す'))
        other=ts[:2]+[('読み','動詞:自立','よみ',2,4,True,'連用形'),
            ('て','助詞:接続助詞','て',4,5,True,''),('友人','名詞:一般','ゆうじん',5,7,True,''),
            ('に','助詞:格助詞','に',7,8,True,'')]
        self.assertEqual(S.object_before('本を読みて友人に話す',8,lambda s:other),'')


    def test_native_adverbial_keeps_argument_but_does_not_cross_a_predicate(self):
        noun=('文字','名詞:一般','もじ',0,2,True,'')
        case=('を','助詞:格助詞:一般','を',2,3,True,'')
        manner=('大きく','形容詞:自立','おおきく',3,6,True,'連用テ接続')
        forms=(('形容詞,自立,*,*','連用テ接続','大きい','おおきく'),)
        with patch.object(M,'dictionary_inflections',return_value=forms):
            self.assertEqual(S.object_before('文字を大きく描く',6,lambda _:[noun,case,manner]),'文字')
            self.assertEqual(S.object_before('文字を大きく 描く',7,lambda _:[noun,case,manner]),'')
            other=('読ん','動詞:自立','よん',3,5,True,'連用タ接続')
            te=('で','助詞:接続助詞','で',5,6,True,'')
            self.assertEqual(S.object_before('文字を読んで描く',6,lambda _:[noun,case,other,te]),'')
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertEqual(S.object_before('文字を大きく描く',6,lambda _:[noun,case,manner]),'')



    def test_physical_tools_keep_their_own_meaning(self):
        for text in ('筆','筆ペン','ボールペン','消しゴム','定規','刷毛','はけ','ハケ',
                     '箒','ほうき','ホウキ','ブラシ','雑巾','ぞうきん','ゾウキン'):
            with self.subTest(text=text):self.assertIn('object',S.nominal_roles(text))
        for text in ('放棄','蜂起','布施','不出','しらゆほ'):
            with self.subTest(text=text):self.assertNotIn('object',S.nominal_roles(text))

    @unittest.skipUnless(M.dictionary_inflections('筆'),'requires native dictionary')
    def test_native_tool_objects_share_normal_and_repaired_clause_proof(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text,expected in (
            # 2026-10-04: the user put the former drawing/brush example on hold.
            ('ほうきをあらいます。','ほうきをあらいます。'),
            ('ふでをあらいます。','筆を洗います。'),
            ('ぶらしをつかいます。','ブラシを使います。'),
            ('ぞうきんをほします。','雑巾を干します。'),
            ('ふでをあらいまぇ。',('ふでをあらいます。','筆を洗います。')),
            ('権利を放棄します。','権利を放棄します。'),
            ('軍が蜂起します。','軍が蜂起します。')):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                self.assertIn(result['corrected'],expected if isinstance(expected,tuple) else (expected,))
                self.assertEqual(result['odd_spans'],[])

    @unittest.skipUnless(M.HAS_JANOME,'native lexical and potential readings')
    def test_homographic_opening_and_potential_keep_native_reading_roles(self):
        self.assertIn('text',S.native_verb_roles('ひらけ','連用形','ひらけ',tail='ます'))
        self.assertNotIn('text',S.native_verb_roles('あけ','連用形','あけ',tail='ます'))
        self.assertIn('food',S.native_verb_roles('食べ','連用形','たべ',tail='ます'))
        self.assertFalse(S.native_verb_roles('しらゆほ','連用形','しらゆほ',tail='ます'))


    @unittest.skipUnless(M.HAS_JANOME,'native multiple-argument boundaries')
    def test_repaired_case_head_keeps_its_role_across_an_unchanged_object(self):
        for noun,tail,role in (('箱','に本を入れます','container'),
                               ('辞書','で言葉を調べます','reference')):
            proof=S.candidate_object_evidence(noun,tail)
            self.assertTrue(proof and proof['shared_roles'],(noun,tail))
        for noun,tail in (('箱','に本を食べます'),('箱','に本を読み、椅子に座ります'),
                           ('未分類語','に本を入れます')):
            self.assertFalse((S.candidate_object_evidence(noun,tail) or {}).get('shared_roles'),(noun,tail))


if __name__=='__main__':unittest.main()
