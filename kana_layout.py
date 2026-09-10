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
かな入力（JIS配列）のキー物理配置と、隣接キー誤打の距離計算。

かな入力ではキーに直接ひらがなが割り当てられているため、
指が隣のキーにずれると「文字入力(もじにゅうりょく)」が
「もぱなゃうりゅき」のような別のかな列になる。

このモジュールは、あるかな文字に対して
「押し間違えた可能性のある文字」を距離付きで列挙する。
"""

import functools
import math
import os

# --- 測るための入り／切り（項目48-FX）---
# **既定はどちらも入り。** 版どうしを比べるときに、
# どの部分がどの数字を動かしたのかを1つずつ確かめられるようにする
# （`CORRECTNOTE_D18` などと同じ形）。
#
#   CN_MARK_TWO_STROKE  濁点・半濁点を2打鍵として数える
#                       （ベースも印も違うなら2回の誤り＝遠い）
#   CN_MARK_KEY_ADJ     ゛(@) と ゜([) は隣のキー（ば ↔ ぱ）
_MARK_TWO_STROKE = (os.environ.get('CN_MARK_TWO_STROKE', '1') != '0')
# **既定は切り**。`ば ↔ ぱ` を隣として数えると、readcheck で
# `こんぷと`（＝こんせぷと の脱字）が `こんぶと` に化けた。
# うにさんの指定に無く、得るものも見つからなかったので
# 入れない（`CN_MARK_KEY_ADJ=1` で入る。測るためだけ）。
_MARK_KEY_ADJ = (os.environ.get('CN_MARK_KEY_ADJ', '0') != '0')

# 各かなキーの物理座標 (row, col)
# row 0 = 数字キー段, 1 = 上段(QWERTY), 2 = 中段(ASDF), 3 = 下段(ZXCV)
#
# col は各段の左端を 0 とした通し番号。
# 実際のキーボードは段ごとに少しずつ右へずれているため、
# 距離計算のときに ROW_OFFSET で補正する。
#
#  数字段: 1  2  3  4  5  6  7  8  9  0  -  ^
#          ぬ ふ あ う え お や ゆ よ わ ほ へ
#  上段:   Q  W  E  R  T  Y  U  I  O  P  @  [
#          た て い す か ん な に ら せ ゛ ゜
#  中段:   A  S  D  F  G  H  J  K  L  ;  :  ]
#          ち と し は き く ま の り れ け む
#  下段:   Z  X  C  V  B  N  M  ,  .  /  \
#          つ さ そ ひ こ み も ね る め ろ
KANA_POSITIONS = {
    # 数字段
    'ぬ': (0, 0), 'ふ': (0, 1), 'あ': (0, 2), 'う': (0, 3), 'え': (0, 4),
    'お': (0, 5), 'や': (0, 6), 'ゆ': (0, 7), 'よ': (0, 8), 'わ': (0, 9),
    'ほ': (0, 10), 'へ': (0, 11),
    # 上段
    'た': (1, 0), 'て': (1, 1), 'い': (1, 2), 'す': (1, 3), 'か': (1, 4),
    'ん': (1, 5), 'な': (1, 6), 'に': (1, 7), 'ら': (1, 8), 'せ': (1, 9),
    # 中段
    'ち': (2, 0), 'と': (2, 1), 'し': (2, 2), 'は': (2, 3), 'き': (2, 4),
    'く': (2, 5), 'ま': (2, 6), 'の': (2, 7), 'り': (2, 8), 'れ': (2, 9),
    'け': (2, 10), 'む': (2, 11),
    # 下段
    'つ': (3, 0), 'さ': (3, 1), 'そ': (3, 2), 'ひ': (3, 3), 'こ': (3, 4),
    'み': (3, 5), 'も': (3, 6), 'ね': (3, 7), 'る': (3, 8), 'め': (3, 9),
    'ろ': (3, 10),
    # 長音符「ー」。JISかな配列では「ろ」の刻印があるキー（下段
    # 右端）を押すと実際には長音「ー」が入力される
    # （「ろ」はキー印字であって、かな入力モードでの出力ではない）。
    # 物理的に同じキーなので、押し間違えるとすれば「ろ」そのものと
    # 混同するのではなく、Shift の有無や隣接キーとの取り違えになる。
    # ここでは同じ座標に置き、「ろ」と「ー」を同一キー上の
    # 表記違いとして距離0で近接させる（半角入力の復元で
    # 「ふれろむ」のような、長音を隣接する別のかなと誤打した並びを
    # 「ふれーむ」に訂正できるようにするため。実機で
    # 「2;\\]（かな変換で ふれろむ）がフレームの候補に出ない」と
    # 報告された）。
    'ー': (3, 10),
    # 小書きかな: Shift + 清音キー なので物理位置は清音と同じ
    'ぁ': (0, 2), 'ぅ': (0, 3), 'ぇ': (0, 4), 'ぉ': (0, 5),
    'ゃ': (0, 6), 'ゅ': (0, 7), 'ょ': (0, 8),
    'ぃ': (1, 2), 'っ': (3, 0),
    # **濁点・半濁点のキーそのもの**（項目48-FX・うにさんの指定・
    # 2026-08-19「かな入力において、濁音、半濁音は2打鍵である
    # ことを考慮します」）。
    #
    # JIS配列では `@` が ゛、`[` が ゜。上段の P の右に並ぶ:
    #     Q  W  E  R  T  Y  U  I  O  P  @  [
    #     た て い す か ん な に ら せ ゛ ゜
    # ここに置くと `_base_distance` がそのまま使えるので、
    # 「゛のつもりで隣を押した」を他のかなと同じ物差しで測れる。
    # 段のずれ（ROW_OFFSET）を入れた実座標では、
    # ゛(1,10) の隣は ほ(0,10)・へ(0,11)・せ(1,9)・゜(1,11)・
    # け(2,10)・れ(2,9)・む(2,11) になる（うにさんの
    # `さへいりょう ⇒ ざいりょう` は へ→゛ の取り違え）。
    '゛': (1, 10), '゜': (1, 11),
}

# 各段の横方向のずれ。実際のキーボードは下の段ほど右にずれている。
# これを入れないと、斜め方向の隣接判定が実態と合わない。
ROW_OFFSET = {0: 0.0, 1: 0.5, 2: 0.75, 3: 1.25}

# 小書き <-> 清音 の対応（Shiftの押し忘れ／余分な押下）
SMALL_KANA_PAIR = {
    'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
    'っ': 'つ', 'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ',
    'あ': 'ぁ', 'い': 'ぃ', 'う': 'ぅ', 'え': 'ぇ', 'お': 'ぉ',
    'つ': 'っ', 'や': 'ゃ', 'ゆ': 'ゅ', 'よ': 'ょ',
}

# 濁点・半濁点付き -> ベースとなる清音キー
# かな入力では「清音キー + ゛キー」の2打鍵なので、
# 濁点の有無違いは「゛キーの押し忘れ／余分」として近接扱いする
DAKUTEN_BASE = {
    'が': 'か', 'ぎ': 'き', 'ぐ': 'く', 'げ': 'け', 'ご': 'こ',
    'ざ': 'さ', 'じ': 'し', 'ず': 'す', 'ぜ': 'せ', 'ぞ': 'そ',
    'だ': 'た', 'ぢ': 'ち', 'づ': 'つ', 'で': 'て', 'ど': 'と',
    'ば': 'は', 'び': 'ひ', 'ぶ': 'ふ', 'べ': 'へ', 'ぼ': 'ほ',
    'ゔ': 'う',
    'ぱ': 'は', 'ぴ': 'ひ', 'ぷ': 'ふ', 'ぺ': 'へ', 'ぽ': 'ほ',
}

# かな → その字を出すのに要る「濁点キー」（項目48-FX）。
# かな入力では 濁音＝清音キー＋`@`、半濁音＝清音キー＋`[` の
# **2打鍵**なので、どちらの打鍵が要るのかを字ごとに持っておく。
# `DAKUTEN_BASE` は「どのキーか」しか言わないので、
# 濁点と半濁点（ば と ぱ）を見分けられなかった。
MARK_OF = {}
for _c in 'がぎぐげござじずぜぞだぢづでどばびぶべぼゔ':
    MARK_OF[_c] = '゛'
for _c in 'ぱぴぷぺぽ':
    MARK_OF[_c] = '゜'


def keystrokes(kana):
    """
    そのかな1文字を出すのに要る**打鍵の並び**を返す（項目48-FX）。

        か → ('か',)          1打鍵
        が → ('か', '゛')     2打鍵
        ぱ → ('は', '゜')     2打鍵
        ゃ → ('や',)          Shift は同じキーなので1打鍵と数える

    かな入力の誤打を「何回の誤りか」で数えるための土台。
    """
    base = DAKUTEN_BASE.get(kana, kana)
    mark = MARK_OF.get(kana, '')
    return (base, mark) if mark else (base,)


# 48-XC・2026-09-10: 未入力キーの補充は、隣接・巻き込み・転置より後。
MISSING_KEY_COST = 2.8


def additional_kana_keys(typed, restored):
    """補正後に増えるかな打鍵数の下限。濁点/半濁点も独立した1打。"""
    def size(text):
        total=0
        for ch in text or '':
            if 'ァ'<=ch<='ヶ':
                ch=chr(ord(ch)-0x60)
            total+=len(keystrokes(ch))
        return total
    return max(0,size(restored)-size(typed))


def kana_repair_cost(typed, restored, cost, input_method='kana'):
    """明示的な追加打鍵を、安い巻き戻し費用へ紛れ込ませない。"""
    if input_method=='romaji':
        return cost
    return max(cost,MISSING_KEY_COST*additional_kana_keys(typed,restored))


# 距離計算の対象になる全かな
ALL_KANA = list(KANA_POSITIONS.keys()) + list(DAKUTEN_BASE.keys())
ALL_KANA = list(dict.fromkeys(ALL_KANA))  # 重複除去（順序保持）

FAR = 99.0  # 「押し間違えとは考えにくい」を表す値


# ---------------------------------------------------------------
# 同一キーの表（うにさんの指定・2026-08-11・C-4）
#
# 「（は、ゆを候補に出したり、！は、ぬや１を候補に出したり、
#   同一キーにある文字を候補に出す」。
#
# JIS配列では1つのキーに最大4つの文字が乗っている:
#   そのまま / Shift / かな / かな+Shift。
# 入力方式やモードを取り違えると、この4つの中で入れ替わる。
# **キーの押し間違いではなくモードの取り違え**なので、
# 隣接キー距離（上の KANA_POSITIONS）とは別の表として持つ。
#
# 並びは (そのまま, Shift, かな, かな+Shift)。無いものは ''。
# 全角形（！ （ など）は IME が作るものなので、下の
# `_WIDE` で半角へ寄せてから引く。
#
# うにさんが 2026-08-11 に送ってくれた対応表:
#   - ⇒ ほ / \ ⇒ ー / \ ⇒ ろ / ^ ⇒ へ / [ ⇒ ゜ / ] ⇒ む
#   @ ⇒ ゛ / : ⇒ け / ; ⇒ れ / , ⇒ ね / . ⇒ る / / ⇒ め
# ---------------------------------------------------------------
_JIS_KEYS = [
    # 数字段
    ('1', '!', 'ぬ', 'ぬ'),
    ('2', '"', 'ふ', 'ふ'),
    ('3', '#', 'あ', 'ぁ'),
    ('4', '$', 'う', 'ぅ'),
    ('5', '%', 'え', 'ぇ'),
    ('6', '&', 'お', 'ぉ'),
    ('7', "'", 'や', 'ゃ'),
    ('8', '(', 'ゆ', 'ゅ'),
    ('9', ')', 'よ', 'ょ'),
    ('0', '',  'わ', 'を'),
    ('-', '=', 'ほ', 'ほ'),
    ('^', '~', 'へ', 'へ'),
    ('¥', '|', 'ー', 'ー'),      # 円記号キー（Backspace の左）
    # 上段
    ('q', 'Q', 'た', 'た'), ('w', 'W', 'て', 'て'),
    ('e', 'E', 'い', 'ぃ'), ('r', 'R', 'す', 'す'),
    ('t', 'T', 'か', 'か'), ('y', 'Y', 'ん', 'ん'),
    ('u', 'U', 'な', 'な'), ('i', 'I', 'に', 'に'),
    ('o', 'O', 'ら', 'ら'), ('p', 'P', 'せ', 'せ'),
    ('@', '`', '゛', '゛'),
    ('[', '{', '゜', '「'),
    # 中段
    ('a', 'A', 'ち', 'ち'), ('s', 'S', 'と', 'と'),
    ('d', 'D', 'し', 'し'), ('f', 'F', 'は', 'は'),
    ('g', 'G', 'き', 'き'), ('h', 'H', 'く', 'く'),
    ('j', 'J', 'ま', 'ま'), ('k', 'K', 'の', 'の'),
    ('l', 'L', 'り', 'り'),
    (';', '+', 'れ', 'れ'),
    (':', '*', 'け', 'け'),
    (']', '}', 'む', '」'),
    # 下段
    ('z', 'Z', 'つ', 'っ'), ('x', 'X', 'さ', 'さ'),
    ('c', 'C', 'そ', 'そ'), ('v', 'V', 'ひ', 'ひ'),
    ('b', 'B', 'こ', 'こ'), ('n', 'N', 'み', 'み'),
    ('m', 'M', 'も', 'も'),
    (',', '<', 'ね', '、'),
    ('.', '>', 'る', '。'),
    ('/', '?', 'め', '・'),
    ('\\', '_', 'ろ', 'ろ'),      # 右Shift の左のキー
]

# 全角 → 半角（同一キーを引く前に寄せる）。
# IME が作る全角形は、もとの半角キーと同じキーの上にある。
_WIDE_TO_ASCII = {
    '！': '!', '”': '"', '＃': '#', '＄': '$', '％': '%',
    '＆': '&', '’': "'", '（': '(', '）': ')', '＝': '=',
    '～': '~', '｜': '|', '＋': '+', '＊': '*', '＜': '<',
    '＞': '>', '？': '?', '＿': '_', '｛': '{', '｝': '}',
    '＠': '@', '｀': '`', '＾': '^', 'ー': 'ー', '－': '-',
    '：': ':', '；': ';', '、': '、', '。': '。', '・': '・',
    '「': '「', '」': '」', '￥': '¥', '＼': '\\', '／': '/',
    # 波ダッシュ（U+301C）と全角チルダ（U+FF5E）は見た目が同じで、
    # IME や環境によってどちらが出るかが違う。どちらも ^ のキー。
    '〜': '~',
}
for _d in range(10):
    _WIDE_TO_ASCII[chr(ord('０') + _d)] = str(_d)

# 半角 → 全角（候補に全角形も並べるため）。
_ASCII_TO_WIDE = {v: k for k, v in _WIDE_TO_ASCII.items() if v != k}

# 文字 → その文字が乗っているキー
_KEY_OF_CHAR = {}
for _key in _JIS_KEYS:
    for _ch in _key:
        if _ch and _ch not in _KEY_OF_CHAR:
            _KEY_OF_CHAR[_ch] = _key


def same_key_characters(ch):
    """
    その文字と**同じ物理キーに乗っている、ほかの文字**を返す。

    「（」なら 8 のキーなので ゆ・ゅ・8・８・（の相方 を返す。
    「！」なら 1 のキーなので ぬ・1・１ を返す。
    かな入力とローマ字入力を取り違えたとき、あるいは Shift を
    取り違えたときに実際に起こる入れ替わりだけを並べる。

    並びは**かな → 全角 → 半角**の順。かな入力での取り違えが
    いちばん多いので、かなを先に出す（うにさんの例も
    「（ ⇒ ゆ」「！ ⇒ ぬ や １」の順）。

    自分自身と、空のものは入らない。該当キーが無ければ空リスト。
    """
    if not ch or len(ch) != 1:
        return []
    key = _KEY_OF_CHAR.get(ch)
    if key is None:
        key = _KEY_OF_CHAR.get(_WIDE_TO_ASCII.get(ch, ''))
    if key is None:
        return []
    plain, shift, kana, kana_shift = key
    out = []
    for cand in (kana, kana_shift, plain, shift):
        if not cand:
            continue
        for form in (cand, _ASCII_TO_WIDE.get(cand, '')):
            if form and form != ch and form not in out:
                out.append(form)
    return out


def _euclid(p1, p2):
    if p1 is None or p2 is None:
        return FAR
    # 段ごとの横ずれを加味した実座標に直してから距離を測る
    x1 = p1[1] + ROW_OFFSET.get(p1[0], 0.0)
    x2 = p2[1] + ROW_OFFSET.get(p2[0], 0.0)
    return math.hypot(p1[0] - p2[0], x1 - x2)


@functools.lru_cache(maxsize=None)
def _base_distance(c1, c2):
    """
    清音同士のキー距離。

    「隣接キー」とは、そのキーを中心とした周囲8方向のキーを指す。
    段ごとの横ずれがあるため単純な座標差では判定できないので、
    実座標での距離が「キー1個分の範囲に収まるか」で判断する。

    戻り値: 隣接なら 1.0 前後、2つ隣なら 2.0 前後、それ以上は FAR
    """
    p1 = KANA_POSITIONS.get(c1)
    p2 = KANA_POSITIONS.get(c2)
    if p1 is None or p2 is None:
        return FAR

    row_diff = abs(p1[0] - p2[0])
    # 3段以上離れていれば押し間違いとは考えにくい
    if row_diff > 2:
        return FAR

    x1 = p1[1] + ROW_OFFSET.get(p1[0], 0.0)
    x2 = p2[1] + ROW_OFFSET.get(p2[0], 0.0)
    col_diff = abs(x1 - x2)

    # 同じ段: 横に何個離れているか
    if row_diff == 0:
        if col_diff <= 1.05:
            return 1.0          # 隣
        if col_diff <= 2.05:
            return 2.0          # 2つ隣
        return FAR

    # 隣の段: 段ごとの横ずれがあるため、真上・斜め上のどれも
    # 「キー1個分＋ずれ」の範囲に入る。実機で指が届く範囲に合わせて
    # 横方向 1.55 までを隣接として扱う。
    # （例: 「い」から見た「あ う え て す と し は」がすべてこの範囲）
    if row_diff == 1:
        if col_diff <= 1.55:
            return 1.0          # 真上・真下・斜め隣
        if col_diff <= 2.55:
            return 1.8          # やや離れた斜め
        return FAR

    # 2段離れ: 縦に2つ飛ばし。起こりうるが可能性は低い
    if row_diff == 2:
        if col_diff <= 1.05:
            return 2.2
        return FAR

    return FAR


@functools.lru_cache(maxsize=None)
def kana_key_distance(c1, c2):
    """
    2つのかな文字の「押し間違えやすさ」を距離で返す。
    0 に近いほど間違えやすい。FAR(99) は無関係。

    **かな2文字だけで決まる純粋な計算**なので、まるごと控える。
    組み合わせはかなの種類ぶんしか無い（数千通り）ので、
    上限を設けずに持ってよい。
    1000行のタブの解析では、この関数が**55万回**呼ばれていた
    （`weighted_edit_distance` の中から）。控えを付けるだけで
    解析が体感で変わる（2026-08-11・うにさんから
    「1000行あると待ち時間が長い」の指摘）。
    """
    if c1 == c2:
        return 0.0

    # 「ろ」と「ー」（長音）は物理的に同じキー。
    # キー印字は「ろ」だが、かな入力モードで実際にこのキーを押すと
    # 長音「ー」が入力される。半角モード等で誤って「ろ」が混ざった
    # 場合、実際に打ちたかったのはほぼ確実に長音なので、
    # 最も間違えやすい関係として扱う（Shiftの押し忘れと同程度）。
    if {c1, c2} == {'ろ', 'ー'}:
        return 0.2

    # Shift の押し忘れ／余分（小書き <-> 清音）
    if SMALL_KANA_PAIR.get(c1) == c2:
        return 0.3

    base1 = DAKUTEN_BASE.get(c1, c1)
    base2 = DAKUTEN_BASE.get(c2, c2)
    mark1 = MARK_OF.get(c1, '')
    mark2 = MARK_OF.get(c2, '')
    has_mark1 = bool(mark1)
    has_mark2 = bool(mark2)

    # 同じキーで濁点の有無だけが違う（例: か <-> が, は <-> ぱ）。
    # **゛キーの押し忘れ／余分な1打鍵**。1回の誤りなので安い。
    if base1 == base2 and has_mark1 != has_mark2:
        return 0.4

    # 同じキーで、濁点と半濁点を取り違えた（ば <-> ぱ）。
    # **゛(@) と ゜([) は隣どうしのキー**なので、これも1回の誤り
    # （項目48-FX）。以前はここが素通りして FAR になっていた。
    if (_MARK_KEY_ADJ and base1 == base2
            and has_mark1 and has_mark2 and mark1 != mark2):
        return _base_distance('゛', '゜')

    # ベースキーが違う場合
    if base1 != base2:
        # **濁点の有無まで違うなら、それは2回の誤り**（項目48-FX・
        # うにさんの指定・2026-08-19）:
        #
        # > 「かな入力において、濁音、半濁音は2打鍵であることを
        # >   考慮します。ざいりょう、はいりょうはそのため遠く、
        # >   隣接キーでもありません。補正対象外です。」
        #
        #     ざ = さ(X) ＋ ゛(@)   … 2打鍵
        #     は = は(F)            … 1打鍵
        #     → ベースの X→F を打ち間違え、**さらに** ゛ を
        #       押し忘れた、という2つの誤りが同時に要る
        #
        # 前はここが `+0.4` で済んでいたので、ざ↔は が **1.40**
        # ＝「隣接キー1回ぶん」の値になっていた。実機の
        # `ざいりよう → はいりよう` はこれが作っていた。
        # **1回の打ち損ねで説明が付かないものは、隣接ではない。**
        if _MARK_TWO_STROKE and (has_mark1 != has_mark2 or mark1 != mark2):
            return FAR
        d = _base_distance(base1, base2)
        if d >= FAR:
            return FAR
        if not _MARK_TWO_STROKE and has_mark1 != has_mark2:
            return d + 0.4          # 旧: 印の違いを 0.4 で済ませる
        # 濁点が両方に付いている場合のわずかな上乗せ（従来どおり）。
        return d + (0.1 if has_mark1 else 0.0)

    return _base_distance(c1, c2)


# ============================================================
# 音韻的な混同（キー位置とは別軸の誤り）
# ============================================================
# 五十音表。行 = 子音グループ、列 = 母音(あいうえお)
GOJUON = [
    ['あ', 'い', 'う', 'え', 'お'],
    ['か', 'き', 'く', 'け', 'こ'],
    ['さ', 'し', 'す', 'せ', 'そ'],
    ['た', 'ち', 'つ', 'て', 'と'],
    ['な', 'に', 'ぬ', 'ね', 'の'],
    ['は', 'ひ', 'ふ', 'へ', 'ほ'],
    ['ま', 'み', 'む', 'め', 'も'],
    ['や', None, 'ゆ', None, 'よ'],
    ['ら', 'り', 'る', 'れ', 'ろ'],
    ['わ', None, None, None, 'を'],
]

# かな -> (行index, 列index)
_GOJUON_POS = {}
for _r, _row in enumerate(GOJUON):
    for _c, _ch in enumerate(_row):
        if _ch:
            _GOJUON_POS[_ch] = (_r, _c)

# 小書きかなも清音と同じ音韻位置として扱う
_SMALL_TO_NORMAL = {
    'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
    'っ': 'つ', 'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ',
}

# 音韻的な混同のコスト。キー距離とスケールを揃えるため 1.0 前後にする
_VOWEL_CONFUSION_COST = 1.0    # 同じ子音・母音違い（例: う ⇔ い）
_CONSONANT_CONFUSION_COST = 1.4  # 同じ母音・子音違い（例: う ⇔ く）


def phonetic_candidates(char):
    """
    音韻的に混同しやすいかなを返す。
    キー配列上は遠くても打ち間違えることがあるため、キー距離を補完する。

    戻り値: [(候補文字, 疑似距離), ...]
    """
    is_small = char in _SMALL_TO_NORMAL
    is_dakuten = char in DAKUTEN_BASE

    # 音韻位置を調べるための基準文字（小書き・濁点を清音に戻す）
    base = _SMALL_TO_NORMAL.get(char, char)
    base = DAKUTEN_BASE.get(base, base)

    pos = _GOJUON_POS.get(base)
    if pos is None:
        return []
    row, col = pos

    out = []

    def _restore(target):
        """元の文字が小書き／濁点だったなら、候補も同じ形に揃える"""
        if is_small:
            for small, normal in _SMALL_TO_NORMAL.items():
                if normal == target:
                    return small
            return None   # 小書きが存在しない音は候補にしない
        if is_dakuten:
            for dak, b in DAKUTEN_BASE.items():
                if b == target:
                    return dak
            return None
        return target

    # 同じ子音で母音が違う（例: う ⇔ い, き ⇔ く）
    for c in range(5):
        if c == col:
            continue
        target = GOJUON[row][c]
        if not target:
            continue
        restored = _restore(target)
        if restored:
            out.append((restored, _VOWEL_CONFUSION_COST))

    # 同じ母音で子音が違う（例: う ⇔ く ⇔ す）
    for r in range(len(GOJUON)):
        if r == row:
            continue
        target = GOJUON[r][col]
        if not target:
            continue
        restored = _restore(target)
        if restored:
            out.append((restored, _CONSONANT_CONFUSION_COST))

    return out


import functools


# --- 項目48-NJ: **ローマ字入力のときは、ローマ字のキーで測る**
#     （試し・2026-09-01。既定は off）------------------------------
#
# この関数は**かなキー配列の距離**だけで候補を集めている。
# ローマ字入力の人にとっては別のキー配列なのに:
#
#     や → た   かな **99.0**（無関係）／ ローマ字 ya→ta は **隣**
#     や → か   かな **1.0**（隣）    ／ ローマ字 ya→ka は 隣ではない
#
# 実測（`readcheck romaji 600 --adjacent`・項目48-NI で材料を作り、
# `tools_local/probe_rom2.py` で数えた・初期状態）:
#
#     **ローマ字では隣キー1打・かなでは遠い**行  **275**
#       正解の読みが 1位 105 ／ 2〜3位 76 ／ **4位以下 94**
#       正解の読みの費用は **181件が 2.0〜3.0**（＝遠い置換の値段）
#       例: じんどく → じんそく（費用 2.2・**12位**）。
#           1位は しんどく（0.4・かなで隣）
#
# **費用は下げるだけ**（かなで近い組はそのまま）。上げると今までの
# 直りが落ちるので。
_ROMAJI_SUB_NEAR = 0.5      # ローマ字で1字が隣のキー
_ROMAJI_SUB_SAME = 0.0      # 同じ綴り


@functools.lru_cache(maxsize=4)
def _romaji_pairs():
    """かな同士で、**ローマ字の綴りが1字違い・その1字が隣のキー**の組。"""
    from corrector import _KANA_TO_ROMAJI, _qwerty_adjacent
    out = {}
    items = [(k, r) for k, r in _KANA_TO_ROMAJI.items() if r]
    for a, ra in items:
        for b, rb in items:
            if a == b or len(ra) != len(rb):
                continue
            diff = [(x, y) for x, y in zip(ra, rb) if x != y]
            if len(diff) == 1 and _qwerty_adjacent(diff[0][0], diff[0][1]):
                out.setdefault(a, {})[b] = _ROMAJI_SUB_NEAR
    return out


@functools.lru_cache(maxsize=512)
def nearby_candidates(char, max_dist=1.6, include_phonetic=True,
                      input_method=None):
    """
    ある文字について、押し間違えた可能性のある候補を近い順に返す。
    戻り値: [(候補文字, 距離), ...]  自分自身を距離0で含む。

    include_phonetic=True のときは、キー配列上は遠くても
    音韻的に混同しやすいかな（母音の取り違えなど）も候補に加える。
    実際の入力ミスはキー位置の誤りだけでなく、
    「にゅうりょく」を「にゅいりょく」と打つような音の取り違えも多いため。

    入力の組み合わせ（かな文字 × max_dist）は有限で少数なので、
    計算結果をキャッシュして毎回の再計算を避ける。
    これは1文字ごとに何度も呼ばれるため、キャッシュの有無で
    補正全体の速度が大きく変わる。
    """
    if char not in KANA_POSITIONS and char not in DAKUTEN_BASE:
        # かな以外（記号・英数・スペース等）はそのまま
        return [(char, 0.0)]

    scored = {}
    # **ローマ字入力では、かな配列の隣接は見ない**（項目48-NJ・
    # うにさんの指定・2026-09-01）:
    #
    #     「ローマ字入力はローマ字の隣接キーを見てください。
    #       かな入力の隣接は見ません。」
    #
    # 最初は「かなの距離に**足す**」形で作って、育ちの数字が下がる
    # ので見送っていた。**足すのではなく、置き換える**のが指定。
    # 打った人はローマ字の配列しか触っていないのだから、かなの
    # 配列で近いこと（`や`と`か`）は**その人にとって根拠ではない**。
    _rom = (input_method == 'romaji' and _romaji_cost_on())
    if _rom:
        try:
            for c, d in _romaji_pairs().get(char, {}).items():
                if d <= max_dist:
                    scored[c] = d
            # **同じキーの変わり者は、どちらの入力方式でも残す**——
            # 小書き（Shift の押し忘れ）と濁点・半濁点は**キー配列の
            # 話ではない**（ローマ字でも `ya`/`xya`・`ka`/`ga` という
            # 綴りの違いとして同じだけ起きる）。`adjacent_slip` も
            # 入力方式を問わずこの2つを通している——**同じ判定を
            # 道ごとに書き分けない**（48-GN）。
            for c in (SMALL_KANA_PAIR.get(char),
                      _same_key_kana(char)):
                if c and c != char:
                    scored.setdefault(c, 0.3)
            for c, base in SMALL_KANA_PAIR.items():
                if base == char:
                    scored.setdefault(c, 0.3)
        except Exception:
            _rom = False
    if not _rom:
        for c in ALL_KANA:
            d = kana_key_distance(char, c)
            if d <= max_dist:
                scored[c] = d
    scored.setdefault(char, 0.0)

    if include_phonetic:
        for c, d in phonetic_candidates(char):
            # キー距離でも拾えている場合は近いほうを採用
            if c not in scored or d < scored[c]:
                scored[c] = d

    result = sorted(scored.items(), key=lambda x: x[1])
    return result


def _same_key_kana(ch):
    """濁点・半濁点を外した／付けた相手（同じキー）。項目48-NJ。"""
    base = DAKUTEN_BASE.get(ch)
    if base and base != ch:
        return base
    for k, v in DAKUTEN_BASE.items():
        if v == ch and k != ch:
            return k
    return None


def _romaji_cost_on():
    """**測るための切り替え口**（項目48-NJ）。**既定は on**。

    `CN_ROMAJI_COST=0` で、かな配列だけの昔の形に戻せる。
    """
    return os.environ.get('CN_ROMAJI_COST', '1') != '0'


@functools.lru_cache(maxsize=8)
def mark_key_neighbors(mark='゛', max_dist=1.05):
    """
    **その印のキーの「隣」にあるかな**（項目48-FX）。

    うにさんの指定（2026-08-19）:

    > 「さへいりょう、これは濁音の隣接キー判定です。」

    `ざいりょう` は かな入力では さ(X) ＋ ゛(@) の2打鍵。
    2打鍵めで `@` の隣の `^`(へ) を叩くと **さへいりょう** になる。
    ここで返すのは、その「叩いてしまった側」の一覧。

    ゛(@) の隣: わ ほ へ せ れ け む ゜
    ゜([) の隣: へ ー ゛ む  （実測）

    **並べ直して返す**（集合を経由しても順序が動かないように。
    項目48-DR「起動ごとに答えが変わる」の再発防止）。
    """
    out = []
    for c in ALL_KANA:
        if c == mark or c in ('゛', '゜'):
            continue
        if _base_distance(c, mark) <= max_dist:
            out.append(c)
    return tuple(sorted(out))


def mark_slip_enabled():
    """測定用の既存設定を、芯と語彙木で共用する。"""
    return os.environ.get('CN_MARK_SLIP','1') != '0'


@functools.lru_cache(maxsize=2048)
def mark_slip_candidates(base, pressed, max_dist=1.05):
    """48-XO: 清音＋隣接キーを、清音＋濁点/半濁点の1打置換として読む。"""
    if base in MARK_OF or len(keystrokes(pressed)) != 1:
        return ()
    out=[]
    for marked, plain in DAKUTEN_BASE.items():
        if plain != base:
            continue
        mark=MARK_OF[marked]
        if pressed == mark:
            continue  # 表記の結合であり、隣接誤打ではない。
        distance=_base_distance(pressed,mark)
        if distance <= min(max_dist,1.05):
            out.append((marked,distance))
    return tuple(sorted(out,key=lambda item:(item[1],item[0])))


def build_candidate_map(text):
    """文字列全体について、各位置の候補リストを構築する。"""
    return [(ch, nearby_candidates(ch)) for ch in text]


if __name__ == '__main__':
    # 簡易動作確認
    target = 'もぱなゃうりゅき'   # 「もじにゅうりょく」の誤打を想定
    expected = 'もじにゅうりょく'

    print(f'入力: {target}')
    print(f'期待: {expected}')
    print()
    for i, (ch, cands) in enumerate(build_candidate_map(target)):
        want = expected[i] if i < len(expected) else '-'
        chars = [c for c, _ in cands]
        hit = '○' if want in chars else '×'
        shown = ' '.join(f'{c}({d:.2f})' for c, d in cands[:8])
        print(f'{i+1}. {ch} -> {shown}   [期待{want} {hit}]')
