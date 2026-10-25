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

from cache_limits import size as _cache_size   # 控えの上限は cache_limits で1か所に（2026-10-24）
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
#  数字段: 1  2  3  4  5  6  7  8  9  0  -  ^  ¥
#          ぬ ふ あ う え お や ゆ よ わ ほ へ ー
#  上段:   Q  W  E  R  T  Y  U  I  O  P  @  [
#          た て い す か ん な に ら せ ゛ ゜
#  中段:   A  S  D  F  G  H  J  K  L  ;  :  ]
#          ち と し は き く ま の り れ け む
#  下段:   Z  X  C  V  B  N  M  ,  .  /  \
#          つ さ そ ひ こ み も ね る め ろ
_JIS_KANA_POSITIONS = {
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
    # Standard JIS: long vowel is on the yen key, distinct from bottom-row ろ.
    # FMV input quick sheet: https://www.fmworld.net/download/DD000923/DD000923.pdf
    # Ambiguous ASCII backslash belongs to halfwidth.AMBIGUOUS_KEYS.
    'ー': (0, 12), 'を': (0, 9),
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
# **いま選ばれているかな配列**の位置（項目48-KB・かな配列・2026-10-14）。
# 既定は JIS で、中身は上の表そのまま。親指シフト（NICOLA）・新JIS を選ぶと
# `set_kana_layout` が**中身を入れ替える**（辞書そのものは差し替えない——
# `from kana_layout import KANA_POSITIONS` で持った先にも効くように）。
KANA_POSITIONS = dict(_JIS_KANA_POSITIONS)

# 各段の横方向のずれ。実際のキーボードは下の段ほど右にずれている。
# これを入れないと、斜め方向の隣接判定が実態と合わない。
# **形が「格子」のときは全部 0 になる**（下の `set_shape`・項目48-KB）。
# 中身を入れ替えるだけで辞書そのものは差し替えない（`ROW_OFFSET.get`
# で引いている先が全部そのまま効くように）。
_ROW_OFFSET_STAGGERED = {0: 0.0, 1: 0.5, 2: 0.75, 3: 1.25}
ROW_OFFSET = dict(_ROW_OFFSET_STAGGERED)

# --- キーボードの形（項目48-KB・2026-10-14）---
# うにさんの指定「左右で分割されたキーボードなどの選択を用意してください。
# これは隣接キーに影響します」。選ぶのは `keyboard_layout.apply`、ここは
# 位置の物差し（隣か・距離）を形に合わせるだけ。かなの位置そのもの
# （KANA_POSITIONS）は JIS のまま動かさない。
#
#   standard     段ずれあり（既定・今までどおり）
#   split        左右に分かれている（段ずれあり）。別の手の側は隣でない
#   ortho        格子。段ずれ 0、上下の隣は同じ列だけ（斜めは隣でない）
#   split_ortho  左右に分かれた格子
#
# 分割の境は字の段では t|y・g|h・b|n（列 4|5）。数字の段は、段ずれの
# ある分割（Barocco・Freestyle・Keychron Q11）では 6 が左に付くので 6|7
# （列 5|6）、格子の分割（ErgoDox・Corne・Lily58）では 5|6（列 4|5）。
SHAPES = ('standard', 'split', 'ortho', 'split_ortho')
_SHAPE = 'standard'
_ORTHO = False
_SPLIT_LEFT_MAX = None          # 段 → 左手の右端の列。None なら分割なし
_SPLIT_LEFT_MAX_STAGGERED = {0: 5, 1: 4, 2: 4, 3: 4}
_SPLIT_LEFT_MAX_ORTHO = {0: 4, 1: 4, 2: 4, 3: 4}


def current_shape():
    return _SHAPE


def is_ortho():
    return _ORTHO


def same_half(p1, p2):
    """分割キーボードで、2つの位置が同じ手の側か（分割でなければ常に真）。"""
    if _SPLIT_LEFT_MAX is None:
        return True
    return ((p1[1] <= _SPLIT_LEFT_MAX.get(p1[0], 4))
            == (p2[1] <= _SPLIT_LEFT_MAX.get(p2[0], 4)))


def set_shape(shape):
    """形を変える。変わったら真を返し、位置に依る控えを全部捨てる。

    知らない名前は standard。`keyboard_layout.apply` から呼ばれる。
    """
    global _SHAPE, _ORTHO, _SPLIT_LEFT_MAX
    if shape not in SHAPES:
        shape = 'standard'
    if shape == _SHAPE:
        return False
    _SHAPE = shape
    _ORTHO = shape in ('ortho', 'split_ortho')
    if shape == 'split':
        _SPLIT_LEFT_MAX = dict(_SPLIT_LEFT_MAX_STAGGERED)
    elif shape == 'split_ortho':
        _SPLIT_LEFT_MAX = dict(_SPLIT_LEFT_MAX_ORTHO)
    else:
        _SPLIT_LEFT_MAX = None
    ROW_OFFSET.clear()
    ROW_OFFSET.update({r: 0.0 for r in _ROW_OFFSET_STAGGERED} if _ORTHO
                      else _ROW_OFFSET_STAGGERED)
    clear_caches()
    return True

# 小書き <-> 清音 の対応（Shiftの押し忘れ／余分な押下）
SMALL_KANA_PAIR = {
    'ぁ': 'あ', 'ぃ': 'い', 'ぅ': 'う', 'ぇ': 'え', 'ぉ': 'お',
    'っ': 'つ', 'ゃ': 'や', 'ゅ': 'ゆ', 'ょ': 'よ',
    'あ': 'ぁ', 'い': 'ぃ', 'う': 'ぅ', 'え': 'ぇ', 'お': 'ぉ',
    'つ': 'っ', 'や': 'ゃ', 'ゆ': 'ゅ', 'よ': 'ょ',
}

# Printed kana on the same physical key, including JIS Shift+0.
_JIS_SHIFT_KANA_PAIR = dict(SMALL_KANA_PAIR, **{'わ': 'を', 'を': 'わ'})
# 同じ物理キーの別の面の字（かな配列ごとに `set_kana_layout` が入れ替える）。
SHIFT_KANA_PAIR = dict(_JIS_SHIFT_KANA_PAIR)

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
_JIS_MARK_OF = {}
for _c in 'がぎぐげござじずぜぞだぢづでどばびぶべぼゔ':
    _JIS_MARK_OF[_c] = '゛'
for _c in 'ぱぴぷぺぽ':
    _JIS_MARK_OF[_c] = '゜'
# いまのかな配列で**印のキーが要る字**。JIS・新JIS は上の表、親指シフトは
# 濁音・半濁音が親指との同時打鍵（1打）なので**空**（`set_kana_layout`）。
MARK_OF = dict(_JIS_MARK_OF)


def keystrokes(kana):
    """
    そのかな1文字を出すのに要る**打鍵の並び**を返す（項目48-FX）。

        か → ('か',)          1打鍵
        が → ('か', '゛')     2打鍵
        ぱ → ('は', '゜')     2打鍵
        ゃ → ('ゃ',)          表記は保持し、キーの同一性は same_physical_key で判定

    かな入力の誤打を「何回の誤りか」で数えるための土台。
    """
    # 印のキーが要らない字（清音・小書き、親指シフトの濁音）は1打のまま。
    # DAKUTEN_BASE は五十音の表なので、印が要るときだけ清音へ開く
    # （親指シフトで が を か に潰さない・項目48-KB）。
    mark = MARK_OF.get(kana, '')
    if not mark:
        return (kana,)
    return (DAKUTEN_BASE.get(kana, kana), mark)


# 48-XC・2026-09-10: 未入力キーの補充は、隣接・巻き込み・転置より後。
MISSING_KEY_COST = 2.8


def _single_key_drop_positions(typed, restored):
    """Original physical keys and every position explaining one deletion."""
    if len(typed)<=len(restored):return None
    keys=tuple(k for char in typed for k in keystrokes(char))
    target=tuple(k for char in restored for k in keystrokes(char))
    if len(keys)!=len(target)+1:return None
    positions=tuple(i for i in range(len(keys)) if keys[:i]+keys[i+1:]==target)
    if not positions or any(not ('ぁ'<=keys[i]<='ゖ' or keys[i] in 'ー゛゜') for i in positions):
        return None
    return keys,positions


# Only the directly neighboring printable key on each side of a JIS Shift.
# The source must actually require Shift; a hypothetical changed kana does not.
_JIS_SHIFT_NEIGHBORS = {'left': frozenset('つ'), 'right': frozenset('ろ')}
_JIS_SHIFT_KANA = frozenset('ぁぃぅぇぉっゃゅょを')
# いまのかな配列の分（`set_kana_layout` が入れ替える）。親指シフトでは
# 「Shift」は親指キーで、面は 左親指 'L'・右親指 'R' の2つ。
_SHIFT_NEIGHBORS = dict(_JIS_SHIFT_NEIGHBORS)
_SHIFT_KANA = _JIS_SHIFT_KANA
# 字 → 面（'' 単独・'S' Shift・'L' 左親指・'R' 右親指）。無い字は ''。
_LAYER_OF = {c: 'S' for c in _JIS_SHIFT_KANA}


@functools.lru_cache(maxsize=None)
def intrusion_key_distance(pressed, neighbor):
    """Distance to a source character's key or its required Shift modifier.

    Modifier evidence is directional and only for deletion. It must not make
    distant kana substitutions adjacent or change the cost of surviving keys.
    """
    distance = kana_key_distance(pressed, neighbor, intrusion=True)
    # Deletion removes a source key without changing any surviving Shift.
    # The extra key may have been hit just before or after Shift was pressed;
    # only its physical adjacency matters here, unlike substitution.
    if pressed in KANA_POSITIONS and neighbor in KANA_POSITIONS:
        distance = min(distance, _intrusion_base_distance(pressed, neighbor))
    if neighbor in _SHIFT_KANA and any(pressed in keys for keys in _SHIFT_NEIGHBORS.values()):
        distance = min(distance, 1.0)
    return distance


def single_key_drop_adjacency(typed, restored, max_distance=1.0):
    """Physical proof for a length-reducing single kana keystroke deletion.

    None means a different operation. Repetition permission is separate.
    Punctuation deletion and same-length voicing are different operations.
    """
    proof=_single_key_drop_positions(typed,restored)
    if proof is None:return None
    keys,positions=proof
    return any(any(intrusion_key_distance(keys[i],keys[j])<=max_distance
                   for j in (i-1,i+1) if 0<=j<len(keys)) for i in positions)


@functools.lru_cache(maxsize=_cache_size(4096))
def multiple_key_drop_adjacency(typed, restored, max_distance=1.0):
    """48-AJM: pure multi-key deletion cannot bypass original adjacency.

    A voiced kana occupies two physical keys. Check every removed key
    against its immediate original neighbors, including retained context.
    None leaves other edit kinds to their existing generator contracts.
    Same-length voicing and punctuation deletion are not this operation.
    """
    if len(typed)<=len(restored):return None
    keys=tuple(k for char in typed for k in keystrokes(char))
    target=tuple(k for char in restored for k in keystrokes(char))
    if len(keys)<=len(target)+1:return None
    def reaches(require_adjacency):
        reachable={0}
        for i,key in enumerate(keys):
            droppable=(key in KANA_POSITIONS and (not require_adjacency or
                any(intrusion_key_distance(key,keys[j])<=max_distance
                    for j in (i-1,i+1) if 0<=j<len(keys))))
            following=set(reachable) if droppable else set()
            following.update(j+1 for j in reachable if j<len(target) and key==target[j])
            reachable=following
            if not reachable:return False
        return len(target) in reachable
    if not reaches(False):return None
    return reaches(True)


def same_physical_key(left,right):
    """Shift changes the printed kana, not which physical key was pressed."""
    return left==right or (left in KANA_POSITIONS
                           and KANA_POSITIONS.get(left)==KANA_POSITIONS.get(right))


def single_key_drop_is_duplicate(typed, restored):
    """Voiced kana still begin with the same physical base key.

    そぞ -> ぞ deletes a repeated そ before the dakuten keystroke;
    a different neighboring key cannot relabel that repetition an intrusion.
    """
    proof=_single_key_drop_positions(typed,restored)
    if proof is None:return None
    keys,positions=proof
    # Shift changes the printed kana, not the physical repeated key.
    # Keep literal forms in the deletion proof; only key identity ignores
    # Shift, so this cannot silently change the surviving kana's spelling.
    return any(any(same_physical_key(keys[i],keys[j])
                   for j in (i-1,i+1) if 0<=j<len(keys)) for i in positions)


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
    plain, shift, *kanas = key          # かなの面は配列により 2つか 3つ
    out = []
    for cand in tuple(kanas) + (plain, shift):
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


def physical_intrusion_keys_adjacent(p1, p2):
    """JIS neighbours: exclude upper-left/lower-right and middle-row diagonals.

    Rows include the number row. The QWERTY/ASDF pair has only vertical
    neighbours; the other row pairs also allow the lower key to the left.
    Shift variants share positions but are not a different adjacent key.
    形（項目48-KB）: 分割では別の手の側は隣でない。格子では上下は同じ列だけ。
    """
    if p1 is None or p2 is None or p1 == p2:return False
    if not same_half(p1, p2):return False
    if p1[0] == p2[0]:return abs(p1[1]-p2[1]) == 1
    upper,lower=sorted((p1,p2))
    if lower[0]-upper[0] != 1:return False
    if _ORTHO:return lower[1] == upper[1]
    return lower[1] == upper[1] or (upper[0] != 1 and lower[1] == upper[1]-1)


def physical_keys_adjacent(p1, p2):
    """Substitution uses only the immediately left/right key on one row."""
    return bool(p1 is not None and p2 is not None
                and p1[0]==p2[0] and abs(p1[1]-p2[1])==1
                and same_half(p1, p2))


# 指の受け持ち（タッチタイピングの標準）。列 0〜8 は 小・薬・中・人・人・人・人・中・薬、9 から右は小指。
_FINGER_OF_COLUMN = (0, 1, 2, 3, 3, 4, 4, 5, 6)


def _finger(p):
    c = p[1]
    return _FINGER_OF_COLUMN[c] if 0 <= c < len(_FINGER_OF_COLUMN) else 7


import contextvars as _contextvars
#: 縦の置き換えを候補に使ってよいか。補正の後の読み直し（last_keystroke の1打の戻し・文節の読み直し）の間は切る:
#: そこは紫を手掛かりに正しい行の語も1打で替えてみる道で、縦まで広げると正しい語を別の語に替えた（合わない→合せない）
VERTICAL_OK = _contextvars.ContextVar('VERTICAL_OK', default=True)


def is_vertical_distance(d):
    return d == VERTICAL_DISTANCE


#: 同じ指の上下の置き換えの距離。横の隣（1.0）より少し遠く、隣として数える上限（1.05）の内側。
VERTICAL_DISTANCE = 1.05


def same_finger_vertical(p1, p2):
    """同じ指で1段上・下のキーか（かな入力の置き換えの縦・2026-10-24）。

    一般のタイピングの誤りでは、置き換えは同じ段の左右が最多で、次が同じ指の
    上下（左右のおよそ 1/3〜1/2）。斜め（隣の指の上下）は採らない。うにさん
    10-24「縦も入れる方向で詰める」。巻き込みの隣（physical_intrusion_keys_adjacent）
    の中で、指が同じものだけ。
    """
    if p1 is None or p2 is None or abs(p1[0] - p2[0]) != 1:
        return False
    return (_finger(p1) == _finger(p2)
            and physical_intrusion_keys_adjacent(p1, p2))


@functools.lru_cache(maxsize=None)
def _base_distance(c1, c2):
    """Substitution distance: same row, or the same finger one row up/down."""
    p1,p2=KANA_POSITIONS.get(c1),KANA_POSITIONS.get(c2)
    if p1 is None or p2 is None:return FAR
    if p1[0]!=p2[0]:
        # 縦は横より一段弱い（同じ点の候補が並ぶと横が勝つ）。隣の広さ 1.05 の内側に置く
        return VERTICAL_DISTANCE if same_finger_vertical(p1,p2) else FAR
    return _intrusion_base_distance(c1,c2)


@functools.lru_cache(maxsize=None)
def _intrusion_base_distance(c1, c2):
    """
    清音同士のキー距離。

    巻き込みの隣接はphysical_intrusion_keys_adjacentで定める。除外方向を距離の近さだけで
    隣接へ戻さない。非隣接の距離は候補比較用であり、隣接の証明ではない。

    戻り値: 隣接なら 1.0 前後、2つ隣なら 2.0 前後、それ以上は FAR
    """
    p1 = KANA_POSITIONS.get(c1)
    p2 = KANA_POSITIONS.get(c2)
    if p1 is None or p2 is None:
        return FAR
    # 分割キーボードの別の手の側は、押し間違えない（項目48-KB）
    if not same_half(p1, p2):
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

    # Only the explicitly permitted physical directions count as adjacent.
    if row_diff == 1:
        if physical_intrusion_keys_adjacent(p1, p2):
            return 1.0
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
def kana_key_distance(c1, c2, *, intrusion=False):
    """
    2つのかな文字の「押し間違えやすさ」を距離で返す。
    0 に近いほど間違えやすい。FAR(99) は無関係。

    置換は同じ段の左右と同じ指の上下を隣接とする。intrusion=True は巻き込み専用で、
    従来の上下・斜めを含む距離を使う。同一キーのShift・印は別扱い。
    **かな2文字と用途だけで決まる純粋な計算**なので、まるごと控える。
    組み合わせはかなの種類ぶんしか無い（数千通り）ので、
    上限を設けずに持ってよい。
    1000行のタブの解析では、この関数が**55万回**呼ばれていた
    （`weighted_edit_distance` の中から）。控えを付けるだけで
    解析が体感で変わる（2026-08-11・うにさんから
    「1000行あると待ち時間が長い」の指摘）。
    """
    base_distance=_intrusion_base_distance if intrusion else _base_distance
    if c1 == c2:
        return 0.0

    # Shift changes kana output on one physical key (including わ / を).
    if same_physical_key(c1,c2):
        return 0.3

    # A different base key may not also change Shift state. The user
    # excludes small ゅ -> large よ; composing Shift and a neighbor slip
    # must not bring it back. Same-key Shift repairs are handled above.
    # 面（JIS: Shift の有無。親指シフト: 単独・左親指・右親指）が違う
    # 2字は、キーも違えば2回の誤り。JIS では _SHIFT_KANA の判定と同じ。
    if _LAYER_OF.get(c1, '') != _LAYER_OF.get(c2, ''):
        return FAR

    # 位置の表に**そのまま載っている字はそのキー**で測る。載っていない
    # 濁音・半濁音（JIS・新JIS）は清音キー＋印に開く。親指シフトでは
    # 濁音も表に載っている（ぽ は い のキー）ので五十音の表で引き直さない。
    base1 = c1 if c1 in KANA_POSITIONS else DAKUTEN_BASE.get(c1, c1)
    base2 = c2 if c2 in KANA_POSITIONS else DAKUTEN_BASE.get(c2, c2)
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
        return base_distance('゛', '゜')

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
        d = base_distance(base1, base2)
        if d >= FAR:
            return FAR
        if not _MARK_TWO_STROKE and has_mark1 != has_mark2:
            return d + 0.4          # 旧: 印の違いを 0.4 で済ませる
        # 濁点が両方に付いている場合のわずかな上乗せ（従来どおり）。
        return d + (0.1 if has_mark1 else 0.0)

    return base_distance(c1, c2)


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

    現行の打ち間違いは同じ段の左右だけ。゛の左はせ、右は゜。
    ゜の左は゛。上下・斜めは巻き込み専用の範囲を使う。

    **並べ直して返す**（集合を経由しても順序が動かないように。
    項目48-DR「起動ごとに答えが変わる」の再発防止）。
    """
    out = []
    if not marks_are_keys():        # 親指シフト: 濁音は印のキーで打たない
        return ()
    for c in ALL_KANA:
        if c == mark or c in ('゛', '゜'):
            continue
        # 同じキーの別の面（新JIS の ゛ と わ）は隣ではなく Shift の話。
        # 面が違う隣（Shift が要る字）は、印を狙って隣を叩いた1回の誤りでは
        # 出ない（JIS では ゛゜ の段に Shift の字が無いので同じ答え）。
        if same_physical_key(c, mark) or _LAYER_OF.get(c, '') != _LAYER_OF.get(mark, ''):
            continue
        if _base_distance(c, mark) <= max_dist:
            out.append(c)
    return tuple(sorted(out))


def mark_slip_enabled():
    """測定用の既存設定を、芯と語彙木で共用する。"""
    return os.environ.get('CN_MARK_SLIP','1') != '0'


@functools.lru_cache(maxsize=_cache_size(2048))
def mark_slip_candidates(base, pressed, max_dist=1.05):
    """48-XO: 清音＋隣接キーを、清音＋濁点/半濁点の1打置換として読む。"""
    if base in MARK_OF or len(keystrokes(pressed)) != 1:
        return ()
    out=[]
    for marked, plain in DAKUTEN_BASE.items():
        if plain != base:
            continue
        mark=MARK_OF.get(marked)
        if not mark or pressed == mark:
            continue  # 表記の結合であり、隣接誤打ではない（印のキーが無い配列は空）。
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


def clear_caches():
    """位置・隣接に依る控え（lru_cache）を全部捨てる（項目48-KB）。

    配列か形を変えたとき `keyboard_layout.apply` が呼ぶ。ふだんは1度も
    呼ばれない（既定のまま使う人には何も起きない）。

    **他のモジュールが持つ、かなの位置に依る控え**も捨てる（控えが残ると
    切り替えた前の配列で答える）。読み込まれていないモジュールには
    控えも無いので、`sys.modules` に在るものだけ触る。
    """
    for fn in (intrusion_key_distance, multiple_key_drop_adjacency,
               _base_distance, _intrusion_base_distance, kana_key_distance,
               _romaji_pairs, nearby_candidates, mark_key_neighbors,
               mark_slip_candidates):
        fn.cache_clear()
    import sys
    for name, attrs in _FOREIGN_CACHES:
        mod = sys.modules.get(name)
        if mod is None:
            continue
        for attr in attrs:
            obj = getattr(mod, attr, None)
            if obj is None:
                continue
            if hasattr(obj, 'cache_clear'):
                obj.cache_clear()
            elif isinstance(obj, dict):
                obj.clear()
    mod = sys.modules.get('vocabulary')
    if mod is not None and hasattr(mod, '_CHAR_FLOOR'):
        mod._CHAR_FLOOR = None


# かなの位置・距離から作った控えを持つ他のモジュール（名前, 属性）。
# lru_cache なら cache_clear、辞書なら clear。
_FOREIGN_CACHES = (
    ('contextual_repair', ('_key_neighbors', 'sahen_omission_repairs',
                           '_cached_whole_written_nominal_omissions')),
    ('vocabulary', ('_sub_cost', '_SIM_CACHE', '_FLEX_CACHE')),
)


# ============================================================
# かな配列の選択（項目48-KB・かな配列・2026-10-14）
# ============================================================
# うにさんの指定（2026-10-14・カードで「用意する」）: かな入力の配列として
# **親指シフト（NICOLA）** と **新JIS（JIS X 6004）** を選べるようにする。
# 既定は JIS で、選ばなければ上の表は1字も動かない。
#
# 配列ごとに違うもの:
#
#   位置          どのキーにどのかなが刻まれているか（KANA_POSITIONS）
#   面            JIS・新JIS は Shift の有無（'' / 'S'）。親指シフトは
#                 単独・左親指・右親指の3面（'' / 'L' / 'R'）。
#                 **面が違い、キーも違う2字は2回の誤り**（FAR）。
#                 同じキーの別の面は Shift（親指）の押し違い（0.3）。
#   濁音の打鍵    JIS・新JIS は 清音＋゛（2打。新JIS の ゛ は中段の L、
#                 ゜ は Shift＋W）。**親指シフトは濁音・半濁音も1打**
#                 （反対の手の親指と同時に押す＝クロスシフト）なので
#                 MARK_OF は空、keystrokes は1つ、印の隣の誤り
#                 （mark_key_neighbors・mark_slip_candidates）は出ない。
#   Shift の隣    JIS: 左 Shift の隣 つ・右 Shift の隣 ろ。新JIS: す・れ。
#                 親指シフト: 親指キー（無変換・変換）の上の ふ へ／め そ。
#
# 表の出どころ:
#   NICOLA  親指シフト道場「親指シフト入力のキーボードレイアウト」
#           （forum.pc5bai.com/work/oya/layout/）の段ごとの一覧と、
#           NICOLA 規格書の例（は のキー: 右親指で み、左親指で ぱ 系）。
#           ぱぴぷぺぽ は ら・，・め・ね・い のキーを左親指と同時に押す
#           （Wikipedia「親指シフト」の記述と一致）。
#   新JIS   JIS X 6004 の無シフト面（Wikipedia「新JIS配列」の候補1の表＝
#           採用された配列）と、シフト面（新JIS の解説記事・
#           maborotopia の親指新JIS の左親指面と一致）。
#
# 半角の表（halfwidth.HALFWIDTH_TO_KANA / SHIFT_TO_KANA）は
# `halfwidth_tables()` を `on_kana_layout_change` で受け取って追う。

KANA_LAYOUTS = ('jis', 'nicola', 'shin_jis')
DEFAULT_KANA_LAYOUT = 'jis'
_KANA_LAYOUT = DEFAULT_KANA_LAYOUT
_kana_listeners = []

# 刻印の表（JIS の記号キーと同じ物理キーに乗せる）。
# 段ごとに (段番号, 面ごとの字の並び…)。並びの n 文字目が列 n のキー。
# 全角空白は「その面に字が無い」。かな以外（。．，・？）は位置の表には
# 入れず、同じキーの文字の表（same_key_characters）にだけ載せる。
_NICOLA_ROWS = (
    #    単独                     左親指                   右親指
    (1, '。かたこさらちくつ，', 'ぁえりゃれぱぢぐづぴ', '゜がだござよにるまぇ'),
    (2, 'うしてけせはときいん', 'をあなゅもばどぎぽ　', 'ゔじでげぜみおのょっ'),
    (3, '．ひすふへめそねほ・', 'ぅーろやぃぷぞぺぼ゛', '　びずぶべぬゆむわぉ'),
)
_SHIN_JIS_ROWS = (
    #    無シフト                  シフト
    (1, 'そけせてょつんのをりち', 'ぁ゜ほふめひえみやぬ　'),
    (2, 'はかしとたくうい゛きな', 'ぃへらゅよまおもわゆ　'),
    (3, 'すこにさあっる、。れ',   'ぅぇぉねゃむろ・ー？'),
)
_KANA_LAYOUT_TABLES = {
    'nicola': {'rows': _NICOLA_ROWS, 'layers': ('', 'L', 'R'), 'marks': False,
               'shift_neighbors': {'left': frozenset('ふへ'),
                                   'right': frozenset('めそ')}},
    'shin_jis': {'rows': _SHIN_JIS_ROWS, 'layers': ('', 'S'), 'marks': True,
                 'shift_neighbors': {'left': frozenset('す'),
                                     'right': frozenset('れ')}},
}

# JIS のキーの表を段ごとに切る（半角の刻印を位置から引くため）。
# 数字段 13・上段 12・中段 12・下段 11。
_JIS_ROW_LENGTHS = (13, 12, 12, 11)
_JIS_KEY_AT = {}
_i = 0
for _row, _n in enumerate(_JIS_ROW_LENGTHS):
    for _col in range(_n):
        _JIS_KEY_AT[(_row, _col)] = _JIS_KEYS[_i]
        _i += 1
assert _i == len(_JIS_KEYS)

# いまのかな配列のキーの表（same_key_characters が引く）。
_KEYS = list(_JIS_KEYS)
# 同じキーの別の面のかな（かな → 組）。JIS では SHIFT_KANA_PAIR と同じ中身。
_SAME_KEY_ALTS = {}


def _is_kana_char(ch):
    return bool(ch) and ('ぁ' <= ch <= 'ゖ' or ch in 'ー゛゜')


def _generated_layout(table):
    """刻印の段の並びから 位置・面・キーの表・Shift の相方 を作る。"""
    layers = table['layers']
    positions, layer_of, keys, pair = {}, {}, [], {}
    for col in range(_JIS_ROW_LENGTHS[0]):          # 数字段: 数字と記号だけ
        plain, shift = _JIS_KEY_AT[(0, col)][:2]
        keys.append((plain, shift) + ('',) * len(layers))
    for row, *faces in table['rows']:
        for col in range(_JIS_ROW_LENGTHS[row]):
            plain, shift = _JIS_KEY_AT[(row, col)][:2]
            chars = []
            for face in faces:
                ch = face[col] if col < len(face) else ''
                chars.append('' if ch in (' ', '　') else ch)
            keys.append((plain, shift) + tuple(chars))
            for layer, ch in zip(layers, chars):
                if _is_kana_char(ch) and ch not in positions:
                    positions[ch] = (row, col)
                    layer_of[ch] = layer
            unshifted = chars[0]
            shifted = [ch for ch in chars[1:] if _is_kana_char(ch)]
            for ch in shifted:
                if unshifted:
                    pair.setdefault(ch, unshifted)
            if _is_kana_char(unshifted) and shifted:
                pair.setdefault(unshifted, shifted[0])
    layer_of = {c: l for c, l in layer_of.items() if l}
    return positions, layer_of, keys, pair


def current_kana_layout():
    return _KANA_LAYOUT


def marks_are_keys():
    """濁点・半濁点を**印のキー**で打つ配列か（JIS・新JIS は真、親指シフトは偽）。"""
    return bool(MARK_OF)


def kana_layer(kana):
    """字の面（'' 単独・'S' Shift・'L' 左親指・'R' 右親指）。"""
    return _LAYER_OF.get(kana, '')


def same_key_kana_alternatives(kana):
    """同じ物理キーの**別の面**のかな（JIS: あ→(ぁ,)・わ→(を,)。親指シフト: か→(え, が)）。"""
    return _SAME_KEY_ALTS.get(kana, ())


def halfwidth_tables():
    """半角のまま打ったときの表（半角 → かな, Shift つき半角 → かな）。

    JIS では None（halfwidth.py の書き下しをそのまま使う）。他の配列では
    無シフトの面を半角から、Shift 面を Shift つきの半角から引く。親指シフトの
    親指の面は IME が切れていると出ないので、無シフトの面だけ。
    """
    if _KANA_LAYOUT == DEFAULT_KANA_LAYOUT:
        return None
    plain, shift = {}, {}
    for key in _KEYS:
        ascii_plain, ascii_shift, *kanas = key
        if kanas and _is_kana_char(kanas[0]):
            plain.setdefault(ascii_plain, kanas[0])
        if len(kanas) > 1 and _LAYER_OF.get(kanas[1]) == 'S' and _is_kana_char(kanas[1]):
            shift.setdefault(ascii_shift, kanas[1])
    return plain, shift


def on_kana_layout_change(callback):
    """かな配列が変わったら呼んでほしい側（halfwidth）が登録する。すぐ1回呼ぶ。"""
    if callback not in _kana_listeners:
        _kana_listeners.append(callback)
    callback()


def _install_tables(positions, layer_of, keys, pair, marks, shift_neighbors):
    global _SHIFT_KANA
    KANA_POSITIONS.clear()
    KANA_POSITIONS.update(positions)
    _LAYER_OF.clear()
    _LAYER_OF.update(layer_of)
    _SHIFT_KANA = frozenset(layer_of)
    SHIFT_KANA_PAIR.clear()
    SHIFT_KANA_PAIR.update(pair)
    MARK_OF.clear()
    MARK_OF.update(marks)
    _SHIFT_NEIGHBORS.clear()
    _SHIFT_NEIGHBORS.update(shift_neighbors)
    ALL_KANA[:] = list(dict.fromkeys(list(KANA_POSITIONS) + list(DAKUTEN_BASE)))
    _KEYS[:] = keys
    _KEY_OF_CHAR.clear()
    for key in _KEYS:
        for ch in key:
            if ch and ch not in _KEY_OF_CHAR:
                _KEY_OF_CHAR[ch] = key
    _SAME_KEY_ALTS.clear()
    by_pos = {}
    for ch, pos in KANA_POSITIONS.items():
        by_pos.setdefault(pos, []).append(ch)
    for ch, pos in KANA_POSITIONS.items():
        # 印のキー（親指シフトの Q・／ のクロス面）は「別の面の字」に数えない
        others = tuple(c for c in by_pos[pos] if c != ch and c not in '゛゜')
        if others and ch not in '゛゜':
            _SAME_KEY_ALTS[ch] = others


def set_kana_layout(name):
    """かな配列を変える。変わったら真。知らない名前は JIS。

    `keyboard_layout.apply` から呼ばれる（設定の 'kana_layout'）。
    """
    global _KANA_LAYOUT
    if name not in KANA_LAYOUTS:
        name = DEFAULT_KANA_LAYOUT
    if name == _KANA_LAYOUT and _SAME_KEY_ALTS:
        return False
    changed = name != _KANA_LAYOUT
    _KANA_LAYOUT = name
    if name == DEFAULT_KANA_LAYOUT:
        _install_tables(_JIS_KANA_POSITIONS, {c: 'S' for c in _JIS_SHIFT_KANA},
                        list(_JIS_KEYS), _JIS_SHIFT_KANA_PAIR, _JIS_MARK_OF,
                        _JIS_SHIFT_NEIGHBORS)
    else:
        table = _KANA_LAYOUT_TABLES[name]
        positions, layer_of, keys, pair = _generated_layout(table)
        _install_tables(positions, layer_of, keys, pair,
                        _JIS_MARK_OF if table['marks'] else {},
                        table['shift_neighbors'])
    if changed:
        clear_caches()
        for callback in list(_kana_listeners):
            callback()
    return changed


# 既定（JIS）の表を同じ道で据える（_SAME_KEY_ALTS を作る。中身は1字も動かない）。
set_kana_layout(DEFAULT_KANA_LAYOUT)
