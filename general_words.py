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

**この表は「書かれた語を認識する」側にだけ使う。**
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

VERSION = 3  # 48-ACB / GPT-6 / 2026-09-13

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
    'アソート': ('あそーと', '一般', 'godiva', ('product',)),
    'アソートメント': ('あそーとめんと', '一般', 'godiva_assortment', ('product',)),
    'マイバッグ': ('まいばっぐ', '一般', 'mybag', ('product',)),
    '爽健美茶': ('そうけんびちゃ', '固有名詞:一般', 'sokenbicha', ('product', 'beverage')),
    '綾鷹': ('あやたか', '固有名詞:一般', 'ayataka', ('product', 'beverage')),
    '伊右衛門': ('いえもん', '固有名詞:一般', 'iyemon', ('product', 'beverage')),
    '特茶': ('とくちゃ', '固有名詞:一般', 'tokucha', ('product', 'beverage')),
}

GENERAL_WORDS = (frozenset(_FROM_MEMO) | frozenset(_AI_PICKED)
                 | frozenset(w for w,entry in EXACT_NOUNS.items()
                             if entry[1]=='一般'))


def attested_noun(word, reading=None):
    """Exact written-word evidence only; never a substring/approximate match."""
    entry=EXACT_NOUNS.get(word)
    return entry if entry and (reading is None or reading==entry[0]) else None


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
