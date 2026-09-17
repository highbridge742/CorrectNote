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
KNOWLEDGE_VERSION = '2026-09-16ab'

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


def adverbial_reading_needs_host(face,reading):
    return (face,reading) in DEPENDENT_TEMPORAL_READINGS | DEPENDENT_RHETORICAL_READINGS


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
CULINARY_VEGETABLES='玉葱 玉ねぎ タマネギ たまねぎ 人参 ニンジン にんじん 大根 ダイコン だいこん キャベツ 白菜 ピーマン じゃがいも ジャガイモ'.split()


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

NOUN_GROUPS={
 'presentation':'画面 タブ 表示面 描画面 プレビュー 表示'.split(),
 'information':'感想 見解 批評 論評 レビュー 意見 要望 提案 考え 方針 評価 判断 知識 経験 見識 日付 やり方 理由 原因 結果 意味 意図 事情 状況 状態 条件 仕様 設定 決定 手順 方法 概要 詳細 情報 内容 データ 記録 履歴 数値 値 住所 名前 氏名 番号 日時 時刻 時間 日程 予定 計画 事実'.split(),
 # Native writing systems are text arguments for input, reading and editing.
 # GPT-6 Astra: ordinary role classification; no intended correction pairs.
 # Explanations, reports and instructions can denote written content.
 'text':'言葉 表現 説明 解説 報告 案内 指示 回答 解答 文章 文 文字 文字列 単語 語句 書類 資料 書面 文書 見出し 注釈 目次 段落 本 書籍 新聞 雑誌 冊子 原稿 記事 報告書 説明書 手紙 メール 図 表 画像 写真 図面 ページ 頁 仮名 かな カナ 平仮名 ひらがな 片仮名 カタカナ 漢字 ローマ字 英字 数字 記号 点字'.split(),
 # 48-AJP / Astra: character systems can be conversion results, not
 # the owner/location to which a borrowed item is returned.
 'writing_system':'仮名 かな カナ 平仮名 ひらがな 片仮名 カタカナ 漢字 ローマ字 英字 数字 点字'.split(),
 'extent':'範囲 区間 部分 領域'.split(),
 # 48-AIK / GPT-6 Astra / 2026-09-16: the original position or state
 # is a return destination. This is not a person's identity (身元).
 'origin':'元 もと 元通り 元どおり もとどおり'.split(),
 'time':'日時 日付 日程 期日 日取り 時刻 時間 日 朝 夜 午前 午後'.split(),
 # Appointments and plans are not a duration lived through.
 'schedule':'日程 予定 計画 期日 日取り'.split(),
 # Native input actions can target written text or a physical input control.
 'input_control':'キー ボタン キーボード'.split(),
 'scent':'香り 匂い におい 臭い'.split(),
 'sound':'声 音 音声 音楽 音響 鳴き声 物音'.split(),
 'recording':'動画 映像 ビデオ 録画'.split(),
 # Calls are acts of communication as well as device names; no spelling pair.
 'call':'電話 通話 コール'.split(),
 # 48-AJY / GPT-6 Astra / 2026-09-16: channels of communication,
 # independent of the content object or the recipient. Positive roles
 # only; a device or an arbitrary text is not automatically a channel.
 # NINJAL Verb Handbook, くれる/行く: communication-medium sense.
 'communication_medium':'メール 電子メール 電話 手紙 はがき 葉書 電報 ファクス ファックス チャット'.split(),
 'light':'電気 電灯 明かり 灯り 照明 灯火'.split(),
 'reference':'辞書 辞典 事典 百科事典 索引 一覧 リファレンス'.split(),
 # 48-AKE / GPT-6 Astra / 2026-09-16: vessels receive their contents.
 # The same destination role preserves source readings; no typo pairs.
 'container':'鍋 フライパン 皿 お皿 茶碗 コップ カップ 瓶 壺 ボウル 封筒 包み 箱 袋 容器 倉庫 棚 引き出し 物置 冷蔵庫 冷凍庫 保管庫 保存先 フォルダ ディレクトリ ドライブ ディスク メモリ データベース'.split(),
 'writing_surface':'紙 用紙 ノート 手帳 帳面 便箋 メモ帳 白板 黒板 掲示板 紙面 頁 ページ 画面'.split(),
 # GPT-6 Astra: visual form, as distinct from the text being described.
 # Written glyphs can be drawn as visual forms (lettering), even when
 # their ordinary linguistic role is text. Adobe's own lettering tutorial:
 # https://blog.adobe.com/jp/publish/2021/04/20/cc-design-fresco-creative-relay-14-bechori
 'shape':'形 形状 輪郭 線 曲線 直線 円 丸 四角 三角 四角形 三角形 図形 模様 絵 イラスト 風景 字 文字 字形 字体 漢字 仮名 平仮名 片仮名 英字 数字 記号 ロゴ'.split(),
 # 48-AIQ / GPT-6 Astra / 2026-09-16: ordinary human referents.
 # Their custody/status does not change the existing person category.
 'person':'人質 捕虜 囚人 奴隷 受刑者 友達 友だち 官僚 議員 医師 看護師 警官 教員 職人 人 人物 本人 他人 大人 巨人 人員 社員 部員 学生 先生 友人 家族 客 子供 子ども 利用者 作者 担当者 選手'.split(),
 # Ordinary physical cleaning, including the body and tableware.
 'body_part':'手 顔 体 身体 足 頭 髪'.split(),
 # 48-AHS / GPT-6 Astra: ordinary writing and cleaning tools are physical
 # objects. Native reading/POS proof still owns each nominal interpretation.
 # A homophone such as 放棄 or 蜂起 does not inherit the tool's role.
 # 48-AIJ / GPT-6 Astra / 2026-09-16: plant material is a physical
 # object that can be washed, moved and arranged. This does not classify
 # every plant as edible or transfer its sense to a homophonic verb.
 'object':'植物 草花 草 花 葉 茎 根 芽 枝 苗 蓼 葱 韮 筆 筆ペン ボールペン 消しゴム 定規 刷毛 はけ ハケ 箒 ほうき ホウキ ブラシ 雑巾 ぞうきん ゾウキン 物 もの 布 布地 タオル ハンカチ 糸 紐 繊維 皿 お皿 食器 茶碗 コップ カップ 箸 鍋 フライパン 荷物 忘れ物 落とし物 遺失物 道具 部品 材料 机 椅子 家具 服 衣服 靴 鉛筆 用紙 箱 袋 容器 鍵 窓 扉 戸'.split(),
 # 48-AGU / GPT-6 Astra: expense amounts are settlement obligations,
 # distinct from tangible manufactured products. Exact native frames only.
 'expense':'交通費 旅費 宿泊費 出張費 経費 費用 料金 代金'.split(),
 'money':'金 お金 資金 財産 費用 料金 代金 寄付金'.split(),
 'representation_format':REPRESENTATION_FORMATS,
 'attribute':'構造 性質 特徴 色 重さ 長さ 大きさ 寸法 番号 名称 名前'.split()+REPRESENTATION_FORMATS,
 'event':'開業 開店 閉店 開校 卒業 入学 会議 会合 集会 大会 試合 競技 選挙 授業 講義 式 会見 行事 催し'.split(),
 'process':'料理 調理 食事 散歩 運動 練習 作業 仕事 処理 操作 計算 解析 検査 実験 調査 開発 印刷 通信 接続'.split(),
 # Spatial nominal heads remain locations inside Nの上/中等. Literal
 # kana うえ/した/なか have the same ordinary locative noun sense; native
 # noun/case proof is still required before these roles can certify a clause.
 # 48-AGQ / GPT-6 Astra: native locative demonstratives, positive case evidence.
 'place':'店 近く 付近 近所 辺り そば 脇 ここ そこ あそこ どこ 上 下 中 内 表面 周囲 周り 隅 奥 手前 うえ した なか 外 屋外 室内 庭 家 自宅 学校 図書館 会社 場所 会場 部屋 教室 会議室 席 座席 宿 施設 店舗 建物 公園 道路 道 山 海 川 空 星空'.split(),
 # 48-AHE / GPT-6 Astra: ordinary fruit senses and their attested native
 # spellings. Other homophones do not inherit these roles by reading alone.
 'food':'卵 玉子 林檎 リンゴ りんご 蜜柑 ミカン みかん 苺 イチゴ いちご バナナ 食事 料理 食品 食料 食糧 食べ物 ご飯 米 パン 肉 魚 野菜 果物 菓子 お菓子'.split()+CULINARY_VEGETABLES,
 'ingredient':'卵 玉子 米 肉 魚 野菜 果物'.split()+CULINARY_VEGETABLES,
 # GPT-6 Astra / 2026-09-15: ordinary drink nouns, positive argument evidence.
 'drink':'水 茶 お茶 紅茶 緑茶 麦茶 コーヒー 珈琲 ジュース 乳飲料 牛乳 飲料 飲み物 汁 スープ'.split(),
 'medicine':'薬 錠剤 カプセル'.split(),
 # 48-AIB / GPT-6 Astra / 2026-09-16: environmental exposure is an
 # ordinary object of avoidance. Positive roles only: avoiding moisture
 # does not mean reading/eating it; 裂く/裂ける do not inherit 避ける's role.
 'exposure':'湿気 多湿 高温 熱 日光 直射日光 雨 風 冷気'.split(),
 'issue':'問題 課題 難問 懸案 紛争 対立 不具合 障害 トラブル 疑問 謎 不明点 矛盾'.split()+DISORDER_NOUNS,
 'disorder':DISORDER_NOUNS,
 'device':'電話 キーボード マウス カメラ マイク モニター 機械 装置 機器 パソコン 端末 サーバー サーバ プリンター 印刷機 エンジン システム ソフト ソフトウェア アプリ'.split(),
}
# 48-ABU / GPT-6 / 2026-09-13: positive ordinary object/action fit.
# Used with exact native readings and actual inflection for clause composition.
# These roles do not declare other objects impossible (metaphor is still possible).
PREDICATE_GROUPS=(
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
 # GPT-6 Astra / 2026-09-14: ordinary use and transfer/request roles.
 ('information text object device reference money place ingredient','使う 用いる 利用 活用'),
 ('information text object food drink money device','くださる 下さる もらう 貰う いただく 頂く'),
 ('extent','保存 確認 選択 削除 表示 印刷 読む 書く 調べる'),
 ('information text sound','聞く 聴く'),
 ('scent object food drink','嗅ぐ'),
 ('information attribute money object text','得る 獲得'),
 ('information text object person device place event shape attribute','見る'),
 # Ordinary visual presentation and a gaze toward an object or place.
 ('information text sound object person shape presentation body_part','見せる'),
 ('place object person shape presentation','見上げる 見下ろす'),
 # GPT-6 Astra: ordinary comparison, collection and retrieval roles.
 # A word outside these positive categories remains unclassified.
 ('information text attribute object person device place food money event process','比べる 較べる 選ぶ'),
 ('information text object person money food device','集める 数える'),
 # 48-AJJ: gathering and settling have distinct ordinary objects.
 # 収拾 also has the literal gathering sense; do not force 資料を収拾
 # into a different spelling merely because 収集 is more familiar.
 ('information text object money','収集 蒐集 採集 収拾'),
 ('disorder','収拾 鎮める 収める'),
 ('information text object person device place','見つける'),
 ('information text process event person','覚える 学ぶ 思い出す'),
 ('information text reference','引く'),
 # Ordinary investigation, trials and temperature changes; no typo pairs.
 ('information text object person device place','調べる 確かめる 探す'),
 ('information text device process','試す'),
 ('food drink object','温める 暖める 冷やす 冷ます'),
 ('object food','干す 乾かす'),
 # 48-AIW: physical cutting, including food, cloth and paper.
 ('food object writing_surface body_part','切る 刻む 切り刻む'),
 ('text sound','続ける'),
 # 48-ACT / GPT-6 Astra / 2026-09-14: switching display/content is an
 # ordinary operation. Counterexamples: read paper, switch audio, not
 # eat a display. Unknown roles remain unknown; these are not typo pairs.
 ('information text presentation sound device','切り替える 切り換える'),
 # GPT-6 Astra / 2026-09-14: content/entity transformation, including its result.
 ('information text presentation attribute object device person place container','変える 替える 代える 変更 交換 置換 変換'),
 # 48-ACM / GPT-6: ordinary operations on a visual presentation surface.
 # This positive role evidence is used after a source meaning anomaly;
 # an unclassified word is not itself declared an anomalous source.
 ('presentation','表示 描画 更新 反映 切替 遷移 回転 拡大 縮小 分割 結合 合成 共有 録画 投影 投写 同期 調整 補正 設定 制御 固定 確認 検査 保存 印刷 撮影 接続 操作'),
 ('information text','反映'),
 ('expense money','精算 清算 支払 支払い 払う 支払う 払い戻す 返金'),
 ('information text','作成 補正 修正 編集 選択 削除 登録 検索 集計'),
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
 ('information text','入力 変更 送信 受信'),
 ('information text object food','保存'),
 ('information text','説明 解説 記述 表示 記録 報告 通知 伝達 提示 理解 把握 確認 検証 比較'),
 ('event process','説明 解説 記述 報告 通知 伝達 提示 案内'),
 ('information text event process','知らせる 伝える'),
 ('object device person event process','理解 把握 説明 解説'),
 ('text','印刷 出版 再版 製本 校正 校閲 添削 翻訳 朗読 音読 書写 転記'),
 # GPT-6 Astra: verification includes identity, presence and condition of
 # people and concrete things. This is not a license for unrelated actions.
 ('person object place device','確認 検証'),
 ('person','募集 採用 雇用 招待 招聘 招へい 救助'),
 # Opening access and releasing restraint have different arguments.
 # Kanjipedia: /kotoba/0000810400 (開放), /kotoba/0000817800 (解放).
 # No homophone/answer pair: the source conflict below uses only the
 # written predicate's physical-opening sense and an explicit person.
 ('person','解放 釈放 釈免'),
 ('object place','開放 開閉 開扉'),
 ('money object food text','寄付 寄附 寄贈 提供 贈与'),
 ('event','休会 閉会 開会 開催 棄権 欠席'),
 ('event process','中止 再開 継続 実施 開始 終了 続ける 始める 終える'),
 # Accusative place arguments describe a path, not a consumed object.
 ('place','歩く 走る 通る 散歩 通過 横断 登る 上る'),
 # 48-AIF / GPT-6 Astra / 2026-09-16: physical devices can be arranged,
 # transported and stored. This role does not license reading/eating them.
 ('object device text food','並べる 整列 整理 運搬 保管 収納'),
 ('object text money','貸す 借りる'),
 ('object text money food','渡す 返す 戻す 預ける'),
 ('object device text food','運ぶ 片付ける 仕舞う しまう 買う 売る'),
 # 48-AHE: a dictionary/reference or writing medium can be purchased;
 # stacking applies to physical sheets and repeated events/experience.
 ('reference writing_surface','買う'),
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
 ('object text presentation','開く 閉じる'),
 ('call','掛ける'),
 # GPT-6 Astra: physical openings (windows, doors, boxes), not text content.
 ('object','開ける 閉める'),
 # GPT-6 Astra: physical movement and operation of people/devices/items.
 ('object device person','動かす'),
 ('text information','読む 書く 書き直す'),
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
 ('drink medicine','飲む'),
 # 2026-09-14 / GPT-6 Astra: ordinary insertion/pouring. Positive fit only.
 ('object food drink information text','入れる'),
 # 2026-09-14 / GPT-6 Astra: creation of things/content/meals, and washing
 # physical items or ingredients. Food as a whole does not license washing:
 # a meal or confection is not classified as an ingredient by this evidence.
 ('object food text device information','作る'),
 ('object ingredient body_part','洗う'),
 ('medicine','服用'),
)
# GPT-6 Astra: the person addressed/consulted is a dative argument,
# distinct from the content heard, spoken or conveyed. Positive proof only.
CASE_PREDICATE_GROUPS=(
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
 ('に','container place writing_surface','置く'),
 ('に','place process event','行く 来る 向かう 出かける 出掛ける'),
 ('へ','place process event','行く 来る 向かう 出かける 出掛ける'),
 ('で','reference','調べる 探す 引く 確かめる 確認 比べる 較べる 学ぶ 覚える 選ぶ 見つける 思い出す'),
 # A meeting or event can supply the setting for communication and
 # distribution, independently of their explicit accusative object.
 ('で','place event','配る 配布 分配 説明 発表 報告 共有 確認 議論 相談 話す'),
 ('と','person','話す 会う 相談 確認 検証 調整 交渉 協議 会話 食事 作業 運動'),
 # 48-AJE / GPT-6 Astra, 2026-09-16: a person can accompany ordinary
 # intentional daily activities. This shares the actual comitative case;
 # it does not make people the accusative food/object of those verbs.
 ('と','person','食べる 食う 飲む 作る 調理 料理 試食 買う 選ぶ 運ぶ 歩く 走る 散歩 遊ぶ 旅行 買い物 読む 書く 練習 勉強 学習'),
 ('から','person','教わる 聞く 学ぶ 受け取る 借りる 受信 受領 伝授'),
 ('で','place','遊ぶ 働く 学ぶ 暮らす 泳ぐ 休む 待つ 走る 歩く 散歩 運動 食事 会議 作業 調理 料理 掃除 保存 確認 勉強 練習'),
 ('に','writing_surface','書く 描く 記す 写す 記入 入力 記載'),
 ('に','shape','描く 描写'),
 ('に','place','見える'),
 ('に','place','登る 上る'),
 ('に','person','見せる'),
 # A visual surface is also a target of projection/reflection, not just navigation.
 ('に','presentation','映る 映す 写る 投影 投写'),
 ('に','person','聞く 尋ねる 問う 話す 伝える 教える 渡す 返す 届ける 送る 会う 頼む 相談 質問 報告 説明 通知'),
 ('へ','person','伝える 渡す 返す 届ける 送る 連絡 報告 通知 送信 転送'),
)
CASE_VERB_ROLES={}
for case,roles,words in CASE_PREDICATE_GROUPS:
 for word in words.split():CASE_VERB_ROLES.setdefault(case,{}).setdefault(word,set()).update(roles.split())

NOUN_ROLES={}
for role,words in NOUN_GROUPS.items():
 for w in words:NOUN_ROLES.setdefault(w,set()).add(role)
VERB_ROLES={}
for roles,words in PREDICATE_GROUPS:
 for w in words.split():VERB_ROLES.setdefault(w,set()).update(roles.split())




@lru_cache(maxsize=4096)
def nominal_roles(surface):
    """Known senses plus a native adjective's productive attribute noun."""
    roles=frozenset(NOUN_ROLES.get(surface,()))
    # 48-AHP / GPT-6 Astra: an exact native counter names its counted
    # referent. 本 as a counter is not the independent noun 'book'.
    # Unclassified units give only quantity, not guessed object semantics.
    from reading_segments import native_counted_nominal_evidence
    counted=native_counted_nominal_evidence(surface)
    if counted:
        if any(not ordinal for unit,ordinal in counted):roles=roles | {'quantity'}
        for unit,ordinal in counted:
            roles=roles | {'冊':frozenset(('text','reference','object')),
                           '台':frozenset(('device','object')),
                           '人':frozenset(('person',))}.get(unit,frozenset())
    # 48-AGV / GPT-6 Astra: an independently classified native action
    # can also name a process. An attested two-noun object/action compound
    # inherits that role only when its original argument fits the action.
    from morphology import dictionary_inflections,tokenize
    if surface in VERB_ROLES and any(classified_nominal_action(surface,rd)
            for pos,form,base,rd in dictionary_inflections(surface) or ()):
        roles=roles | {'process'}
    if not roles and len(surface)>2:
        parts=tokenize(surface)
        if (len(parts)>=2 and all(t.has_reading and t.pos=='名詞'
                and not any(x in t.pos_sub for x in ('固有名詞','非自立')) for t in parts)
                and parts[0].start==0 and parts[-1].end==len(surface)
                and all(a.end==b.start for a,b in zip(parts,parts[1:]))
                and classified_nominal_action(parts[-1].surface,parts[-1].reading)
                and support(surface[:parts[-1].start],parts[-1].surface)):
            # 48-AIR: the actual object can itself be an already classified
            # compound (描画面). Keep its whole meaning, not its last token.
            roles=frozenset(('process',))
    if not roles and surface.endswith('まで'):
        from reading_segments import native_deictic_range
        if native_deictic_range(surface):return frozenset(('extent',))
    if not roles and surface.endswith('たち'):
        from reading_segments import native_plural_nominal_heads
        if native_plural_nominal_heads(surface):return frozenset(('person',))
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
    return (face,j) if nominal_roles(face) else None


def _token_object_before(context, start, tokenize):
    """Use an explicit を head across contiguous simple dative/location arguments."""
    parts,edge=_argument_prefix(context,start,tokenize)
    if not parts or parts[-1][4]!=edge:return ''
    i=len(parts)-1
    for _ in range(3):
        if i<1:return ''
        particle=parts[i];noun=parts[i-1]
        if (not particle[1].startswith('助詞:格助詞') or particle[4]!=edge
                or noun[4]!=particle[3] or not noun[5] or not noun[1].startswith('名詞')):
            return ''
        if particle[0]=='を':
            if '接尾' in noun[1] and i>=2:
                from reading_segments import nominalized_adjective_context
                head=parts[i-2]
                if nominalized_adjective_context(context,head[3],noun[4],lambda _:parts):
                    return context[head[3]:noun[4]]
            whole=_classified_argument_head(context,parts,i-1)
            if whole:return whole[0]
            return '' if '固有名詞' in noun[1] or '接尾' in noun[1] else noun[0]
        if particle[0] not in ('に','で','へ'):return ''
        # 別の述語や助詞を越えない。受け手・場所を表す既知の名詞句だけ。
        j=i-1
        while j>0 and i-j<4 and parts[j-1][4]==parts[j][3] and parts[j-1][5] and parts[j-1][1].startswith('名詞'):
            j-=1
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


def _token_case_argument_before(context,start,tokenize,through_object=False):
    """One explicit native common noun plus its actual non-accusative case."""
    parts,edge=_argument_prefix(context,start,tokenize)
    if through_object and len(parts)>=2:
        noun,particle=parts[-2:]
        if (particle[4]==edge and particle[0]=='を' and particle[5]
                and particle[1].startswith('助詞:格助詞') and noun[4]==particle[3]
                and noun[5] and noun[1].startswith('名詞')
                and not any(kind in noun[1] for kind in ('固有名詞','接尾','非自立'))):
            whole=_classified_argument_head(context,parts,len(parts)-2)
            begin=whole[1] if whole else len(parts)-2
            edge=parts[begin][3];parts=parts[:begin]
    if len(parts)<2:return None
    noun,particle=parts[-2:]
    if (particle[4]!=edge or particle[0] not in CASE_VERB_ROLES
            or not particle[1].startswith('助詞:格助詞') or noun[4]!=particle[3]
            or not noun[5] or not noun[1].startswith('名詞')
            or '固有名詞' in noun[1] or '接尾' in noun[1]):return None
    whole=_classified_argument_head(context,parts,len(parts)-2)
    if whole:return whole[0],particle[0]
    if len(parts)>2 and parts[-3][4]==noun[3] and parts[-3][1].startswith(('名詞','接頭詞')):
        return None
    return noun[0],particle[0]


@lru_cache(maxsize=4096)
def classified_nominal_action(surface, reading):
    """A native ordinary noun with an independently classified action use."""
    if surface not in VERB_ROLES:
        return False
    from morphology import dictionary_inflections
    return any(pos.startswith(('名詞,一般,','名詞,サ変接続,'))
               and base==surface and rd==reading
               for pos,form,base,rd in dictionary_inflections(surface) or ())


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
    return native_verb_roles(t.surface,t.infl_form,t.reading,case=case)


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


# GPT-6 Astra / 2026-09-15: a receiving auxiliary supplies the person
# who performs the action. This is positive case evidence, not an anomaly.
_BENEFACTIVE_AGENT_CASES={
    'に':frozenset(('もらう','貰う','いただく','頂く')),
    'から':frozenset(('もらう','貰う','いただく','頂く')),
}


@lru_cache(maxsize=4096)
def native_benefactive_case_roles(surface,form,reading,tail,case,before=''):
    if case not in _BENEFACTIVE_AGENT_CASES or not tail:return frozenset()
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
            or not aux.pos_sub.startswith('非自立')
            or aux.base_form not in _BENEFACTIVE_AGENT_CASES[case]):return frozenset()
    if not any(p.startswith('動詞,非自立,') and f==aux.infl_form and b==aux.base_form and rd==aux.reading
               for p,f,b,rd in dictionary_inflections(aux.surface) or ()):return frozenset()
    from contextual_repair import _modern_te_allowed,_allows_grammatical_tail,_productive_predicate,_completed_predicate_token
    last=parts[-1]
    if (not _completed_predicate_token((last.surface,last.pos+':'+last.pos_sub,last.reading,
                                       last.start,last.end,last.has_reading,last.infl_form))
            or _modern_te_allowed(head.surface,head.reading,link.surface) is not True
            or not _allows_grammatical_tail(dictionary_inflections(surface) or (),tail,reading,surface)
            or not _productive_predicate(surface+tail,surface,before=before)):return frozenset()
    return frozenset(('person',))


@lru_cache(maxsize=8192)
def native_verb_roles(surface, form, reading, subject=False, case=None, tail=None, before="", allow_open_tail=False):
    """Bind meaning and a supplied grammatical tail to the same native lemma.

    Without a tail, source role lookup retains its former lexical scope.
    With a tail, a homophone cannot lend its meaning to another verb's
    inflection (書く versus 嗅ぐ). The output never chooses these spellings.
    """
    from morphology import dictionary_inflections
    roster=CASE_VERB_ROLES.get(case,{}) if case is not None else (SUBJECT_VERB_ROLES if subject else VERB_ROLES)
    roles=set();lexemes=set()
    kana=surface==reading and all('ぁ'<=c<='ゖ' for c in surface)
    for pos,inflection,base,rd in dictionary_inflections(surface) or ():
        if not pos.startswith('動詞,自立,') or inflection!=form or rd!=reading:continue
        lexemes.add(base)
        if kana:
            for p,f,b,lemma_reading in dictionary_inflections(base) or ():
                if p.startswith('動詞,自立,') and f=='基本形' and b==base:
                    lexemes.update(_native_verb_reading_lexemes().get(lemma_reading,()))
    for lexeme in lexemes:
        known=roster.get(lexeme,())
        if not known:continue
        if tail is not None:
            from contextual_repair import _allows_grammatical_tail,_productive_predicate
            forms=_native_lexeme_forms(lexeme,form,reading) if kana else (surface,)
            from reading_segments import _native_open_predicate
            if not any((_allows_grammatical_tail(dictionary_inflections(face) or (),tail,reading,face)
                        or allow_open_tail and _native_open_predicate(face+tail,face,before))
                       and _productive_predicate(face+tail,face,before=before) for face in forms):continue
        roles.update(known)
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


def support(object_word, predicate):
    """Positive fit only: unclassified or other senses are not incompatibilities."""
    return bool(nominal_roles(object_word) & predicate_roles(predicate))


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
    if not following.startswith(('を',)+tuple(CASE_VERB_ROLES)):return None
    from morphology import tokenize
    end=len(before)+len(surface)
    parts=list(tokenize(before+surface+following))
    left=[t for t in parts if t.start<end and t.end>len(before)]
    right=[t for t in parts if t.start>=end]
    if (not left or left[0].start!=len(before) or left[-1].end!=end
            or not all(t.has_reading for t in left) or left[-1].pos!='名詞'
            or len(right)<2):return None
    case,head=right[:2]
    if (case.start!=end or case.surface not in ('を',)+tuple(CASE_VERB_ROLES) or not case.has_reading
            or case.pos!='助詞' or not case.pos_sub.startswith('格助詞')
            or head.start!=case.end or not head.has_reading):return None
    if all('ぁ'<=c<='ゖ' or c=='ー' for c in surface):
        from reading_segments import native_nominal_phrase_faces
        faces=native_nominal_phrase_faces(surface)
    else:faces=(surface,)
    suffix=(before+surface+following)[head.end:]
    evidence=[candidate_evidence(face,head.surface,suffix,before=before+surface+case.surface,
                                case=None if case.surface=='を' else case.surface)
              for face in faces if nominal_roles(face)]
    evidence=[row for row in evidence if row is not None]
    return max(evidence,key=lambda row:bool(row['shared_roles'])) if evidence else None


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
            if head.end!=case.start or head.pos!='名詞' or not head.has_reading:continue
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


def candidate_evidence(object_word, surface, following, before="", case=None):
    """Expose the source and roles used for ranking, including no-fit results."""
    faces=(object_word,)
    # 48-AJX: an unchanged kana accusative has the same native noun
    # readings as other cases. A best-parse kana spelling must not hide
    # its already attested roles from candidate ranking. Written nouns
    # retain their exact sense; unknown readings provide no evidence.
    if object_word and all('ぁ'<=c<='ゖ' or c=='ー' for c in object_word):
        from reading_segments import native_nominal_phrase_faces
        faces=native_nominal_phrase_faces(object_word)
    nominal=frozenset(role for face in faces for role in nominal_roles(face))
    if not nominal:return None
    head=_action_head(surface,following[:8],before)
    predicate=predicate_roles(head,following,before,case=case) if head else frozenset()
    # 48-AKB: a proved kana suru action has the same meaning as its
    # written native spelling. Share the completion proof here so a
    # best-parse fragment cannot rank its kanji counterpart above it.
    reading=(surface+following).rstrip('。！？.!?')
    if (not nominal & predicate and reading
            and all('ぁ'<=c<='ゖ' or c=='ー' for c in reading)):
        from reading_segments import completed_sahen_reading
        action=completed_sahen_reading(reading,allow_nonpolite=True,return_action=True,
            object_faces=tuple(faces) if case is None else None,
            case_argument=(case,tuple(faces)) if case is not None else None)
        if action:
            head=action
            predicate=predicate_roles(action,case=case)
    if not head:return None
    return dict(version=KNOWLEDGE_VERSION,object=object_word,predicate=head,case=case or 'を',
                object_roles=sorted(nominal),predicate_roles=sorted(predicate),
                shared_roles=sorted(nominal & predicate))



def genitive_nominal_support(left,right,*,nominalized_attribute=False):
    """Ordinary event/time and entity/attribute relations with an actual の."""
    a=nominal_roles(left);b=nominal_roles(right)
    if nominalized_attribute:b=b | {'attribute'}
    return bool(a & {'event','process'} and b & {'time','information','text'}
                or a and 'attribute' in b
                or 'person' in a and b & {'object','device','text'})


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
            roles=native_verb_roles(part.surface,part.infl_form,part.reading,
                subject=case=='が',case=None if case in ('を','が') else case)
            return bool(roles & nominal_roles(word))
        if part.pos=='名詞' and part.pos_sub.startswith('サ変接続'):
            following=rest[i+1] if i+1<len(rest) else None
            from morphology import native_suru_form
            native_suru=bool(following and following.pos=='動詞' and following.has_reading
                and native_suru_form(following.surface,following.infl_form,following.reading,False)
                and any(pos.startswith('動詞,') and base=='する' and form==following.infl_form
                        and rd==following.reading for pos,form,base,rd
                        in dictionary_inflections(following.surface) or ()))
            if nominalized or native_suru:
                return case_action_support(word,case,part.surface)
        if nominalized:break
    return False


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
    if particle=='が':return bool(nominal_roles(noun) & SUBJECT_VERB_ROLES.get(action,set()))
    if nominal_roles(noun) & predicate_roles(action,case=particle):
        return True
    if particle in ('は','も','しか'):
        return bool(support(noun,action) or
                    nominal_roles(noun) & SUBJECT_VERB_ROLES.get(action,set()))
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
    if not action or not all('ぁ'<=c<='ゖ' for c in action):return False
    from morphology import dictionary_inflections
    roles=set()
    for pos,form,base,rd in dictionary_inflections(action) or ():
        if pos.startswith('動詞,自立,') and rd==action:
            if particle in ('が','は','も','しか'):
                roles.update(native_verb_roles(action,form,rd,subject=True))
            if particle!='が':
                roles.update(native_verb_roles(action,form,rd,
                    case=None if particle in ('を','は','も','しか') else particle))
    # Preserve the completed clause's auxiliary when an outer case is
    # carried by receiving an action, not by the lexical verb alone.
    if context and particle in _BENEFACTIVE_AGENT_CASES:
        from morphology import tokenize
        heads=[t for t in tokenize(context) if t.surface==action and t.has_reading
               and t.pos=='動詞' and t.pos_sub.startswith('自立')]
        if len(heads)==1:
            head=heads[0]
            roles.update(native_benefactive_case_roles(head.surface,head.infl_form,head.reading,
                context[head.end:],particle,context[:head.start]))
    return bool(nominal_roles(noun) & roles)


def relative_action_support(noun, action, occupied_cases=()):
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
    return bool(nominal_roles(noun) & (roles | subject_roles) or
                'time' in nominal_roles(noun) and event_roles)


def candidate_support(object_word, surface, following):
    evidence=candidate_evidence(object_word,surface,following)
    return bool(evidence and evidence['shared_roles'])


# GPT-6 / 2026-09-11 / 48-YJ: 主体の生死・存在を述べる一項述語。
# 誤字と正解の対応表ではなく、直接の目的語を取らない語義の分類。
# 移動の経路、期間、他動詞の別義を持つ動詞は含めない。
SUBJECT_ONLY_PREDICATES = frozenset(
    '絶命 死亡 死去 逝去 急逝 他界 夭折 崩御 病死 餓死 溺死 戦死 '
    '誕生 生誕 実在 存在 死ぬ 亡くなる 生まれる'.split())


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
    text=text.lstrip('、, ').rstrip(' 。！？!?\t\r\n')
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
    return bool(_terminal_predicate_tail(text,legacy,finite.end,finite.infl_form)
                and _productive_predicate(tail,head.surface,before=before))


def _terminal_predicate_tail(text, tokens, edge, last_form, independent_next=False):
    """連体節・接続節を越えて後ろの述語へ係る「を」を誤って取らない。"""
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
        elif (independent_next and token[0] in ('て','で')
                and token[1].startswith('助詞:接続助詞') and token[5]):
            from contextual_repair import _modern_te_allowed
            previous=next((t for t in tokens if t[4]==token[3]),None)
            return bool(previous and previous[5] and previous[1].startswith('動詞')
                        and _modern_te_allowed(previous[0],previous[2],token[0]) is True
                        and _independent_accusative_clause(text[token[4]:]))
        elif token[1].startswith('助詞:終助詞'):
            edge = token[4]
        else:
            # 句点で終わった述語だけ。読点や閉じ括弧を文末と取り違えない。
            return finite() and token[0] in ('。', '！', '？', '!', '?')
    return finite() and not text[edge:].strip()


def _closed_object_predicate_spans(text, tokens, predicates=None):
    """実辞書の述語＋明示目的語＋文末を照合してから異様の範囲を返す。

    直前の目的語が、後ろの別の述語に係る読みを排除しない。
    使役、受身、補助動詞、引用、名詞修飾ではこの判定をしない。
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
            if bases and (predicates is None or bases <= predicates):
                lemma = sorted(bases)[0]
        if lemma is None or not _terminal_predicate_tail(text, tokens, edge, last_form, independent_next=True):
            continue
        obj = object_before(text, token[3], lambda _: tokens)
        if obj:
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
    return [row for row in rows if _OBJECT_CONFLICT_ROLES.get(row[1],frozenset()) & nominal_roles(row[0])
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
        if not any(a<end and start<b or a==b and start<=a<end for a,b in edits):continue
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
        if not fitting:return False
    return True


# GPT-6 / 2026-09-11 / 48-YO: positive nominative roles, not anomaly rules.
# These broad ordinary meanings are shared across spellings and conjugations.
# Unknown nouns, passive/causative frames, and ambiguous は topics give no claim.
SUBJECT_PREDICATE_GROUPS=(
 ('object person place shape presentation text body_part','見える'),
 ('information text time','分かる 判る 解る 合う 違う 伝わる'),
 ('issue','解決 解消 発生 生じる 起きる 残る'),
 ('person','参加 出席 欠席 到着 出発 入場 退場 説明 解説 報告 発言 質問 回答 応答 読む 書く 話す 働く 学ぶ 勉強 休憩 休息 遊ぶ 休む 待つ 走る 歩く 泳ぐ'),
 ('event process','開始 終了 中断 再開 継続 完了 進行 始まる 終わる 進む'),
 ('device','起動 稼働 動作 停止 故障'),
 ('text information','届く 残る 消える'),
 ('money','増える 減る 足りる 余る'),
)
SUBJECT_VERB_ROLES={}
for roles,words in SUBJECT_PREDICATE_GROUPS:
    for word in words.split():SUBJECT_VERB_ROLES.setdefault(word,set()).update(roles.split())


def subject_before(context,start,tokenize):
    """Only an adjacent, explicit が with a single known common nominal head."""
    parts=[t for t in tokenize(context) if t[4]<=start]
    if len(parts)<2:return ''
    noun,particle=parts[-2:]
    if (particle[4]!=start or particle[0]!='が'
            or not particle[1].startswith('助詞:格助詞') or noun[4]!=particle[3]
            or not noun[5] or not noun[1].startswith('名詞')
            or '固有名詞' in noun[1] or '接尾' in noun[1]):
        return ''
    # Do not read only the last part of a compound as the whole subject.
    if len(parts)>2 and parts[-3][4]==noun[3] and parts[-3][1].startswith(('名詞','接頭詞')):
        return ''
    return noun[0]


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
    first=tokenize(head)[0]
    roles=native_verb_roles(first.surface,first.infl_form,first.reading,subject=True) if first.pos=='動詞' else frozenset()
    return head,roles


def subject_candidate_evidence(subject_word,surface,following):
    """Rank positive fits after detection; never reject unmatched natural senses."""
    if subject_word not in NOUN_ROLES:return None
    head,predicate=_subject_predicate_roles(surface,following)
    if not head:return None
    nominal=frozenset(NOUN_ROLES[subject_word])
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


# 48-ABY / GPT-6 / 2026-09-13. Actions controlling the execution/order of
# another action. The lexical classes are independent of typo/answer pairs.
ACTION_CONTROL_PREDICATES=frozenset('優先 終了 開始 再開 中止 継続 完了'.split())


# 48-ACE: related activity domains are separate from accusative object
# roles. Intransitive improvement/recovery need not acquire an object role
# merely to establish a natural sequence. AI judgment, GPT-6, 2026-09-13.
ACTION_DOMAIN_GROUPS=(
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
def nominal_compound_support(left,right):
    """Positive relation of two already identified nominal candidate parts."""
    from seed_japanese import is_unit
    from kango_tier import affinity
    if is_unit(left+right) is True or affinity(left,right)>0:return True
    if support(left,right):return True
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
