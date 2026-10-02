# -*- coding: utf-8 -*-
"""Source meaning, native alternate readings and independent image fields."""
import unittest
import app
from tests_analysis_async import initial

from morphology import HAS_JANOME

@unittest.skipUnless(HAS_JANOME, "Requires real Janome; run with the native integration suite")
class ContextMeaningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=initial()

    def check(self,source,expected):
        s=self.state
        r=app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
                           decisions=s.decisions,context_vec=None)
        self.assertEqual(expected,r['corrected'],source)
        self.assertFalse(r.get('odd_spans'),source)
        self.assertEqual('complete',r.get('analysis_status'),source)

    def test_meaning_and_field_boundaries(self):
        for a,b in [('箸でカーソルの','端でカーソルの'),
                    ('日本の線\t地図','二本の線\t地図'),
                    ('地図\t日本の線','地図\t二本の線'),
                    ('地図に日本の線を引く','地図に二本の線を引く'),
                    ('地図で日本の線を確認する','地図で二本の線を確認する'),
                    ('巻き込み乳力\t別の欄','巻き込み入力\t別の欄')]:
            with self.subTest(source=a):self.check(a,b)

    def test_nominalized_continuative_before_unknown_compound(self):
        for a,b in [('書き込み乳力','書き込み入力'),
                    ('読み込み乳力','読み込み入力'),
                    ('打ち込み乳力','打ち込み入力'),
                    ('書き込み圧力','書き込み圧力'),
                    ('読み込み人力','読み込み人力'),
                    ('書き込み入力','書き込み入力')]:
            with self.subTest(source=a):self.check(a,b)

    def test_nominal_scope_does_not_hide_orphan_case(self):
        for a,b in [('にほんの鉄道について説明する','日本の鉄道について説明する'),
                    ('にほんの文化','日本の文化'),('にほんの会社','日本の会社'),
                    ('地図ににほんの鉄道を描く','地図に日本の鉄道を描く'),
                    ('にほんの線','二本の線'),
                    ('にほんの線と韓国の線','日本の線と韓国の線'),
                    ('机にほんの少し置く','机にほんの少し置く'),
                    ('ほんの少し待つ','ほんの少し待つ'),
                    ('日本の鉄道について説明する','日本の鉄道について説明する'),
                    ('「にほんの文化」という文字列','「にほんの文化」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_process_quality_and_explicit_institution_action(self):
        for a,b in [('予測の制度を上げる','予測の精度を上げる'),
                    ('計測の制度が低い','計測の精度が低い'),
                    ('推定の制度','推定の精度'),
                    ('予測のせいど','予測の精度'),
                    ('評価の制度','評価の制度'),
                    ('測定の制度を導入する','測定の制度を導入する'),
                    ('予測のせいどを改正する','予測の制度を改正する'),
                    ('評価のせいどを高める','評価の精度を高める'),
                    ('予測の制度\t制度を改正する','予測の精度\t制度を改正する')]:
            with self.subTest(source=a):self.check(a,b)

    def test_mechanism_owns_motion(self):
        for a,b in [('ホイールの開店が速い','ホイールの回転が速い'),
                    ('車輪の開店を止める','車輪の回転を止める'),
                    ('歯車の開店','歯車の回転'),
                    ('ダイヤルの開店角度','ダイヤルの回転角度'),
                    ('ホイールのかいてん','ホイールの回転'),
                    ('店舗の開店を待つ','店舗の開店を待つ'),
                    ('車輪の販売店の開店','車輪の販売店の開店'),
                    ('ホイールの店が開店する','ホイールの店が開店する'),
                    ('ホイールの開店\t店の開店','ホイールの回転\t店の開店')]:
            with self.subTest(source=a):self.check(a,b)

    def test_native_counter_selects_its_actual_object(self):
        for a,b in [('二台の機会','二台の機械'),('一枚の神','一枚の紙'),
                    ('二台のきかい','二台の機械'),('一枚のかみ','一枚の紙'),
                    ('一枚の神の絵','一枚の神の絵'),('一枚のかみの絵','一枚のかみの絵'),
                    ('二回の機会','二回の機会'),('三枚の皿','三枚の皿'),
                    ('二台の機会\t機会を待つ','二台の機械\t機会を待つ')]:
            with self.subTest(source=a):self.check(a,b)

    def test_screen_marker_destination_and_native_nominal_reading(self):
        for a,b in [('カーソルを箸に移動する','カーソルを端に移動する'),
                    ('ポインターを箸へ移す','ポインターを端へ移す'),
                    ('箸にカーソルを合わせる','端にカーソルを合わせる'),
                    ('カーソルをはしに移動する','カーソルを端に移動する'),
                    ('キャレットを箸に置く','キャレットを端に置く'),
                    ('箸で豆をつかむ','箸で豆をつかむ'),
                    ('箸の写真にカーソルを合わせる','箸の写真にカーソルを合わせる'),
                    ('カーソルを端に移動する','カーソルを端に移動する'),
                    ('カーソルを箸に移動\t箸で豆をつかむ','カーソルを端に移動\t箸で豆をつかむ')]:
            with self.subTest(source=a):self.check(a,b)

    def test_photographic_action_and_physical_continuation(self):
        for a,b in [('写真を取る','写真を撮る'),('写真を取った','写真を撮った'),
                    ('写真を取ります','写真を撮ります'),('写真をとる','写真を撮る'),
                    ('動画を取って保存する','動画を撮って保存する'),
                    ('写真を取って机に置く','写真を取って机に置く'),
                    ('写真を撮って机に置く','写真を取って机に置く'),
                    ('写真を取って荷物を置く','写真を撮って荷物を置く'),
                    ('メモを取る','メモを取る'),('本を取る','本を取る'),
                    ('写真を取る\t本を取る','写真を撮る\t本を取る'),
                    ('「写真を取る」という文字列','「写真を取る」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_native_owner_spelling_and_predicate(self):
        for a,b in [('よそくのせいど','予測の精度'),('ほせいのせいど','補正の精度'),
                    ('ほいーるのかいてん','ホイールの回転'),('よそくのせいどをたかめる','予測の精度を高める'),
                    ('にだいのきかいをつかう','二台の機械を使う'),('いちまいのかみをおる','一枚の紙を折る'),
                    ('よそくの制度を改正する','予測の制度を改正する'),
                    ('社会の制度を改正する','社会の制度を改正する'),
                    ('ほいーるの店が開店する','ほいーるの店が開店する'),
                    ('よそくのせいど\t制度を改正する','予測の精度\t制度を改正する'),
                    ('「よそくのせいど」という文字列','「よそくのせいど」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_edit_activity_and_actual_content_object(self):
        for a,b in [('文書を偏執する','文書を編集する'),('原稿を偏執した','原稿を編集した'),
                    ('文章を偏執します','文章を編集します'),('記事をへんしゅうする','記事を編集する'),
                    ('映像を偏執する','映像を編集する'),('音声を偏執する','音声を編集する'),
                    ('偏執的な文章','偏執的な文章'),('原稿に執着する','原稿に執着する'),
                    ('文書の作者が偏執的だ','文書の作者が偏執的だ'),
                    ('文書を偏執する\t偏執的な文章','文書を編集する\t偏執的な文章'),
                    ('「文書を偏執する」という文字列','「文書を偏執する」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_measured_values_and_planned_achievement(self):
        for a,b in [('距離を図る','距離を測る'),('高さを計る','高さを測る'),
                    ('温度を量る','温度を測る'),('時間を図る','時間を計る'),
                    ('重さを測る','重さを量る'),('重さをはかる','重さを量る'),
                    ('改善を測る','改善を図る'),('効率化を測ります','効率化を図ります'),
                    ('距離を図った','距離を測った'),('長さを図って記録する','長さを測って記録する'),
                    ('改善を数値で測る','改善を数値で測る'),('会議に諮る','会議に諮る'),
                    ('距離を図る\t図を描く','距離を測る\t図を描く'),
                    ('「距離を図る」という文字列','「距離を図る」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_native_kana_object_and_verb(self):
        for a,b in [('きょりをはかる','距離を測る'),('じかんをはかる','時間を計る'),
                    ('おもさをはかる','重さを量る'),('たかさをはかる','高さを測る'),
                    ('かいぜんをはかる','改善を図る'),('しゃしんをとった','写真を撮った'),
                    ('げんこうをへんしゅうする','原稿を編集する'),('おんせいをへんしゅうした','音声を編集した'),
                    ('きょりをはかって記録する','距離を測って記録する'),
                    ('きょりをはかる\t図を描く','距離を測る\t図を描く'),
                    ('「きょりをはかる」という文字列','「きょりをはかる」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_physical_destination_and_digital_storage(self):
        for a,b in [('写真を撮って机に置く','写真を取って机に置く'),
                    ('写真を撮ってつくえにおく','写真を取って机に置く'),
                    ('写真を取ってフォルダに置く','写真を撮ってフォルダに置く'),
                    ('写真を撮ってフォルダに置く','写真を撮ってフォルダに置く'),
                    ('しゃしんをとってフォルダにおく','写真を撮ってフォルダに置く'),
                    ('写真を撮って箱にしまう','写真を取って箱にしまう'),
                    ('写真を撮って荷物を机に置く','写真を撮って荷物を机に置く'),
                    ('写真を撮って荷物をつくえにおく','写真を撮って荷物を机に置く')]:
            with self.subTest(source=a):self.check(a,b)

    def test_measurement_does_not_claim_other_native_actions(self):
        for source in ('距離をのばす','重さをかえる','改善をめざす','時間をつかう','長さをたす','幅をせばめる'):
            with self.subTest(source=source):self.check(source,source)

    def test_placement_spelling_with_independent_contextual_repairs(self):
        for a,b in [('机におく','机に置く'),('机においた','机に置いた'),
                    ('箱におきます','箱に置きます'),('床において待つ','床に置いて待つ'),
                    ('棚においてある','棚に置いてある'),
                    ('しゃしんをとってつくえにおく','写真を取って机に置く'),
                    ('写真を撮ってつくえにおいた','写真を取って机に置いた'),
                    ('机の上におく','机の上に置く'),('そこにおく','そこに置く'),
                    ('確認しておく','確認しておく'),('準備しておきます','準備しておきます'),
                    ('ほんをよんでねま','ほんをよんでねま'),
                    ('机におく\t準備しておく','机に置く\t準備しておく'),
                    ('「机におく」という文字列','「机におく」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_healing_and_repair_follow_the_actual_object(self):
        for a,b in [('風邪を直す','風邪を治す'),('怪我を直した','怪我を治した'),
                    ('虫歯を直します','虫歯を治します'),('時計を治す','時計を直す'),
                    ('姿勢を治す','姿勢を直す'),('文章を治した','文章を直した'),
                    ('びょうきをなおす','病気を治す'),('ごじをなおす','誤字を直す'),
                    ('とけいをなおす','時計を直す'),('風邪をなおす','風邪を治す'),
                    ('風邪薬を直す','風邪薬を直す'),('文章を読む','文章を読む'),
                    ('誤字を減らす','誤字を減らす'),('距離をのばす','距離をのばす'),
                    ('高さを直す','高さを直す'),
                    ('「風邪を直す」という文字列','「風邪を直す」という文字列'),
                    ('風邪を直す\t時計を治す','風邪を治す\t時計を直す')]:
            with self.subTest(source=a):self.check(a,b)

    def test_duty_employment_and_effort_use_the_actual_case(self):
        for a,b in [('司会を勤める','司会を務める'),('議長を努めた','議長を務めた'),
                    ('主役をつとめます','主役を務めます'),('会社に務める','会社に勤める'),
                    ('銀行に努めた','銀行に勤めた'),('改善に勤める','改善に努める'),
                    ('事故防止に務めます','事故防止に努めます'),
                    ('品質の向上に務める','品質の向上に努める'),
                    ('しかいをつとめる','司会を務める'),('かいしゃにつとめる','会社に勤める'),
                    ('かいぜんにつとめる','改善に努める'),
                    ('会社に入る','会社に入る'),('司会を頼む','司会を頼む'),
                    ('会社の会議に努める','会社の会議に努める'),
                    ('会社のために努める','会社のために努める'),
                    ('司会を勤める\t会社に務める','司会を務める\t会社に勤める'),
                    ('「会社に務める」という文字列','「会社に務める」という文字列'),
                    ('つくえにおく','机に置く'),('はこにおいた','箱に置いた'),
                    ('準備しておく','準備しておく'),('今すぐに行く','今すぐに行く')]:
            with self.subTest(source=a):self.check(a,b)

    def test_attainment_action_uses_what_is_attained(self):
        for a,b in [('税金を収める','税金を納める'),('会費を修めた','会費を納めた'),
                    ('月謝をおさめます','月謝を納めます'),('勝利を治めた','勝利を収めた'),
                    ('武術を収めます','武術を修めます'),('領地を収めた','領地を治めた'),
                    ('ぜいきんをおさめる','税金を納める'),('せいこうをおさめた','成功を収めた'),
                    ('がくもんをおさめる','学問を修める'),('くにをおさめる','国を治める'),
                    ('税金を払う','税金を払う'),('国を訪れる','国を訪れる'),
                    ('「税金を収める」という文字列','「税金を収める」という文字列'),
                    ('税金を収める\t国を修める','税金を納める\t国を治める')]:
            with self.subTest(source=a):self.check(a,b)

    def test_reserved_places_and_natural_environments(self):
        for a,b in [('海上を予約する','会場を予約する'),
                    ('海上を借りる','会場を借りる'),
                    ('海上を確保する','会場を確保する'),
                    ('海上を予約\t海上を航行する','会場を予約\t海上を航行する'),
                    ('海上を航行する','海上を航行する'),
                    ('海上輸送を予約する','海上輸送を予約する'),
                    ('会議室を予約する','会議室を予約する'),
                    ('客室を予約する','客室を予約する'),
                    ('解錠を予約する','解錠を予約する'),
                    ('「海上を予約する」という文字列','「海上を予約する」という文字列')]:
            with self.subTest(source=a):self.check(a,b)

    def test_reading_and_written_forms_share_meaning(self):
        for a,b in [('にほんの線','二本の線'),('にほんの線\t','二本の線\t'),
                    ('にほんの直線\t','二本の直線\t'),('はしでカーソルの','端でカーソルの'),
                    ('地図ににほんの線を引く','地図に二本の線を引く'),
                    ('ほんの線','ほんの線'),('ここの線','ここの線')]:
            with self.subTest(source=a):self.check(a,b)

    def test_specific_parallel_relation_can_choose_country(self):
        for a,b in [('日本の線と韓国の線を比較する','日本の線と韓国の線を比較する'),
                    ('にほんの線と韓国の線を比較する','日本の線と韓国の線を比較する'),
                    ('韓国の線とにほんの線を比較する','韓国の線と日本の線を比較する'),
                    ('にほんの線\t韓国の線','二本の線\t韓国の線'),
                    ('日本の線と一本の線を比較する','二本の線と一本の線を比較する')]:
            with self.subTest(source=a):self.check(a,b)

    def test_arrival_and_political_context(self):
        for a,b in [('政界に辿り着く','正解に辿り着く'),
                    ('考え続けて政界に辿り着く','考え続けて正解に辿り着く'),
                    ('政界に辿り着く\t議員','正解に辿り着く\t議員'),
                    ('政治家を目指して政界に辿り着く','政治家を目指して政界に辿り着く'),
                    ('日本の政界に辿り着く','日本の政界に辿り着く')]:
            with self.subTest(source=a):self.check(a,b)

    def test_question_extent_and_actual_tools(self):
        for a,b in [('出るカマで考える','出るかまで考える'),
                    ('いつ出るカマで考える','いつ出るかまで考える'),
                    ('分かるカマで調べる','分かるかまで調べる'),
                    ('古い釜で煮る','古い釜で煮る'),
                    ('使う鎌で刈る','使う鎌で刈る'),
                    ('作った鍋で考える','作った鍋で考える')]:
            with self.subTest(source=a):self.check(a,b)

    def test_alternative_reading_retains_pos(self):
        from contextual_repair import _same_context_reading
        self.assertTrue(_same_context_reading([('端','名詞:一般','はじ',0,1,True,'')],'はし'))
        self.assertFalse(_same_context_reading([('正','名詞:一般','せい',0,1,True,'')],'ただし'))

if __name__=='__main__':unittest.main()
