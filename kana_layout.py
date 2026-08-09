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

import math

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

# 距離計算の対象になる全かな
ALL_KANA = list(KANA_POSITIONS.keys()) + list(DAKUTEN_BASE.keys())
ALL_KANA = list(dict.fromkeys(ALL_KANA))  # 重複除去（順序保持）

FAR = 99.0  # 「押し間違えとは考えにくい」を表す値


def _euclid(p1, p2):
    if p1 is None or p2 is None:
        return FAR
    # 段ごとの横ずれを加味した実座標に直してから距離を測る
    x1 = p1[1] + ROW_OFFSET.get(p1[0], 0.0)
    x2 = p2[1] + ROW_OFFSET.get(p2[0], 0.0)
    return math.hypot(p1[0] - p2[0], x1 - x2)


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


def kana_key_distance(c1, c2):
    """
    2つのかな文字の「押し間違えやすさ」を距離で返す。
    0 に近いほど間違えやすい。FAR(99) は無関係。
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
    has_mark1 = c1 in DAKUTEN_BASE
    has_mark2 = c2 in DAKUTEN_BASE

    # 同じキーで濁点の有無だけが違う（例: か <-> が, は <-> ぱ）
    if base1 == base2 and has_mark1 != has_mark2:
        return 0.4

    # ベースキーが違う場合: ベース同士の物理距離 + 濁点差分のコスト
    if base1 != base2:
        d = _base_distance(base1, base2)
        if d >= FAR:
            return FAR
        if has_mark1 != has_mark2:
            penalty = 0.4
        elif has_mark1 and has_mark2:
            penalty = 0.1
        else:
            penalty = 0.0
        return d + penalty

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


@functools.lru_cache(maxsize=512)
def nearby_candidates(char, max_dist=1.6, include_phonetic=True):
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
    for c in ALL_KANA:
        d = kana_key_distance(char, c)
        if d <= max_dist:
            scored[c] = d

    if include_phonetic:
        for c, d in phonetic_candidates(char):
            # キー距離でも拾えている場合は近いほうを採用
            if c not in scored or d < scored[c]:
                scored[c] = d

    result = sorted(scored.items(), key=lambda x: x[1])
    return result


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
