# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch


from morphology import HAS_JANOME

@unittest.skipUnless(HAS_JANOME, "Requires real Janome; run with the native integration suite")
class FamiliarSpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state=initial()

    def test_accepted_natural_spelling_survives_finishing(self):
        import app
        s=self.state
        for source,expected in [('聞いた話を纏路手文章にします。','聞いた話をまとめて文章にします。'),
                                ('話を纏めて文章にします。','話を纏めて文章にします。'),
                                ('「纏路手」という文字列','「纏路手」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertNotEqual('incomplete',r.get('analysis_status'))

    def test_same_native_inflection_and_explicit_choice(self):
        from familiar_spelling import prefers_kana
        from kana_spelling import project
        for face,reading in [('纏め','まとめ'),('躊躇う','ためらう'),('頷い','うなずい')]:
            with self.subTest(face=face):self.assertTrue(prefers_kana(face,reading))
        self.assertFalse(prefers_kana('微笑み','ほほえみ'))
        self.assertFalse(prefers_kana('頷い','うなづい'))
        s=self.state
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'纏め' if rd=='まとめ' else None):
            result=project('話をまとめて文章にします',s.store,s.dict_index,s.decisions)
        self.assertIsNotNone(result)
        self.assertEqual('話を纏めて文章にします',result[0])

    def test_native_connective_keeps_source_noun_and_ordinary_spelling(self):
        import app,corrector
        from repaired_spelling import finish
        s=self.state
        for source,expected in [
                ('聞いた話をまとめる手文章にします。','聞いた話をまとめて文章にします。'),
                ('聞いた話をまとめる文章にします。','聞いた話をまとめる文章にします。'),
                ('聞いた話をまとめて文章にします。','聞いた話をまとめて文章にします。'),
                ('話を纏めて文章にします。','話を纏めて文章にします。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))
        # A synthetic remembered spelling checks this finishing contract only;
        # it does not load or exercise the user's stopped learning pipeline.
        source='聞いた話をまとめる手文章にします。'
        proposed='聞いた話を纏めて文章にします。'
        result=dict(corrected=proposed,changed=True,analysis_status='complete',
                    _repair_surfaces=[(5,12,'纏めて文章','lexical')])
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'纏めて' if rd=='まとめて' else None):
            kept=finish(source,result,s.store,corrector.make_tokenizer(s.store),s.dict_index,s.decisions)
        self.assertEqual(proposed,kept['corrected'])

    def test_source_connective_frame_overrides_unbacked_tail_frequency(self):
        import app
        s=self.state
        for source,expected in [
                ('説明をまとめる手資料にします。','説明をまとめて資料にします。'),
                ('荷物を片付ける手部屋を掃除する。','荷物を片付けて部屋を掃除する。'),
                ('話をまとめる手文章にする。','話をまとめて文章にする。'),
                ('契約をまとめる手腕が必要だ。','契約をまとめる手腕が必要だ。'),
                ('データを集める手作業を減らす。','データを集める手作業を減らす。'),
                ('紙を切る手が震える。','紙を切る手が震える。'),
                ('紙資料を読む。','紙資料を読む。'),
                ('音資料を集める。','音資料を集める。'),
                ('「説明をまとめる手資料」という文字列','「説明をまとめる手資料」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))


    def test_general_action_and_explicit_role_choose_different_words(self):
        import app
        s=self.state
        for source,expected in [
                ('詰名します','説明します'),
                ('飲んで゛゜から詰名します','飲んでから説明します'),
                ('原因を詰名します','原因を説明します'),
                ('担当者を詰名します','担当者を指名します'),
                ('次の回答者を詰名します','次の回答者を指名します'),
                ('新しい機械を発明する','新しい機械を発明する'),
                ('事故で失明した','事故で失明した'),
                ('「詰名します」という文字列','「詰名します」という文字列')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_ime_attestation_keeps_other_native_readings_and_spelling_candidates(self):
        import app
        s=self.state
        for source,expected in [
                ('予定を聞く人しました。','予定を確認しました。'),
                ('文章を乳りらょくして内容を確認します。','文章を入力して内容を確認します。'),
                ('話を聞く人がいます。','話を聞く人がいます。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_original_ime_word_edges_retain_complete_neighbors(self):
        import app
        s=self.state
        for source,expected in [
                ('必要なしはょ類を送信しました。','必要な書類を送信しました。'),
                ('わたしはょ類を送信しました。','私は書類を送信しました。'),
                ('店で買ったいょく材を冷蔵庫に入れます。','店で買った食材を冷蔵庫に入れます。'),
                ('集めた資料をならぺ手内容を比べます。','集めた資料を並べて内容を比べます。'),
                ('集めて資料をならぺ手内容を比べます。','集めて資料を並べて内容を比べます。'),
                ('わたしは書類を送信しました。','わたしは書類を送信しました。'),
                ('食べたい料理を選びます。','食べたい料理を選びます。'),
                ('読みたい資料を選びます。','読みたい資料を選びます。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_marked_lexical_tail_is_read_in_original_suru_context(self):
        import app
        s=self.state
        for source,expected in [
                ('故障の原因を背詰めてしてから修理します。','故障の原因を説明してから修理します。'),
                ('故障の原因を背詰めていしてから修理します。','故障の原因を説明してから修理します。'),
                ('書類を箱に詰めて仕事をします。','書類を箱に詰めて仕事をします。'),
                ('よく考えてします。','よく考えてします。')]:
            with self.subTest(source=source):
                r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                                   decisions=s.decisions,context_vec=None)
                self.assertEqual(expected,r['corrected'])
                self.assertFalse(r.get('odd_spans'))
                self.assertEqual('complete',r.get('analysis_status'))

    def test_written_candidate_cannot_borrow_a_different_reading_object(self):
        import app
        state=self.state
        for source,expected in (
                ('詳しい説明をきういてください。','詳しい説明を聞いてください。'),
                ('説明を打ってください。','説明を打ってください。'),
                ('木を伐ってください。','木を伐ってください。'),
                ('紙を切ってください。','紙を切ってください。'),
                ('予定を聞く人しました。','予定を確認しました。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
        # These inputs still need a stronger key hypothesis for 聞いて.
        # Do not freeze today's unchanged output as a permanent protection.
        for source,bad in (
                ('詳しい説明をきっいてください。',('詳しい説明を切ってください。','詳しい説明を伐ってください。')),
                ('説明をきっいてください。',('説明を切ってください。','説明を伐ってください。'))):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertNotIn(result['corrected'],bad)
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_original_case_and_unchanged_return_choose_natural_action(self):
        import app
        state=self.state
        for source,expected in (
                ('店で本を貸さて帰ります。','店で本を買って帰ります。'),
                ('家族に本を貸さて帰ります。','家族に本を貸して帰ります。'),
                ('棚に本を貸さて帰ります。','棚に本を重ねて帰ります。'),
                ('切手を貸さて帰ります。','切手を買って帰ります。'),
                ('道具をかさて戻ります。','道具を買って戻ります。'),
                ('料理の材料をかさて帰ります。','料理の材料を買って帰ります。'),
                ('道具を借りて戻ります。','道具を借りて戻ります。'),
                ('家族に本を貸して帰ります。','家族に本を貸して帰ります。'),
                ('道具をさて置いて帰ります。','道具をさて置いて帰ります。'),
                ('彼をばかって呼びます。','彼をばかって呼びます。'),
                ('「かさて」と書いてあります。','「かさて」と書いてあります。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_two_physical_events_and_the_same_yoon_anomaly(self):
        import app,kana_layout as K
        from contextual_repair import neighbor_shift_key_repairs
        options=list(neighbor_shift_key_repairs('かさ'))
        found=[row for row in options if row.reading=='かっ']
        self.assertEqual(len(found),1)
        self.assertEqual([step.operation for step in found[0].steps],['adjacent_substitution','shift'])
        self.assertEqual([step.position for step in found[0].steps],[1,1])
        self.assertGreater(K.kana_key_distance('さ','っ'),1.05)
        self.assertFalse(any(row.reading=='かょ' for row in options))
        state=self.state
        for source,expected in (
                ('古い設定を作治和して保存します。','古い設定を削除して保存します。'),
                ('知りわ宇を整理してください。','資料を整理してください。'),
                ('つょい','強い'),('風がつょい','風がつよい'),
                ('つよい','つよい'),('だょね','だょね')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_original_modifiers_leave_the_same_marked_word_for_repair(self):
        import app
        state=self.state
        for source,expected in (
                ('すごくつょいです','すごく強いです'),
                ('小さくてつょい','小さくて強い'),
                ('とってもつょい','とっても強い'),
                ('もっともつょい','もっとも強い'),
                ('この道具はつょい','この道具は強い'),
                ('これもつょい','これも強い'),
                ('母の声はつょい','母の声は強い'),
                ('この道具は小さくてつょい','この道具は小さくて強い'),
                ('明日のしばゅんびを済ませて早く寝ます。','明日の準備を済ませて早く寝ます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_native_final_particle_reading_is_shared_without_changing_intent(self):
        import app,morphology as M
        state=self.state
        for source in ('行くょ！','あるょね','それだょね','あるょねえ',
                       '食事をするょ','作業をするょね','しょくじをするよ'):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
        self.assertEqual(M.colloquial_particle_normal_form('とってもつょい'),'とってもつょい')
        self.assertEqual(M.colloquial_particle_normal_form('すふょ'),'すふょ')
        self.assertEqual(M.colloquial_particle_normal_form('行くょね'),'行くよね')

    def test_coordinated_noun_and_unadorned_process_use_source_meaning(self):
        import app
        state=self.state
        for source,expected in (
                ('小さくて鉄製の箱','小さくて鉄製の箱'),
                ('大きくて木製の机','大きくて木製の机'),
                ('軽くて金属製の道具','軽くて金属製の道具'),
                ('古い設定を素削除して保存します。','古い設定を削除して保存します。'),
                ('設定を素削除します。','設定を削除します。'),
                ('素画像を表示します。','素画像を表示します。'),
                ('素通りします。','素通りします。'),
                ('図を素描します。','図を素描します。'),
                ('書類を素読みします。','書類を素読みします。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_return_spelling_uses_ordinary_meaning_and_actual_destination(self):
        import app
        state=self.state
        for source,expected in (
                ('料理の材料を貸さて還ります。', '料理の材料を買って帰ります。'),
                ('家に還ります。', '家に帰ります。'),
                ('自宅へ還る。', '自宅へ帰る。'),
                ('国へ還る。', '国へ帰る。'),
                ('正気にかえる。', '正気に返る。'),
                ('我に帰った。', '我に返った。'),
                ('土に帰る。', '土に還る。'),
                ('自然に還る。', '自然に還る。'),
                ('本を返します。', '本を返します。'),
                ('新しい設定に変えます。', '新しい設定に変えます。'),
                ('「還る」という表記を使う。', '「還る」という表記を使う。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_native_coordination_retains_context_without_erasing_default_sense(self):
        import app
        state=self.state
        for source,expected in (('日本の線と中国の線', '日本の線と中国の線'), ('日本の線や中国の線', '日本の線や中国の線'), ('日本の線', '二本の線'), ('にほんの線', '二本の線'), ('机の脚と椅子の背', '机の脚と椅子の背')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_stranded_object_leaves_the_return_verb_as_context(self):
        import app
        state=self.state
        for source,expected in (
                ('荷物をもさて帰ります。', '荷物を持って帰ります。'),
                ('メモをとさて帰ります。', 'メモを取って帰ります。'),
                ('荷物をもさて帰った。', '荷物を持って帰った。'),
                ('荷物をもって帰ります。', '荷物をもって帰ります。'),
                ('荷物を持ち、さて帰ります。', '荷物を持ち、さて帰ります。'),
                ('仕事をさておいて休みます。', '仕事をさておいて休みます。'),
                ('彼は「荷物をもさて帰る」と誤入力した。', '彼は「荷物をもさて帰る」と誤入力した。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_final_particle_needs_a_real_text_boundary(self):
        import app
        state=self.state
        for source,expected in (('必要なしはょ類を送信しました。', '必要な書類を送信しました。'), ('会議のしはょ類を送信します。', '会議の書類を送信します。'), ('するょ、またね。', 'するょ、またね。'), ('「あるょ」と返事する。', '「あるょ」と返事する。')):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_completed_past_requires_a_real_action_link(self):
        import app
        state=self.state
        for source,expected in (
                ('料理の材料を買った帰りますよ。', '料理の材料を買って帰りますよ。'),
                ('料理の材料を買ってた帰ります。', '料理の材料を買って帰ります。'),
                ('本を読んだ戻りますね。', '本を読んで戻りますね。'),
                ('料理を食べた寝ます。', '料理を食べて寝ます。'),
                ('本を買っていた帰りますよ。', '本を買っていて帰りますよ。'),
                ('料理の材料を買った還ります。', '料理の材料を買って帰ります。'),
                ('本を買った帰り道ですよ。', '本を買った帰り道ですよ。'),
                ('本を買った。帰ります。', '本を買った。帰ります。'),
                ('料理を食べたくなりました。', '料理を食べたくなりました。'),
                ('「買った帰ります」と誤入力した。', '「買った帰ります」と誤入力した。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_repeated_completed_utterance_has_its_own_original_syntax(self):
        import app
        state=self.state
        for source,expected in (
                ('分かった分かった。', '分かった分かった。'),
                ('やったやった。', 'やったやった。'),
                ('読んだ読んだよ。', '読んだ読んだよ。'),
                ('見た見た見た。', '見た見た見た。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_photo_meaning_ranks_repaired_action_with_unchanged_context(self):
        import app
        state=self.state
        for source,expected in (
                ('写真をとさて帰りますよ。', '写真を撮って帰りますよ。'),
                ('メモをとさて帰ります。', 'メモを取って帰ります。'),
                ('写真を取って机に置く。', '写真を取って机に置く。'),
                ('写真を取ってファイルに保存します。', '写真を撮ってファイルに保存します。'),
                ('写真をは撮って帰ります。', '写真を貼って帰ります。'),
                ('写真を貼って帰ります。', '写真を貼って帰ります。'),
                ('糸を張って帰ります。', '糸を張って帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_later_motion_does_not_own_a_content_object(self):
        import app
        state=self.state
        for source,expected in (
                ('道を入って帰ります。', '道を入って帰ります。'),
                ('写真の中を歩きます。', '写真の中を歩きます。'),
                ('写真を入った箱に貼ります。', '写真を入った箱に貼ります。'),
                ('本を読んで帰ります。', '本を読んで帰ります。'),
                ('データを進めて確認します。', 'データを進めて確認します。'),
                ('感覚が冴えて帰ります。', '感覚が冴えて帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_rejects_intransitive_escape_without_claiming_a_complete_repair(self):
        import app
        for source,expected,unresolved in (('メモをとさえて帰ります。','メモをとさえて帰ります。',True),
                ('写真を走って帰ります。','写真を貼って帰ります。',False)):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(bool(result.get('odd_spans')),unresolved)

    def test_finite_predicate_shares_actual_final_particle_readings(self):
        from contextual_repair import _finite_written_predicate
        for text in ('帰りますよ','帰るょ','帰りたいよ','帰れないね','買ったよ','帰るよねえ'):
            self.assertTrue(_finite_written_predicate(text),text)
        for text in ('帰るには','帰りよ','買って位置帰ります','買った帰り道'):
            self.assertFalse(_finite_written_predicate(text),text)

    def test_marked_kana_onset_uses_same_semantics_as_written_onset(self):
        import app
        state=self.state
        for source,expected in (
                ('事情をはとって帰ります。', '事情を悟って帰ります。'),
                ('事情をは撮って帰ります。', '事情を悟って帰ります。'),
                ('写真をはとって帰ります。', '写真を貼って帰ります。'),
                ('切手をはとって帰ります。', '切手を貼って帰ります。'),
                ('写真をとって帰ります。', '写真を撮って帰ります。'),
                ('切手をはって帰ります。', '切手をはって帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_written_usage_and_motion_keep_contextual_counterexamples(self):
        import app
        state=self.state
        for source,expected in (
                ('事情を聰って帰ります。', '事情を悟って帰ります。'),
                ('コンクリートをはつります。', 'コンクリートをはつります。'),
                ('床を這って進みます。', '床を這って進みます。'),
                ('苦労を厭わない。', '苦労を厭わない。'),
                ('その人を伊良部と呼びます。', 'その人を伊良部と呼びます。'),
                ('彼を太郎て呼びます。', '彼を太郎て呼びます。'),
                ('伊良部って誰ですか。', '伊良部って誰ですか。'),
                ('駅には行きます。', '駅には行きます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_stranded_object_retains_destination_and_physical_type(self):
        import app
        state=self.state
        for source,expected in (
                ('荷物をもさて駅へ向かいます。', '荷物を持って駅へ向かいます。'),
                ('写真をとさて空港へ行きます。', '写真を撮って空港へ行きます。'),
                ('切手をもさて帰ります。', '切手を持って帰ります。'),
                ('テープをもさて駅へ向かいます。', 'テープを持って駅へ向かいます。'),
                ('荷物を持ち、さて駅へ向かいます。', '荷物を持ち、さて駅へ向かいます。'),
                ('仕事をさておいて休みます。', '仕事をさておいて休みます。'),
                ('ホームを歩いて帰ります。', 'ホームを歩いて帰ります。'),
                ('図面を入った入口に貼ります。', '図面を入った入口に貼ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',dict_index=state.dict_index,
                    decisions=state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_native_inflection_keeps_explicit_usage_without_borrowing_a_homophone(self):
        from kango_tier import candidate_usage_tier
        self.assertEqual(candidate_usage_tier('聰っ'),3)
        self.assertEqual(candidate_usage_tier('覚っ'),3)
        self.assertEqual(candidate_usage_tier('悟っ'),2)
        self.assertEqual(candidate_usage_tier('貼っ'),1)
        self.assertIsNone(candidate_usage_tier('分類していない綴り'))

    def test_marked_kana_action_retains_the_original_following_movement(self):
        import app
        for source,expected in (
                ('時刻をいらべて駅へ向かいます。','時刻を調べて駅へ向かいます。'),
                ('資料をいらべて帰ります。','資料を調べて帰ります。'),
                ('時刻をしらべて駅へ向かいます。','時刻をしらべて駅へ向かいます。'),
                ('時間をかけて駅へ向かいます。','時間をかけて駅へ向かいます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',
                    dict_index=self.state.dict_index,decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
        import contextual_repair as Q,corrector as C
        source='時刻をいらべて\t駅へ向かいます。'
        targets=Q.targets_for_line(source,C.make_tokenizer(self.state.store),self.state.store,self.state.dict_index)
        self.assertTrue(targets)
        self.assertTrue(all('\t' not in t.context for t in targets))

    def test_written_nominal_link_recovers_an_exact_ime_source_reading(self):
        import app
        source='電車の時刻を伊良部て駅へ向かいます。'
        result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
            decisions=self.state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'電車の時刻を調べて駅へ向かいます。')
        self.assertFalse(result.get('odd_spans'))

    def test_motion_relation_is_independent_of_neighboring_fields(self):
        import app
        for source,expected in (
                ('荷物をもさて駅へ向かいます。\t別の欄です。', '荷物を持って駅へ向かいます。\t別の欄です。'),
                ('別の欄です。\t荷物をもさて駅へ向かいます。', '別の欄です。\t荷物を持って駅へ向かいます。'),
                ('荷物をもさて駅へ向かいます。\t荷物を捨てて駅へ向かいます。', '荷物を持って駅へ向かいます。\t荷物を捨てて駅へ向かいます。'),
                ('荷物をもさて駅へ向かいます。⇒荷物を捨てて駅へ向かいます。', '荷物を持って駅へ向かいます。⇒荷物を捨てて駅へ向かいます。'),
                ('荷物をもさて駅へ向かいます。次の文です。', '荷物を持って駅へ向かいます。次の文です。'),
                ('写真を走って帰ります。\t別の欄です。', '写真を貼って帰ります。\t別の欄です。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_original_rare_action_compares_same_native_reading_and_inflection(self):
        import app
        for source,expected in (
                ('事情を聰って帰ります。', '事情を悟って帰ります。'),
                ('事情を覚って帰ります。', '事情を悟って帰ります。'),
                ('彼は真実を聰った。', '彼は真実を悟った。'),
                ('事情を聰りません。', '事情を悟りません。'),
                ('すべてを覚れば分かる。', 'すべてを悟れば分かる。'),
                ('彼は真実をさとった。', '彼は真実をさとった。'),
                ('コンクリートをはつります。', 'コンクリートをはつります。'),
                ('本の内容を覚える。', '本の内容を覚える。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_spelling_report_names_the_exact_rare_spelling(self):
        import app
        for source,expected in (
                ('「聰って」と表記する。', '「聰って」と表記する。'),
                ('「覚る」と表記しました。', '「覚る」と表記しました。'),
                ('「聰る」と表記しない。', '「聰る」と表記しない。'),
                ('「聰って」と言った。', '「悟って」と言った。'),
                ('事情を聰って帰ります。\t「聰って」と表記する。', '事情を悟って帰ります。\t「聰って」と表記する。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_accusative_onset_does_not_reinterpret_other_particle_collisions(self):
        import app
        for source,expected in (
                ('かくにんしてた', '確認してた'),
                ('事情をはとって帰ります。', '事情を悟って帰ります。'),
                ('写真をはとって帰ります。', '写真を貼って帰ります。'),
                ('切手をはとって帰ります。', '切手を貼って帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_exact_explicit_spelling_precedes_general_familiarity(self):
        import app
        for reading,face,source in (('さとっ','聰っ','事情を聰って帰ります。'),
                ('さとって','聰って','事情を聰って帰ります。')):
            with self.subTest(reading=reading), patch('last_choice.surface_for_reading',
                    side_effect=lambda rd:face if rd==reading else None):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertFalse(result.get('odd_spans'))

    def test_rare_nominal_sense_uses_ordinary_action_argument(self):
        import app
        for source,expected in (
                ('思料を印刷します。', '資料を印刷します。'),
                ('必要な思量を送ります。', '必要な資料を送ります。'),
                ('会議の思料を配布します。', '会議の資料を配布します。'),
                ('会議の思料を印刷して帰ります。', '会議の資料を印刷して帰ります。'),
                ('そのように思料します。', 'そのように思料します。'),
                ('慎重に思量する。', '慎重に思量する。'),
                ('深い思量を重ねます。', '深い思量を重ねます。'),
                ('彼の思料を説明します。', '彼の思料を説明します。'),
                ('資料を印刷します。', '資料を印刷します。'),
                ('飼料を購入します。', '飼料を購入します。'),
                ('「思料」と表記し、思料を印刷します。', '「思料」と表記し、資料を印刷します。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_rare_action_defaults_to_fitting_sense_and_keeps_geographic_patrol(self):
        import app
        for source,expected in (
                ('友人を哨戒します。', '友人を紹介します。'),
                ('新しい道具を哨戒します。', '新しい道具を紹介します。'),
                ('お客様に友人を哨戒します。', 'お客様に友人を紹介します。'),
                ('資料を哨戒して帰ります。', '資料を紹介して帰ります。'),
                ('友人を哨戒した後で帰ります。', '友人を紹介した後で帰ります。'),
                ('海上を哨戒します。', '海上を哨戒します。'),
                ('近海を哨戒して帰ります。', '近海を哨戒して帰ります。'),
                ('海域を巡回します。', '海域を巡回します。'),
                ('制度の内容を照会します。', '制度の内容を照会します。'),
                ('「哨戒」と表記する。', '「哨戒」と表記する。'),
                ('資料を哨戒して帰ります。\t海上を哨戒して帰ります。', '資料を紹介して帰ります。\t海上を哨戒して帰ります。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_repaired_action_clears_only_proved_adjacent_connectives(self):
        import app
        for source,expected in (
                ('荷物をは今夏でから休みます。', '荷物を運んでから休みます。'),
                ('荷物をはコンクでから休みます。', '荷物を運んでから休みます。'),
                ('荷物を運んでから休みます。', '荷物を運んでから休みます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_adjacent_proof_does_not_cover_another_field_or_invalid_particles(self):
        import app
        for source,expected,odd in (
                ('荷物を箱館でから休みます。','荷物を箱館でから休みます。',[(5,8)]),
                ('荷物をはコンクでから休みます。\t時刻を伊良部て駅へ向かいます。',
                 '荷物を運んでから休みます。\t時刻を調べて駅へ向かいます。',[]),
                ('時刻を伊良部て駅へ向かいます。\t荷物をはコンクでから休みます。',
                 '時刻を調べて駅へ向かいます。\t荷物を運んでから休みます。',[]),
                ('荷物をはコンクでには休みます。','荷物を運んでには休みます。',[(7,9)])):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual([tuple(x) for x in result.get('odd_spans',[])],odd)

    def test_completed_meaning_requires_its_own_same_reading_source_proof(self):
        from contextual_repair import preserves_completed_reading_link
        for source,old,new,accepted in (
                ('資料を哨戒して帰ります。','哨戒','紹介',True),
                ('海上を哨戒して帰ります。','哨戒','紹介',False),
                ('資料を保存して話ました。','保存','説明',False),
                ('資料を保存して話ました。','話','話し',True)):
            a=source.index(old)
            self.assertEqual(preserves_completed_reading_link(source,a,a+len(old),new),accepted,source)

    def test_rare_nominal_explicit_choice_is_stronger_than_default_usage(self):
        import app
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'思料' if rd=='しりょう' else None):
            source='思料を印刷します。'
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'))

    def test_translation_uses_content_and_native_auxiliary_connection(self):
        import app
        for source,expected in (
                ('会場を和訳します。', '会場を予約します。'),
                ('明日の会場を和訳しておきます。', '明日の会場を予約しておきます。'),
                ('会議室を和訳しています。', '会議室を予約しています。'),
                ('会場を和訳してしまいました。', '会場を予約してしまいました。'),
                ('会場を和訳しておいてください。', '会場を予約しておいてください。'),
                ('会場を和訳して人数を伝えておきます。', '会場を予約して人数を伝えておきます。'),
                ('会議室を和訳して資料を読んでいます。', '会議室を予約して資料を読んでいます。'),
                ('資料を和訳しておきます。', '資料を和訳しておきます。'),
                ('英文を和訳しています。', '英文を和訳しています。'),
                ('会場を和訳している人に貸します。', '会場を和訳している人に貸します。'),
                ('「会場」を和訳しておきます。', '「会場」を和訳しておきます。'),
                ('海上を哨戒しています。', '海上を哨戒しています。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_ordinary_use_and_concrete_private_purpose(self):
        import app
        for source,expected in (
                ('私用した道具を片付けます。', '使用した道具を片付けます。'),
                ('私用する資料を準備します。', '使用する資料を準備します。'),
                ('道具を私用します。', '道具を使用します。'),
                ('資料を私用して内容を説明します。', '資料を使用して内容を説明します。'),
                ('会社の道具を私用します。', '会社の道具を私用します。'),
                ('社用車を私用します。', '社用車を私用します。'),
                ('公用車を私用しておきます。', '公用車を私用しておきます。'),
                ('私的に私用した道具を片付けます。', '私的に私用した道具を片付けます。'),
                ('会社の会議で私用した道具を片付けます。', '会社の会議で使用した道具を片付けます。'),
                ('私用した道具を個人的に買います。', '使用した道具を個人的に買います。'),
                ('会社の道具を使用します。', '会社の道具を使用します。'),
                ('私用のため休みます。', '私用のため休みます。'),
                ('「私用」と表記し、私用した道具を片付けます。', '「私用」と表記し、使用した道具を片付けます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_independent_next_object_stops_at_its_source_field(self):
        import app
        for source,expected in (
                ('会場を和訳して人数を伝えます。\t海上を哨戒します。', '会場を予約して人数を伝えます。\t海上を哨戒します。'),
                ('海上を哨戒します。\t会場を和訳して人数を伝えておきます。', '海上を哨戒します。\t会場を予約して人数を伝えておきます。'),
                ('会場を和訳して人数を伝えます。説明を英訳します。', '会場を予約して人数を伝えます。説明を英訳します。'),
                ('私用した道具を片付けます。\t会社の道具を私用します。', '使用した道具を片付けます。\t会社の道具を私用します。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_partial_semantic_repair_keeps_the_unchanged_source_remainder(self):
        import app
        # A deliberate same-reading choice keeps the argument while the action repairs.
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'海上' if rd=='かいじょう' else None):
            for source,expected,odd in (
                    ('海上を和訳して人数を伝えます。','海上を予約して人数を伝えます。',[(0,2)]),
                    ('海上を和訳して人数を伝えます。\t会場を予約します。','海上を予約して人数を伝えます。\t会場を予約します。',[(0,2)]),
                    ('海上を和訳して人数を伝えます。 ⇒海上を和訳します。','海上を予約して人数を伝えます。 ⇒海上を予約します。',[(0,2),(17,19)])):
                with self.subTest(source=source):
                    result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                        decisions=self.state.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual([tuple(x) for x in result.get('odd_spans',[])],odd)
                    diagnosis=result['diagnosis']
                    self.assertEqual(diagnosis['language_state'],'anomaly_unrepaired')
                    self.assertFalse(diagnosis['range_errors'])
                    for x in odd:self.assertIn(list(x),diagnosis['unreplaced_odd_spans'])

    def test_auxiliary_is_one_action_and_relative_head_keeps_its_object_slot(self):
        from semantic_roles import _independent_accusative_clause
        for source in ('本を読んでいます。','本を読んでおきます。','本を読んでしまいました。',
                       '人数を伝えておきます。\t未完成の別欄'):
            self.assertTrue(_independent_accusative_clause(source),source)
        for source in ('本を読んでいる人に渡します。','本を読んで位置ます。','本を読むには'):
            self.assertFalse(_independent_accusative_clause(source),source)

    def test_explicit_private_use_choice_overrides_ordinary_default(self):
        import app
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'私用' if rd=='しよう' else None):
            source='私用した道具を片付けます。'
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'))

    def test_joint_object_and_action_meaning_uses_one_original_key_proof(self):
        import app
        for source,expected in (
                ('海上を和訳して人数を伝えます。', '会場を予約して人数を伝えます。'),
                ('海上を読奥して人数を伝えます。', '会場を予約して人数を伝えます。'),
                ('海上を和訳しておきます。', '会場を予約しておきます。'),
                ('人数を確認し、海上を和訳しておきます。', '人数を確認し、会場を予約しておきます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
                self.assertFalse(result['diagnosis']['range_errors'])

    def test_joint_argument_meaning_is_local_to_its_original_field(self):
        import app
        for source,expected in (
                ('海上を和訳して人数を伝えます。\t会場を予約します。', '会場を予約して人数を伝えます。\t会場を予約します。'),
                ('海上を和訳して人数を伝えます。 ⇒海上を和訳します。', '会場を予約して人数を伝えます。 ⇒会場を予約します。'),
                ('海上を和訳します。\t海上を哨戒します。', '会場を予約します。\t海上を哨戒します。'),
                ('会議室を和訳します。\t海上を和訳します。', '会議室を予約します。\t会場を予約します。'),
                ('海上を哨戒して人数を伝えておきます。', '海上を哨戒して人数を伝えておきます。'),
                ('海上を和訳している人に貸します。', '海上を和訳している人に貸します。'),
                ('「海上」を和訳しておきます。', '「海上」を和訳しておきます。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')
                self.assertFalse(result['diagnosis']['range_errors'])

    def test_joint_meaning_keeps_physical_key_positions_and_reading_sources(self):
        import app,corrector
        source='海上を和訳して人数を伝えます。'
        corrector.trace_on()
        try:
            result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                decisions=self.state.decisions,context_vec=None)
        finally:corrector.trace_off()
        selected=next(d for d in result['contextual_diagnostics'] if d.get('selected')=='会場を予約')
        row=next(c for c in selected['candidates'] if c['surface']=='会場を予約')
        self.assertEqual(row['reading']['source'],'joint_source_argument')
        self.assertEqual(row['reading']['text'],'かいじょうをわやく')
        self.assertEqual(row['repair']['reading'],'かいじょうをよやく')
        self.assertEqual(row['reading']['text'][row['repair']['position']],row['repair']['pressed'])
        self.assertEqual(row['repair']['intended'],'よ')
        self.assertFalse(row['also_from_legacy'])
        self.assertEqual(row['source_meaning']['original_argument'],'海上')

    def test_joint_correct_text_does_not_hide_existing_search_limit(self):
        import app
        source='海上を読湯訳して人数を伝えます。'
        result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
            decisions=self.state.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'会場を予約して人数を伝えます。')
        self.assertFalse(result.get('odd_spans'))
        self.assertEqual(result.get('analysis_status'),'limited')
        self.assertEqual(result.get('stop_reason'),'search_limit')

    def test_native_nominal_copula_closes_the_same_action_object(self):
        import app
        for source,expected in (
                ('会場を和訳しておく予定です。', '会場を予約しておく予定です。'),
                ('会場を和訳する予定です。', '会場を予約する予定です。'),
                ('会場を和訳する人です。', '会場を予約する人です。'),
                ('会場を和訳した人でした。', '会場を予約した人でした。'),
                ('会場を和訳していた人です。', '会場を予約していた人です。'),
                ('会場を和訳するつもりです。', '会場を予約するつもりです。'),
                ('海上を和訳する予定です。', '会場を予約する予定です。'),
                ('資料を私用する予定です。', '資料を使用する予定です。'),
                ('会場を和訳する予定の人に貸します。', '会場を和訳する予定の人に貸します。'),
                ('会場を和訳する人だと聞きました。', '会場を和訳する人だと聞きました。'),
                ('資料を和訳する予定です。', '資料を和訳する予定です。'),
                ('英文を和訳する人です。', '英文を和訳する人です。'),
                ('本を読んだ人でした。', '本を読んだ人でした。'),
                ('海上を哨戒する予定です。', '海上を哨戒する予定です。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_following_nominal_clause_uses_the_same_completed_object_proof(self):
        import app
        for source,expected in (
                ('会場を和訳して人数を伝える予定です。', '会場を予約して人数を伝える予定です。'),
                ('海上を和訳して人数を伝える予定です。', '会場を予約して人数を伝える予定です。'),
                ('会場を和訳して本を読むつもりです。', '会場を予約して本を読むつもりです。'),
                ('会場を和訳して人数を伝えておく予定です。', '会場を予約して人数を伝えておく予定です。'),
                ('会場を和訳して人数を伝える予定です。\t海上を哨戒します。', '会場を予約して人数を伝える予定です。\t海上を哨戒します。'),
                ('会場を和訳して人数を伝える予定の人に貸します。', '会場を和訳して人数を伝える予定の人に貸します。'),
                ('海上を哨戒して人数を伝える予定です。', '海上を哨戒して人数を伝える予定です。'),
                ('資料を和訳して人数を伝える予定です。', '資料を和訳して人数を伝える予定です。'),
                ('会社の道具を私用する予定です。', '会社の道具を私用する予定です。'),
        ):
            with self.subTest(source=source):
                result=app.correct_line(source,self.state.store,input_method='kana',dict_index=self.state.dict_index,
                    decisions=self.state.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
                self.assertEqual(result.get('analysis_status'),'complete')

    def test_nominal_completion_requires_the_native_components(self):
        from semantic_roles import _independent_accusative_clause
        for source in ('人数を伝える予定です。','人数を伝えておく予定です。','本を読むつもりです。','本を読んだ人です。'):
            self.assertTrue(_independent_accusative_clause(source),source)
        for source in ('人数を伝えます予定です。','人数を伝える予定の人に貸します。',
                       '人数を伝える予定だと聞きます。','本を読むには','本を読み予定です。'):
            self.assertFalse(_independent_accusative_clause(source),source)
