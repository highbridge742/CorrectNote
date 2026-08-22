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

"""
アプリの設定（グローバルホットキーのオン/オフなど）の保存。

decisions.py / choices.py と同じ考え方で、実行時に生成される
JSON ファイルに控える。壊れていても起動を止めない。

既定値は「全てオン」。ユーザーが明示的に切ったときだけ記録する
（設定ファイルが無い・壊れている場合は、既定値＝オンで動く）。

**一時解除はここに保存しない。**
簡易入力ウィンドウからの「一時的に解除」は、その回の起動中だけ
効く措置であり、アプリを閉じれば元に戻る（app.py が持つ）。
ここに書いてしまうと次回起動時にも解除されたままになり、
「一時的」ではなくなる。
"""

import json
import os

# 画面レイアウトの選択肢と、画面に出す名前。
# メニューの表示もここを参照して、表記をばらけさせない。
LAYOUT_SPLIT = 'split'
LAYOUT_UNIFIED = 'unified'
LAYOUT_LABELS = {
    LAYOUT_SPLIT: '入力エリアと補正エリアを左右に並べる',
    LAYOUT_UNIFIED: '入力と補正をひとつのエリアにまとめる',
}
LAYOUT_CHOICES = tuple(LAYOUT_LABELS)

# 入力方式（かな打ち / ローマ字打ち）。
# 打ち間違いの検査方向がこれで変わる。かな打ちなら JIS かな配列の
# 隣接キー、ローマ字打ちなら QWERTY の隣接キーで「元の打鍵」を推測する
# （「ほ」と「ご」は、かな配列では遠いが、ローマ字では h/g の隣）。
INPUT_KANA = 'kana'
INPUT_ROMAJI = 'romaji'
INPUT_METHOD_LABELS = {
    INPUT_KANA: 'かな入力（JISかな配列で打つ）',
    INPUT_ROMAJI: 'ローマ字入力（QWERTYで打つ）',
}
INPUT_METHOD_CHOICES = tuple(INPUT_METHOD_LABELS)

DEFAULTS = {
    # Ctrl+Insert で簡易入力ウィンドウを開く
    'hotkey_insert_enabled': True,
    # Ctrl+Shift+- で簡易入力ウィンドウを開く
    'hotkey_minus_enabled': True,
    # 簡易入力ウィンドウに、呼び出したホットキーについての
    # 説明文を出すかどうか（一時解除ボタン自体は説明文とは別に常に出す）
    'show_quick_hint': True,
    # ダークモード。既定はオフ（既存の見た目を変えないため）
    'dark_mode': False,
    # 画面のレイアウト。
    #   'split'   入力エリアと補正エリアを左右に並べる（従来どおり・既定）
    #   'unified' 入力と補正をひとつのエリアにまとめる
    # 真偽値ではなく文字列なので、load() の bool 判定とは別に扱う。
    'layout': 'split',
    # 入力方式。既定はローマ字入力（2026-08-09 変更。うにさん指定）
    'input_method': 'romaji',
    # 入力方式を IME から自動判定する（Windowsのみ）。
    # 打鍵のたびに IME の変換モード（ローマ字/かな）を確かめ、
    # メニューの選択と補正の検査方向を自動で切り替える。
    # ペーストは判定できないので、その場合は現在の設定のまま。
    'input_method_auto': True,
    # 検索ダイアログのチェックボックス。
    # 一度設定したら、同じ検索中はもちろん、次にアプリを
    # 開き直したときも同じ条件で検索できるようにする
    # （実機からの要望。正規表現は既定でオンにする）。
    # OSのタイトルバーを隠す（Windows）。最上部の水色の枠
    # （アクセントカラーの帯）ごと無くしたい、といううにさんの
    # 指定で既定オン（2026-08-09）。表示メニューで戻せる。
    'hide_titlebar': True,
    # 紫の色付け（判断に迷った箇所 unsure）。あまり役に立って
    # いないとの指摘で、既定はオフ（2026-08-09）。
    'show_unsure': False,
    # 目に見えない空白（半角・全角・タブ）を見せる（項目48-IF・
    # うにさんの指定・2026-08-21「**デフォルトはオン**」）。
    'show_whitespace': True,
    'find_match_case': False,
    'find_whole_word': False,
    'find_regex': True,
    'find_wrap': True,
    # 語彙の一回きりの手入れ（活用の途中の形の使用実績の取り消し）を
    # 実施済みか。過去の自動学習が、編集のたびにメモ全文を再学習して
    # 使用回数を水増ししていた（2026-08-09 修正）。その名残で
    # 「分から」「使え」のような活用の断片が「使用実績のある語」に
    # なっており、補正の当て先として誤爆を量産するため、初回起動時に
    # 一度だけ count を実績なし（1）へ戻す。実施したらこの印を立て、
    # 二度は行わない（ユーザーが今後本当に使った実績を消さないため）。
    'vocab_repair_fragments_done': False,
    # 手入れの第2版。第1版は連用形（打ち・入れ）まで取り消す誤りが
    # あったため、基準を直した版（連用形は残す）で改めて一度だけ
    # 実施する。復元（vocabulary_restore.json）とあわせて app.py 参照。
    'vocab_repair_fragments_v2_done': False,
    # 統合表示のとき、補正をメモ欄へ自動で反映するか
    # （うにさんの指定・2026-08-10。既定はオン）。
    # 分割表示では補正欄が別にあるので、この設定は効かない。
    'unified_autofix': True,
    # 同梱の説明書を exe と同じフォルダへ書き出したか。
    # 真偽値ではなく**書き出したファイル名**を入れる。説明書の版が
    # 上がって名前が変われば、印と一致しなくなるので新しい版が
    # 書き出される（app.py の MANUAL_FILENAME / _extract_manual）。
    'manual_extracted': '',
}

# 古い設定ファイルからの読み替え。
# 以前は 2つ目のホットキーを「Ctrl+=」として 'equals' と呼んでいたが、
# JIS配列で実際に打つ組み合わせに合わせて 'minus'（Ctrl+Shift+-）に
# 改めた。既に「オフにする」と決めた人の意思を消さないよう、
# 古い名前で保存された値があればそのまま引き継ぐ。
_RENAMED = {
    'hotkey_equals_enabled': 'hotkey_minus_enabled',
}


class Settings:
    def __init__(self, path=None):
        self.path = path
        self.values = dict(DEFAULTS)
        if path and os.path.exists(path):
            self.load()

    def get(self, key):
        return self.values.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.values[key] = value

    def save(self, path=None):
        path = path or self.path
        if not path:
            return
        try:
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.values, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except Exception:
            pass    # 保存できなくても既定値で動くので致命的ではない

    def load(self, path=None):
        path = path or self.path
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return    # 壊れていても既定値のまま動く
        if not isinstance(data, dict):
            return
        # 先に古い名前を読む。同じファイルに新旧が両方あれば、
        # あとから読む新しい名前のほうが優先される。
        for old, new in _RENAMED.items():
            if old in data and isinstance(data[old], bool):
                self.values[new] = data[old]
        # 受け入れる値の一覧を持つ設定（真偽値ではないもの）。
        # ここに無い値が書かれていたら、既定値のまま動かす。
        allowed = {'layout': LAYOUT_CHOICES,
                   'input_method': INPUT_METHOD_CHOICES}

        for key, default in DEFAULTS.items():
            if key not in data:
                continue
            value = data[key]
            # 既定値と同じ型で、決められた値のときだけ受け入れる。
            # 壊れた・古い形式の値で動きが変わらないようにする。
            if isinstance(default, bool):
                if isinstance(value, bool):
                    self.values[key] = value
            elif key in allowed:
                if value in allowed[key]:
                    self.values[key] = value
            elif isinstance(default, str):
                # 決められた候補を持たない文字列の設定
                # （説明書を書き出した印など）。文字列でありさえ
                # すれば受け入れる。
                if isinstance(value, str):
                    self.values[key] = value


def active_hotkeys(settings):
    """
    設定から、実際に登録すべきホットキーの一覧を返す。

    戻り値: [(名前, 組み合わせの説明), ...] 例: [('insert', 'Ctrl+Insert')]
    ホットキー登録処理（hotkeys.py）とは独立して、
    「どれを有効にするか」の判断だけを切り出してある。
    tkinter や OS のフック抜きでテストできるようにするため。

    なお、ここが返すのは「設定として有効か」であって、
    その回の起動中だけの一時解除は含まない（app.py が重ねて判断する）。
    """
    out = []
    if settings.get('hotkey_insert_enabled'):
        out.append(('insert', 'Ctrl+Insert'))
    if settings.get('hotkey_minus_enabled'):
        out.append(('minus', 'Ctrl+Shift+-'))
    return out


def effective_hotkeys(settings, suspended=()):
    """
    設定と一時解除を重ねて、実際に登録すべき名前の集合を返す。

    suspended: この起動の間だけ解除されている名前の集まり。

    「設定でオン」かつ「一時解除されていない」ものだけが有効。
    判断をこの1箇所に集めておくと、画面（tkinter）抜きで
    検証できる。app.py 側はこの結果をそのまま登録に流すだけにする。
    """
    suspended = set(suspended or ())
    return {name for name, _label in active_hotkeys(settings)
            if name not in suspended}
