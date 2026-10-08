# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
**辞書に無いが、一般的な語**（AI が焼いた表・項目48-JG・2026-08-25）。

同梱の解析辞書（IPAdic・2007年ごろの語彙）には、現代のメモでごく普通に
出る語が入っていない。「辞書に無い断片が内容語に直付き＝異様」の印
（`oddness.is_odd_run`）を開けたとき、実機メモで立った誤爆は**全部この型**
だった（アプリ 19件・アイコン・ガター・バフ・オンオフ——どれも正しい行）。

**GENERAL_WORDS / EXACT_NOUNS は「書かれた語を認識する」側にだけ使う。**
版4の SOURCED_COMMON_NOUNS は外部辞書・公式用例で確認した普通名詞の完全な読みを
共通の読み検算へ渡す別の証拠。native辞書の行と同表記の既知の人名・地名の読みを維持する。
版6では、未読の名詞範囲に完全一致する一意の外部読み・品詞だけを解析へ共有する。単語の正解対や部分一致ではない。
版3では、完全一致する名詞の読み・品詞と、商品種別との同格を解析側へ渡す。商品名は一般語とは
別に型を持ち、かなから商品名へ寄せる候補名簿にはしない。語の途中からは
取り出さず、周囲の誤字や文法まで正しいとは判定しない。 載せ過ぎの害は
「印が立たない」だけ（直しは動かない）なので、48-ID の「載せ漏れは無害・
載せ過ぎだけが危ない」とは向きが逆——**確実に一般的な語だけを、
AI の判断で焼く**（うにさんの指定 2026-08-24「AI の判断を、表を作るときに
使ってよい」）。

**版つき**（48-IQ の形）。足すときは版を上げ、出どころを書く。
    版1  2026-08-25  実機メモの誤爆5語＋AI の判断で現代の一般語を選定
"""

VERSION = 17  # 2026-10-04; shared externally attested action POS

# 実機メモで実際に誤爆した5語（2026-08-25・probe_odd_fragments）
_FROM_MEMO = (
    'アプリ', 'アイコン', 'ガター', 'バフ', 'オンオフ',
)

# AI の判断で足した現代の一般語（IPAdic に無い・メモに出やすいもの）。
# 判断の基準: PC・スマホの操作の話で普通に使う／略語として定着している。
_AI_PICKED = (
    'スマホ', 'タブレット', 'タップ', 'スワイプ', 'フリック', 'ピンチ',
    'クリップボード', 'スクショ', 'スクリーンショット', 'ダウンロード',
    'アップロード', 'アップデート', 'インストーラ', 'ブラウザ', 'サイト',
    'リンク', 'ログ', 'バグ', 'デバッグ', 'リリース', 'バージョン',
    'フォルダ', 'ファイラ', 'ツールバー', 'サイドバー', 'ステータスバー',
    'ダイアログ', 'ポップアップ', 'ツールチップ', 'プルダウン', 'チェックボックス',
    'ラジオボタン', 'ショートカット', 'ホットキー', 'テンキー', 'バックスペース',
    'オートセーブ', 'プレビュー', 'ダークモード', 'ライトモード', 'フォント',
    'レイアウト', 'ペイン', 'ウィジェット', 'モーダル', 'フォーカス',
    'カーソル', 'キーボード', 'キーワード', 'ブックマーク', 'コピペ',
)

# 48-ABW: exact lexical facts, independently of an input/repair pair.
# AI judgment: these ordinary retail nouns and established names are natural
# in shopping notes. Proper names are NOT added to the ordinary-word roster.
# Official spelling sources checked 2026-09-13. Kana readings are GPT-6's
# lexical judgment (SOKENBICHA / AYATAKA / IYEMON / TOKUCHA also appear in the
# manufacturers' brand names/URLs). These are not native IPAdic entries.
SOURCES = {
    'click_microsoft': 'https://learn.microsoft.com/ja-jp/windows/win32/uxguide/inter-mouse',
    'roast_agf': 'https://agf.ajinomoto.co.jp/support/faq_detail.html?category=4&id=231&page=1',
    'hake_asahipen': 'https://asahipen.jp/howto/tosou_how.html',
    'betsugo_dictionary': 'https://kotobank.jp/word/別語-379122',
    'pragmatics_cinii': 'https://cir.nii.ac.jp/crid/1970867909787941888',
    'pragmatics_society': 'https://pragmatics.gr.jp/society_info/rules.html',
    'undo_dictionary': 'https://kotobank.jp/word/あんどう-3206998',
    'dispatcher_microsoft': 'https://learn.microsoft.com/ja-jp/dotnet/desktop/wpf/advanced/threading-model',
    'pokemon': 'https://corporate.pokemon.co.jp/produce/',
    'web_dictionary': 'https://kotobank.jp/word/うえぶ-3207568',
    'play_dictionary': 'https://kotobank.jp/word/ぷれー-3218017',
    'preste_dictionary': 'https://kotobank.jp/word/ぷれすて-3168567',
    'shashi_dictionary': 'https://kotobank.jp/word/謝詞-2048137',
    'projection_dictionary': 'https://kotobank.jp/word/ぷろじえくしよん-3221935',
    'solution_ninjal': 'https://www2.ninjal.ac.jp/gairaigo/Teian1_4/Words/solution.gen.html',
    'waei_dictionary': 'https://kotobank.jp/word/和英-664476',
    'yakutai_dictionary': 'https://kotobank.jp/word/薬袋-647918',
    'godiva': 'https://www.godiva.co.jp/news/news20250408_1.html',
    'godiva_assortment': 'https://www.godiva.co.jp/items/patisseries.html',
    'mybag': 'https://www.env.go.jp/recycle/yoki/campaign/introduction03.html',
    'sokenbicha': 'https://www.coca-cola.com/jp/ja/brands/sokenbicha',
    'ayataka': 'https://www.coca-cola.com/jp/ja/brands/ayataka',
    'iyemon': 'https://www.suntory.co.jp/softdrink/iyemon/index.html',
    'tokucha': 'https://www.suntory.co.jp/customer/faq/foshu/tokucha/',
}
# surface -> (reading, nominal subtype, source key, semantic categories)
EXACT_NOUNS = {
    # Independent lexical/bibliographic evidence, not a malformed input pair.
    # NII's book record attests 語用論 / ゴヨウロン. The society's rule 1
    # gives its official name; NII AA11860505 gives ニホン ゴヨウロン ガッカイ.
    '語用論': ('ごようろん', '一般', 'pragmatics_cinii', ()),
    '日本語用論学会': ('にほんごようろんがっかい', '固有名詞:組織', 'pragmatics_society', ()),
    'ポケモン': ('ぽけもん', '固有名詞:一般', 'pokemon', ()),
    'アソート': ('あそーと', '一般', 'godiva', ('product',)),
    'アソートメント': ('あそーとめんと', '一般', 'godiva_assortment', ('product',)),
    'マイバッグ': ('まいばっぐ', '一般', 'mybag', ('product',)),
    '爽健美茶': ('そうけんびちゃ', '固有名詞:一般', 'sokenbicha', ('product', 'beverage')),
    '綾鷹': ('あやたか', '固有名詞:一般', 'ayataka', ('product', 'beverage')),
    '伊右衛門': ('いえもん', '固有名詞:一般', 'iyemon', ('product', 'beverage')),
    '特茶': ('とくちゃ', '固有名詞:一般', 'tokucha', ('product', 'beverage')),
}

# 48-AMI / GPT-6 Astra / 2026-09-20. Shogakukan Daijisen and
# Seisen Nikkoku explicitly attest these whole ordinary noun readings.
# A proper-name entry in IPADIC is neither replaced nor borrowed as proof.
# Semantic roles remain in semantic_roles; existing product facts stay
# in EXACT_NOUNS. Only unambiguous whole unread nouns use this map in analysis.
SOURCED_COMMON_NOUNS = {
    # Microsoft names the mouse action and explicitly uses クリックする.
    # Same native reading; a lexical POS fact, not a malformed input pair.
    'クリック': (('くりっく','click_microsoft','サ変接続'),),
    # AGF's technical description attests the complete action noun and
    # 焙煎する. Reading is ordinary lexical knowledge, not an input pair.
    '焙煎': (('ばいせん','roast_agf','サ変接続'),),
    # Ordinary tool noun; manufacturer usage and explicit user spelling.
    'ハケ': (('はけ', 'hake_asahipen'),),
    # Seisen Nikkoku: a different expression/wording, an exact whole noun.
    '別語': (('べつご', 'betsugo_dictionary'),),
    # Microsoft WPF documentation: a complete ordinary technical noun.
    'ディスパッチャー': (('でぃすぱっちゃー', 'dispatcher_microsoft'),),
    # Daijisen: reverting an operation. Exact noun reading; suru usage is
    # ordinary Japanese lexical judgment, not a synthesized IPAdic entry.
    'アンドゥ': (('あんどぅ', 'undo_dictionary', 'サ変接続'),),
    # Seisen Nikkoku: an ordinary information-system noun with this exact reading.
    'ウェブ': (('うぇぶ', 'web_dictionary'),),
    # Daijisen explicitly attests the プレイ variant and its noun + する use.
    'プレイ': (('ぷれい', 'play_dictionary', 'サ変接続'),),
    # Daijisen records the complete lexical abbreviation, not a repair pair.
    'プレステ': (('ぷれすて', 'preste_dictionary'),),
    # Seisen Nikkoku / Jitsu: a noun for words of thanks, not a typo.
    '謝詞': (('しゃし', 'shashi_dictionary'),),
    # Dictionary noun/reading evidence, independent of malformed input.
    # Projection: Shogakukan Seisen Nikkoku, noun; solution: NINJAL's
    # attested nominal use. No semantic roles or usage tiers are added.
    'プロジェクション': (('ぷろじぇくしょん', 'projection_dictionary'),),
    'ソリューション': (('そりゅーしょん', 'solution_ninjal'),),
    '和英': (('わえい', 'waei_dictionary'),),
    '薬袋': (('やくたい', 'yakutai_dictionary'),
             ('くすりぶくろ', 'yakutai_dictionary')),
}


def sourced_common_noun_evidence(surface, reading=None):
    """Exact external common-noun facts with inspectable provenance.

    This supplies possible lexical senses, not a chosen interpretation,
    anomaly judgment, replacement spelling or synthesized native row.
    """
    return tuple(dict(surface=surface,reading=item[0],
                      pos='名詞,'+(item[2] if len(item)==3 else '一般')+',*,*',
                      version=VERSION,source=SOURCES[item[1]])
                 for item in SOURCED_COMMON_NOUNS.get(surface,())
                 if reading is None or reading==item[0])


def sourced_sahen_noun(surface,reading):
    """Exact external noun + suru evidence; not a synthesized native row."""
    return any(entry['pos'].startswith('名詞,サ変接続,')
               for entry in sourced_common_noun_evidence(surface,reading))


# Attested expressions are source evidence only, not native noun rows or
# replacement candidates. TUFS records the anger expression in actual usage.
SOURCED_EXPRESSIONS = {
    'まじおこ': 'https://www.tufs.ac.jp/blog/ts/p/tanana/2013/04/post_504.html',
}


GENERAL_WORDS = (frozenset(_FROM_MEMO) | frozenset(_AI_PICKED)
                 | frozenset(w for w,entry in EXACT_NOUNS.items()
                             if entry[1]=='一般'))


def attested_noun(word, reading=None):
    """Exact written-word evidence only; never a substring/approximate match."""
    entry=EXACT_NOUNS.get(word)
    return entry if entry and (reading is None or reading==entry[0]) else None


def general_katakana_noun_reading(surface, reading):
    """Exact kana reading of the existing, reviewed ordinary-word roster.

    48-ANS / GPT-6 Astra / 2026-09-20. The roster is unchanged; spelling
    directly attests this kana reading. No cost-table entry, product proper
    name, user vocabulary or substring becomes ordinary-noun evidence.
    Icon's common-noun sense was also checked against Shogakukan:
    https://kotobank.jp/word/あいこん-3140184
    """
    return bool(surface in GENERAL_WORDS and surface
                and all('ァ'<=char<='ヶ' or char=='ー' for char in surface)
                and ''.join(chr(ord(char)-0x60) if 'ァ'<=char<='ヶ' else char
                            for char in surface)==reading)


def is_general(word):
    """その語は、辞書に無くても一般的といえるか。"""
    return word in GENERAL_WORDS


# 48-ACB: the cited lexical entry also states possible product membership.
# A category label followed by a matching name is ordinary apposition;
# this does not license unrelated noun/name pairs or assert that every use
# of an ambiguous name (e.g. 伊右衛門) is a beverage.
CATEGORY_LABELS={
    'product':frozenset('商品 製品 品物 銘柄 ブランド'.split()),
    'beverage':frozenset('飲料 清涼飲料 飲み物 お茶 茶'.split()),
}


def attested_apposition(label,name):
    entry=attested_noun(name)
    return bool(entry and any(label in CATEGORY_LABELS.get(category,())
                             for category in entry[3]))
