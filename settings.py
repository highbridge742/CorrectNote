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

MEMORY_LOW = 'low'
MEMORY_HIGH = 'high'
MEMORY_LABELS = {MEMORY_LOW: '低', MEMORY_HIGH: '高'}
MEMORY_CHOICES = tuple(MEMORY_LABELS)

DEFAULT_EDITOR_FONT = ('Yu Mincho', 10)
FONT_SIZE_MIN = 6
FONT_SIZE_MAX = 96


def editor_font(family, size):
    """保存値が壊れていても本文の字を使える範囲に保つ。"""
    if not isinstance(family, str) or not family.strip() or len(family) > 200:
        family = DEFAULT_EDITOR_FONT[0]
    if type(size) is not int or not FONT_SIZE_MIN <= size <= FONT_SIZE_MAX:
        size = DEFAULT_EDITOR_FONT[1]
    return family, size


# 2: 数詞を1.2倍・緑（とても明るい）、記号を黄（とても明るい）にした。
# 3: 名詞を1.1倍・緑（ごく明るい）、英字と記号をグレー（明るい）にし、
#    ライトモードの色を別に持つようにした（2026-10-13 うにさん）。
POS_FONT_DEFAULTS_VERSION = '3'
# 2: 印を一度オフにした（重かった）。3: Ctrl を押している間だけ出る下線に
# なったので、一度オンに戻した（2026-10-12 うにさん）。
CTRL_BOUNDARIES_DEFAULTS_VERSION = '3'


DEFAULTS = {
    # 高は先読みと解析子を保持。低は完了後の待機中に解放する。
    'memory_usage': MEMORY_HIGH,
    # Ctrl＋左右で止まる場所の印。Ctrl を押している間だけ出る（既定オン）。
    'show_ctrl_boundaries': True,
    # Ctrl＋左右の印をカーソルのある行だけに出す（既定オン）。オフで全行。
    # 以前の 'ctrl_boundaries_all_rows'（逆の意味）は load() で読み替える。
    'ctrl_boundaries_cursor_row_only': True,
    'toolbar_order': [],
    'toolbar_hidden': [],
    'recent_files': [],
    'wheel_inertia': True,
    'right_drag_inertia': True,
    'bulk_insert_text': '',
    'bulk_insert_direction': 'start',
    'bulk_insert_distance': '0',
    # Ctrl+Insert で簡易入力ウィンドウを開く
    'hotkey_insert_enabled': True,
    # Ctrl+Shift+- で簡易入力ウィンドウを開く
    'hotkey_minus_enabled': True,
    # 簡易入力ウィンドウに、呼び出したホットキーについての
    # 説明文を出すかどうか（一時解除ボタン自体は説明文とは別に常に出す）
    'show_quick_hint': True,
    'capslock_backspace_enabled': True,
    'insert_quote_enabled': True,
    # ダークモード。既定はオフ（既存の見た目を変えないため）
    'dark_mode': False,
    'editor_font_family': DEFAULT_EDITOR_FONT[0],
    'editor_font_size': DEFAULT_EDITOR_FONT[1],
    # 品詞ごとの表示倍率。本文と補正欄の文字サイズだけに使い、
    # 入力文字・補正結果・解析内容は変えない。
    'pos_font_multipliers': {
        '名詞': 1.1, '名詞（サ変）': 1.0, '数詞': 1.2, '英字': 1.0, '動詞': 1.1,
        '形容詞': 1.1, '形容動詞': 1.0,
        '副詞': 1.1, '連体詞': 1.0, '接続詞': 1.0, '感動詞': 1.0,
        '助詞': 1.0, '助動詞': 1.1, '接頭詞': 1.0, '記号': 1.0,
        'フィラー': 1.0, 'その他': 1.0,
    },
    # 品詞ごとの文字色（ダークモード）。空文字は色を変えない。書かれて
    # いない品詞は pos_font.POS_COLOR_DEFAULTS（名詞・数詞は緑、英字・
    # 記号はグレー）になる。
    'pos_font_colors': {},
    # ライトモードの文字色。別に持つ（2026-10-13 うにさん）。書かれて
    # いない品詞は pos_font.POS_COLOR_DEFAULTS_LIGHT（名詞は青緑など）。
    'pos_font_colors_light': {},
    # 品詞の初期値の版。これより古い設定ファイルは、初期値のままだった
    # 品詞だけ load() で新しい初期値へ移す。
    'pos_font_defaults': POS_FONT_DEFAULTS_VERSION,
    # Ctrl＋左右の印の初期値の版。これより古い設定ファイルは、印を一度
    # オフにする（それまでは既定オンで保存されていた）。
    'ctrl_boundaries_defaults': CTRL_BOUNDARIES_DEFAULTS_VERSION,
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
    # 不自然な文字列を紫で見せる（項目48-IZ・うにさんの指定・
    # 2026-08-23「**デフォルトオン**」）。
    #
    # **`show_unsure`（判断に迷った箇所）は無くした。** 直し方が
    # 決められないだけの箇所に色を付けても役に立たない、という
    # 指摘（2026-08-09）で既定オフのまま置いてあったもの。紫は
    # **異様さの印**（`oddness.py`）ひとつの意味に絞る。
    # 古い設定ファイルに `show_unsure` が残っていても、読む側が
    # 無いので黙って無視される。
    'show_odd': True,
    # 目に見えない空白（半角・全角・タブ）を見せる（項目48-IF・
    # うにさんの指定・2026-08-21「**デフォルトはオン**」）。
    'show_whitespace': True,
    # 補正候補の一番下に**品詞の判定**を出す（項目48-MD・
    # うにさんの指定・2026-08-31「**デフォルトオフ**」）。
    #
    #   「オンにすると、候補欄の一番下に『－ 品詞判定 －』の項目が
    #     増え、選択範囲の単語が何の品詞に判定されたかを書く。
    #     このメニューがオンになると、**まったく候補がない単語に
    #     対しても補正候補を出し**、その場合は『－ 品詞判定 －』の
    #     項目だけが見える」
    #
    # **なかなか進まない開発を分析するため**の窓（うにさんの言葉）。
    # 補正の答えには一切影響しない（画面に出す言葉だけ）。
    'show_pos_info': False,
    # 補正候補に**補正の根拠**を出す（項目48-MD・同じ指定。
    # 「メニューのさらにそのひとつ下」・**デフォルトオフ**）。
    # `show_pos_info` が入っていないと出す場所が無いので、
    # 画面側は品詞判定と一緒のときだけ並べる。
    'show_reason_info': False,
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
    # 簡易入力の欄の中へ、補正を自動で反映するか
    # （うにさんの指定・2026-08-30・項目48-LR）。
    # **既定はオン**（うにさんの指定・2026-08-30・項目48-LX。
    # 入れた当日は「書いている途中の文字が動く」ことを警戒して
    # オフで置いたが、実機で使って問題が無かったため既定を上げた）。
    # 統合表示の `unified_autofix` と揃う形。切りたい人は
    # 表示メニューの「簡易入力で、補正を自動で反映する」で外せる。
    'quick_autofix': True,
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
        # 「すべての行に示す」は「カーソルのある行だけ」に反転した（2026-10-12）。
        if isinstance(data.get('ctrl_boundaries_all_rows'), bool):
            self.values['ctrl_boundaries_cursor_row_only'] = not data['ctrl_boundaries_all_rows']
        # 受け入れる値の一覧を持つ設定（真偽値ではないもの）。
        # ここに無い値が書かれていたら、既定値のまま動かす。
        allowed = {'layout': LAYOUT_CHOICES,
                   'input_method': INPUT_METHOD_CHOICES,
                   'memory_usage': MEMORY_CHOICES}

        for key, default in DEFAULTS.items():
            if key not in data:
                continue
            value = data[key]
            # 既定値と同じ型で、決められた値のときだけ受け入れる。
            # 壊れた・古い形式の値で動きが変わらないようにする。
            if isinstance(default, bool):
                if isinstance(value, bool):
                    self.values[key] = value
            elif key in ('toolbar_order', 'toolbar_hidden'):
                if isinstance(value, list):
                    self.values[key] = [item for item in value if isinstance(item, str)][:100]
            elif key == 'recent_files':
                from recent_files import normalized
                self.values[key] = normalized(value)
            elif key == 'editor_font_family':
                self.values[key] = editor_font(value, DEFAULT_EDITOR_FONT[1])[0]
            elif key == 'editor_font_size':
                self.values[key] = editor_font(DEFAULT_EDITOR_FONT[0], value)[1]
            elif key == 'pos_font_multipliers':
                from pos_font import normalize_multipliers
                self.values[key] = normalize_multipliers(value)
            elif key in ('pos_font_colors', 'pos_font_colors_light'):
                from pos_font import normalize_colors
                self.values[key] = normalize_colors(
                    value, key == 'pos_font_colors')
            elif key in allowed:
                if value in allowed[key]:
                    self.values[key] = value
            elif key in ('pos_font_defaults', 'ctrl_boundaries_defaults'):
                continue    # 下で古い初期値を移してから新しい版にする
            elif isinstance(default, str):
                # 決められた候補を持たない文字列の設定
                # （説明書を書き出した印など）。文字列でありさえ
                # すれば受け入れる。
                if isinstance(value, str):
                    self.values[key] = value
        if data.get('pos_font_defaults') != POS_FONT_DEFAULTS_VERSION:
            _move_to_new_pos_defaults(self.values, data)
        if data.get('ctrl_boundaries_defaults') != CTRL_BOUNDARIES_DEFAULTS_VERSION:
            # 印は Ctrl を押している間だけになったので一度オンにする
            # （2026-10-12 うにさん）。あとでオフにした人の設定は、新しい
            # 版で保存されるのでそのまま残る。
            self.values['show_ctrl_boundaries'] = True
            self.values['ctrl_boundaries_defaults'] = CTRL_BOUNDARIES_DEFAULTS_VERSION


def _move_to_new_pos_defaults(values, data):
    """古い版の初期値のままだった品詞だけ、今の初期値にする。

    版1では数詞が1.0倍、文字色はすべて空（変えない）だった。
    版2では名詞が1.0倍・色なし、記号が黄（とても明るい）、英字が色なし
    で、ライトモードの色はダークの色の濃さを反転して出していた。
    利用者が選び直した値はそのまま残す（ライトでは反転した色として）。"""
    from pos_font import (POS_FONT_DEFAULTS, POS_COLOR_DEFAULTS,
                          POS_COLOR_DEFAULTS_LIGHT, POS_CATEGORIES,
                          normalize_colors, palette_color, display_color)
    version = data.get('pos_font_defaults')
    multipliers = dict(values.get('pos_font_multipliers') or {})
    old_colors = {key: '' for key in POS_CATEGORIES}
    if version == '2':
        old_colors.update({'数詞': palette_color('緑', 'とても明るい'),
                           '記号': palette_color('黄', 'とても明るい')})
    else:
        if multipliers.get('数詞') == 1.0:
            multipliers['数詞'] = POS_FONT_DEFAULTS['数詞']
    if multipliers.get('名詞') == 1.0:
        multipliers['名詞'] = POS_FONT_DEFAULTS['名詞']
    values['pos_font_multipliers'] = multipliers
    saved = data.get('pos_font_colors')
    saved = saved if isinstance(saved, dict) else {}
    colors = normalize_colors(saved)
    light = normalize_colors(None, False)
    for key in POS_CATEGORIES:
        if key not in saved or colors[key] == old_colors[key]:
            colors[key] = POS_COLOR_DEFAULTS[key]
        elif colors[key] == POS_COLOR_DEFAULTS[key]:
            # 選んであった色が新しいダークの初期値と同じなら、ライトも
            # 新しい初期値にする（うにさんの設定は名詞＝緑・ごく明るい、
            # 英字・記号＝グレー・明るいを選んであり、反転だと名詞が
            # 緑・濃い、英字・記号がグレー・中間になってしまう）。
            pass
        else:
            # 選び直してあった色。ライトでは今まで見えていた色のまま。
            light[key] = display_color(colors[key], False)
    values['pos_font_colors'] = colors
    if not isinstance(data.get('pos_font_colors_light'), dict):
        values['pos_font_colors_light'] = light
    values['pos_font_defaults'] = POS_FONT_DEFAULTS_VERSION


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
