# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""General semantic roles for explicit arguments and native action sequences.
Design and counterexamples: GPT-6, 2026-09-11. No typo/answer pairs or personal data.
Positive role matches rank candidates after anomaly detection. A separate, narrow
argument-frame check recognizes terminal subject-only predicates with an explicit object.
Unknown or unmatched categories provide no evidence. Metaphor, metonymy and omitted
arguments remain possible. This is a small, versioned classification of ordinary
words and grammatical roles; it is not intended to describe all Japanese semantics.
"""
KNOWLEDGE_VERSION = '2026-10-04d'
ROLE_ASSIGNMENT_ACTIONS = ('指名','任命','選任','選出','推薦')
TRANSLATION_ACTIONS=frozenset('翻訳 和訳 英訳 直訳 意訳 訳す'.split())

from functools import lru_cache

# 48-AHO / GPT-6 Astra / 2026-09-16: these temporal readings need a
# host/interval; an IPADIC 副詞可能 entry alone does not license a bare adverb.
# Nouns (powder 末, grade 中), other readings, and whole native compounds
# remain available. Daijisen/Nikkoku: 末, 間, 中 (kotobank); no repair pairs.
DEPENDENT_TEMPORAL_READINGS=frozenset((
    ('末','まつ'),('間','かん'),('中','ちゅう'),('中','じゅう'),
    ('前','ぜん'),('後','ご'),
))


# 48-AIY / GPT-6 Astra / 2026-09-16: rhetorical あに requires a
# responding negative/modal construction, not any arbitrary finite clause.
# Daijisen/Nikkoku: https://kotobank.jp/word/豈-426190 . This excludes it
# only from unconditional adverb projection; original literary text remains
# available to the existing grammar and literal protections.
DEPENDENT_RHETORICAL_READINGS=frozenset((('あに','あに'),('豈','あに')))


# 48-AMD / GPT-6 Astra / 2026-09-20: ごく describes a degree of
# a property/frequency/amount. Its POS alone does not license an arbitrary
# following nominal clause. Original lexical/grammatical evidence remains.
# Shogakukan Daijisen/Nikkoku: https://kotobank.jp/word/極-53196
# 48-ANV / GPT-6 Astra / 2026-09-20: 分/ぶん expresses an amount
# relative to its nominal/clausal host, not an unconditional bare adverb.
# JF B1-2 grammar: https://md.jpf.go.jp/userfiles/file/2018/Lengua%20Japonesa/Gramatica/B1-2-JP.pdf
# The standalone noun, counted 分 and whole 半分/十分 remain independent.
DEPENDENT_DEGREE_READINGS=frozenset((('ごく','ごく'),('極','ごく'),('極く','ごく'),('分','ぶん'),('位','くらい')))


def adverbial_reading_needs_host(face,reading):
    return (face,reading) in (DEPENDENT_TEMPORAL_READINGS | DEPENDENT_RHETORICAL_READINGS
                            | DEPENDENT_DEGREE_READINGS)


@lru_cache(maxsize=2048)
def unadorned_nominal_prefix_parts(text):
    """48-AIS: 素 + an unchanged native common noun, as an unadorned thing.

    Reviewed grammatical prefix, not an IPAdic entry or a typo pair.
    Daijisen 素: https://kotobank.jp/word/素-539379 . Its nominal prefix
    sense survives IPAdic choosing the homographic noun もと. A native
    common-noun host is required; no arbitrary action, name or unknown tail.
    Independent use of 素画像: ITE Winter 2002, paper 9-3,
    https://www.jstage.jst.go.jp/article/itetaikai/02win/0/02win_0_62/_pdf/-char/en .
    """
    if not text.startswith('素') or len(text)<2:return None
    from morphology import dictionary_inflections
    host=text[1:]
    rows=tuple(row for row in dictionary_inflections(host) or ()
               if row[0].startswith('名詞,一般,') and row[2]==host)
    if not rows:return None
    return ('素','す',host,tuple(sorted({row[3] for row in rows})))


@lru_cache(maxsize=2048)
def unadorned_nominal_prefix_ranges(text):
    if '素' not in text:return ()
    from morphology import tokenize
    parts=tokenize(text);out=[]
    for i,(a,b) in enumerate(zip(parts,parts[1:])):
        # 48-AIV: a prefix begins a nominal word. Do not certify an
        # internal substring of an unexplained adjacent noun compound
        # (or unknown token) as an independently complete source word.
        previous=parts[i-1] if i else None
        if (previous and previous.end==a.start
                and (not previous.has_reading or previous.pos in ('名詞','接頭詞'))):
            continue
        if (a.surface=='素' and a.end==b.start and a.has_reading and b.has_reading
                and b.pos=='名詞' and unadorned_nominal_prefix_parts(a.surface+b.surface)):
            out.append((a.start,b.end))
    return tuple(out)


def unadorned_action_conflicts(text,tokens):
    """Bare/unadorned modifies an entity, not an arbitrary procedure.

    This is the same ordinary prefix sense as unadorned_nominal_prefix_parts.
    An actual whole native compound has its own lexical meaning. Require
    a positively classified process and a sahen-only head, not just an
    absent word in a list. No corrected word supplies the source judgment.
    """
    if '素' not in text:return ()
    from morphology import dictionary_inflections
    from literal_examples import protected_ranges,overlaps
    out=[];protected=None
    for left,right in zip(tokens,tokens[1:]):
        if not (left[0]=='素' and left[5] and right[5] and left[4]==right[3]
                and right[1].startswith('名詞:サ変接続')
                and 'process' in nominal_roles(right[0])):continue
        if unadorned_nominal_prefix_parts(left[0]+right[0]):continue
        if dictionary_inflections(left[0]+right[0]):continue
        if protected is None:protected=protected_ranges(text)
        if not overlaps(left[3],right[4],protected):
            out.append((left[0],right[0],left[3],right[4]))
    return tuple(out)


def preserves_unadorned_nominal_prefix(original,changed):
    """The same source evidence also rejects a one-character legacy deletion."""
    spans=unadorned_nominal_prefix_ranges(original)
    if not spans:return True
    from difflib import SequenceMatcher
    blocks=SequenceMatcher(None,original,changed,autojunk=False).get_matching_blocks()
    return all(any(block.a<=start and end<=block.a+block.size for block in blocks)
               for start,end in spans)


# 48-AIW / GPT-6 Astra / 2026-09-16: ordinary edible vegetables and
# their common written forms. Positive food/ingredient evidence only;
# no typo pair and no inference that every plant is edible.
# 48-ALB / GPT-6 Astra / 2026-09-20: common raw vegetables retain
# both food and ingredient roles. Feed below is food, not a washing ingredient.
CULINARY_VEGETABLES='玉葱 玉ねぎ タマネギ たまねぎ 人参 ニンジン にんじん 大根 ダイコン だいこん キャベツ 白菜 ピーマン じゃがいも ジャガイモ トマト とまと 胡瓜 きゅうり キュウリ 茄子 なす ナス 南瓜 かぼちゃ カボチャ ほうれん草 ほうれんそう ホウレンソウ ブロッコリー レタス 葱 ねぎ ネギ'.split()


# 48-AJJ / GPT-6 Astra / 2026-09-16: disorder as a state, rather
# than collectible objects or records about that state. Exact written heads
# only; unknown objects remain unclassified, and literal protection applies.
# Kanjipedia 収拾 /kotoba/0003095300 and 収集 /kotoba/0003095400.
DISORDER_NOUNS='混乱 騒動 紛糾 混迷'.split()


# 48-AKG / GPT-6 Astra / 2026-09-16: representation properties,
# not files, documents or rights temporarily held for another owner.
# Bare 形式/書式 remain ambiguous and are not assigned this category.
# https://support.microsoft.com/ja-jp/excel/save-a-workbook-in-another-file-format
# https://www.kanjipedia.jp/kotoba/0006259300
REPRESENTATION_FORMATS='データ形式 ファイル形式 保存形式 表示形式 画像形式 音声形式 動画形式 文字コード 符号化方式 エンコーディング'.split()

# 48-AMM / GPT-6 Astra / 2026-09-20: ordinary edible shellfish,
# reviewed as food and raw ingredients, not every shell-bearing organism.
# A shell, container, picture or name of a shellfish does not inherit food.
# Kanjipedia: https://www.kanjipedia.jp/kotoba/0004993200 (マテガイ).
CULINARY_SHELLFISH='アサリ 浅蜊 ハマグリ 蛤 シジミ 蜆 ホタテ 帆立 カキ 牡蠣 サザエ 栄螺 アワビ 鮑 マテガイ 馬刀貝'.split()

# 48-AMQ / GPT-6 Astra / 2026-09-20: ordinary physical materials are
# tangible objects as well as possible container materials. The same roster
# supplies both roles; no edible/content/abstract role is inherited.
# Reuse AMH physical-material classifications; Daijisen 木材-142205.
# Exact native noun readings and actual predicate inflections still own use.
PHYSICAL_MATERIALS='紙 木材 竹 布 革 金属 鉄 銅 ガラス 樹脂 プラスチック'.split()

# GPT-6 Astra / 2026-09-26: ordinary quality, mechanism and art senses.
# These classes compare source relationships and candidate relationships;
# they are not misspelling/answer pairs or a declaration that every use fits.
QUALITY_ASSESSMENTS=frozenset('判定 測定 計測 計算 検出 認識 識別 予測 分析 評価 推定 判断 補正 校正 修正 翻訳 照合 検索 抽出 分類 推論 診断 推測'.split())
# Cognitive predicates select a proposition, not a physical cooking/cutting tool.
COGNITIVE_PREDICATES=frozenset('考える 思う 悩む 迷う 調べる 確かめる'.split())
# Same-reading verb forms retain their actual native conjugation and sense.
ACTION_MEANINGS={'object_placement':frozenset(('置く',)),'image_capture':frozenset('撮る 撮影'.split()),
                 'acquisition':frozenset('取る 採る 得る 取得 採取'.split())}
from measurement_meaning import OBJECTS as MEASUREMENT_OBJECTS, ACTIONS as MEASUREMENT_ACTIONS, CASES as ACTION_CASES
ACTION_MEANINGS.update(MEASUREMENT_ACTIONS)
ACTION_MEANINGS.update({'homecoming':frozenset(('帰る',)),
    'restored_state':frozenset(('返る',)),'natural_cycle':frozenset(('還る',))})
NOUN_GROUPS={
 # Daijisen/Nikkoku 移す, illness transmission: https://kotobank.jp/word/移す-440805
 # Keep this separate from healable injuries and other non-transmissible conditions.
 'transmissible_illness':'病気 風邪'.split(),
 # 48-AYM / GPT-6 Astra, 2026-10-01: ordinary relational noun senses.
 # Shared source/candidate compounds; no mistyped-word/answer pairs.
 'operation_mode':'モード 方式 形式'.split(),
 'information_field':'欄'.split(),
 'effect':'効果 効き目'.split(),
 'state_change':'バフ デバフ'.split(),
 'spatial_attribute':'位置'.split(),
 'visual_region':'ウィンドウ ウインドウ'.split(),
 'cancellation':'解除 取消 取消し'.split(),
 'support_surface':'机 テーブル 台 棚 床 地面 椅子 ベンチ 台座 卓上 机上 卓 盆'.split(),
 'digital_destination':'フォルダ ディレクトリ ドライブ ディスク メモリ データベース 保存先 クラウド サーバー サーバ'.split(),
 'text_edit_activity':'編集 校正 推敲 添削 加筆 修正 書き直し'.split(),
 'fixation_state':'偏執 執着 固執 執念 偏愛'.split(),
 'photographic_media':'写真 画像 映像 動画 ビデオ'.split(),
 # Ordinary sheet-like objects counted with 枚; native quantities own use.
 'sheet_object':'紙 用紙 紙片 紙切れ 葉 写真 図面 絵 布 板 皿 札 カード 切符 便箋 封筒'.split(),
 'adhesive':'糊 テープ シール ラベル 切手 絆創膏 湿布 壁紙'.split(),
 'flexible_material':'布 糸 紐 綱 縄 ロープ 弦 膜 皮 皮革 テント 幕 網'.split(),
 # GPT-6 Astra / 2026-09-26: facilities that people reserve or borrow,
 # versus open natural environments. Shared senses, not homophone pairs.
 'reservable_place':'会場 会議室 ホール 部屋 客室 教室 体育館 講堂 式場 宴会場 スタジオ 店舗 施設 席 座席 宿 ホテル 旅館'.split(),
 'open_environment':'海上 海中 海底 洋上 水上 水中 河口 河川 山中 上空 空中 地中 天空 高空'.split(),
 'method':'手段 方法 方策 対策 措置 選択肢'.split(),
 # A person's unspoken content is inferred, understood or taken into account.
 'mental_content':'意図 意向 真意 本意 気持ち 心情 胸中 心中 思い 趣旨 狙い'.split(),
 'intrinsic_process':'退化 進化 老化 劣化 酸化 硬化 軟化'.split(),
 'cooking_cutting_tool':'鎌 釜 カマ 鍋 ナベ 包丁 ハサミ 鋏'.split(),
 'political_arena':'政界 議会 国会 内閣 政治'.split(),
 'political_context':'政治 政治家 議員 代議士 選挙 当選 立候補 官僚 政党 政治活動 議会 国会 内閣'.split(),
 'epistemic_result':'正解 解答 答え 結論 真相 真理 理解 解決策 最適解 解決'.split(),
 'eating_tool':'箸 スプーン フォーク 匙 包丁 菜箸'.split(),
 'screen_marker':'カーソル ポインター ポインタ キャレット 選択範囲'.split(),
 'screen_location':'端 中央 隅 右 左 上 下'.split(),
 'geometric_line':'線 直線 曲線 平行線 縦線 横線 矢印'.split(),
 'quality_measure':'精度 正確度 正確性 確度 感度 信頼性 解像度 分解能 再現性 安定性 精密さ'.split(),
 'social_institution':'制度 体制 法制 政体 組織'.split(),
 'rotating_control':'ホイール 車輪 タイヤ 歯車 ハンドル ダイヤル ローラー ノブ'.split(),
 'physical_motion':'回転 旋回 回動 移動 変位 角度 振動 スクロール'.split(),
 'opening_event':'開店 閉店 開業 開校 閉校 開通 開会 閉会'.split(),
 'literary_style':'古典 近代 現代 古代 中世 伝統 前衛 抽象 具象 叙情 叙事 写実 浪漫 印象'.split(),
 'art_form':'詩 散文 韻文 小説 文学 音楽 歌曲 絵画 演劇 美術 舞踊 映画 芸術'.split(),
 # 48-AML / GPT-6 Astra / 2026-09-20: an error is the object
 # of correction or detection. It is not the document containing it.
 # Shogakukan Daijisen: /word/間違い-634581, /word/修正-182008,
 # /word/直す-587499 at https://kotobank.jp . Positive senses only.
 'error':'間違い 誤り 誤記 誤字 脱字 記載ミス 入力ミス 計算ミス ミス エラー'.split(),
 # 48-ANW / GPT-6 Astra / 2026-09-20: the clipboard view is a
 # displayed interface; spring parts are ordinary objects, not food.
 # https://support.microsoft.com/ja-jp/windows/apps/using-the-clipboard
 # https://www.jsme.or.jp/jsme-medwiki/doku.php?id=13%3A1010281
 'presentation':'画面 タブ 表示面 描画面 プレビュー 表示 クリップボード'.split(),
 # 48-APE / GPT-6 Astra / 2026-09-24: spoken content is information.
 # Daijisen: https://kotobank.jp/word/話-603466 .
 'quantity':'人数'.split(),
 # JIS X 0006 06.02.01/04: input/output also denote data, not just
 # processing. Reuse that information sense across ordinary predicates.
 # https://ny.ics.keio.ac.jp/ipsjts1/2nd-ver/htm/x0006.htm
 # GPT-6 / 2026-10-04: facts and their true circumstances are information
 # which can be known, explained or understood, not physical objects/food.
 # This lexical classification is independent of a spelling or key repair.
 'information':'真実 真相 実情 実態 入力 出力 ウェブ 話 合格 不合格 当選 落選 採用 不採用 感想 見解 批評 論評 レビュー 意見 要望 提案 考え 方針 評価 判断 知識 経験 見識 日付 やり方 理由 原因 結果 意味 意図 事情 状況 状態 条件 仕様 設定 決定 手順 方法 概要 詳細 情報 内容 データ 記録 履歴 数値 値 住所 名前 氏名 番号 日時 時刻 時間 日程 予定 計画 事実'.split(),
 # Native writing systems are text arguments for input, reading and editing.
 # GPT-6 Astra: ordinary role classification; no intended correction pairs.
 # Explanations, reports and instructions can denote written content.
 # 48-AKZ / GPT-6 Astra / 2026-09-20: books and literary works are text.
 # 48-AME / GPT-6 Astra / 2026-09-20: ordinary communicated text,
 # selection outcomes, and table textiles share existing roles. The message
 # does not inherit the outcome's action or a depicted/contained food sense.
 # GPT-6 Astra / 2026-09-24: written rules and agreements are documents.
 # They may arrive or be read; this does not prescribe their literal subject actions.
 # Copies of written documents retain the existing text-object sense.
 # Ricoh explains their paper/text content; JF teaches コピーを取る.
 # https://www.kouken.ricoh/science_caravan/QandA/science/qanda1_3.html
 # https://www.erin.jpf.go.jp/jp/lesson/04/let-us-see/
 'text':'読み キー コピー 規約 規則 規定 約款 条例 契約 規程 要領 マニュアル ファイル メモ 通知 通達 告知 言葉 表現 説明 解説 報告 案内 指示 回答 解答 文章 文 文字 文字列 単語 語句 書類 資料 書面 文書 見出し 注釈 目次 段落 本 書 書籍 絵本 童話 物語 小説 詩 詩集 図鑑 史料 新聞 雑誌 冊子 原稿 記事 報告書 説明書 手紙 メール 図 表 画像 写真 図面 ページ 頁 仮名 かな カナ 平仮名 ひらがな 片仮名 カタカナ 漢字 ローマ字 英字 数字 記号 点字'.split(),
 # 48-AJP / Astra: character systems can be conversion results, not
 # the owner/location to which a borrowed item is returned.
 'writing_system':'仮名 かな カナ 平仮名 ひらがな 片仮名 カタカナ 漢字 ローマ字 英字 数字 点字'.split(),
 'extent':'範囲 区間 部分 領域'.split(),
 # 48-AIK / GPT-6 Astra / 2026-09-16: the original position or state
 # is a return destination. This is not a person's identity (身元).
 'origin':'元 もと 元通り 元どおり もとどおり'.split(),
 'return_state':'正気 我 童心 初心 白紙 意識 手元 原点'.split(),
 'cyclic_origin':'土 自然 大地 大自然'.split(),
 'home_destination':'故郷 実家 里 祖国 母国 国'.split(),
 # 48-ANC / GPT-6 Astra / 2026-09-20: a deadline is a time limit.
 # Keep 閉め切り (closed room) separate; no new native reading is invented.
 # Daijisen 締め切り sense 2: https://kotobank.jp/word/締切り-524015 .
 'time':'日時 日付 日程 期日 日取り 時刻 時間 日 朝 夜 午前 午後 期限 締切 締切り 締め切り デッドライン タイムリミット'.split(),
 # 48-ALX / GPT-6 Astra / 2026-09-20: calendar words relative to now.
 # Keep this role distinct from the existing に adjunct class; an absolute
 # time and a deictic time have different ordinary particle behavior.
 # JPF: Japanese language communication 202201; grammar 200911 (まで・までに).
 # https://www.jpf.go.jp/j/project/japanese/teach/tsushin/language/202201.html
 # https://www.jpf.go.jp/j/project/japanese/teach/tsushin/grammar/200911.html
 # Previous/current/next occurrence also supplies a relative time (Daijisen 前回).
 # https://kotobank.jp/word/前回-549454
 'relative_time':'前回 今回 次回 一昨日 昨日 今日 明日 明後日 先週 今週 来週 先月 今月 来月 去年 昨年 今年 来年 再来年'.split(),
 # Appointments and plans are not a duration lived through.
 'schedule':'日程 予定 計画 期日 日取り 待ち合わせ 待合せ 待ち合せ 約束 打ち合わせ'.split(),
 # Native input actions can target written text or a physical input control.
 'input_control':'キー ボタン キーボード'.split(),
 'pointing_device':'マウス タッチパッド トラックパッド'.split(),
 'scent':'香り 匂い におい 臭い'.split(),
 'sound':'声 音 音声 音楽 音響 鳴き声 物音'.split(),
 'recording':'動画 映像 ビデオ 録画'.split(),
 # 48-ALV / GPT-6 Astra / 2026-09-20: a visual representation has a
 # depicted subject. Its ordinary content relation is positive evidence;
 # a picture of food does not itself inherit an edible object's role.
 'depiction':'写真 画像 映像 絵 イラスト 図 図面 動画'.split(),
 # Calls are acts of communication as well as device names; no spelling pair.
 'call':'電話 通話 コール'.split(),
 # GPT-6 Astra / 2026-09-24: effort/inconvenience imposed by 掛ける.
 # Daijisen/Nikkoku 手数: https://kotobank.jp/word/手数-176926
 'burden':'手数 お手数 手間 迷惑 負担 心配'.split(),
 # 48-AJY / GPT-6 Astra / 2026-09-16: channels of communication,
 # independent of the content object or the recipient. Positive roles
 # only; a device or an arbitrary text is not automatically a channel.
 # NINJAL Verb Handbook, くれる/行く: communication-medium sense.
 'communication_medium':'メール 電子メール 電話 手紙 はがき 葉書 電報 ファクス ファックス チャット'.split(),
 # Electrical transfer acts on power/current, independently of text or plans.
 # TEPCO PG: https://www4.tepco.co.jp/pg/electricity-supply/operation/flow.html
 'electric_power':'電気 電力 電流'.split(),
 'light':'電気 電灯 明かり 灯り 照明 灯火'.split(),
 # 48-AMI: 和英 also denotes a Japanese-English dictionary (Daijisen).
 'reference':'和英 辞書 辞典 事典 百科事典 索引 一覧 リファレンス 史料'.split(),
 # 48-AMA / GPT-6 Astra / 2026-09-20: a subject field can qualify a
 # reference work or teaching profession. These are ordinary meanings,
 # not typo pairs or a substitute for native word/POS/reading evidence.
 'field':'日本語 国語 英語 中国語 韓国語 ドイツ語 フランス語 数学 算数 理科 物理 化学 生物 歴史 地理 医学 法律 英和 和英 漢和'.split(),
 'teaching':'教師 教員 講師 先生 教授'.split(),
 # 48-AKE / GPT-6 Astra / 2026-09-16: vessels receive their contents.
 # The same destination role preserves source readings; no typo pairs.
 # 48-AMI: the sourced ordinary 薬袋 sense is a physical container.
 # NINJAL basic verb bank 開ける 2-2/2-3 and verb handbook 閉める 7-9.
 # Physical access and business premises, not every tangible object.
 'physical_opening':'窓 扉 ドア 戸 門 雨戸 襖 障子 シャッター カーテン 幕 蓋 ふた 栓'.split(),
 'sealable_container':'缶 缶詰 瓶 ビン 箱 ダンボール箱 袋 封筒'.split(),
 'business_premises':'店 店舗 商店 事務所 窓口 会社 工場 診療所 病院 図書館 教室 レストラン'.split(),
 'container':'薬袋 鍋 フライパン 皿 お皿 茶碗 コップ カップ 瓶 壺 ボウル 封筒 包み 箱 袋 容器 倉庫 棚 引き出し 物置 冷蔵庫 冷凍庫 保管庫 保存先 フォルダ ディレクトリ ドライブ ディスク メモリ データベース'.split(),
 # 48-AMH / GPT-6 Astra / 2026-09-20: attested ordinary physical
 # materials can qualify a container. Writing surfaces, screen contents
 # and abstract representations are not materials as a whole category.
 # Clothing and ordinary wearing are positive senses, shared by source
 # reading and candidate validation. This does not label other actions wrong.
 'clothing':'服 衣服 洋服 和服 着物 上着 シャツ ブラウス コート セーター 制服 礼服'.split(),
 'material':PHYSICAL_MATERIALS,
 # GPT-6 Astra / 2026-09-24: ingredients and water sources qualify hot
 # water; an abstract hierarchy can be represented as a tree. Positive
 # nominal relations only, not a list of corrections or all noun pairs.
 # Shogakukan Daijisen, 湯: https://kotobank.jp/word/湯-563581
 # JAIST: https://www.jaist.ac.jp/project/NLP_Portal/doc/glossary/
 'infusion_material':'炭酸 薬草 香草 薬品 薬 茶 葛 飴 卵 生姜 柚子 菖蒲 塩 蕎麦'.split(),
 'spring_water_source':'温泉 源泉 鉱泉'.split(),
 'hierarchy':'構文 統語 系統 家系 階層 構造'.split(),
 'writing_surface':'紙 用紙 ノート 手帳 帳面 便箋 メモ帳 白板 黒板 掲示板 紙面 頁 ページ 画面'.split(),
 # GPT-6 Astra: visual form, as distinct from the text being described.
 # Written glyphs can be drawn as visual forms (lettering), even when
 # their ordinary linguistic role is text. Adobe's own lettering tutorial:
 # https://blog.adobe.com/jp/publish/2021/04/20/cc-design-fresco-creative-relay-14-bechori
 'shape':'形 形状 輪郭 線 曲線 直線 円 丸 四角 三角 四角形 三角形 図形 模様 絵 イラスト 風景 字 文字 字形 字体 漢字 仮名 平仮名 片仮名 英字 数字 記号 ロゴ'.split(),
 # 48-AIQ / GPT-6 Astra / 2026-09-16: ordinary human referents.
 # Their custody/status does not change the existing person category.
 # 48-ALB / GPT-6 Astra / 2026-09-20: ordinary human pronouns,
 # family members and addressed guests; demonstratives for things are excluded.
 # GPT-6 Astra / 2026-09-21: people named by illness/injury retain the
 # existing person role. This does not classify the disease, institution,
 # a homophone, or the state noun produced by adding 待ち as a person.
 # https://www.kanjipedia.jp/kotoba/0001064000
 # https://kotobank.jp/word/%E7%97%85%E4%BA%BA-613493
 # A named task/office makes its holder a natural selection argument.
 'role_candidate':'担当者 回答者 質問者 候補者 代表 代表者 代理人 後任 進行役 司会者 責任者'.split(),
 'person':'者 患者 病人 怪我人 負傷者 私 わたし わたくし 僕 ぼく 俺 おれ 自分 自身 我々 われわれ あなた 君 きみ 彼 彼女 父 母 兄 姉 弟 妹 祖父 祖母 夫 妻 両親 親 子 きょうだい 兄弟 姉妹 兄妹 姉弟 お客様 お客さま 御客様 人質 捕虜 囚人 奴隷 受刑者 友達 友だち 官僚 議員 医師 看護師 警官 教員 教師 講師 教授 職人 人 人物 本人 他人 大人 巨人 人員 社員 部員 学生 先生 友人 家族 客 子供 子ども 利用者 作者 担当者 選手'.split(),
 # Ordinary physical cleaning, including the body and tableware.
 # 48-ALD / GPT-6 Astra / 2026-09-20: acting on one's own is an
 # adverbial manner. Other people do not inherit this de construction.
 'reflexive_agent':'自分 自身'.split(),
 'body_part':'手 顔 体 身体 足 頭 髪 目 耳 口 鼻 喉 肺 心臓 胃 腸 肝臓 腎臓'.split(),
 # 48-AHS / GPT-6 Astra: ordinary writing and cleaning tools are physical
 # objects. Native reading/POS proof still owns each nominal interpretation.
 # A homophone such as 放棄 or 蜂起 does not inherit the tool's role.
 # 48-AIJ / GPT-6 Astra / 2026-09-16: plant material is a physical
 # object that can be washed, moved and arranged. This does not classify
 # every plant as edible or transfer its sense to a homophonic verb.
 # 48-ALY / GPT-6 Astra / 2026-09-20: ordinary movable household textiles.
 'object':'ばね バネ 発条 薬袋 テーブルクロス ナプキン 布巾 敷物 毛布 絨毯 カーペット マット ラグ 植物 草花 草 花 葉 茎 根 芽 枝 苗 蓼 葱 韮 筆 筆ペン ボールペン 消しゴム 定規 刷毛 はけ ハケ 箒 ほうき ホウキ ブラシ 雑巾 ぞうきん ゾウキン 物 もの 布 布地 タオル ハンカチ 糸 紐 繊維 皿 お皿 食器 茶碗 コップ カップ 箸 鍋 フライパン 荷物 忘れ物 落とし物 遺失物 洗濯物 道具 部品 材料 机 椅子 家具 服 衣服 靴 鉛筆 用紙 箱 袋 容器 鍵 窓 扉 戸'.split()+PHYSICAL_MATERIALS,
 # 48-AGU / GPT-6 Astra: expense amounts are settlement obligations,
 # distinct from tangible manufactured products. Exact native frames only.
 # GPT-6 Astra / 2026-09-27: consideration, remuneration and fees are
 # obligations paid for work, services or an exchange. Positive senses,
 # shared across native spellings; no input-to-answer mapping.
 'expense':'交通費 旅費 宿泊費 出張費 経費 費用 料金 代金 対価 謝礼 報酬 賃金 給料 給与 手数料'.split(),
 'money':'金 お金 資金 財産 費用 料金 代金 寄付金'.split(),
 'representation_format':REPRESENTATION_FORMATS,
 'attribute':'構造 性質 特徴 色 重さ 長さ 幅 高さ 深さ 奥行 奥行き 距離 角度 大きさ 寸法 番号 名称 名前'.split()+REPRESENTATION_FORMATS,
 'event':'開業 開店 閉店 開校 卒業 入学 会議 会合 集会 大会 試合 競技 選挙 授業 講義 式 会見 行事 催し'.split(),
 # 48-AMR / GPT-6 Astra / 2026-09-20: these explicitly classified
 # processes have an ongoing activity sense. Keep this one inventory for
 # process roles and the native N+中 construction; a sahen POS alone is not
 # enough (e.g. 完了/死亡). Other derived process senses are not assumed ongoing.
 # Daijisen 中-96994, suffix sense 3; NINJAL 分類語彙表 1.1652.
 # GPT-6 Astra / 2026-09-24: communicative acts can be the purpose
 # of a document. These are semantic senses, never misspelling pairs.
 'communication_process':'連絡 伝達 報告 説明 通知 相談 引き継ぎ 引継ぎ 申し送り'.split(),
 'general_use_action':['使用'],
 'private_use_action':['私用'],
 'organization':'会社 企業 職場 役所 官公庁 団体 組織 学校 大学'.split(),
 'organizational_property':'社用車 社有車 公用車 社有機材 公有財産'.split(),
 # GPT-6 Astra / 2026-09-27: activities produce outcomes. This positive
 # relation is shared by source integrity and candidate composition; it
 # does not call unknown noun combinations anomalous.
 'outcome':'成果 結果 成績 実績 収穫'.split(),
 # Native nominal heads taking a direct interrogative prefix; a semantic
 # dimension alone is insufficient (direction needs どの方角).
 'interrogative_category_head':'曜日 色 種類 型'.split(),
 'process':'研究 料理 調理 食事 散歩 運動 練習 作業 仕事 処理 操作 計算 解析 検査 実験 調査 開発 印刷 通信 接続 入力 出力 編集 保存 添付 使用 利用 勉強 学習 読書 睡眠 会議 授業 工事 修理 通話'.split(),
 # Spatial nominal heads remain locations inside Nの上/中等. Literal
 # kana うえ/した/なか have the same ordinary locative noun sense; native
 # noun/case proof is still required before these roles can certify a clause.
 # 48-AGQ / GPT-6 Astra: native locative demonstratives, positive case evidence.
 'place':'店 近く 付近 近所 辺り そば 脇 ここ そこ あそこ どこ 上 下 中 内 表面 周囲 周り 隅 奥 手前 うえ した なか 外 屋外 室内 庭 家 自宅 学校 図書館 会社 場所 会場 部屋 教室 会議室 席 座席 宿 施設 店舗 建物 公園 道路 道 山 海 川 空 星空 海上 海域 空域 国境 沿岸 近海 湾岸 駅 空港 港 停留所 バス停 駐車場 改札 ホーム 乗り場 入口 出口 廊下 階段 通路 橋 交差点 横断歩道 病院 工場 役所 市役所 公民館 体育館 食堂 スーパー コンビニ 書店 本屋 銀行 郵便局 警察署 消防署 受付 ロビー'.split(),
 # 48-AHE / GPT-6 Astra: ordinary fruit senses and their attested native
 # spellings. Other homophones do not inherit these roles by reading alone.
 'food':'卵 玉子 林檎 リンゴ りんご 蜜柑 ミカン みかん 苺 イチゴ いちご バナナ 食事 料理 食材 食品 食料 食糧 飼料 食べ物 ご飯 米 パン 肉 魚 野菜 果物 菓子 お菓子'.split()+CULINARY_VEGETABLES+CULINARY_SHELLFISH,
 'ingredient':'卵 玉子 米 肉 魚 野菜 果物 食材'.split()+CULINARY_VEGETABLES+CULINARY_SHELLFISH,
 # GPT-6 Astra / 2026-09-15: ordinary drink nouns, positive argument evidence.
 'drink':'水 茶 お茶 紅茶 緑茶 麦茶 コーヒー 珈琲 ジュース 乳飲料 牛乳 飲料 飲み物 汁 スープ'.split(),
 'medicine':'薬 錠剤 カプセル'.split(),
 # 48-AIB / GPT-6 Astra / 2026-09-16: environmental exposure is an
 # ordinary object of avoidance. Positive roles only: avoiding moisture
 # does not mean reading/eating it; 裂く/裂ける do not inherit 避ける's role.
 'exposure':'湿気 多湿 高温 熱 日光 直射日光 雨 風 冷気'.split(),
 'issue':'問題 課題 難問 懸案 紛争 対立 不具合 障害 トラブル 疑問 謎 不明点 矛盾'.split()+DISORDER_NOUNS,
 'disorder':DISORDER_NOUNS,
 # Ordinary continuation of an activity or text, independent of any misspelling.
 'continuation':'続き'.split(),
 # GPT-6 / 2026-10-04: an ordinary part or remainder relates to its
 # whole object, amount, text or activity. Lexical senses, not repair pairs.
 'partitive':'残り 一部 部分 残部'.split(),
 'device':'電話 キーボード マウス カメラ マイク モニター 機械 装置 機器 パソコン 端末 サーバー サーバ プリンター 印刷機 エンジン システム ソフト ソフトウェア アプリ'.split(),
}

NOUN_GROUPS.update({group:words for group,(role,words) in MEASUREMENT_OBJECTS.items()})
# 48-ABU / GPT-6 / 2026-09-13: positive ordinary object/action fit.
# Used with exact native readings and actual inflection for clause composition.
# These roles do not declare other objects impossible (metaphor is still possible).
# 48-ABY / GPT-6 / 2026-09-13. Actions controlling the execution/order of
# another action. The lexical classes are independent of typo/answer pairs.
ACTION_CONTROL_PREDICATES=frozenset('優先 終了 開始 再開 中止 継続 完了'.split())


PREDICATE_GROUPS=(
 # The existing action-control class also takes a process/event object.
 # Share positive case and relative-head evidence, not typo/answer pairs.
 # Native source morphology still owns the actual argument and ending.
 # https://anzeninfo.mhlw.go.jp/hiyari/hiy_0312.html
 ('process event',' '.join(sorted(ACTION_CONTROL_PREDICATES))),
 # IPAL おこなう: the object is an act or event. This is positive
 # argument evidence; unclassified objects are not declared anomalous.
 # https://www2.ninjal.ac.jp/dictionaries/IPALBV/pdf_dir/おこなう.pdf
 ('process event continuation','行う 行なう やる する'),
 # An activity/text continuation can be resumed or edited. These are
 # positive ordinary senses, not an assertion about any surname.
 # Daijisen 続き sense 1: https://kotobank.jp/word/続き-571885 .
 ('continuation','始める 続ける 終える 読む 書く 再開 編集'),
 ('sound recording depiction photographic_media','編集'),
 ('quality_measure','高める 上げる 下げる 向上 改善 確認 測る 測定 評価 比較'),
 ('object material writing_surface','折る 折り畳む 畳む'),
 ('photographic_media','撮る'),
 ('text object','取る'),
 ('object text information money','受け取る'),
 ('method','取る 採る 選ぶ 用いる 採用 実行 試みる 講じる'),
 # 48-AGH / GPT-6 Astra: reducing a duration or the time spent on a task.
 # Attested action usage, not a homophone/answer pair. NDL bibliographic use:
 # https://ndlsearch.ndl.go.jp/books/R100000002-I032604496
 ('time process event','短縮 時短'),
 # 48-AHL / GPT-6 Astra: ordinary adjustment of schedules, settings,
 # balance and equipment. JPF language/202407 and Kanjipedia 0004835100.
 ('time schedule event process information attribute device','調整'),
 # 48-AIL / GPT-6 Astra / 2026-09-16: plans, issues and information
 # can be the matter discussed. The addressed person retains its own に/と
 # role; no reading pair or incompatibility is inferred from missing roles.
 ('information schedule issue','相談 協議 議論 検討 審議'),
 # Resolving an issue has an ordinary accusative argument as well as
 # the existing subject use. This is positive evidence, not exclusion.
 # https://kotoba.ninjal.ac.jp/mado/19/19-01/
 ('issue','解決'),
 # Kanjipedia 配電: https://www.kanjipedia.jp/kotoba/0005571800
 ('electric_power','送電 配電'),
 # GPT-6 Astra / 2026-09-14: ordinary use and transfer/request roles.
 ('information text object device reference money place ingredient','使う 用いる 利用 活用 使用'),
 ('information text object food drink money device','くださる 下さる もらう 貰う いただく 頂く'),
 ('extent','保存 確認 選択 削除 表示 印刷 読む 書く 調べる'),
 ('information text sound','聞く 聴く'),
 ('scent object food drink','嗅ぐ'),
 ('information attribute money object text','得る 獲得'),
 # 48-AMX / GPT-6 Astra / 2026-09-20: ordinary visual perception
 # includes a displayed image and a writing surface, independent of
 # reading its contents. This does not make those surfaces edible.
 # https://www.kanjipedia.jp/kotoba/0001902300 (senses 1-2)
 # Schedule contents can also be inspected (IPAL miru #03; calendar
 # information in Microsoft Outlook's official user guide). Share the
 # existing schedule category, without making it edible or a physical tool.
 ('information text object person device place event shape attribute presentation writing_surface schedule','見る'),
 # Ordinary visual presentation and a gaze toward an object or place.
 ('information text sound object person shape presentation body_part','見せる'),
 ('place object person shape presentation','見上げる 見下ろす'),
 # GPT-6 Astra: ordinary comparison, collection and retrieval roles.
 # A word outside these positive categories remains unclassified.
 ('information text attribute object person device place food money event process','比べる 較べる 選ぶ'),
 ('information text object person money food device','集める'),
 # Counting a stated number is an ordinary quantitative action.
 ('information text object person money food device quantity','数える'),
 # 48-AJJ: gathering and settling have distinct ordinary objects.
 # 収拾 also has the literal gathering sense; do not force 資料を収拾
 # into a different spelling merely because 収集 is more familiar.
 ('information text object money','収集 蒐集 採集 収拾'),
 ('disorder','収拾 鎮める 収める'),
 ('information text object person device place','見つける'),
 ('information text process event person','覚える 学ぶ 思い出す'),
 # NINJAL IPAL hiku #09: drawing a line is a distinct ordinary sense.
 ('information text reference geometric_line','引く'),
 # Ordinary investigation, trials and temperature changes; no typo pairs.
 ('information text reference object person device place','調べる 確かめる 探す'),
 # IPAL しらべる #02: investigate an abstract matter, including an event
 # or an action/process. A process is not thereby a physical reading object.
 # https://www2.ninjal.ac.jp/dictionaries/IPALBV/pdf_dir/しらべる.pdf
 ('process event','調べる'),
 # Physical inspection can establish an organ's nominal reading as well.
 ('body_part object device food ingredient information attribute','検査'),
 ('body_part','調べる 確かめる'),
 ('information text device process','試す'),
 ('food drink object','温める 暖める 冷やす 冷ます'),
 ('object food','干す 乾かす'),
 # 48-AMM: native 焼く includes cooking, heating/manufacture, combustion,
 # photographic printing and effects on skin. Other senses are not denied.
 # Shogakukan Daijisen: https://kotobank.jp/word/焼く-9411 .
 ('food ingredient object material writing_surface text depiction body_part place','焼く'),
 # 48-AIW: physical cutting, including food, cloth and paper.
 ('food object writing_surface body_part','切る 刻む 切り刻む'),
 ('text sound','続ける'),
 # 48-ACT / GPT-6 Astra / 2026-09-14: switching display/content is an
 # ordinary operation. Counterexamples: read paper, switch audio, not
 # eat a display. Unknown roles remain unknown; these are not typo pairs.
 ('information text presentation sound device','切り替える 切り換える'),
 # GPT-6 Astra / 2026-09-14: content/entity transformation, including its result.
 # GPT-6 Astra / 2026-09-22: changing an attribute differs from replacing
 # an object/role. Positive meanings, not typo-to-answer pairs. Source:
 # https://www.bunka.go.jp/seisaku/bunkashingikai/kokugo/hokoku/pdf/ijidokun_140221.pdf (041)
 ('information text presentation attribute object device person place container','変える 変更 変換'),
 ('information text presentation object device person place container','替える 代える 交換 置換'),
 # 48-ACM / GPT-6: ordinary operations on a visual presentation surface.
 # This positive role evidence is used after a source meaning anomaly;
 # an unclassified word is not itself declared an anomalous source.
 ('presentation','表示 描画 更新 反映 切替 遷移 回転 拡大 縮小 分割 結合 合成 録画 投影 投写 同期 調整 補正 設定 制御 固定 確認 検査 保存 印刷 撮影 接続 操作'),
 # GPT-6 Astra / 2026-09-24: fixing an object's position or a dimension.
 ('attribute object','固定'),
 ('information text presentation','共有'),
 ('information text','反映'),
 ('expense money','精算 清算 支払 支払い 払う 支払う 払い戻す 返金'),
 ('information text','作成 補正 修正 編集 選択 削除 登録 検索 集計'),
 ('error','直す 正す 修正 訂正 補正 指摘 発見'),
 ('information text','記憶 分析 撹乱 攪乱 加工 変換 暗号化 圧縮 復号'),
 # 48-AIR / GPT-6 Astra / 2026-09-16: content processing and checking
 # an action/event are ordinary relations. This also covers native
 # object/action compounds through their existing process role.
 ('information text','処理'),
 ('process event','確認 検証'),
 ('information sound','録音 収録'),
 ('information text sound recording','録画 再生'),
 ('object food','収穫 採取 乾燥'),
 ('device','起動 稼働 駆動'),
 ('exposure issue object person place event process','避ける 回避'),
 ('place object','掃除'),
 ('object','洗濯'),
 # GPT-6 / 2026-09-29: recorded content can accompany another document
 # as an attachment. This classifies an ordinary action, not a typo pair.
 ('information text','入力 変更 送信 受信 添付'),
 # GPT-6 Astra / 2026-09-21: transfer recorded content to another document
 # or storage container. This positive content sense does not classify
 # every physical/figurative use of 移す or borrow 写す/映す meanings.
 # Daijisen 移す: https://kotobank.jp/word/移す-440805 (contents transfer).
 ('information text transmissible_illness','移す'),
 ('information text object food','保存'),
 # GPT-6 Astra / 2026-09-21: an existing depiction (picture, drawing,
 # photograph or recording) can be retained or acquired/transferred as a
 # work. This class-level positive role does not turn its depicted food,
 # people or scenery into the physical object of unrelated predicates.
 ('depiction','保存 保管 買う 売る'),
 # GPT-6 Astra / 2026-09-27: present people/things or information to
 # someone, inquire about information, and patrol a geographic area.
 # The actual object can select a specialized action over a common homophone.
 ('person object device place information text event process','紹介'),
 ('information text issue','照会'),
 ('place','哨戒 巡回 巡察'),
 ('information text','説明 解説 記述 表示 記録 報告 通知 伝達 提示 理解 把握 確認 検証 比較'),
 # Cognition concerns information or mental content, across original
 # objects and every native inflection; this is no source/answer mapping.
 ('information mental_content','知る 悟る 察知 認識'),
 ('mental_content','察す 察する 汲む 汲み取る 推し量る 理解 把握 尊重'),
 ('event process','説明 解説 記述 報告 通知 伝達 提示 案内'),
 ('information text event process','知らせる 伝える'),
 ('object device person event process','理解 把握 説明 解説'),
 ('text','印刷 出版 再版 製本 校正 校閲 添削 朗読 音読 書写 転記'),
 ('text information writing_system',' '.join(sorted(TRANSLATION_ACTIONS))),
 # GPT-6 Astra: verification includes identity, presence and condition of
 # people and concrete things. This is not a license for unrelated actions.
 # Verification can concern any attested referent, including nouns whose
 # narrower food/device/etc. meaning has not been classified. This does
 # not give those nouns an invented physical or edible sense.
 ('referent person object place device','確認 検証'),
 # Appointments can be confirmed without being physical things.
 ('schedule','確認 確かめる'),
 ('person','募集 採用 雇用 招待 招聘 招へい 救助'),
 ('person',' '.join(ROLE_ASSIGNMENT_ACTIONS)),
 # Opening access and releasing restraint have different arguments.
 # Kanjipedia: /kotoba/0000810400 (開放), /kotoba/0000817800 (解放).
 # No homophone/answer pair: the source conflict below uses only the
 # written predicate's physical-opening sense and an explicit person.
 ('person','解放 釈放 釈免'),
 ('object place','開放 開閉 開扉'),
 ('money object food text','寄付 寄附 寄贈 提供 贈与'),
 ('event','休会 閉会 開会 開催 棄権 欠席'),
 # 48-ANB / GPT-6 Astra / 2026-09-20: 中断/完了 have both
 # intransitive and transitive senses. The existing subject relation alone
 # was insufficient for 作業を中断 and its regular object/action nominal.
 # Daijisen: https://kotobank.jp/word/中断-97392 ; /word/完了-471748 .
 ('event process','中止 中断 完了 再開 継続 実施 開始 終了 続ける 始める 終える'),
 # Accusative place arguments describe a path, not a consumed object.
 ('place','歩く 走る 通る 散歩 通過 横断 登る 上る'),
 # 48-AIF / GPT-6 Astra / 2026-09-16: physical devices can be arranged,
 # transported and stored. This role does not license reading/eating them.
 ('object device text food','並べる 整列 整理 運搬 保管 収納'),
 # Daijisen まとめる senses: gather objects and organize content/plans.
 # https://kotobank.jp/word/纏める-635287 . Positive roles, not typo pairs.
 ('object text information schedule','まとめる 纏める'),
 # 48-AMG / GPT-6 Astra / 2026-09-20: ordinary possession, carrying,
 # responsibility/cost, properties and arranged events share the lemma.
 # The intransitive persistence sense does not create an accusative frame.
 # Meanings: Shogakukan Daijisen, https://kotobank.jp/word/持つ-645807 .
 # Actual reading/inflection remains attested by the native dictionary.
 # The controlled on-screen marker can also be brought to a position.
 # Microsoft accessibility guide uses ポインタを持っていく:
 # https://www.microsoft.com/ja-jp/enable/guides/dexterity
 ('object device text reference writing_surface material container food drink medicine money expense information attribute event process schedule place person body_part screen_marker','持つ'),
 # Displayed things, adorned places, language and marked events. Do not
 # restrict 飾る to photos or declare unmatched/metaphorical objects wrong.
 # Meanings: Shogakukan Daijisen, https://kotobank.jp/word/飾る-461831 .
 ('object text depiction place presentation body_part food event','飾る'),
 ('object text money','貸す'),
 # NINJAL IPAL kariru #01/#02 includes rooms, places and venues.
 ('object text money reservable_place','借りる'),
 # NINJAL Verb Handbook あげる: transfer of an owned item to a recipient.
 # https://www2.ninjal.ac.jp/verbhandbook/headwords/あげる.html
 ('object text money food','渡す 返す 戻す 預ける あげる 上げる'),
 ('object device text food','運ぶ 片付ける 仕舞う しまう 買う 売る'),
 # Bringing tangible things or recorded contents inside is transitive.
 ('object information text depiction','取り込む'),
 # 48-AHE: a dictionary/reference or writing medium can be purchased;
 # stacking applies to physical sheets and repeated events/experience.
 ('reference writing_surface','買う'),
 # 48-ALY / Astra: a reference work has readable contents as well as lookup use.
 ('reference','読む'),
 ('object text writing_surface process event information','重ねる'),
 # Ordinary placement has a moved object and an independent destination.
 ('object text food device container','置く'),
 # GPT-6 Astra / 2026-09-14: ordinary cleanup of rooms, surfaces and storage.
 ('place container','掃除 清掃 片付ける 整理'),
 # GPT-6 Astra: ordinary transfer of tangible items and conveyed content.
 # These positive roles are shared by source reading and candidate proof.
 ('object text food information','届ける 送る'),
 ('object text money place','返還 返却 返納'),
 # 48-AJN / GPT-6 Astra: distributing tangible items, money or content.
 ('object text information food money','配る 配布 分配'),
 # 48-ALC / GPT-6 Astra / 2026-09-20: present, serve or supply something.
 # NINJAL Verb Handbook 出す, especially provision/payment senses (19/20).
 # https://www2.ninjal.ac.jp/verbhandbook/headwords/出す.html
 ('information text object food drink money sound','出す'),
 # GPT-6 Astra / 2026-09-24: reference works/indexes can be opened or
 # closed as books or displayed reference material, without changing their
 # separate lookup role. Positive lexical senses, not typo/answer pairs.
 ('object text presentation reference','開く 閉じる'),
 # Attaching an adhesive/sheet to a surface, and stretching/spreading
 # flexible material, are distinct ordinary senses. Positive fit only.
 ('sheet_object adhesive','貼る'),
 ('flexible_material','張る'),
 # NINJAL verb handbook, 掛ける sense 7: expend duration, cost or effort.
 # A measured duration is not an arbitrary clock time or deadline.
 ('call burden measured_duration expense','掛ける'),
 # https://www2.ninjal.ac.jp/verbhandbook/headwords/締める・閉める・絞める.html
 # https://www2.ninjal.ac.jp/basicverbbank/single_headwords/あける-空ける・開ける.html
 ('physical_opening sealable_container business_premises','開ける 閉める'),
 # Movement also applies to visual items, such as tabs and windows.
 ('object device person presentation visual_region screen_marker','動かす 移動'),
 ('screen_marker','移す'),
 ('text information','読む 書く 書き直す'),
 # 48-AMB / Astra / 2026-09-20: repairing text, equipment or a defect.
 ('text information object device attribute','直す'),
 ('text object information food person','分ける 分割 区分'),
 ('text input_control','打つ'),
 # Positive ordinary depiction and imaging roles, not spelling-answer pairs.
 ('shape presentation attribute object person place body_part','描く 描写'),
 ('presentation object person place shape text','映す'),
 ('information text','消す 間違える'),
 ('light','消す 点ける つける 灯す'),
 ('place event','予約'),
 ('food','食べる 食う 調理 料理 試食'),
 # 48-AJZ / GPT-6 Astra / 2026-09-16: heating food/ingredients.
 # Positive ordinary cooking senses, not an anomaly for other objects.
 ('food ingredient','煮る 煮込む 茹でる 蒸す 蒸かす 炒める 揚げる'),
 # Kanjipedia 吞む (0005362500) and 吞/呑 (0005361400): swallowing.
 # These are positive ingestible-object senses, not spelling replacements.
 ('drink medicine','飲む 呑む 吞む'),
 # 2026-09-14 / GPT-6 Astra: ordinary insertion/pouring. Positive fit only.
 # NINJAL Basic Verb Bank, 入れる: the moved object (ヲ) can be a
 # person as well as a thing. This is lexical meaning, not a repair rule.
 # https://www2.ninjal.ac.jp/basicverbbank/single_headwords/いれる-入れる.html
 ('object person food drink information text','入れる'),
 # NINJAL Compound Verb Lexicon, 取り出す: physical removal, with
 # an accusative item and a source marked by から (e.g. bag and notebook).
 # https://www2.ninjal.ac.jp/vvlexicon/js/headwords.js (headword_id 1633)
 ('object text','取り出す 取出す'),
 # 2026-09-14 / GPT-6 Astra: creation of things/content/meals, and washing
 # physical items or ingredients. Food as a whole does not license washing:
 # a meal or confection is not classified as an ingredient by this evidence.
 ('object food text device information','作る'),
 ('object ingredient body_part','洗う'),
 ('medicine','服用'),
 ('clothing','着る 着用'),
)

PREDICATE_GROUPS+=tuple((group,' '.join(MEASUREMENT_ACTIONS[role]))
                       for group,(role,words) in MEASUREMENT_OBJECTS.items() if ACTION_CASES.get(role,'を')=='を')
# GPT-6 Astra: the person addressed/consulted is a dative argument,
# distinct from the content heard, spoken or conveyed. Positive proof only.
CASE_PREDICATE_GROUPS=(
 # GPT-6 / 2026-09-29: the location of an unchanged existential verb.
 # TUFS grammar 005/006: https://www.coelang.tufs.ac.jp/mt/ja/gmod/contents/explanation/006.html
 # A document/display may contain the described object. Positive senses
 # only; this supplies neither a corrected word nor an anomaly rule.
 ('に','place container text presentation','ある 有る 在る いる 居る'),
 # 48-AKA / GPT-6 Astra: an exchange/transaction has a place,
 # distinct from its object and the person lending or receiving it.
 ('で','place','借りる 貸す 買う 売る 返す 預ける 受け取る'),
 ('で','communication_medium','送る 届ける 伝える 知らせる 連絡 報告 通知 送信 受信 相談 質問 確認 説明'),
 ('に','person place container origin','返還 返却 返納'),
 ('に','place origin','戻る 帰る 戻す 返す'),
 ('へ','place origin','戻る 帰る 戻す 返す'),
 ('に','quantity','分ける 分割 区分'),
 # Resultative に differs from a storage destination or addressed person.
 ('に','information text presentation attribute object device person place container','変える 替える 代える 変更 交換 置換 変換'),
 ('に','container','入れる 入る 仕舞う しまう 戻す 収める 納める 保存 保管 収納'),
 # 48-APW: へ gives the direction; a validated 戻す candidate supplies the return action.
 # https://www.kyozai.jpf.go.jp/kyozai/material/BTS00055/ja/render.do
 ('へ','container','戻す'),
 ('に','screen_location','動かす 移動 移す'),
 ('へ','screen_location','動かす 移動 移す'),
 ('に','text container person','移す'),
 ('へ','text container person','移す'),
 # GPT-6 Astra / 2026-09-21: arranging items has a spatial destination,
 # shared with placing them; the unchanged accusative still owns the item.
 ('に','container place writing_surface support_surface','置く 並べる 重ねる'),
 ('に','place process event','行く 来る 向かう 出かける 出掛ける'),
 ('へ','place process event','行く 来る 向かう 出かける 出掛ける'),
 # A drawn shape is the means of enclosing an item on a page.
 ('で','shape','囲う 囲む'),
 # The device is the input instrument, distinct from the text being entered.
 ('で','input_control','打つ 入力'),
 ('で','reference','調べる 探す 引く 確かめる 確認 比べる 較べる 学ぶ 覚える 選ぶ 見つける 思い出す'),
 # A meeting or event can supply the setting for communication and
 # distribution, independently of their explicit accusative object.
 ('で','place event','配る 配布 分配 説明 発表 報告 共有 確認 議論 相談 話す'),
 ('と','person','話す 会う 相談 確認 検証 調整 交渉 協議 会話 食事 作業 運動'),
 # 48-AJE / GPT-6 Astra, 2026-09-16: a person can accompany ordinary
 # intentional daily activities. This shares the actual comitative case;
 # it does not make people the accusative food/object of those verbs.
 ('と','person','食べる 食う 飲む 作る 調理 料理 試食 買う 選ぶ 運ぶ 歩く 走る 散歩 遊ぶ 旅行 買い物 読む 書く 練習 勉強 学習'),
 ('から','container','取り出す 取出す'),
 ('から','person','教わる 聞く 学ぶ 受け取る 借りる 受信 受領 伝授'),
 ('から','continuation','始める 再開'),
 ('で','place','遊ぶ 働く 学ぶ 暮らす 泳ぐ 休む 待つ 走る 歩く 散歩 運動 食事 会議 作業 調理 料理 掃除 保存 確認 勉強 練習'),
 ('に','writing_surface','書く 描く 記す 写す 記入 入力 記載'),
 ('に','shape','描く 描写'),
 ('に','place','見える'),
 ('に','place','登る 上る'),
 ('に','person','見せる'),
 # The supplied item and recipient are independent arguments of the same verb.
 ('に','person','出す あげる 上げる'),
 ('へ','person','出す'),
 # A visual surface is also a target of projection/reflection, not just navigation.
 ('に','presentation','映る 映す 写る 投影 投写'),
 # GPT-6 Astra / 2026-09-21: contact/transmission can address a person
 # with に as with へ. This is recipient evidence, not content or channel.
 # A person can receive a loan; this is not the object lent or the
 # lending location. Exact native lemma/tail evidence remains required.
 ('に','person','読む 聞く 尋ねる 問う 話す 伝える 教える 渡す 返す 届ける 送る 会う 頼む 相談 質問 報告 説明 通知 貸す 連絡 送信 転送 紹介'),
 ('へ','person','伝える 渡す 返す 届ける 送る 連絡 報告 通知 送信 転送'),
)
CASE_PREDICATE_GROUPS+=tuple((ACTION_CASES[role],group,' '.join(MEASUREMENT_ACTIONS[role]))
                             for group,(role,words) in MEASUREMENT_OBJECTS.items() if role in ACTION_CASES)
CASE_VERB_ROLES={}
for case,roles,words in CASE_PREDICATE_GROUPS:
 for word in words.split():CASE_VERB_ROLES.setdefault(case,{}).setdefault(word,set()).update(roles.split())

NOUN_ROLES={}
for role,words in NOUN_GROUPS.items():
 for w in words:NOUN_ROLES.setdefault(w,set()).add(role)
VERB_ROLES={}
for roles,words in PREDICATE_GROUPS:
 for w in words.split():VERB_ROLES.setdefault(w,set()).update(roles.split())




# 48-ALE / GPT-6 Astra / 2026-09-20: the existing counter referents
# also constrain the noun they count. Books/devices are physical objects,
# but that broad property alone does not make every object a book/device.
_COUNTER_CORE_ROLES={
    '冊':frozenset(('text','reference')),
    '台':frozenset(('device',)),
    '人':frozenset(('person',)),
}


@lru_cache(maxsize=1024)
def counted_object_roles(quantity):
    """Positive type evidence for an exact native quantity, or None.

    Untyped counts and ordinal referents do not impose a guessed noun class.
    This does not declare an unclassified original noun anomalous.
    """
    from reading_segments import native_counted_nominal_evidence
    evidence=native_counted_nominal_evidence(quantity)
    if not evidence or any(ordinal or unit not in _COUNTER_CORE_ROLES for unit,ordinal in evidence):
        return None
    return frozenset().union(*(_COUNTER_CORE_ROLES[unit] for unit,ordinal in evidence))


# The existing two context meanings of quantity + の + a counted noun.
# Kept separate from generic counted-object roles and ordinal noun meaning.
_COUNTED_GENITIVE_ROLES={'枚':'sheet_object','台':'device'}


def counted_genitive_roles(quantity):
    """Share the existing modifier's role; not a free quantity's meaning."""
    from reading_segments import native_counted_nominal_evidence
    evidence=native_counted_nominal_evidence(quantity)
    units={unit for unit,ordinal in evidence or () if not ordinal}
    if len(units)!=1 or not units<=_COUNTED_GENITIVE_ROLES.keys():return None
    return frozenset((_COUNTED_GENITIVE_ROLES[next(iter(units))],))


def ongoing_nominal_support(surface):
    """Positive activity sense; absence never declares a source anomalous."""
    return 'process' in NOUN_ROLES.get(surface,())


def _native_storage_compound_role(surface):
    """An attested content noun + storage head with matching native readings."""
    heads={'棚':'た', '箱':'は'}
    from morphology import dictionary_inflections
    for head,onset in heads.items():
        if (not surface.endswith(head) or len(surface)<=len(head)
                or head not in NOUN_GROUPS['container']):continue
        content=surface[:-len(head)]
        if not nominal_roles(content) & {'object','text','food','drink','medicine','material'}:
            continue
        def readings(face):
            return {rd for pos,form,base,rd in dictionary_inflections(face) or ()
                    if pos.startswith('名詞,一般,') and base==face and rd}
        left=readings(content);right=readings(head);whole=readings(surface)
        if any(rd.startswith(onset) and wr==lr+tail
               for wr in whole for lr in left for rd in right
               for tail in (rd,{'た':'だ','は':'ば'}[onset]+rd[1:])):
            return True
    return False


@lru_cache(maxsize=4096)
def nominal_roles(surface):
    """Known senses plus a native adjective's productive attribute noun."""
    roles=frozenset(NOUN_ROLES.get(surface,()))
    from general_words import attested_noun
    attested=attested_noun(surface)
    if attested:
        categories=set(attested[3])
        if 'product' in categories:roles=roles | {'object'}
        if 'beverage' in categories:roles=roles | {'drink'}
    if 'role_candidate' in roles:roles=roles | {'person'}
    # Adhesives and flexible materials are also handled physical objects.
    # Reuse the classified sense instead of repeating each noun in a roster.
    if roles & {'adhesive','flexible_material'}:roles=roles | {'object'}
    # 48-AHP / GPT-6 Astra: an exact native counter names its counted
    # referent. 本 as a counter is not the independent noun 'book'.
    # Unclassified units give only quantity, not guessed object semantics.
    from reading_segments import native_counted_nominal_evidence
    counted=native_counted_nominal_evidence(surface)
    if counted:
        if any(not ordinal for unit,ordinal in counted):roles=roles | {'quantity'}
        for unit,ordinal in counted:
            roles=roles | _COUNTER_CORE_ROLES.get(unit,frozenset())
            if unit in ('冊','台'):roles=roles | {'object'}
            if unit=='本' and not ordinal:roles=roles | {'linear_quantity'}
    # 48-AGV / GPT-6 Astra: an independently classified native action
    # can also name a process. An attested two-noun object/action compound
    # inherits that role only when its original argument fits the action.
    from morphology import dictionary_inflections,tokenize
    if any(pos.startswith('名詞,固有名詞,地域,国')
           for pos,form,base,rd in dictionary_inflections(surface) or ()):
        roles=roles | {'country'}
    if surface in VERB_ROLES and any(classified_nominal_action(surface,rd)
            for pos,form,base,rd in dictionary_inflections(surface) or ()):
        roles=roles | {'process'}
    if not roles and len(surface)>2:
        parts=tokenize(surface)
        from reading_segments import native_deverbal_nominal_faces
        # The same written continuative may have an independently attested
        # common-noun use with exactly this reading. Share that lexical
        # proof; the whole object's positive relation to the action below
        # is still required before the compound can name a process.
        if (len(parts)>=2 and all(t.has_reading and (
                t.pos=='名詞' and not any(x in t.pos_sub for x in ('固有名詞','非自立'))
                or t is parts[0] and t.pos=='動詞' and t.pos_sub=='自立'
                and t.infl_form=='連用形'
                and t.surface in native_deverbal_nominal_faces(t.reading)) for t in parts)
                and parts[0].start==0 and parts[-1].end==len(surface)
                and all(a.end==b.start for a,b in zip(parts,parts[1:]))
                and classified_nominal_action(parts[-1].surface,parts[-1].reading)
                and support(surface[:parts[-1].start],parts[-1].surface)):
            # 48-AIR: the actual object can itself be an already classified
            # compound (描画面). Keep its whole meaning, not its last token.
            roles=frozenset(('process',))
    if not roles and _native_storage_compound_role(surface):
        roles=frozenset(('container',))
    if not roles and surface.endswith('まで'):
        from reading_segments import native_deictic_range
        if native_deictic_range(surface):return frozenset(('extent',))
    if not roles and surface.endswith(('たち','達')):
        from reading_segments import native_plural_nominal_heads
        if native_plural_nominal_heads(surface):return frozenset(('person',))
    # A single role still requires that role for every coordinated member.
    if not roles and 'と' in surface:
        groups=coordinated_nominal_role_groups(surface)
        if groups:return frozenset.intersection(*groups)
    if roles or not surface.endswith('さ'):
        return roles
    from morphology import tokenize
    from reading_segments import nominalized_adjective_context
    parts=tokenize(surface)
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    if nominalized_adjective_context(surface,0,len(surface),lambda _:legacy):
        return frozenset(('attribute',))
    return roles


def _argument_prefix(context,start,tokenize):
    """Native adverbial modifiers do not sever an argument from its verb.

    Keep the original contiguous coordinates. Do not cross another verb,
    a connective, an unknown reading or a gap. Both case readers use this
    one syntactic boundary, independently of any proposed correction.
    """
    from morphology import dictionary_inflections
    parts=[t for t in tokenize(context) if t[4]<=start];edge=start
    while parts and parts[-1][4]==edge:
        t=parts[-1]
        if not t[5] or len(t)<7:break
        forms=dictionary_inflections(t[0]) or () if t[1].startswith(('副詞','形容詞','助動詞','助詞:副詞化')) else ()
        adverb=t[1].startswith('副詞') and any(p.startswith('副詞,') and rd==t[2] for p,f,b,rd in forms)
        adjective=t[1].startswith('形容詞') and t[6]=='連用テ接続' and any(p.startswith('形容詞,') and f==t[6] and rd==t[2] for p,f,b,rd in forms)
        if adverb or adjective:
            edge=t[3];parts.pop();continue
        if (t[0]=='に' and len(parts)>1 and (
                t[1]=='助詞:副詞化' and any(p.startswith('助詞,副詞化,') and rd==t[2] for p,f,b,rd in forms)
                or t[1]=='助動詞' and any(p.startswith('助動詞,') and b=='だ' and f=='連用形' and rd==t[2] for p,f,b,rd in forms))):
            head=parts[-2]
            if (head[5] and head[4]==t[3] and head[1].startswith('名詞:形容動詞語幹')
                    and any(p.startswith('名詞,形容動詞語幹,') and rd==head[2]
                            for p,f,b,rd in dictionary_inflections(head[0]) or ())):
                edge=head[3];del parts[-2:];continue
        break
    return parts,edge



@lru_cache(maxsize=2048)
def following_shared_object(text,start,end):
    """A following conjunct supplies a possible omitted object for spelling.

    Both actions still need their own positive object meaning. This only
    ranks a same-reading verb, never declares the source erroneous.
    """
    from reading_segments import native_predicate_link_boundaries,native_object_predicate_contexts,native_object_predicate_proof
    if text[end:end+1] not in ('て','で'):return ''
    edge=end+1
    if edge not in native_predicate_link_boundaries(text,start):return ''
    following=text[edge:]
    frames=[(cut,faces) for begin,cut,faces in native_object_predicate_contexts(following,True)
        if begin==0 and len(faces)==1 and native_object_predicate_proof(following,cut,faces)]
    return frames[0][1][0] if len(frames)==1 else ''


def object_before(context, start, tokenize):
    """Keep a native head; reconstruct an exact kana chain only if missing."""
    noun=_token_object_before(context,start,tokenize)
    if noun:return noun
    from reading_segments import native_literal_argument_chain
    _,edge=_argument_prefix(context,start,tokenize)
    chain=native_literal_argument_chain(context[:edge])
    if chain and sum(case=='を' for noun,case,a,b in chain)==1:
        obj=next(i for i,row in enumerate(chain) if row[1]=='を')
        if all(row[1] in ('に','で','へ') for row in chain[obj+1:]):return chain[obj][0]
    return ''



def _classified_argument_head(context,parts,noun_index):
    """An independently classified whole noun keeps its contiguous native parts."""
    j=noun_index
    while (j>0 and parts[j-1][4]==parts[j][3] and parts[j-1][5]
            and parts[j-1][1].startswith('名詞')):
        j-=1
    run=parts[j:noun_index+1]
    if (len(run)<2 or not all(t[5] and t[1].startswith('名詞') for t in run)
            or any(any(kind in t[1] for kind in ('固有名詞','非自立')) for t in run)):
        return None
    face=context[run[0][3]:run[-1][4]]
    return (face,j) if all(coordinated_nominal_role_groups(face) or (nominal_roles(face),)) else None


def _native_argument_phrase_start(parts,noun_index):
    """Keep actual NのN modifiers within the same following case phrase."""
    from morphology import dictionary_inflections
    j=noun_index
    def noun_start(index):
        first=index
        while (first>0 and index-first<3 and parts[first-1][4]==parts[first][3]
                and parts[first-1][5] and parts[first-1][1].startswith('名詞')):
            first-=1
        return first
    j=noun_start(j)
    for _ in range(3):
        if j<2:break
        marker,modifier=parts[j-1],parts[j-2]
        if not (marker[5] and marker[0]=='の' and marker[1]=='助詞:連体化'
                and marker[4]==parts[j][3] and modifier[4]==marker[3]
                and modifier[5] and modifier[1].startswith('名詞')
                and any(p.startswith('助詞,連体化,') and rd==marker[2]
                        for p,f,b,rd in dictionary_inflections(marker[0]) or ())
                and any(p.startswith('名詞,') and rd==modifier[2]
                        for p,f,b,rd in dictionary_inflections(modifier[0]) or ())):break
        j=noun_start(j-2)
    return j



def _case_noun_index(parts,index):
    """Native focus particles keep the same noun and explicit case."""
    from morphology import dictionary_inflections
    edge=parts[index][3];index-=1
    while index>=0 and parts[index][1].startswith('助詞:副助詞'):
        token=parts[index]
        if not (token[4]==edge and token[5] and any(
                pos.startswith('助詞,副助詞,') and rd==token[2]
                for pos,form,base,rd in dictionary_inflections(token[0]) or ())):return -1
        edge=token[3];index-=1
    return index if index>=0 and parts[index][4]==edge else -1


def _token_object_before(context, start, tokenize):
    """Use an explicit を head across contiguous simple dative/location arguments."""
    parts,edge=_argument_prefix(context,start,tokenize)
    if not parts or parts[-1][4]!=edge:return ''
    i=len(parts)-1
    for _ in range(3):
        if i<1:return ''
        particle=parts[i];noun_index=_case_noun_index(parts,i)
        if noun_index<0:return ''
        noun=parts[noun_index]
        if (not particle[1].startswith('助詞:格助詞') or particle[4]!=edge
                or not noun[5] or not noun[1].startswith('名詞')):
            return ''
        if particle[0]=='を':
            if '接尾' in noun[1] and noun_index>=1:
                from reading_segments import nominalized_adjective_context
                head=parts[noun_index-1]
                if nominalized_adjective_context(context,head[3],noun[4],lambda _:parts):
                    return context[head[3]:noun[4]]
            whole=_classified_argument_head(context,parts,noun_index)
            if whole:return whole[0]
            return '' if ('固有名詞' in noun[1] and not nominal_roles(noun[0])) or '接尾' in noun[1] else noun[0]
        if particle[0] not in ('に','で','へ'):return ''
        # 別の述語や助詞を越えない。受け手・場所を表す既知の名詞句だけ。
        j=_native_argument_phrase_start(parts,noun_index)
        edge=parts[j][3];i=j-1
    return ''


def case_argument_before(context,start,tokenize,through_object=False):
    """Prefer the native argument head over a longer reconstructed phrase."""
    argument=_token_case_argument_before(context,start,tokenize,through_object)
    if argument:return argument
    from reading_segments import native_literal_argument_chain
    _,edge=_argument_prefix(context,start,tokenize)
    chain=native_literal_argument_chain(context[:edge])
    if chain:
        if through_object and chain[-1][1]=='を':chain=chain[:-1]
        if chain and chain[-1][1] in CASE_VERB_ROLES:return chain[-1][:2]
    return None


def _argument_prefix_before_object(context,parts,edge):
    """Keep the existing whole native object seam for every earlier argument."""
    if len(parts)>=2:
        particle=parts[-1];noun_index=_case_noun_index(parts,len(parts)-1)
        if noun_index<0:return parts,edge
        noun=parts[noun_index]
        if (particle[4]==edge and particle[0]=='を' and particle[5]
                and particle[1].startswith('助詞:格助詞')
                and noun[5] and noun[1].startswith('名詞')
                and not any(kind in noun[1] for kind in ('固有名詞','接尾','非自立'))):
            whole=_classified_argument_head(context,parts,noun_index)
            begin=whole[1] if whole else noun_index
            edge=parts[begin][3];parts=parts[:begin]
    return parts,edge


def _token_case_argument_before(context,start,tokenize,through_object=False):
    """One explicit native common noun plus its actual non-accusative case."""
    parts,edge=_argument_prefix(context,start,tokenize)
    if through_object:
        parts,edge=_argument_prefix_before_object(context,parts,edge)
    if len(parts)<2:return None
    particle=parts[-1];noun_index=_case_noun_index(parts,len(parts)-1)
    if noun_index<0:return None
    noun=parts[noun_index]
    if (particle[4]!=edge or particle[0] not in CASE_VERB_ROLES
            or not particle[1].startswith('助詞:格助詞')
            or not noun[5] or not noun[1].startswith('名詞')
            or '固有名詞' in noun[1] or '接尾' in noun[1]):return None
    whole=_classified_argument_head(context,parts,noun_index)
    if whole:return whole[0],particle[0]
    if noun_index>0 and parts[noun_index-1][4]==noun[3] and parts[noun_index-1][1].startswith(('名詞','接頭詞')):
        return None
    return noun[0],particle[0]


@lru_cache(maxsize=4096)
def classified_nominal_action(surface, reading):
    """A native ordinary noun with an independently classified action use."""
    if surface not in VERB_ROLES:
        return False
    from morphology import dictionary_inflections,native_sahen_compound_reading
    return (native_sahen_compound_reading(surface)==reading and bool(reading)
            or any(pos.startswith(('名詞,一般,','名詞,サ変接続,'))
               and base==surface and rd==reading
               for pos,form,base,rd in dictionary_inflections(surface) or ()))


@lru_cache(maxsize=4096)
def predicate_roles(surface, following='', before='', case=None):
    roster=VERB_ROLES if case is None else CASE_VERB_ROLES.get(case,{})
    if surface in roster:return frozenset(roster[surface])
    from morphology import tokenize,dictionary_inflections
    parts=[t for t in tokenize(before+surface+following) if t.start>=len(before)]
    # Keep the actual left context too: 並べて can otherwise become the
    # homographic adverb なべて when its explicit object is omitted.
    # A token crossing the proposed source boundary supplies no evidence.
    if (not parts or parts[0].start!=len(before)
            or parts[0].pos!='動詞' or not parts[0].has_reading):return frozenset()
    t=parts[0]
    # A lexical lookup need not revalidate an unambiguous action's whole
    # surrounding sentence. The shared candidate validator owns grammar.
    # Bind a tail here only to distinguish differently classified native
    # homophones, where borrowing another lemma's meaning is possible.
    meanings={frozenset(roster.get(base,()))
              for base in native_verb_lexemes(t.surface,t.infl_form,t.reading)}
    if not following or len(meanings)<=1:
        return native_verb_roles(t.surface,t.infl_form,t.reading,case=case)
    # Candidate context supplies the actual suffix. The semantic role and
    # that suffix must belong to the same native verb, including kana forms.
    # A bare lexical lookup keeps its original scope when no tail is given.
    from contextual_repair import _source_clause_bounds
    full=before+surface+following
    lo,hi=_source_clause_bounds(full,t.start,t.end)
    tail=full[t.end:hi] if following else None
    roles=native_verb_roles(t.surface,t.infl_form,t.reading,case=case,
                             tail=tail,before=full[lo:t.start])
    if roles or tail is None:return roles
    # A following clause is not this verb's auxiliary tail. Its actual
    # te/de link can delimit this action for lexical meaning; the caller
    # still proves the object's ownership and the whole candidate grammar.
    for link in parts[1:]:
        if link.end>hi:break
        if (link.pos=='助詞' and link.pos_sub=='接続助詞'
                and link.surface in ('て','で') and link.has_reading):
            roles=native_verb_roles(t.surface,t.infl_form,t.reading,case=case,
                tail=full[t.end:link.end],before=full[lo:t.start])
            if roles:return roles
    return frozenset()


@lru_cache(maxsize=1)
def _native_verb_reading_lexemes():
    """Canonical classified verbs retain identity as well as their reading."""
    from morphology import dictionary_inflections
    result={}
    words=set(VERB_ROLES)|set(SUBJECT_VERB_ROLES)
    for roster in CASE_VERB_ROLES.values():words.update(roster)
    for word in sorted(words):
        for pos,form,base,reading in dictionary_inflections(word) or ():
            if pos.startswith('動詞,自立,') and form=='基本形' and base==word:
                result.setdefault(reading,set()).add(word)
    return {rd:tuple(sorted(words)) for rd,words in result.items()}


@lru_cache(maxsize=8192)
def _native_lexeme_forms(word,form,reading):
    """Only native entries can attest a written inflection of this lemma."""
    from morphology import dictionary_inflections
    candidates={word[:i]+reading[j:] for i in range(len(word)+1)
                for j in range(len(reading)+1)}
    return tuple(sorted(candidate for candidate in candidates
        if any(pos.startswith('動詞,自立,') and f==form and base==word and rd==reading
               for pos,f,base,rd in dictionary_inflections(candidate) or ())))


# 48-AFZ / Astra, 2026-09-15: ordinary result states of explicit objects.
# Positive evidence only; absence does not declare metaphor or a new noun wrong.
# The dictionary supplies the adjective's exact reading and continuative form.
RESULTATIVE_ADJECTIVE_GROUPS=(
    ('object shape presentation extent attribute sound','大きい 小さい'),
    ('object shape presentation extent place attribute','広い 狭い'),
    ('text object extent time attribute','長い 短い'),
    ('light presentation place','明るい 暗い'),
    ('food drink object place body_part','暖かい 温かい 冷たい'),
    ('object shape presentation attribute','赤い 青い 黒い 白い'),
)


@lru_cache(maxsize=1)
def _short_role_noun_readings():
    """One-kana common role nouns still need a matching explicit case frame."""
    from morphology import dictionary_inflections
    out={}
    for noun in NOUN_ROLES:
        for pos,form,base,reading in dictionary_inflections(noun) or ():
            if (len(reading)==1 and pos.startswith('名詞,') and base==noun
                    and not any(kind in pos for kind in ('固有名詞','接尾','非自立'))):
                out.setdefault(reading,set()).add(noun)
    return {reading:tuple(sorted(words)) for reading,words in out.items()}


def short_role_noun_faces(reading):
    return _short_role_noun_readings().get(reading,()) if len(reading)==1 else ()


@lru_cache(maxsize=1)
def _resultative_adjective_readings():
    from morphology import dictionary_inflections
    out={}
    for roles,words in RESULTATIVE_ADJECTIVE_GROUPS:
        for word in words.split():
            for pos,form,base,reading in dictionary_inflections(word) or ():
                if pos.startswith('形容詞,') and form=='基本形' and base==word:
                    out.setdefault(reading,set()).update(roles.split())
    return {reading:frozenset(roles) for reading,roles in out.items()}


@lru_cache(maxsize=4096)
def resultative_adjective_roles(reading):
    from morphology import dictionary_inflections
    roles=set();known=_resultative_adjective_readings()
    for pos,form,base,rd in dictionary_inflections(reading) or ():
        if not pos.startswith('形容詞,') or form!='連用テ接続' or rd!=reading:continue
        for p,f,b,lemma_reading in dictionary_inflections(base) or ():
            if p.startswith('形容詞,') and f=='基本形' and b==base:
                roles.update(known.get(lemma_reading,()))
    return frozenset(roles)


# GPT-6 Astra / 2026-09-20: receiving auxiliaries license a person as
# agent; giving auxiliaries license a person as recipient in ni, not kara.
# Positive case evidence only. Japan Foundation, "授受表現" (2014-09/12):
# https://www.jpf.go.jp/j/project/japanese/teach/tsushin/grammar/201409.html
_BENEFACTIVE_CASES={
    'に':frozenset(('もらう','貰う','いただく','頂く','あげる','上げる','さしあげる','差し上げる','やる','くれる','呉れる')),
    'から':frozenset(('もらう','貰う','いただく','頂く')),
}


@lru_cache(maxsize=4096)
def native_te_auxiliary_forms(surface,form,reading):
    """Exact auxiliary forms, including lexical-POS benefactive verbs.

    IPAdic tags さしあげる as independent even after te/de. The same
    documented benefactive inventory supplies grammar and argument roles.
    """
    from morphology import dictionary_inflections,TE_AUXILIARY_BASES
    benefactive=frozenset().union(*_BENEFACTIVE_CASES.values())
    return tuple(row for row in dictionary_inflections(surface) or ()
        if row[1]==form and row[3]==reading and row[2] in TE_AUXILIARY_BASES and (
            row[0].startswith('動詞,非自立,')
            or row[0].startswith('動詞,自立,') and row[2] in benefactive))


@lru_cache(maxsize=4096)
def native_benefactive_case_roles(surface,form,reading,tail,case,before=''):
    if case not in _BENEFACTIVE_CASES or not tail:return frozenset()
    from morphology import tokenize,dictionary_inflections
    parts=[t for t in tokenize(before+surface+tail) if t.start>=len(before)]
    if (len(parts)<3 or parts[0].surface!=surface or parts[0].start!=len(before)
            or parts[0].infl_form!=form or parts[0].reading!=reading
            or not all(t.has_reading for t in parts)
            or ''.join(t.surface for t in parts)!=surface+tail):return frozenset()
    head,link,aux=parts[:3]
    if (head.pos!='動詞' or not head.pos_sub.startswith('自立')
            or link.pos!='助詞' or link.pos_sub!='接続助詞'
            or link.surface not in ('て','で') or head.end!=link.start
            or aux.start!=link.end or aux.pos!='動詞'
            or aux.base_form not in _BENEFACTIVE_CASES[case]):return frozenset()
    if not any(b==aux.base_form for p,f,b,rd in native_te_auxiliary_forms(
            aux.surface,aux.infl_form,aux.reading)):return frozenset()
    from contextual_repair import _modern_te_allowed,_allows_grammatical_tail,_productive_predicate,_completed_predicate_token
    last=parts[-1]
    if (not _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,last.reading,
                                       last.start,last.end,last.has_reading,last.infl_form))
            or _modern_te_allowed(head.surface,head.reading,link.surface) is not True
            or not _allows_grammatical_tail(dictionary_inflections(surface) or (),tail,reading,surface)
            or not _productive_predicate(surface+tail,surface,before=before)):return frozenset()
    return frozenset(('person',))


@lru_cache(maxsize=4096)
def native_verb_lexemes(surface,form,reading):
    """Exact inflection/reading senses; literal kana retains attested spellings."""
    from morphology import dictionary_inflections,native_suru_form
    lexemes=set()
    kana=surface==reading and all('ぁ'<=c<='ゖ' for c in surface)
    for pos,inflection,base,rd in dictionary_inflections(surface) or ():
        if not pos.startswith('動詞,自立,') or inflection!=form or rd!=reading:continue
        # The functional suru meaning belongs to the native sahen paradigm.
        # Its identically spelled godan homograph cannot inherit process roles;
        # actual rubbing/printing lexemes remain available below.
        functional=(base!='する' or native_suru_form(surface,form,reading,False))
        if functional:lexemes.add(base)
        if kana:
            for p,f,b,lemma_reading in dictionary_inflections(base) or ():
                if p.startswith('動詞,自立,') and f=='基本形' and b==base:
                    lexemes.update(word for word in _native_verb_reading_lexemes().get(lemma_reading,())
                                   if word!='する' or functional)
    return frozenset(lexemes)


# The written homographs have different lexical readings. Object roles for
# opening a book belong to hiraku; physically opening a door belongs to akeru.
# Native potential hirakeru inherits hiraku only through its attested origin.
_OBJECT_ROLE_READINGS={'開く':('ひらく',),'開ける':('あける',)}


@lru_cache(maxsize=8192)
def native_verb_roles(surface, form, reading, subject=False, case=None, tail=None, before="", allow_open_tail=False):
    """Bind meaning and a supplied grammatical tail to the same native lemma.

    Without a tail, source role lookup retains its former lexical scope.
    With a tail, a homophone cannot lend its meaning to another verb's
    inflection (書く versus 嗅ぐ). The output never chooses these spellings.
    """
    from morphology import dictionary_inflections
    roster=CASE_VERB_ROLES.get(case,{}) if case is not None else (SUBJECT_VERB_ROLES if subject else VERB_ROLES)
    kana=surface==reading and all('ぁ'<=c<='ゖ' for c in surface)
    roles=set();lexemes=set(native_verb_lexemes(surface,form,reading))
    for lexeme in lexemes:
        known=roster.get(lexeme,())
        if not known:continue
        lemma_readings=_OBJECT_ROLE_READINGS.get(lexeme) if not subject else None
        if lemma_readings and not any(_native_lexeme_forms(rd,form,reading) for rd in lemma_readings):continue
        if tail is not None:
            from contextual_repair import _allows_grammatical_tail,_productive_predicate
            forms=_native_lexeme_forms(lexeme,form,reading) if kana else (surface,)
            from reading_segments import _native_open_predicate
            if not any((_allows_grammatical_tail(dictionary_inflections(face) or (),tail,reading,face)
                        or allow_open_tail and _native_open_predicate(face+tail,face,before))
                       and _productive_predicate(face+tail,face,before=before) for face in forms):continue
        roles.update(known)
    if lexemes and not roles:
        # A lexical verb's own explicit meaning takes precedence over a
        # formally possible potential derivation. Native ichidan/godan
        # pairs also include lexical transitive/intransitive counterparts;
        # their spelling relation alone cannot add another argument sense.
        # Potential forms retain the same action's argument meaning. Validate
        # the actual potential tail before consulting its native godan origin;
        # a homophone's incompatible conjugation cannot lend its role.
        from morphology import native_potential_origins
        potential=native_potential_origins(surface,form,reading)
        if potential and tail is not None:
            from contextual_repair import _allows_grammatical_tail,_productive_predicate
            from reading_segments import _native_open_predicate
            if not ((_allows_grammatical_tail(dictionary_inflections(surface) or (),tail,reading,surface)
                     or allow_open_tail and _native_open_predicate(surface+tail,surface,before))
                    and _productive_predicate(surface+tail,surface,before=before)):
                potential=()
        for origin,origin_reading in potential:
            # Potential derivation above proves a godan origin. The bare
            # homograph suru must not regain the functional sahen sense
            # through a second lookup which has discarded that paradigm.
            if origin=='する':continue
            roles.update(native_verb_roles(origin,'基本形',origin_reading,subject=subject,case=case))
    if not roles and lexemes:
        # A native compound V+phase keeps its first verb's argument roles.
        # The same dictionary continuative and phase attachment are required
        # whether IPAdic stores the compound as one token or two.
        from contextual_repair import _PHASE_VERB_BASES,_allows_grammatical_tail,_productive_predicate
        for cut in range(1,len(surface)):
            prefix=surface[:cut];suffix=surface[cut:]
            phase=tuple(row for row in dictionary_inflections(suffix) or ()
                        if row[0].startswith('動詞,') and row[1]==form
                        and row[2] in _PHASE_VERB_BASES)
            if not phase:continue
            forms=tuple(row for row in dictionary_inflections(prefix) or ()
                        if row[0].startswith('動詞,自立,') and row[1]=='連用形')
            for pos,inflection,base,rd in forms:
                if not any(rd+item[3]==reading for item in phase):continue
                if tail is not None and not (
                        _allows_grammatical_tail(dictionary_inflections(surface) or (),tail,reading,surface)
                        and _productive_predicate(surface+tail,surface,before=before)):continue
                roles.update(native_verb_roles(prefix,inflection,rd,subject=subject,case=case))
    if lexemes and tail is not None:
        roles.update(native_benefactive_case_roles(surface,form,reading,tail,case,before))
    return frozenset(roles)


@lru_cache(maxsize=4096)
def coordinated_nominal_role_groups(surface):
    """48-AKQ / GPT-6 Astra, 2026-09-19: preserve roles member by member.

    Different categories may each fit one action (cloth and paper: cutting).
    Never let the union license a member with no positive relation to it.
    Lexical readings and the unchanged coordination use the shared proof.
    """
    if 'と' not in surface:return ()
    from reading_segments import native_coordinated_nominal_parts, _native_nominal_reading_faces
    groups=[]
    for member in native_coordinated_nominal_parts(surface):
        faces=(_native_nominal_reading_faces(member)
               if all('ぁ'<=c<='ゖ' or c=='ー' for c in member) else (member,))
        groups.append(frozenset().union(*(nominal_roles(face) for face in faces)))
    return tuple(groups)


def nominal_role_matches(surface, accepted):
    """Positive roles only if every member fits the same action and case."""
    accepted=frozenset(accepted)
    if not accepted:return frozenset()
    if 'referent' in accepted:
        from morphology import dictionary_inflections
        from kango_tier import usage_tier_for_reading
        # Positive everyday-use evidence is required for this broad sense.
        # Lexical existence alone cannot turn an unjudged plant/name into
        # an automatic answer to an unknown source word.
        # A real independent noun supplies the referent. Unknown strings,
        # auxiliaries and mere pieces of a word provide no such evidence.
        if any(pos.startswith('名詞,') and base==surface and usage_tier_for_reading(surface,rd) in (1,2)
                and not any(kind in pos.split(',') for kind in ('非自立','接尾'))
                for pos,form,base,rd in dictionary_inflections(surface) or ()):
            return frozenset(('referent',))
    groups=coordinated_nominal_role_groups(surface) or (nominal_roles(surface),)
    matches=tuple(group & accepted for group in groups)
    return frozenset().union(*matches) if all(matches) else frozenset()


def support(object_word, predicate):
    """Positive fit only: unclassified or other senses are not incompatibilities."""
    return bool(nominal_role_matches(object_word,predicate_roles(predicate)))


@lru_cache(maxsize=4096)
def _action_head(surface, following, before=""):
    """Only use predicate roles where a native verb/suru attachment exists."""
    from morphology import tokenize
    parts=[t for t in tokenize(before+surface+following) if t.start>=len(before)]
    if not parts or parts[0].start!=len(before) or not parts[0].has_reading:return ''
    first=parts[0]
    if first.end>len(before)+len(surface):return ''
    if first.pos=='動詞':return surface
    if first.pos!='名詞' or not first.pos_sub.startswith('サ変接続'):return ''
    rest=parts[1:] if len(parts)>1 else tokenize(following)
    from morphology import native_suru_form
    if (rest and rest[0].has_reading and rest[0].pos=='動詞'
            and native_suru_form(rest[0].surface,rest[0].infl_form,rest[0].reading,False)):
        return first.surface
    return ''


def candidate_object_evidence(surface, following, before=""):
    """Rank a repaired noun against its unchanged explicit case + predicate.

    48-AIK shares the existing non-accusative argument roles in this same
    comparison. Positive fit ranks candidates; missing fit is not an anomaly.
    The existing object/action roles are used in both directions. Native
    boundaries keep a later or quoted verb from becoming the noun's evidence;
    written kanji never borrow roles from a different homophone spelling.
    """
    if not following:return None
    from morphology import tokenize
    end=len(before)+len(surface)
    parts=list(tokenize(before+surface+following))
    left=[t for t in parts if t.start<end and t.end>len(before)]
    right=[t for t in parts if t.start>=end]
    from reading_segments import native_coordinated_nominal_parts
    if (not left or left[0].start!=len(before) or left[-1].end!=end
            or not all(t.has_reading for t in left)
            or not (left[-1].pos=='名詞' or native_coordinated_nominal_parts(surface))
            or len(right)<2):return None
    native=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    case_index=next((i for i,t in enumerate(parts) if t.start>=end
        and not (t.pos=='助詞' and t.pos_sub.startswith('副助詞'))),len(parts))
    if case_index+1>=len(parts):return None
    noun_index=_case_noun_index(native,case_index)
    if noun_index<0 or parts[noun_index].end!=end:return None
    case,head=parts[case_index:case_index+2]
    if (case.surface not in ('を',)+tuple(CASE_VERB_ROLES) or not case.has_reading
            or case.pos!='助詞' or not case.pos_sub.startswith('格助詞')
            or head.start!=case.end or not head.has_reading):return None
    if all('ぁ'<=c<='ゖ' or c=='ー' for c in surface):
        from reading_segments import native_nominal_phrase_faces
        faces=native_nominal_phrase_faces(surface)
    else:
        # Keep the actual written noun's meaning through its unchanged
        # prefix/attested compound. Do not borrow another homophone's face.
        from reading_segments import _native_written_nominal_faces
        faces=_native_written_nominal_faces(surface) or (surface,)
    full=before+surface+following
    evidence=[]
    for head in parts[case_index+1:]:
        if not head.has_reading:break
        # The same argument reader already permits an unchanged native
        # manner modifier; do not let it sever this noun from its action.
        if head.start!=case.end and _argument_prefix(full,head.start,lambda _:native)[1]!=case.end:
            # A following native object is another argument of the same
            # action, not a clause boundary. Reuse the original case reader
            # instead of losing the repaired destination/instrument's roles.
            argument=case_argument_before(full,head.start,lambda _:native,through_object=True)
            if case.surface=='を' or argument!=(parts[noun_index].surface,case.surface):continue
        suffix=full[head.end:]
        evidence.extend(candidate_evidence(face,head.surface,suffix,before=full[:head.start],
                            case=None if case.surface=='を' else case.surface) for face in faces)
    evidence=[row for row in evidence if row is not None]
    return max(evidence,key=lambda row:bool(row['shared_roles'])) if evidence else None


def candidate_nominal_spelling_evidence(before,surface,following):
    """Rank the actual spelling inside its unchanged nominal argument.

    A coordinated member cannot borrow another member's meaning. Reuse
    the native coordination and case/predicate proof, including manner
    modifiers. This is positive candidate evidence, never source oddness.
    """
    from morphology import tokenize
    from reading_segments import native_coordinated_nominal_parts
    full=before+surface+following;start=len(before);end=start+len(surface)
    parts=tokenize(full)
    beginnings=sorted({start}|{t.start for t in parts if t.start<start})
    native=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    for case_index,case in enumerate(parts):
        if (case.start<end or not case.has_reading or case.pos!='助詞'
                or not case.pos_sub.startswith('格助詞')
                or case.surface not in ('を',)+tuple(CASE_VERB_ROLES)):continue
        noun_index=_case_noun_index(native,case_index)
        if noun_index<0:continue
        noun_end=parts[noun_index].end
        for begin in beginnings:
            nominal=full[begin:noun_end]
            if not (begin==start and noun_end==end or native_coordinated_nominal_parts(nominal)):continue
            proof=candidate_object_evidence(nominal,full[noun_end:],full[:begin])
            if proof and proof['shared_roles']:
                groups=coordinated_nominal_role_groups(nominal)
                # Related members add positive contextual support between
                # homophones. Different categories still remain valid if
                # every member fits the action; this is not an exclusion.
                shared=frozenset.intersection(*groups) if len(groups)>1 else frozenset()
                return dict(proof,source='nominal_spelling_argument',coordinated_shared_roles=sorted(shared))
    return None


def preserves_nominal_spelling_argument(line,start,end,surface):
    """A spelling choice must retain an already proved source argument sense."""
    from last_choice import surface_for_reading
    original=line[start:end]
    if surface_for_reading(original)==surface:return True
    from context_meaning import preserves_nominal_spelling_context
    if not preserves_nominal_spelling_context(line,start,end,surface):return False
    before,following=line[:start],line[end:]
    proof=candidate_nominal_spelling_evidence(before,original,following)
    return not proof or bool(candidate_nominal_spelling_evidence(before,surface,following))


def candidate_internal_argument_evidence(surface, following, before=""):
    """Carry a wide candidate's own native argument proof into shared ranking.

    A local predicate already receives the unchanged object's roles. When
    both words are inside one validated repair, their native case boundary
    must supply the same evidence. A missing fit never marks the source odd.
    The actual written noun is checked, not another same-reading spelling.
    """
    if not any(case in surface[1:-1] for case in ('を',)+tuple(CASE_VERB_ROLES)):
        return None
    from morphology import tokenize
    start=len(before);end=start+len(surface)
    for part in tokenize(before+surface+following):
        if (not start<part.start<part.end<end or not part.has_reading
                or part.pos!='助詞' or not part.pos_sub.startswith('格助詞')
                or part.surface not in ('を',)+tuple(CASE_VERB_ROLES)):continue
        cut=part.start-start
        proof=candidate_object_evidence(surface[:cut],surface[cut:]+following,before)
        if proof and proof['shared_roles']:
            return dict(proof,source='candidate_internal_argument')
    return None


@lru_cache(maxsize=4096)
def changed_nominal_object_allowed(original, changed):
    """48-AIO: an adjective conditional cannot become an unsupported noun.

    A native hypothetical adjective changed into a nominal object needs
    positive support from the unchanged case/predicate. Mere dictionary
    noun existence does not explain this change of grammatical role.
    Ordinary nominal repairs retain their existing contracts; incomplete,
    quoted, connected and unrelated edits stay outside this scope.
    """
    if 'を' not in original or original==changed:return True
    from difflib import SequenceMatcher
    from morphology import tokenize,dictionary_inflections
    source_adjectives=[(t.start,t.end) for t in tokenize(original)
        if t.has_reading and t.pos=='形容詞' and t.infl_form=='仮定形'
        and any(pos.startswith('形容詞,') and form==t.infl_form and rd==t.reading
                for pos,form,base,rd in dictionary_inflections(t.surface) or ())]
    if not source_adjectives:return True
    from reading_segments import native_object_predicate_proof,native_object_predicate_contexts,_native_source_clauses
    from contextual_repair import _completed_predicate_token,_productive_predicate
    matcher=SequenceMatcher(None,original,changed,autojunk=False)
    edits=[(c,d) for tag,a,b,c,d in matcher.get_opcodes() if tag!='equal'
           and any(a<hi and lo<b or a==b and lo<=a<hi for lo,hi in source_adjectives)]
    if not edits:return True
    for offset,clause in _native_source_clauses(changed):
        parts=list(tokenize(clause))
        for i,case in enumerate(parts):
            if (i==0 or i+1>=len(parts) or case.surface!='を' or not case.has_reading
                    or case.pos!='助詞' or not case.pos_sub.startswith('格助詞')):continue
            head=parts[i-1]
            if head.end!=case.start:continue
            begin=i-1
            while begin>0 and parts[begin-1].end==parts[begin].start and parts[begin-1].pos in ('名詞','接頭詞'):
                begin-=1
            left=parts[begin].start;right=case.start
            # A literal kana noun may be split as a case plus a noun
            # (が + ぞう). Reuse the native nominal reading frame before
            # taking the best parse's last noun as the entire argument.
            projected=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                              else t.reading for t in parts[i+1:])
            frames=native_object_predicate_contexts(clause[:case.end]+projected)
            native_starts=[a for a,b,faces in frames if b==case.end]
            if native_starts:left=min(native_starts)
            if not any(c<offset+right and offset+left<d or c==d and offset+left<=c<=offset+right
                       for c,d in edits):continue
            # Both case and finite predicate must be unchanged source text.
            if not any(block.b<=offset+right and offset+len(clause)<=block.b+block.size
                       for block in matcher.get_matching_blocks()):continue
            tail=clause[case.end:]
            following=parts[i+1:]
            if not following or not all(t.has_reading for t in following):continue
            first,last=following[0],following[-1]
            if not _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,last.reading,
                    last.start,last.end,last.has_reading,last.infl_form)):continue
            if not _action_head(first.surface,tail[len(first.surface):],clause[:case.end]):continue
            finite=following[1] if first.pos=='名詞' and len(following)>1 else first
            legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
            if not _terminal_predicate_tail(clause,legacy,finite.end,finite.infl_form):continue
            if not _productive_predicate(tail,first.surface,before=clause[:case.end]):continue
            noun=clause[left:right]
            evidence=candidate_object_evidence(noun,clause[right:])
            if not evidence or not evidence['shared_roles']:return False
            # The common full clause proof binds meaning to native inflection.
            faces=(evidence['object'],)
            if not native_object_predicate_proof(clause[left:],case.end-left,faces):return False
    return True


# GPT-6 Astra / 2026-09-27: acquisition followed by returning is an
# ordinary purpose sequence. These are action senses, not typo pairs.
ACQUISITION_ACTIONS=frozenset(('買う','借りる','受け取る','拾う','集める'))
RETURN_MOTION_ACTIONS=frozenset(('帰る','戻る','還る'))


def candidate_origin_return_evidence(surface,following):
    """A native origin noun is the destination of an adjacent return verb."""
    if (not following.startswith(('に','へ')) or 'origin' not in nominal_roles(surface)):
        return False
    from morphology import tokenize
    parts=tokenize(surface+following)
    if len(parts)<3:return False
    noun,case,verb=parts[:3]
    return bool(noun.surface==surface and noun.pos=='名詞' and noun.has_reading
        and noun.end==case.start and case.end==verb.start
        and case.surface in ('に','へ') and case.pos=='助詞'
        and case.pos_sub=='格助詞:一般' and verb.pos=='動詞'
        and verb.pos_sub=='自立' and verb.has_reading
        and native_verb_lexemes(verb.surface,verb.infl_form,verb.reading)
            & RETURN_MOTION_ACTIONS)


def candidate_return_sequence_evidence(original,surface,following,before=''):
    """An edited acquisition immediately precedes an unchanged return act."""
    if not original or original==surface:return None
    from morphology import tokenize
    shared=0
    while shared<min(len(original),len(surface)) and original[-1-shared]==surface[-1-shared]:
        shared+=1
    unchanged=len(before)+len(surface)-shared
    text=before+surface+following
    parts=tokenize(text)
    for first,link,last in zip(parts,parts[1:],parts[2:]):
        if (first.start<len(before) or first.end>unchanged
                or first.end!=link.start or link.end!=last.start
                or link.start<unchanged or link.surface not in ('て','で')
                or link.pos!='助詞' or link.pos_sub!='接続助詞'
                or first.pos!='動詞' or last.pos!='動詞' or last.pos_sub!='自立'
                or not first.has_reading or not last.has_reading
                or not native_verb_lexemes(last.surface,last.infl_form,last.reading) & RETURN_MOTION_ACTIONS):continue
        lemmas=native_verb_lexemes(first.surface,first.infl_form,first.reading)
        acquired=lemmas & ACQUISITION_ACTIONS
        if acquired:
            return dict(version=KNOWLEDGE_VERSION,relation='acquisition_then_return',
                        actions=sorted(acquired),following=last.base_form,
                        connective=link.surface)
    return None


def candidate_evidence(object_word, surface, following, before="", case=None):
    """Expose the source and roles used for ranking, including no-fit results."""
    from morphology import tokenize
    parts=[p for p in tokenize(before+surface+following) if p.start>=len(before)]
    offset=len(before)
    if not parts or parts[0].start!=offset:
        # The caller supplied this original replacement boundary. A whole
        # sentence's unknown parse must not swallow an independently native
        # adjective manner and hide the following action's argument roles.
        parts=tokenize(surface+following);offset=0
    if (len(parts)>1 and parts[0].start==offset and parts[0].pos=='形容詞'
            and parts[0].end<offset+len(surface) and parts[1].pos=='動詞'
            and parts[1].pos_sub=='自立'):
        from reading_segments import native_adjective_adverbial_prefix
        cut=parts[0].end-offset
        if native_adjective_adverbial_prefix(surface+following,cut):
            # The object's roles still come from the original argument. When
            # the outer parse lost this boundary, use the independently
            # attested manner phrase only for the verb's lexical lookup;
            # the caller retains whole-context candidate validation.
            lexical_before=before if offset else ''
            return candidate_evidence(object_word,surface[cut:],following,lexical_before+surface[:cut],case)
    faces=(object_word,)
    # 48-AJX: an unchanged kana accusative has the same native noun
    # readings as other cases. A best-parse kana spelling must not hide
    # its already attested roles from candidate ranking. Written nouns
    # retain their exact sense; unknown readings provide no evidence.
    if object_word and all('ぁ'<=c<='ゖ' or c=='ー' for c in object_word):
        from reading_segments import native_nominal_phrase_faces
        faces=native_nominal_phrase_faces(object_word)
    groups=[coordinated_nominal_role_groups(face) or (nominal_roles(face),) for face in faces]
    if not any(all(group) for group in groups) and not any(
            nominal_role_matches(face,('referent',)) for face in faces):return None
    nominal=frozenset(role for group in groups for member in group for role in member)
    def matches(roles):
        return frozenset().union(*(nominal_role_matches(face,roles) for face in faces))
    head=_action_head(surface,following[:8],before)
    predicate=predicate_roles(head,following,before,case=case) if head else frozenset()
    if not nominal:
        nominal=matches(predicate)
        if not nominal:return None
    # 48-APE / GPT-6 Astra: temporal ni locates an event; it is not
    # that verb's destination/recipient. Exact nominal roles exclude relative
    # days such as ashita, and _action_head still proves a native verb/suru.
    # TUFS: https://www.coelang.tufs.ac.jp/mt/ja/gmod/contents/explanation/029.html
    if head and case=='に' and 'time' in nominal and 'relative_time' not in nominal:
        predicate=predicate|frozenset(('time',))
    # 48-AKB: a proved kana suru action has the same meaning as its
    # written native spelling. Share the completion proof here so a
    # best-parse fragment cannot rank its kanji counterpart above it.
    reading=(surface+following).rstrip('。！？.!?')
    if (not matches(predicate) and reading
            and all('ぁ'<=c<='ゖ' or c=='ー' for c in reading)):
        from reading_segments import completed_sahen_reading
        action=completed_sahen_reading(reading,allow_nonpolite=True,return_action=True,
            object_faces=tuple(faces) if case is None else None,
            case_argument=(case,tuple(faces)) if case is not None else None)
        if action:
            head=action
            predicate=predicate_roles(action,case=case)
    if not head:return None
    # A specific task/office holder supplies a selection relation.
    # General description of a person stays valid, but has no such prior.
    preferred=('role_assignment' if case is None and 'role_candidate' in nominal
               and head in ROLE_ASSIGNMENT_ACTIONS else None)
    if case is None and 'photographic_media' in nominal:
        from context_meaning import photographic_candidate_relation
        photographic=photographic_candidate_relation(before,surface,following)
        if photographic:
            preferred=photographic
            # The actual accusative, native action head and literal suru
            # chain supply the existing capture relationship. This is not
            # a blanket transfer from action meanings to all noun roles.
            if photographic=='photographic_action/image_capture':
                predicate=predicate|frozenset(('photographic_media',))
    return dict(version=KNOWLEDGE_VERSION,object=object_word,predicate=head,case=case or 'を',
                object_roles=sorted(nominal),predicate_roles=sorted(predicate),
                shared_roles=sorted(matches(predicate)),preferred_relation=preferred)



def genitive_nominal_support(left,right,*,nominalized_attribute=False):
    """Ordinary event/time and entity/attribute relations with an actual の."""
    a=nominal_roles(left);b=nominal_roles(right)
    if nominalized_attribute:b=b | {'attribute'}
    if field_nominal_support(left,right):return True
    return bool(a & {'event','process'} and b & {'time','information','text'}
                or a & {'event','process','text','information','time','relative_time'}
                   and 'continuation' in b
                or a & {'object','food','drink','medicine','material','text','information',
                        'time','process','event','quantity','money'} and 'partitive' in b
                or 'information' in a and 'text' in b
                or 'text' in a and 'information' in b
                or a & {'object','food','drink','medicine','material'} and 'container' in b
                or a and 'attribute' in b
                or 'person' in a and b & {'object','device','text'}
                or a & {'shape','person','place','object','device','event','food','body_part','money'}
                   and 'depiction' in b)

def field_nominal_support(left,right):
    """A named subject of a reference work or teaching profession."""
    return bool('field' in nominal_roles(left)
                and nominal_roles(right) & {'reference','teaching'})


def relational_nominal_support(left,right):
    """48-ALY: the same proved noun relation for sources and candidates.

    Native noun identity and exact readings are checked by the caller.
    Existing unit/compound evidence is independent of the cost table.
    """
    # 48-AMC: the word roster includes obscure compounds and surface
    # forms (even シマス). Membership does not assign a noun-head meaning.
    # Infer this alternative reading only when that head has an independent
    # meaning; otherwise leave the existing whole-word/source checks active.
    return bool(genitive_nominal_support(left,right)
                or nominal_roles(right) and nominal_compound_support(left,right))



def _following_case_role(parts,index,word,case):
    """This argument's next native action; do not cross another predicate."""
    from morphology import dictionary_inflections
    rest=parts[index+1:]
    nominalized=bool(rest and rest[0].pos=='助詞' and rest[0].pos_sub=='連体化')
    if nominalized:rest=rest[1:]
    for i,part in enumerate(rest):
        if not part.has_reading or part.pos=='記号':break
        if part.pos=='助詞' and part.pos_sub.startswith('接続助詞'):break
        if part.pos=='動詞':
            if case=='が':
                _,roles=_subject_predicate_roles(part.surface,
                    ''.join(t.surface for t in rest[i+1:]))
            else:
                roles=native_verb_roles(part.surface,part.infl_form,part.reading,
                    case=None if case=='を' else case)
            return bool(nominal_role_matches(word,roles))
        if part.pos=='名詞' and part.pos_sub.startswith('サ変接続'):
            following=rest[i+1] if i+1<len(rest) else None
            from morphology import native_suru_form
            native_suru=bool(following and following.pos=='動詞' and following.has_reading
                and native_suru_form(following.surface,following.infl_form,following.reading,False)
                and any(pos.startswith('動詞,') and base=='する' and form==following.infl_form
                        and rd==following.reading for pos,form,base,rd
                        in dictionary_inflections(following.surface) or ()))
            if nominalized or native_suru:
                if case=='が' and native_suru:
                    _,roles=_subject_predicate_roles(part.surface,
                        ''.join(t.surface for t in rest[i+1:]))
                    return bool(nominal_role_matches(word,roles))
                return case_action_support(word,case,part.surface)
        if nominalized:break
    return False


@lru_cache(maxsize=4096)
def native_case_support(text):
    """Positive native argument links for comparing already admitted candidates.

    Share source-role boundaries and inflections; a later clause or quoted
    action supplies no support. Missing/figurative meanings are not errors.
    Only the actual whole nominal head is classified, never a compound tail.
    """
    from morphology import tokenize
    parts=tokenize(text);supported=[]
    for i in range(1,len(parts)-1):
        noun,case=parts[i-1:i+1]
        if (not noun.has_reading or noun.pos!='名詞'
                or noun.pos_sub.startswith(('固有名詞','非自立','接尾'))
                or not case.has_reading or case.pos!='助詞'
                or not case.pos_sub.startswith('格助詞')
                or case.surface not in ('を','が',*CASE_VERB_ROLES)
                or noun.end!=case.start):continue
        if i>1 and parts[i-2].end==noun.start and parts[i-2].pos in ('名詞','接頭詞'):
            continue
        if _following_case_role(parts,i,noun.surface,case.surface):
            supported.append((noun.start,noun.end,case.surface))
    return tuple(supported)


@lru_cache(maxsize=4096)
def original_argument_evidence(surface,before,after,source):
    """Positive roles of the exact written word, before homophone guessing.

    A concrete subject or an attested object/predicate relation can explain
    the original spelling. A nearby cue cannot outweigh that relationship.
    Missing evidence remains unknown and does not classify the source odd.
    """
    if not source or source!=before+surface+after:return None
    from morphology import tokenize
    parts=tokenize(source);start=len(before);end=start+len(surface)
    current=next((t for t in parts if t.start==start and t.end==end and t.has_reading),None)
    if not current:return None
    if current.pos=='名詞':
        case_index=next((i for i,t in enumerate(parts) if t.start==end),None)
        case=parts[case_index] if case_index is not None else None
        if case and case.has_reading and case.pos=='助詞':
            if case.surface!='を' and case.pos_sub.startswith('格助詞') and 'person' in nominal_roles(surface):
                if case.surface=='が' or _following_case_role(parts,case_index,surface,case.surface):
                    return dict(version=KNOWLEDGE_VERSION,role='argument',word=surface,
                                source_roles=['person'],case=case.surface)
            if case.surface=='を' and case.pos_sub.startswith('格助詞'):
                # The word's own object relation outranks a nearby spelling
                # cue. A preceding genitive modifier must fit as well; a
                # role for 官僚 alone cannot certify 保存の官僚.
                prior=next((i for i,t in enumerate(parts) if t.end==start),None)
                genitive=bool(prior is not None and parts[prior].pos=='助詞'
                              and parts[prior].pos_sub=='連体化')
                modifier_ok=not genitive or (prior>0 and parts[prior-1].has_reading
                    and genitive_nominal_support(parts[prior-1].surface,surface))
                if modifier_ok and _following_case_role(parts,case_index,surface,'を'):
                    return dict(version=KNOWLEDGE_VERSION,role='object',word=surface,case='を')
            if case.pos_sub=='連体化' and case_index+1<len(parts):
                noun=parts[case_index+1]
                nominalized=False;head=noun.surface
                # 長＋さ and 静か＋さ are native nominalized attributes.
                # Reuse the original-form grammar, including its dictionary
                # and suffix checks; do not add a list of derived nouns.
                if case_index+2<len(parts):
                    suffix=parts[case_index+2]
                    if suffix.surface=='さ' and suffix.pos_sub=='接尾:特殊':
                        from reading_segments import nominalized_adjective_context
                        legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                                 t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
                        nominalized=nominalized_adjective_context(
                            source,noun.start,suffix.end,lambda _:legacy)
                        if nominalized:head=source[noun.start:suffix.end]
                if (noun.has_reading and (noun.pos=='名詞' or nominalized)
                        and noun.start==case.end and genitive_nominal_support(
                            surface,head,nominalized_attribute=nominalized)):
                    return dict(version=KNOWLEDGE_VERSION,role='genitive',word=surface,
                                head=head,case=case.surface)
    if current.pos!='動詞':return None
    legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
             t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    obj=object_before(source,start,lambda _:legacy)
    if obj:
        evidence=candidate_evidence(obj,surface,after,before)
        if evidence and evidence['shared_roles']:
            return dict(evidence,role='object',word=surface)
        return None
    # Reuse the actual adjacent native case. A remote cue cannot overturn
    # a positively supported intransitive destination/surface relation.
    argument=case_argument_before(source,start,lambda _:legacy)
    if argument:
        noun,case=argument
        evidence=candidate_evidence(noun,surface,after,before,case=case)
        if evidence and evidence['shared_roles']:
            return dict(evidence,role='case',word=surface)
    return None


# 48-ACF / GPT-6 / 2026-09-13: explicit non-accusative roles.
# A destination/container is not interchangeable with the stored content.
# Positive evidence for composed native clauses; missing roles are not a
# global declaration that a sentence or metaphor is wrong.
STORAGE_DESTINATIONS=frozenset(NOUN_GROUPS['container'])
TRANSFER_DESTINATIONS=frozenset('端末 サーバー サーバ パソコン'.split())


def case_action_support(noun, particle, action):
    if particle=='を':return support(noun,action)
    if particle=='が':return bool(nominal_role_matches(noun,SUBJECT_VERB_ROLES.get(action,set())))
    if nominal_role_matches(noun,predicate_roles(action,case=particle)):
        return True
    if particle in ('は','も','しか'):
        return bool(support(noun,action) or
                    nominal_role_matches(noun,SUBJECT_VERB_ROLES.get(action,set())))
    if particle=='に':
        return bool(action in ('保存','保管','収納','登録') and
                    noun in STORAGE_DESTINATIONS | TRANSFER_DESTINATIONS)
    if particle=='へ':
        return bool(action in ('送信','転送') and
                    (noun in TRANSFER_DESTINATIONS or 'person' in nominal_roles(noun)))
    if particle=='で':
        return bool('place' in nominal_roles(noun) and
                    action in ('保存','保管','確認','作業','調理','料理','掃除'))
    return False


def proved_action_case_support(noun,particle,action,context=''):
    """Reuse a clause-proved kana verb head without its isolated noun parse.

    The caller has already proved the full predicate and its inflection;
    this resolves only the semantic roles of that unchanged action reading.
    """
    if (support(noun,action) if particle=='を' else case_action_support(noun,particle,action)):
        return True
    if not action:return False
    if context and particle=='を' and 'photographic_media' in nominal_roles(noun):
        from context_meaning import _photographic_action_contexts,_meaning_roles,_expected_role
        for frame in _photographic_action_contexts(context):
            if (frame['surface']==action and frame.get('sahen_action')
                    and frame['evidence_start']==0 and frame['start']==len(noun)+1
                    and context[:frame['start']]==noun+'を'
                    and _expected_role(frame)=='image_capture'
                    and 'image_capture' in _meaning_roles(frame)):
                return True
    from morphology import dictionary_inflections
    roles=set()
    for pos,form,base,rd in dictionary_inflections(action) or ():
        if pos.startswith('動詞,自立,'):
            if particle in ('が','は','も','しか'):
                roles.update(native_verb_roles(action,form,rd,subject=True))
            if particle!='が':
                roles.update(native_verb_roles(action,form,rd,
                    case=None if particle in ('を','は','も','しか') else particle))
    # A proved written clause returns its complete inflected predicate,
    # while the reading-only path returns the lexical head. Resolve that
    # same original suffix to its actual verb, keeping the native form,
    # reading and auxiliary context rather than stripping a guessed ending.
    if context:
        from morphology import tokenize
        heads=[t for t in tokenize(context) if t.has_reading
               and t.pos=='動詞' and t.pos_sub=='自立'
               and context[t.start:]==action and t.surface!=action]
        if len(heads)==1:
            head=heads[0]
            kwargs=dict(tail=context[head.end:],before=context[:head.start])
            if particle in ('が','は','も','しか'):
                roles.update(native_verb_roles(head.surface,head.infl_form,
                    head.reading,subject=True,**kwargs))
            if particle!='が':
                roles.update(native_verb_roles(head.surface,head.infl_form,
                    head.reading,case=None if particle in ('を','は','も','しか')
                    else particle,**kwargs))
    # Preserve the completed clause's auxiliary when an outer case is
    # carried by receiving an action, not by the lexical verb alone.
    if context and particle in _BENEFACTIVE_CASES:
        from morphology import tokenize
        heads=[t for t in tokenize(context) if (t.surface==action or t.reading==action
                or context[t.start:]==action) and t.has_reading
               and t.pos=='動詞' and t.pos_sub.startswith('自立')]
        if len(heads)==1:
            head=heads[0]
            roles.update(native_benefactive_case_roles(head.surface,head.infl_form,head.reading,
                context[head.end:],particle,context[:head.start]))
    return bool(nominal_role_matches(noun,roles))


@lru_cache(maxsize=4096)
def native_preference_relative_support(argument,head,stem,reading):
    """A preference has a person experiencing it and a liked/disliked item.

    The caller proves N-ga-NA-na-N in the unchanged source. Keep both
    possible relative argument roles and the exact native adjective.
    TUFS: https://www.coelang.tufs.ac.jp/mt/ja/dmod/class/ja_19.html
    """
    if stem not in ('好き','嫌い'):return False
    from morphology import dictionary_inflections
    if not any(pos.startswith('名詞,形容動詞語幹,') and base==stem and rd==reading
               for pos,form,base,rd in dictionary_inflections(stem) or ()):return False
    a=nominal_roles(argument);b=nominal_roles(head)
    return bool('person' in a and b or 'person' in b and a)


def relative_action_support(noun, action, occupied_cases=(), *, source_head=False):
    """A relative action may describe its object or an event's time.

    2026-09-14 / GPT-6 Astra: 予約した時間 is not an accusative-only
    relationship. Native finite morphology is established by the caller;
    unknown action roles add no new proof of a nominal boundary.
    """
    roles=predicate_roles(action)
    # A relative head can fill a still-open subject or object, not a case
    # already occupied inside the independently proved relative clause.
    _,subject_roles=_subject_predicate_roles(action,'')
    event_roles=roles | subject_roles
    if 'を' in occupied_cases:roles=set()
    if any(case in occupied_cases for case in ('が','は','も')):subject_roles=set()
    # Only an actual source noun head can fill an attested destination or
    # place. A reading guess must not reinterpret a malformed auxiliary as
    # a homophonous noun (したない -> した + 内). The caller proves the
    # original noun, finite predicate and every occupied case before opt-in.
    other_roles=(frozenset().union(*(predicate_roles(action,case=case)
        for case in CASE_VERB_ROLES if case not in occupied_cases))
        if source_head else frozenset())
    return bool(nominal_role_matches(noun,roles | subject_roles | other_roles) or
                'time' in nominal_roles(noun) and event_roles)


def candidate_support(object_word, surface, following):
    evidence=candidate_evidence(object_word,surface,following)
    return bool(evidence and evidence['shared_roles'])


# GPT-6 / 2026-09-11 / 48-YJ: 主体の生死・存在を述べる一項述語。
# 誤字と正解の対応表ではなく、直接の目的語を取らない語義の分類。
# 移動の経路、期間、他動詞の別義を持つ動詞は含めない。
SUBJECT_ONLY_PREDICATES = frozenset(
    '絶命 死亡 死去 逝去 急逝 他界 夭折 崩御 病死 餓死 溺死 戦死 '
    '誕生 生誕 実在 存在 死ぬ 亡くなる 生まれる 冴える さえる ある 有る 在る あり'.split())


@lru_cache(maxsize=4096)
def _independent_accusative_clause(text):
    """48-AIP: syntax establishes the next clause's own object ownership.

    Its lexical meaning need not be classified. A known nominal phrase,
    actual を, and a complete native simple predicate delimit this clause.
    Relative verbs, another case, quotations and unfinished text do not
    establish that the earlier object has already been consumed.
    """
    from morphology import tokenize,dictionary_inflections
    from contextual_repair import _productive_predicate
    text=text.lstrip('、, ')
    from contextual_repair import _source_clause_bounds
    _,end=_source_clause_bounds(text,0,0)
    text=text[:end].rstrip(' 。！？!?\t\r\n')
    if not text:return False
    parts=list(tokenize(text))
    if not parts or not all(t.has_reading for t in parts):return False
    if parts[0].start!=0 or parts[-1].end!=len(text):return False
    cases=[i for i,t in enumerate(parts) if t.surface=='を' and t.pos=='助詞'
           and t.pos_sub.startswith('格助詞')]
    if len(cases)!=1:return False
    i=cases[0]
    if i<1 or i+1>=len(parts):return False
    prefix=parts[:i]
    for j,part in enumerate(prefix):
        if part.pos in ('名詞','接頭詞','連体詞'):continue
        if (part.surface=='の' and part.pos=='助詞' and part.pos_sub=='連体化'
                and 0<j<len(prefix)-1):continue
        if (part.pos=='形容詞' and part.infl_form=='基本形'
                and any(pos.startswith('形容詞,') and form==part.infl_form and rd==part.reading
                        for pos,form,base,rd in dictionary_inflections(part.surface) or ())):continue
        return False
    head=parts[i+1];before=text[:head.start];tail=text[head.start:]
    if not _action_head(head.surface,tail[len(head.surface):],before):return False
    legacy=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in parts]
    if not object_before(text,head.start,lambda _:legacy):return False
    finite=parts[i+2] if head.pos=='名詞' and i+2<len(parts) else head
    if not _terminal_predicate_tail(text,legacy,finite.end,finite.infl_form):return False
    if _productive_predicate(tail,head.surface,before=before):return True
    # A native action followed by a native nominal copula is a complete
    # independent clause too. Reuse the same component completion proofs;
    # merely covering the suffix with noun/auxiliary POS is insufficient.
    from reading_segments import _native_nominal_copula_tail,native_attributive_predicate_end
    for noun in parts[i+2:]:
        if (noun.pos!='名詞' or not noun.has_reading or noun.start<finite.end
            or not native_attributive_predicate_end(text[:noun.start])):continue
        prefix=text[head.start:noun.start]
        if (_productive_predicate(prefix,head.surface,before=before)
            and _native_nominal_copula_tail(noun.surface,text[noun.end:])):
            return True
    return False


def _terminal_predicate_tail(text, tokens, edge, last_form, independent_next=False, object_word=None):
    """連体節・接続節を越えて後ろの述語へ係る「を」を誤って取らない。"""
    # A table field owns its argument and predicate tail. The next
    # arrow/tab field cannot keep this clause open or complete it.
    from contextual_repair import _source_clause_bounds
    _,limit=_source_clause_bounds(text,max(0,edge-1),edge)
    text=text[:limit]
    tokens=[t for t in tokens if t[4]<=limit]
    def finite():
        return last_form == '基本形' or last_form.startswith('命令')
    for token in tokens:
        if token[3] < edge:
            continue
        if token[3] != edge:
            return finite() and not text[edge:].strip(' 。！？!?\t\r\n')
        if token[1].startswith('助動詞') and token[5]:
            if len(token) < 7:
                return False
            from morphology import dictionary_inflections
            bases = {base for pos, form, base, reading in dictionary_inflections(token[0]) or ()
                     if pos.startswith('助動詞,') and form == token[6] and reading == token[2]}
            if not bases or bases - {'ます', 'た', 'ない', 'ぬ', 'ん', 'う', 'だ', 'です'}:
                return False
            edge = token[4]
            last_form = token[6]
        elif (independent_next and token[0] in ('つつ','ながら')
                and token[1].startswith('助詞:接続助詞') and token[5]):
            from morphology import dictionary_inflections
            previous=next((t for t in tokens if t[4]==token[3]),None)
            connected=bool(previous and len(previous)>=7 and previous[5]
                and previous[1].startswith('動詞:自立') and previous[6]=='連用形'
                and any(pos.startswith('動詞,自立,') and form=='連用形' and rd==previous[2]
                        for pos,form,base,rd in dictionary_inflections(previous[0]) or ()))
            from contextual_repair import _finite_written_predicate
            return bool(connected and _finite_written_predicate(text[token[4]:].rstrip('。！？.!?')))
        elif (token[0] in ('て','で')
                and token[1].startswith('助詞:接続助詞') and token[5]):
            from contextual_repair import _modern_te_allowed
            previous=next((t for t in tokens if t[4]==token[3]),None)
            connected=bool(previous and previous[5] and previous[1].startswith('動詞')
                and _modern_te_allowed(previous[0],previous[2],token[0]) is True)
            following=next((t for t in tokens if t[3]==token[4]),None)
            # Native non-independent verbs extend this same action. They
            # do not introduce a separate noun/case or independent predicate.
            from morphology import dictionary_inflections
            if (connected and following and len(following)>=7 and following[5]
                    and following[1].startswith('動詞:非自立')
                    and any(pos.startswith('動詞,非自立,') and form==following[6]
                            and reading==following[2]
                            for pos,form,base,reading in dictionary_inflections(following[0]) or ())):
                edge=following[4];last_form=following[6]
                continue
            # A native sentence-final te/de is a request, not an open
            # connective whose object could belong to an unseen predicate.
            # Final particles may soften the same request. Commas, quotes
            # and a following clause do not close this argument relation.
            tail_edge=token[4]
            for final in tokens:
                if final[3]<tail_edge:continue
                if (final[3]!=tail_edge or not final[5]
                    or not final[1].startswith('助詞:終助詞')):break
                tail_edge=final[4]
            if connected and not text[tail_edge:].strip(' 。！？!?\t\r\n'):
                return True
            # V-te/de-kara retains the same completed first action.
            # Its next explicit object must independently own a finite verb;
            # a shared object, bare kara, or an open clause proves nothing.
            next_edge=token[4]
            if (connected and following and following[0]=='から' and following[5]
                    and following[1].startswith('助詞:格助詞')
                    and any(pos.startswith('助詞,格助詞,') and rd==following[2]
                            for pos,form,base,rd in dictionary_inflections(following[0]) or ())):
                next_edge=following[4]
            return bool(independent_next and connected and (_independent_accusative_clause(text[next_edge:])
                             or object_word and _motion_tail_cannot_take_object(text[next_edge:],object_word)))
        elif token[1].startswith('名詞') and token[5] and finite():
            from reading_segments import native_attributive_predicate_end
            if not native_attributive_predicate_end(text[:token[3]]):return False
            # An adnominal action can close as N + native copula. With no
            # outer transitive predicate, its explicit object still belongs
            # to that action. N + case (person-ni lend, etc.) stays open.
            following=next((t for t in tokens if t[3]==token[4]),None)
            from morphology import dictionary_inflections
            if not (following and len(following)>=7 and following[5]
                    and following[1].startswith('助動詞')
                    and any(pos.startswith('助動詞,') and base in ('だ','です')
                            and form==following[6] and reading==following[2]
                            for pos,form,base,reading in dictionary_inflections(following[0]) or ())):
                return False
            edge=token[4];last_form=''
        elif token[1].startswith('助詞:終助詞'):
            edge = token[4]
        else:
            # 句点で終わった述語だけ。読点や閉じ括弧を文末と取り違えない。
            return finite() and token[0] in ('。', '！', '？', '!', '?')
    return finite() and not text[edge:].strip()


def _closed_object_predicate_spans(text, tokens, predicates=None):
    """実辞書の述語＋明示目的語＋文末を照合してから異様の範囲を返す。

    直前の目的語が、後ろの別の述語に係る読みを排除しない。
    使役、受身、引用や、外側の述語へ目的語が係り得る名詞修飾では判定しない。
    名詞＋実コピュラで閉じる節は、明示目的語を前の動作へ結ぶ。
    実際のて接続と非自立動詞で続く補助動詞は同じ動作へ結びつける。
    て／で接続は、後続節が独立した明示目的語と完成述語を持つ場合だけ閉じる。
    """
    from morphology import dictionary_inflections
    out = []
    for i, token in enumerate(tokens):
        if len(token) < 7 or not token[5]:
            continue
        lemma = None
        edge = token[4]
        last_form = token[6]
        if (predicates is None or token[0] in predicates) and token[1].startswith('名詞:サ変接続'):
            if i+1 >= len(tokens):
                continue
            following = tokens[i+1]
            from morphology import native_suru_form
            if not (len(following) >= 7 and following[3] == edge and following[5] and following[1].startswith('動詞')
                    and native_suru_form(following[0],following[6],following[2],False)
                    and any(pos.startswith('動詞,') and base == 'する'
                            and form == following[6] and reading == following[2]
                            for pos, form, base, reading in dictionary_inflections(following[0]) or ())):
                continue
            lemma, edge, last_form = token[0], following[4], following[6]
        elif token[1].startswith('動詞'):
            bases = {base for pos, form, base, reading in dictionary_inflections(token[0]) or ()
                     if pos.startswith('動詞,') and form == token[6] and reading == token[2]}
            if predicates is not None and bases and not bases<=predicates and token[0]==token[2]:
                lexemes=native_verb_lexemes(token[0],token[6],token[2])
                negative=lexemes & predicates
                obj=object_before(text,token[3],lambda _:tokens)
                if negative and obj and not any(nominal_role_matches(obj,VERB_ROLES.get(word,()))
                                                for word in lexemes-negative):
                    bases=negative
            if bases and (predicates is None or bases <= predicates):
                lemma = sorted(bases)[0]
        if lemma is None:continue
        obj = object_before(text, token[3], lambda _: tokens)
        if obj and _terminal_predicate_tail(text, tokens, edge, last_form,
                independent_next=True,object_word=obj):
            # 異様なのは目的語と語本体の役割。正常な『する』の活用は範囲に入れない。
            # 語尾まで印を広げると、活用修復の入口が正常な『しました』を動かす。
            out.append((obj, lemma, token[3], token[4]))
    return out


# 48-AGU / GPT-6 Astra: physical manufacture cannot directly take an
# expense obligation as its product. Other financial/metaphorical nouns
# remain unclassified. This table is independent of homophone candidates.
_MANUFACTURING_PREDICATES=frozenset('生産 製造 量産'.split())
# 48-AHL / GPT-6 Astra: biological survival has no direct schedule or
# recorded-content object. Duration, living subjects, causative/passive
# uses and unknown/metaphorical categories supply no negative evidence.
# Source senses: Shogakukan Daijisen 長生 (Kotobank word/長生-568665).
_BIOLOGICAL_STATE_PREDICATES=frozenset('長生 長生き 生存 生息'.split())
# 48-AIQ: physical opening/access does not directly release a person.
# Source definitions: https://www.kanjipedia.jp/kotoba/0000810400
# and https://www.kanjipedia.jp/kotoba/0000817800 . Metaphorical objects
# and unknown nouns are not assigned this negative category.
_PHYSICAL_OPENING_PREDICATES=frozenset('開放 開閉 開扉'.split())
_GATHERING_PREDICATES=frozenset('収集 蒐集 採集'.split())
# Daijisen 返還 /word/返還-626122; 変換 /word/変換-8685.
# Returning ownership is distinct from changing character representation.
_BORROWED_RETURN_PREDICATES=frozenset('返還 返却 返納'.split())
_OBJECT_CONFLICT_ROLES={p:frozenset(('expense',)) for p in _MANUFACTURING_PREDICATES}
_OBJECT_CONFLICT_ROLES.update({p:frozenset(('schedule','text','information'))
                              for p in ('送電','配電')})
# Bare kana 'sasu' leaves the action unspecified. With mental content,
# an inference action is the ordinary reading; explicitly written 指す
# can instead describe what a sign/expression refers to.
_OBJECT_CONFLICT_ROLES['さす']=frozenset(('mental_content',))
# Rising/waking is not a direct operation on an ordinary object or text.
# Preserve source/location and duration uses; they have no negative role here.
# Kanjipedia 起きる: https://www.kanjipedia.jp/kotoba/0001225500
_OBJECT_CONFLICT_ROLES['起きる']=frozenset(('object','text','information','device'))
# Ordinary food preparation does not act directly on recorded textual
# content. Unclassified physical material and quoted/metaphorical contexts
# are not assigned a negative food category by this statement.
_OBJECT_CONFLICT_ROLES.update({p:frozenset(('text','information','reference'))
    for p in ('煮る','煮込む','茹でる','蒸す','蒸かす','炒める','揚げる')})
# Translating written/spoken content is distinct from acting on its named place/person.
_OBJECT_CONFLICT_ROLES.update({p:frozenset(('place','person','food','device')) for p in TRANSLATION_ACTIONS})
# Content is not the traversed path of these movement senses. Literal
# and digital places retain their own positive route interpretation.
_PATH_MOTION_ACTIONS=frozenset('入る 出る 帰る 還る 返る 戻る 行く 来る 進む 通る 渡る 走る 歩く 泳ぐ 飛ぶ 出かける 出掛ける 向かう'.split())
_NON_PATH_CONTENT_ROLES=frozenset(('text','information','photographic_media','reference','object','device'))
_ROUTE_OBJECT_ROLES=frozenset(('place','digital_destination','screen_location','time','quantity','origin'))
_OBJECT_CONFLICT_ROLES.update({p:_NON_PATH_CONTENT_ROLES for p in _PATH_MOTION_ACTIONS})
_OBJECT_CONFLICT_ROLES.update({p:frozenset(('representation_format',)) for p in _BORROWED_RETURN_PREDICATES})
_OBJECT_CONFLICT_ROLES.update({p:frozenset(('disorder',)) for p in _GATHERING_PREDICATES})
_OBJECT_CONFLICT_ROLES.update({p:frozenset(('person',)) for p in _PHYSICAL_OPENING_PREDICATES})
_OBJECT_CONFLICT_ROLES.update({p:frozenset(('schedule','text','presentation','reference','device'))
                              for p in _BIOLOGICAL_STATE_PREDICATES})



def subject_only_predicate_spans(text,tokens):
    return _closed_object_predicate_spans(text,tokens,
        SUBJECT_ONLY_PREDICATES | SOCIAL_FLOURISHING_NOUNS)


def object_predicate_conflict_reason(noun,predicate):
    """48-AIM: explain the same semantic class that supplied the anomaly."""
    if predicate in ('送電','配電'):
        return f'「{predicate}」は電流・電力を送る動作で、「{noun}」を直接の対象にする接続が不自然です'
    if predicate in TRANSLATION_ACTIONS:
        return f'「{predicate}」は文章・情報を別の言語に訳す動作で、「{noun}」そのものを直接の対象にする接続が不自然です'
    if predicate in _BORROWED_RETURN_PREDICATES and 'representation_format' in nominal_roles(noun):
        return f'「{noun}」は情報の表現形式を表し、借りた物を返す「{predicate}」との接続が不自然です'
    if predicate in _BORROWED_RETURN_PREDICATES:
        return f'「{predicate}」の返却先と、「{noun}」に続く文字の表記体系との接続が不自然です'
    if predicate in _MANUFACTURING_PREDICATES:
        return f'「{noun}」は費用を表し、製造する対象としての「{predicate}」との接続が不自然です'
    if predicate in _GATHERING_PREDICATES:
        return f'「{predicate}」は物や情報を集めることを表し、混乱した状態を直接の対象にする「{noun}」との接続が不自然です'
    if predicate in _PHYSICAL_OPENING_PREDICATES:
        return f'「{predicate}」は物や場所を開くことを表し、人を直接の対象にする「{noun}」との接続が不自然です'
    if predicate in _BIOLOGICAL_STATE_PREDICATES:
        return f'「{predicate}」は生物が生きることを表し、「{noun}」を直接の対象にする接続が不自然です'
    return f'「{noun}」を直接の対象にする「{predicate}」の意味のつながりが不自然です'


def _borrowed_return_case_conflict(text,tokens,noun,predicate,start):
    if predicate not in _BORROWED_RETURN_PREDICATES or 'writing_system' not in nominal_roles(noun):return None
    argument=case_argument_before(text,start,lambda _:tokens,through_object=True)
    if (argument and argument[1]=='に' and argument[0]!=noun
            and 'writing_system' in nominal_roles(argument[0])):
        from reading_segments import native_nominal_phrase_faces
        source=set(native_nominal_phrase_faces(noun) or (noun,))
        destination=set(native_nominal_phrase_faces(argument[0]) or (argument[0],))
        if source.isdisjoint(destination):return argument
    return None


def conflicting_object_predicates(text,tokens):
    rows=_closed_object_predicate_spans(text,tokens,
        frozenset(_OBJECT_CONFLICT_ROLES) | _BORROWED_RETURN_PREDICATES)
    def source_roles(noun):
        if noun and all('ぁ'<=c<='ゖ' or c=='ー' for c in noun):
            # The source case establishes a noun slot, even when its kana
            # best parse is an adverb. Reuse the same exact nominal readings
            # used by candidate_evidence; do not invent an unknown noun.
            from reading_segments import native_nominal_phrase_faces
            return frozenset().union(*(nominal_roles(face) for face in native_nominal_phrase_faces(noun)))
        return nominal_roles(noun)
    return [row for row in rows if
            (_OBJECT_CONFLICT_ROLES.get(row[1],frozenset()) & source_roles(row[0])
             and not (row[1] in _PATH_MOTION_ACTIONS and nominal_roles(row[0]) & _ROUTE_OBJECT_ROLES)
             and not (row[1] in TRANSLATION_ACTIONS and support(row[0],row[1])))
            or _borrowed_return_case_conflict(text,tokens,row[0],row[1],row[2])]


@lru_cache(maxsize=4096)
def changed_object_conflict_allowed(original, changed):
    """48-AJK: a proved semantic conflict needs a positively fitting repair.

    Unclassified normal source text creates no requirement. For a changed
    conflicting action, bind the candidate to the original action boundary
    and recheck its own explicit object and native closed predicate. A
    later clause or merely attested homophone cannot supply that evidence.
    """
    if original==changed or 'を' not in original:return True
    from morphology import tokenize
    def legacy(text):
        return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,
                 t.has_reading,t.infl_form) for t in tokenize(text)]
    source_tokens=legacy(original)
    conflicts=conflicting_object_predicates(original,source_tokens)
    if not conflicts:return True
    from difflib import SequenceMatcher
    matcher=SequenceMatcher(None,original,changed,autojunk=False)
    edits=[(a,b) for tag,a,b,c,d in matcher.get_opcodes() if tag!='equal']
    rows=None
    for obj,predicate,start,end in conflicts:
        # Insertion at the stem's end still changes this predicate (for
        # example, a new potential ending before its unchanged auxiliary).
        if not any(a<end and start<b or a==b and start<=a<=end for a,b in edits):continue
        # The unchanged prefix reaches the action's start even when the
        # UI replacement covers a wider phrase. Do not infer a new boundary
        # from another occurrence of the same noun or action later on.
        positions={block.b+start-block.a for block in matcher.get_matching_blocks()
                   if block.a<start<=block.a+block.size}
        if len(positions)!=1:return False
        position=next(iter(positions))
        if rows is None:rows=_closed_object_predicate_spans(changed,legacy(changed))
        fitting=False
        for noun,lemma,a,b in rows:
            if a!=position:continue
            evidence=candidate_evidence(noun,changed[a:b],changed[b:],changed[:a])
            if evidence and evidence['shared_roles']:
                source_case=_borrowed_return_case_conflict(original,source_tokens,obj,predicate,start)
                if source_case:
                    candidate_case=case_argument_before(changed,a,legacy,through_object=True)
                    if candidate_case!=source_case:continue
                    case_evidence=candidate_evidence(candidate_case[0],changed[a:b],changed[b:],
                        changed[:a],case=candidate_case[1])
                    if not case_evidence or not case_evidence['shared_roles']:continue
                fitting=True;break
        if not fitting and changed[position-1:position]=='を':
            # The damaged first predicate may have been an adverbial count.
            # Its exact native quantity and the same original object must
            # positively fit the now complete action; no later object is used.
            from reading_segments import _native_counter_prefixes,native_object_predicate_proof,native_nominal_phrase_faces
            tail=changed[position:];sizes=_native_counter_prefixes(tail,tokenize(tail))
            faces=native_nominal_phrase_faces(obj) or (obj,)
            if sizes and native_object_predicate_proof(changed,position,faces):fitting=True
        if not fitting:return False
    return True


# GPT-6 / 2026-09-11 / 48-YO: positive nominative roles, not anomaly rules.
# These broad ordinary meanings are shared across spellings and conjugations.
# Unknown nouns, passive/causative frames, and ambiguous は topics give no claim.
SUBJECT_PREDICATE_GROUPS=(
 # TUFS 005: objects, contents and events exist; people use いる.
 # https://www.coelang.tufs.ac.jp/mt/ja/gmod/contents/explanation/005.html
 ('object device text information money event process quantity shape issue','ある 有る 在る'),
 ('person','いる 居る'),
 ('object person place shape presentation text body_part','見える'),
 ('information text time','分かる 判る 解る 合う 違う 伝わる'),
 ('issue','解決 解消 発生 生じる 起きる 残る'),
 # GPT-6 Astra / 2026-09-21: ordinary sleep/wake states of a person.
 # Positive subject meanings only; no accusative role or spelling pair is
 # supplied. Animal and figurative subjects are not thereby anomalous.
 ('person','参加 出席 欠席 到着 出発 入場 退場 説明 解説 報告 発言 質問 回答 応答 読む 書く 話す 働く 学ぶ 勉強 休憩 休息 遊ぶ 休む 待つ 走る 歩く 泳ぐ 座る 坐る 立つ しゃがむ 横たわる 寝る 眠る 起きる 目覚める 起床 就寝 睡眠'),
 ('event process','開始 終了 中断 再開 継続 完了 進行 始まる 終わる 進む'),
 ('device','起動 稼働 動作 停止 故障'),
 ('text information','届く 残る 消える'),
 ('money','増える 減る 足りる 余る'),
)
SUBJECT_VERB_ROLES={}
for roles,words in SUBJECT_PREDICATE_GROUPS:
    for word in words.split():SUBJECT_VERB_ROLES.setdefault(word,set()).update(roles.split())


def subject_before(context,start,tokenize):
    """Keep a proved whole subject across the shared native argument seam.

    This is the same original boundary used by object/case readers.
    Actual topics also need the already proved separate object/predicate
    frame; an unbound or ambiguous topic supplies no subject claim.
    """
    parts,edge=_argument_prefix(context,start,tokenize)
    object_edge=edge
    parts,edge=_argument_prefix_before_object(context,parts,edge)
    object_begin=edge
    if edge<object_edge:
        # The same source adjunct may precede the intervening object too.
        # Neither an earlier verb nor a gap is an argument seam.
        parts,edge=_argument_prefix(context,edge,tokenize)
    if len(parts)<2:return ''
    noun,particle=parts[-2:]
    actual_ga=particle[0]=='が' and particle[1].startswith('助詞:格助詞')
    topic_heads=()
    if (not actual_ga and edge<object_edge and particle[0] in ('は','も')
            and particle[1]=='助詞:係助詞' and particle[2]==particle[0]
            and particle[5]):
        from reading_segments import native_preposed_object_parts
        topic_heads=tuple(head for begin,case,heads,cut,faces
            in native_preposed_object_parts(context,True,
                object_start=object_begin if edge<object_begin else None)
            if begin==edge and case==particle[0] and cut==object_edge
            for head in heads)
    if (particle[4]!=edge or not (actual_ga or topic_heads) or noun[4]!=particle[3]
            or not noun[5] or not noun[1].startswith('名詞')
            or '固有名詞' in noun[1]):
        return ''
    # Share the whole classified argument used by object and case readers.
    # A productive suffix must not become either a bare noun or no subject.
    whole=_classified_argument_head(context,parts,len(parts)-2)
    if whole:return whole[0] if actual_ga or whole[0] in topic_heads else ''
    if '接尾' in noun[1]:return ''
    # Do not read only the last part of a compound as the whole subject.
    if len(parts)>2 and parts[-3][4]==noun[3] and parts[-3][1].startswith(('名詞','接頭詞')):
        return ''
    return noun[0] if actual_ga or noun[0] in topic_heads else ''


@lru_cache(maxsize=4096)
def _subject_predicate_roles(surface,following):
    from morphology import tokenize,dictionary_inflections
    head=_action_head(surface,following[:8])
    if not head:return '',frozenset()
    # A voice-changing suffix changes which participant is nominative.
    parts=tokenize(surface+following[:12])
    if any(t.pos=='動詞' and t.pos_sub.startswith('接尾')
           and t.base_form in ('れる','られる','せる','させる') for t in parts):
        return '',frozenset()
    if head in SUBJECT_VERB_ROLES:
        return head,frozenset(SUBJECT_VERB_ROLES[head])
    # The actual auxiliary proves the verb inflection. Re-parsing 歩き or
    # 座り alone can turn that same continuative into a noun and lose it.
    first=parts[0]
    roles=native_verb_roles(first.surface,first.infl_form,first.reading,subject=True) if first.pos=='動詞' else frozenset()
    return head,roles


def subject_candidate_evidence(subject_word,surface,following):
    """Rank positive fits after detection; never reject unmatched natural senses."""
    nominal=nominal_roles(subject_word)
    if not nominal:return None
    head,predicate=_subject_predicate_roles(surface,following)
    if not head:return None
    return dict(version=KNOWLEDGE_VERSION,subject=subject_word,predicate=head,
                subject_roles=sorted(nominal),predicate_roles=sorted(predicate),
                shared_roles=sorted(nominal & predicate))


# 48-AAB / GPT-6 / 2026-09-11. Positive accusative use of the basic
# functional verbs already used by the grammar. This is a case-frame
# classification, not a selectional preference or a typo/answer list.
# Other predicates keep their existing analysis; absence is not rejection.
ACCUSATIVE_BASIC_LEMMA_READINGS=frozenset('する おく みる いう おもう つかう うる'.split())


# 48-AAK / GPT-6 / 2026-09-12. In grammatical descriptions these are
# coordinate inflectional categories (e.g. 性・数・格, 時制・相・法).
# Written concatenations can omit list punctuation. This classifies the
# terms, not typo/answer pairs. It supplies no new reading or candidate.
NOMINAL_COORDINATION_GROUPS=(frozenset('性 数 格 人称 時制 相 態 法'.split()),)


@lru_cache(maxsize=4096)
def is_nominal_coordination(text):
    """An entire written nominal list made of distinct members of one class."""
    if not text or not all('一'<=c<='鿿' for c in text):
        return False
    for words in NOMINAL_COORDINATION_GROUPS:
        paths=[(0,frozenset())]
        while paths:
            at,used=paths.pop()
            if at==len(text) and len(used)>=2:
                return True
            for word in words-used:
                if text.startswith(word,at):
                    paths.append((at+len(word),used|{word}))
    return False


# 48-ACE: related activity domains are separate from accusative object
# roles. Intransitive improvement/recovery need not acquire an object role
# merely to establish a natural sequence. AI judgment, GPT-6, 2026-09-13.
ACTION_DOMAIN_GROUPS=(
    # Native maritime activities share their original operational context.
    frozenset('用船 傭船 配船 操船 係船 出港 入港 寄港 航海 運航'.split()),
    frozenset('運動 補給 休憩 休息 休養'.split()),
    frozenset('訓練 上達 練習 学習 習得 復習 勉強 合格 研修 受講 受験'.split()),
)


def action_note_support(first, following):
    """Positive shared task/object roles for an abbreviated sequence of actions.

    Control predicates may qualify an established action. Device operations
    and information/text operations belong to the same ordinary workflow.
    Unknown roles do not prove a link and are not declared incompatible.
    """
    if any(first in domain and following in domain for domain in ACTION_DOMAIN_GROUPS):
        return True
    left,right=predicate_roles(first),predicate_roles(following)
    if first in ACTION_CONTROL_PREDICATES:
        return bool(right or following in ACTION_CONTROL_PREDICATES)
    if following in ACTION_CONTROL_PREDICATES:
        return bool(left)
    information=frozenset(('information','text','device'))
    return bool(left & right or (left & information and right & information))


# GPT-6 Astra: general operation modes and spatial operations. These are
# semantic classes for candidate compounds, never typo/answer pairs. The
# source is not anomalous merely because it is outside these small classes.
OPERATION_MODE_MODIFIERS=frozenset('簡易 簡単 詳細 自動 手動 半自動 高速 低速 並列 逐次 同時 個別 一括 連続 単独'.split())
SPATIAL_MODIFIERS=frozenset('右 左 上 下 前 後 双方向'.split())
SPATIAL_OPERATIONS=frozenset('移動 移設 回転 旋回 クリック ダブルクリック スクロール ドラッグ フリック'.split())



@lru_cache(maxsize=4096)
def retained_nominal_head_support(original,candidate):
    """A whole native noun can preserve the source's written nominal head.

    GPT-6 Astra / 2026-09-24: retaining the same head and its known meaning
    supports a compound reading over turning that head into particles.
    This ranks already validated candidates, never declares a source odd.
    Inflected verb fragments and guessed noun entries supply no evidence.
    """
    from morphology import tokenize,dictionary_inflections
    source=tokenize(original);changed=tokenize(candidate)
    if not source or len(changed)!=1:return False
    head=source[-1];word=changed[0]
    if (not head.has_reading or not word.has_reading or head.end!=len(original)
            or word.start!=0 or word.end!=len(candidate)
            or head.pos!='名詞' or word.pos!='名詞'
            or any(kind in t.pos_sub for t in (head,word)
                   for kind in ('固有名詞','非自立','接尾'))
            or not candidate.endswith(head.surface)):return False
    if not any(pos.startswith('名詞,') and base==candidate and rd==word.reading
               for pos,form,base,rd in dictionary_inflections(candidate) or ()):return False
    return bool(nominal_roles(head.surface) & nominal_roles(candidate))


def document_purpose_support(left,right):
    """An event/activity identifies its documents or recorded information."""
    return bool(nominal_roles(left) & {'process','event','communication_process'}
                and nominal_roles(right) & {'text','information'})


def interrogative_nominal_support(left,right):
    """An interrogative asks the value of an explicitly classified category."""
    return left in ('何','なに','なん') and 'interrogative_category_head' in nominal_roles(right)


@lru_cache(maxsize=4096)
def deverbal_nominal_support(left,right,reading=None):
    """A native action noun/suffix retains its verb's explicit object role."""
    from morphology import dictionary_inflections
    forms=dictionary_inflections(right) or ()
    nouns={rd for pos,form,base,rd in forms
           if pos.startswith(('名詞,一般,','名詞,接尾,一般,')) and base==right
           and (reading is None or rd==reading)}
    if not nouns:return False
    return any(nominal_role_matches(left,native_verb_roles(right,form,rd))
        for pos,form,base,rd in forms if pos.startswith('動詞,自立,')
        and form=='連用形' and rd in nouns)


@lru_cache(maxsize=4096)
def nominal_input_method_evidence(context,start,end,surface,reading):
    """A native input action is a means of an actual text-processing noun.

    This ranks an already validated candidate. The source must supply its
    own case/adnominal connection and preserve the action's written tail.
    """
    if not (0 <= start < end <= len(context) and context[end:].startswith('での')
            and surface != context[start:end]
            and context[start:end][-1:] == reading[-1:]):
        return None
    from reading_segments import native_case_adnominal_parts,native_deverbal_compound_parts
    changed=context[:start]+surface+context[end:]
    linked=[row for row in native_case_adnominal_parts(changed)
            if row[0]==start+len(surface) and row[1]==row[0]+2]
    if not linked:
        return None
    right=tuple(face for _,_,_,faces in linked for face in faces
                if 'process' in nominal_roles(face)
                and 'text' in VERB_ROLES.get(face,()))
    if not right:
        return None
    for cut,object_word,action in native_deverbal_compound_parts(reading):
        if surface != object_word+action:
            continue
        roles=native_verb_roles(action,'連用形',reading[cut:])
        if 'input_control' in roles and 'text' in roles:
            return dict(object=object_word,action=action,process=right[0],
                        reading=reading)
    return None


@lru_cache(maxsize=4096)
def nominal_compound_support(left,right):
    """Positive relation of two already identified nominal candidate parts."""
    from seed_japanese import is_unit
    from kango_tier import affinity
    if is_unit(left+right) is True or affinity(left,right)>0:return True
    if field_nominal_support(left,right):return True
    roles=nominal_roles(left);right_roles=nominal_roles(right)
    if (roles & {'process','event'} and right_roles & {'operation_mode','cancellation'}
            or roles & {'process','text','information'} and 'information_field' in right_roles
            or roles & {'process','event','state_change','medicine'} and 'effect' in right_roles
            or roles & {'object','device','place','body_part','presentation','visual_region'}
                and 'spatial_attribute' in right_roles):return True
    if 'literary_style' in roles and 'art_form' in nominal_roles(right):return True
    if right=='湯' and roles & {'infusion_material','spring_water_source'}:return True
    if right=='木' and 'hierarchy' in roles:return True
    if document_purpose_support(left,right):return True
    if roles & {'process','event','communication_process'} and 'outcome' in nominal_roles(right):return True
    if support(left,right) or deverbal_nominal_support(left,right):return True
    if 'pointing_device' in roles and right in SPATIAL_OPERATIONS:return True
    if 'input_control' in roles and right in ('ショートカット','ホットキー'):return True
    if left in SPATIAL_MODIFIERS and right in SPATIAL_OPERATIONS:return True
    return bool(left in OPERATION_MODE_MODIFIERS
                and (right in VERB_ROLES or right in ACTION_CONTROL_PREDICATES
                     or right in SPATIAL_OPERATIONS))


# 48-ACA / GPT-6 / 2026-09-13. Explicit AI judgment about ordinary senses:
# these are visible presentation surfaces; these actions describe the
# flourishing of a society, culture or trade. Their direct nominal compound
# is semantically incongruous. This is not a typo/answer or homophone table.
# Deliberate quotations and interrupted boundaries supply no such judgment.
VISUAL_PRESENTATION_NOUNS=frozenset(NOUN_GROUPS['presentation'])
SOCIAL_FLOURISHING_NOUNS=frozenset('繁栄 繁盛 繁昌 隆盛 興隆 隆昌'.split())


def conflicting_nominal_compounds(text,tokens):
    """Judge the original known-word relationship before any candidates exist.

    The left noun supplies the context and remains outside the repair span.
    A missing category is no evidence; quoted input/error examples retain
    their existing shared literal protection.
    """
    from literal_examples import protected_ranges,overlaps
    protected=None;out=[]
    for i,right in enumerate(tokens):
        if (right[0] not in SOCIAL_FLOURISHING_NOUNS or not right[5]
                or not right[1].startswith('名詞:サ変接続')):
            continue
        edge=right[3]
        for j in range(i-1,max(-1,i-5),-1):
            left=tokens[j]
            if (not left[5] or left[4]!=edge or not left[1].startswith('名詞')
                    or '固有名詞' in left[1]):
                break
            edge=left[3];context=text[edge:right[3]]
            if context not in VISUAL_PRESENTATION_NOUNS:continue
            if text[right[3]:right[4]]!=right[0]:continue
            if protected is None:protected=protected_ranges(text)
            if not overlaps(edge,right[4],protected):
                out.append((context,right[0],right[3],right[4]))
            break
    return out


# 48-ACI / GPT-6: event phases constrain clock-case interpretation.
# A time at which something starts is different from a duration through
# which it continues. Exact native verb forms are required for kana lemmas.
TEMPORAL_PHASES=(
    ('に から までに','開始 再開 開会 開幕 起動 始まる'),
    ('に までに','終了 完了 閉会 閉幕 停止 終わる'),
    ('に から まで','継続 進行 開催 実施 続く 進む'),
)


@lru_cache(maxsize=1)
def _native_temporal_verb_readings():
    from morphology import dictionary_inflections
    out={}
    for cases,words in TEMPORAL_PHASES:
        for word in words.split():
            for pos,form,base,rd in dictionary_inflections(word) or ():
                if pos.startswith('動詞,自立,') and form=='基本形' and base==word:
                    out.setdefault(rd,set()).update(cases.split())
    return {rd:frozenset(cases) for rd,cases in out.items()}


def temporal_case_support(surface,case,form=None,reading=None):
    if form is None:
        return any(case in cases.split() and surface in words.split()
                   for cases,words in TEMPORAL_PHASES)
    from morphology import dictionary_inflections
    for pos,inflection,base,rd in dictionary_inflections(surface) or ():
        if pos.startswith('動詞,自立,') and inflection==form and rd==reading:
            if any(case in cases.split() and base in words.split() for cases,words in TEMPORAL_PHASES):
                return True
            if surface==reading:
                for p,f,b,r in dictionary_inflections(base) or ():
                    if p.startswith('動詞,自立,') and f=='基本形' and b==base:
                        if case in _native_temporal_verb_readings().get(r,()):return True
    return False


@lru_cache(maxsize=2048)
def relative_method_evidence(surface,following):
    """48-AQK: an available means is the default reading of a bare method head.

    Only rank already validated repairs. Native potential verbs retain the
    method's action role; no original sentence is marked or rewritten here.
    The following head must come from this source field, not another column.
    """
    from morphology import tokenize,native_potential_origins
    from reading_segments import native_common_noun_faces
    head=following.strip()
    if not head:return None
    faces=(head,) if 'method' in nominal_roles(head) else (
        native_common_noun_faces(head) if all('ぁ'<=ch<='ゖ' or ch=='ー' for ch in head) else ())
    faces=tuple(face for face in faces if 'method' in nominal_roles(face))
    if not faces:return None
    parts=tokenize(surface)
    if len(parts)!=1 or parts[0].pos!='動詞' or parts[0].infl_form!='基本形':return None
    verb=parts[0]
    origins=native_potential_origins(verb.surface,verb.infl_form,verb.reading)
    if not origins:return None
    for face in faces:
        evidence=candidate_evidence(face,surface,'')
        if evidence and 'method' in evidence['shared_roles']:
            return dict(version=KNOWLEDGE_VERSION,relation='available_method',
                        head=face,potential_origins=origins)
    return None


def request_action_evidence(source,start,end,surface):
    """An explicit request normally asks for an action, not its ability.

    Rank validated candidates only. A native potential before te-kudasai
    stays available, but an ordinary action is the default interpretation.
    The same native request reading and form must survive in this field.
    """
    if not any(t in source for t in ('ください','下さい')):return None
    from contextual_repair import _source_clause_bounds
    from morphology import tokenize,native_potential_origins,dictionary_inflections
    from reading_segments import _native_request_tail
    lo,hi=_source_clause_bounds(source,start,end)
    original=source[lo:hi];changed=source[lo:start]+surface+source[end:hi]
    def request(text):
        parts=tokenize(text)
        while parts and (parts[-1].surface in ('。','!','?','！','？')
                          or parts[-1].pos=='助詞' and parts[-1].pos_sub=='終助詞'):
            parts.pop()
        legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in parts]
        if len(parts)<3 or not _native_request_tail(legacy):return None
        return parts[-3:]
    old=request(original);new=request(changed)
    if not old or not new:return None
    verb,link,tail=new
    if ((old[1].surface,old[2].reading,old[2].infl_form)!=(link.surface,tail.reading,tail.infl_form)
            or not (start-lo<old[1].start and old[0].end>start-lo)
            or verb.pos!='動詞' or verb.pos_sub!='自立' or not verb.has_reading
            or verb.end!=link.start):return None
    if native_potential_origins(verb.surface,verb.infl_form,verb.reading):return None
    if not any(pos.startswith('動詞,自立,') and form==verb.infl_form and rd==verb.reading
               for pos,form,base,rd in dictionary_inflections(verb.surface) or ()):return None
    return dict(version=KNOWLEDGE_VERSION,relation='requested_action',
                action=verb.base_form,request=tail.surface)


def modifier_candidate_evidence(context,start,surface,tokenize_fn):
    """SR-D / GPT-6, 2026-09-13: the actual preceding relative action.

    Reuse the existing positive object/action role table. A conjunction after
    the predicate does not prove that the following noun is its modified head.
    Missing classification remains neutral; this function never marks text odd.
    """
    from contextual_repair import _completed_predicate_token
    parts=[t for t in tokenize_fn(context) if t[4]<=start]
    if not parts or parts[-1][4]!=start or not _completed_predicate_token(parts[-1]):
        return None
    begin=len(parts)-1
    while begin>0 and parts[begin][1].startswith(('動詞','助動詞')):
        previous=parts[begin-1]
        if previous[4]!=parts[begin][3] or not previous[5]:break
        if previous[1].startswith(('動詞','助動詞')):begin-=1;continue
        if previous[1].startswith('名詞:サ変接続'):begin-=1
        break
    return candidate_evidence(surface,context[parts[begin][3]:start],'')


def interrupted_topic_evidence(source, frame):
    """48-AGK: closed discourse topics with an intervening attention noun.

    GPT-6 Astra, 2026-09-15; user-confirmed kana intrusion interpretation.
    This is a narrow editing policy for punctuated fragments, not a claim
    that every unfinished N-ni-ki-wa is ungrammatical. Any actual continuation
    remains possible unless an independent nominal subject/existence clause
    positively proves the informational topic. Unknown heads are untouched.
    """
    if (frame['case']!='に' or frame['topic']!='は'
            or frame['glyph'] not in ('気','き') or 'き' not in frame['readings']):
        return None
    roles=set().union(*(nominal_roles(face) for face in frame['head_faces']))
    if not roles.intersection(('text','information','presentation','writing_surface','input_control')):
        return None
    from contextual_repair import _source_clause_bounds
    _,context_end=_source_clause_bounds(source,frame['case_start'],frame['end'])
    tail=source[frame['end']:context_end]
    # A comma explicitly delimits a topic fragment. Bare unfinished input
    # waits for continuation; a real predicate after the comma also waits.
    reason='closed_topic' if tail.strip() in ('、',',') else None
    if reason is None:
        # Positive alternative structure, not absence from a predicate list:
        # an explicit native noun + が + existence predicate describes the
        # informational head. Do not consume adverbs or an attention verb.
        import re
        from morphology import dictionary_inflections
        from reading_segments import native_nominal_phrase_faces
        rest=tail.lstrip('、, ').rstrip('。.!！?？')
        match=re.fullmatch(r'(.{1,24})が(あります|ありません|ある|ない)',rest)
        if match:
            noun=match.group(1)
            faces=([noun] if any(pos.startswith('名詞,') and '固有名詞' not in pos
                    for pos,form,base,rd in dictionary_inflections(noun) or ()) else [])
            if all('ぁ'<=c<='ゖ' or c=='ー' for c in noun):
                faces+=list(native_nominal_phrase_faces(noun))
            if any(nominal_roles(face).intersection(('text','information','attribute')) for face in faces):
                reason='independent_information_subject'
    if reason:
        return dict(version=KNOWLEDGE_VERSION,kind=reason,head_roles=sorted(roles))
    return None


# GPT-6 Astra / 48-AGO / 2026-09-15. Productive suffixes that describe a
# whole utterance: impression, manner, method or affiliation. A native noun
# suffix entry alone (a building, tube, official etc.) does not license a
# finite clause as its host. These are grammatical uses, not typo targets.
_CLAUSE_SUFFIX_ROLES = {
    'impression': ('感','圧'),
    'manner': ('風','調','体'),
    'method': ('式','型'),
    'affiliation': ('系','派','流'),
}

def finite_clause_suffix(surface):
    """Positive native evidence for a suffix taking a complete utterance."""
    role=next((role for role,forms in _CLAUSE_SUFFIX_ROLES.items() if surface in forms),None)
    if role is None:return None
    from morphology import dictionary_inflections
    native=any(pos.startswith('名詞,接尾,一般,') for pos,form,base,rd
               in dictionary_inflections(surface) or ())
    # Productive pressure-to-act usage is a reviewed construction even when
    # the native dictionary lacks this standalone noun/suffix entry.
    if not native and surface!='圧':return None
    return dict(version=KNOWLEDGE_VERSION,role=role,
                evidence='native_suffix' if native else 'reviewed_productive_use')


# Positive nominal-host classes, reviewed separately from the clause uses
# above. Unclassified suffixes retain the existing conservative treatment.
# Dictionary suffix status is required by the caller; these words by
# themselves (including personal names) are not declared anomalous.
_NOMINAL_SUFFIX_ROLES = {
    'building': ('館','堂','舎'),
    'component': ('管','軸','弁'),
    'container': ('棺','箱','瓶','袋','筒'),
    'vessel': ('艦','船','艇'),
    'office': ('官','庁','局','署'),
    'publication': ('刊','版','誌'),
    'viewpoint': ('観',),
    'personal_title': ('関','君','嬢','氏','殿'),
}

def nominal_host_suffix(surface):
    """Classified noun-host use; absence gives no new anomaly evidence."""
    role=next((role for role,forms in _NOMINAL_SUFFIX_ROLES.items() if surface in forms),None)
    return dict(version=KNOWLEDGE_VERSION,role=role) if role else None


def finite_clause_addressee(parts, auxiliary_index):
    """A native greeting or interpersonal speech act can address a name."""
    i=auxiliary_index
    if i<2 or parts[i-2].end!=parts[i-1].start:return False
    if parts[i-2].pos=='感動詞':return True
    # GPT-6 Astra / 48-AGO: request, thanks, greeting and leave-taking.
    # These classify the original speech act, not a guessed corrected word.
    from morphology import native_suru_form
    return (parts[i-2].pos=='名詞' and parts[i-2].pos_sub=='サ変接続'
            and parts[i-2].surface in ('お願い','感謝','挨拶','失礼')
            and parts[i-1].pos=='動詞'
            and native_suru_form(parts[i-1].surface,parts[i-1].infl_form,parts[i-1].reading,False))


@lru_cache(maxsize=2048)
def _motion_tail_cannot_take_object(text,object_word):
    """A finite path motion cannot own an earlier textual/photographic object.

    This closes only the preceding predicate's object scope. Unknown objects,
    travel paths, relative clauses and transitive readings remain possible.
    """
    roles=nominal_roles(object_word)
    if not roles&_NON_PATH_CONTENT_ROLES or roles&_ROUTE_OBJECT_ROLES:return False
    from morphology import tokenize
    from contextual_repair import _finite_written_predicate,_source_clause_bounds
    # Only this source clause owns the motion. A later table field or
    # sentence cannot make its finite predicate look unfinished.
    _,end=_source_clause_bounds(text,0,0)
    text=text[:end].rstrip(' 。！？!?')
    parts=tokenize(text)
    if not parts or parts[0].start!=0:return False
    head=parts[0]
    if head.pos!='動詞' or head.pos_sub!='自立':
        # An explicit destination belongs to the following motion. Prove
        # all its own cases and finite tail before closing the earlier
        # object's scope; an unknown destination is not positive evidence.
        from reading_segments import native_written_relative_action
        proof=native_written_relative_action(text,allow_finite=True)
        if not proof:return False
        action=tokenize(proof[0]);head=action[0] if action else None
        if head is None:return False
        text=proof[0]
    if head.pos!='動詞' or head.pos_sub!='自立' or not head.has_reading:return False
    verbs=native_verb_lexemes(head.surface,head.infl_form,head.reading)
    if not verbs or not verbs<=_PATH_MOTION_ACTIONS:return False
    return _finite_written_predicate(text)
