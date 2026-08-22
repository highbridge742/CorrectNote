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

"""
**IME が知っている「表記 → 打った読み」の対の置き場**（設計25(甲)）。

うにさんの指定（2026-08-20）:

    「確定直前のひらがな情報を保持する実装を次に始めてください。
      **ひらがながあれば、読みが分かるので自動補正します**」

--------------------------------------------------------------------
 なぜ位置ではなく「対」で持つのか
--------------------------------------------------------------------

うにさんの案（2026-08-20）:

    「確定文字に、未確定状態平仮名の情報をもてば、引用で拾ったら
      その情報を渡せばよく、簡易入力であれば入力欄の入力時に
      保存すればよいです」

**位置で持つと編集でずれる。** 対で持てば位置を持たずに済み、
引用・簡易入力・アプリ内コピーは対を渡すだけになる。
実機で確かめた（項目48-GX）: **貼り付けからは読みが取れない**が、
**同じ表記を前に打っていれば対で引ける**。

--------------------------------------------------------------------
 **語彙に流してはいけない**（学び2）
--------------------------------------------------------------------

    奥悠久子帝 → おくゆくこてい

これは**誤変換そのもの**であって、正しい語ではない。語彙に入れると
次からその誤変換を守ってしまう。ここは**事実の記録**（何と打ったか）、
語彙は**正しさの記録**（何が正しいか）。**別の置き場**にして、
使うのは「漢字→読み」の**向きだけ**にすること。

    ここへ入れてよい   IME が確定した (表記, 読み) の対
    ここから出すもの   readings_for(表記) → [読み, ...]
    **してはいけない**  語彙・charngram・文脈ベクトルへ流すこと

--------------------------------------------------------------------
 置き場の形
--------------------------------------------------------------------

    ime_readings.json:
    {
      "version": 1,
      "pairs": {
        "奥悠久子帝": ["おくゆくこてい"],
        "行った":     ["おこなった", "いった"]
      }
    }

  - `pairs` の並びは**最後に打たれた順**（新しいものほど後ろ）。
    上限を超えたら**先頭から**落とす。
  - 各表記の読みは**新しい順**。**同じ読みは重ねない**
    （また打たれたら先頭へ寄せるだけ）。
  - 置き場は `app_dir()` の側（**exe の一時展開先に置かない**・
    項目48-GS。そこに置くと読むたび空・終了時に消える）。
  - **`.gitignore` に入れる。** うにさんの打った文章の断片そのもの。

--------------------------------------------------------------------
 **表記と読みが同じものは覚えない**
--------------------------------------------------------------------

うにさんの指定は「**確定したものは全部**」。ただし
`そうですね → そうですね` のように**表記と読みが1文字も違わない**
対だけは置かない。読みを引いても表記そのものが返るだけで、
**どの答えも1件も変えられない**（情報が無い）。置き場には上限が
あるので、これを入れると**効く対のほうが押し出される**。

カタカナは覚える（`パソコン → ぱそこん` は文字が違う＝情報がある）。
"""

import json
import os
import unicodedata

# 置き場の版。形を変えたら上げる（古い形は捨てて作り直す）。
VERSION = 1

# 覚える表記の上限。超えたら**古いほうから**落とす。
# 5,000 は「実機のメモ全部を打ち直しても足りる」目安
# （メモ6タブで内容語はおよそ 2,000 種）。
DEFAULT_LIMIT = 5000

# 1つの表記に覚える読みの数の上限（新しい順に残す）。
# `行った`＝いった／おこなった のように2つあるものは実在するが、
# いくつも溜まるのは打ち間違いの読みなので、浅くてよい。
DEFAULT_PER_SURFACE = 4


def reading_to_hiragana(s):
    """
    IME が返す読みを**ひらがな**に直す。

    **実機で確かめた（2026-08-20・項目48-GX）: 読みは半角カタカナで
    返る。**

        RESULTREADSTR = 'ｻﾞｲﾘｮｳ'   （6文字。**濁点が別の文字**）
                      → 'ざいりょう'（5文字）

    `morphology.katakana_to_hiragana` は**全角カタカナしか見ない**。
    半角のまま渡すと**素通しして、静かに何とも当たらなくなる**
    （項目48-DK と同じ「静かに効かない」形）。**先に NFKC で
    正規化して、濁点を合成すること。**

    確かめた: `ｵｸﾕｸｺﾃｲ`→`おくゆくこてい`／`ｻﾞｲﾘｮｳ`→`ざいりょう`／
    `ﾊﾟｿｺﾝ`→`ぱそこん`／`ﾆｭｳﾘｮｸ`→`にゅうりょく`／`ｶﾞｲﾄｳ`→`がいとう`。

    （`halfwidth.halfwidth_to_kana` は**別の道具**。あれは
    「半角英数キーを JIS かな配列で読み替える」もので、
    半角カタカナの変換ではない。）
    """
    if not s:
        return ''
    z = unicodedata.normalize('NFKC', s)
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c
                   for c in z)


def is_kana_reading(s):
    """
    読みとして受け取ってよい形か（**ひらがなだけ**か）。

    IME は変換の途中で英字や記号を返すことがある。読みとして
    使うのはひらがなの並びだけにして、それ以外は**捨てる**
    （疑わしきは覚えない。覚えた対は補正の答えを変えるため）。

    長音`ー`・小書き・`ゝゞ`は許す。`、。`や空白は許さない。
    """
    if not s:
        return False
    for c in s:
        if 'ぁ' <= c <= 'ん' or c in 'ーゝゞ゛゜':
            continue
        return False
    return True


class IMEReadings:
    """
    (表記 → 打った読み) の対の置き場。

    **補正の答えを変える置き場である。** 足したときは
    `app.py` 側で `_invalidate_analysis_cache()` を呼ぶこと
    （覚えている解析結果が古い判断のまま残る・項目48-BN と同じ形）。

    Windows 以外・IME を使っていない環境では、ただ空のまま
    （`remember` が呼ばれないだけ）。**空なら補正は今までどおり**。
    """

    def __init__(self, path=None, limit=DEFAULT_LIMIT,
                 per_surface=DEFAULT_PER_SURFACE):
        self.path = path
        self.limit = max(1, int(limit or DEFAULT_LIMIT))
        self.per_surface = max(1, int(per_surface or DEFAULT_PER_SURFACE))
        # 挿入順＝**最後に打たれた順**（Python の dict は順を保つ）
        self._pairs = {}
        self._dirty = False
        self._loaded = False
        self._existed = False    # 「まだ無い」と「0件」を分けるため

    # ---------------------------------------------------------- 読み書き

    def load(self):
        """
        置き場を読む。**無くても落ちない**（空で始まるだけ）。

        戻り値: 自分自身（続けて書けるように）
        """
        self._loaded = True
        if not self.path:
            return self
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return self
        except Exception:
            # 壊れていたら**捨てて作り直す**。ここは事実の記録なので、
            # 失うのは「前に打った読み」だけ（語彙は別の置き場）。
            return self
        self._existed = True
        pairs = None
        if isinstance(data, dict):
            if isinstance(data.get('pairs'), dict):
                pairs = data['pairs']
            elif 'version' not in data:
                pairs = data      # `pairs` を包まない形も読む
        if not isinstance(pairs, dict):
            return self
        for surface, readings in pairs.items():
            if not isinstance(surface, str) or not surface:
                continue
            if isinstance(readings, str):
                readings = [readings]
            if not isinstance(readings, (list, tuple)):
                continue
            got = []
            for r in readings:
                if isinstance(r, str) and is_kana_reading(r) \
                        and r != surface and r not in got:
                    got.append(r)
                if len(got) >= self.per_surface:
                    break
            if got:
                self._pairs[surface] = got
        self._trim()
        return self

    def save(self):
        """
        置き場を書く。**変わっていなければ何もしない。**

        戻り値: 書いたら True
        """
        if not self.path or not self._dirty:
            return False
        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'version': VERSION, 'pairs': self._pairs},
                          f, ensure_ascii=False)
            os.replace(tmp, self.path)
            self._dirty = False
            self._existed = True
            return True
        except Exception:
            return False    # 書けなくても、その回の記憶は生きている

    # ------------------------------------------------------------ 出し入れ

    def remember(self, surface, reading):
        """
        1つの対を覚える。

        surface: 確定した表記（`奥悠久子帝`）
        reading: IME が返した読み（半角カタカナでも可・ここで直す）

        戻り値: **中身が変わったら True**（呼び出し側は、そのとき
            だけ覚えている解析結果を捨てればよい）

        覚えないもの:
          - 表記か読みが空
          - 読みがひらがなだけでない（英字・記号が混じる）
          - **表記と読みが同じ**（情報が無い。上の説明を参照）
          - 極端に長いもの（1回の確定は普通そこまで長くない。
            長い塊は文節ごとに分かれて届く）
        """
        if not surface or not isinstance(surface, str):
            return False
        reading = reading_to_hiragana(reading or '')
        if not is_kana_reading(reading):
            return False
        if surface == reading:
            return False
        if len(surface) > 64 or len(reading) > 96:
            return False

        old = self._pairs.get(surface)
        if old is not None and old and old[0] == reading:
            # まったく同じ対をまた打っただけ。**並びだけ**を新しく
            # する（落とされにくくする）。答えは変わらないので
            # 覚えている解析結果は捨てなくてよい。
            self._pairs.pop(surface, None)
            self._pairs[surface] = old
            self._dirty = True
            return False

        got = [reading]
        for r in (old or ()):
            if r != reading:
                got.append(r)
        del got[self.per_surface:]
        self._pairs.pop(surface, None)
        self._pairs[surface] = got
        self._dirty = True
        self._trim()
        return True

    def readings_for(self, surface):
        """
        その表記について、**打たれた読み**を新しい順で返す。

        知らなければ空。**この向きにしか使わない**（学び2）。
        """
        if not surface:
            return []
        got = self._pairs.get(surface)
        return list(got) if got else []

    def _trim(self):
        """上限を超えたぶんを**古いほうから**落とす。"""
        over = len(self._pairs) - self.limit
        if over <= 0:
            return
        for surface in list(self._pairs)[:over]:
            self._pairs.pop(surface, None)
        self._dirty = True

    # ---------------------------------------------------------------- 諸々

    def __len__(self):
        return len(self._pairs)

    def pairs(self):
        """中身をそのまま（診断・集計用。**うにさんの文章の断片**）。"""
        return {k: list(v) for k, v in self._pairs.items()}

    def existed(self):
        """
        **置き場のファイルが在ったか。**

        「まだ無い」と「在るが0件」を分けて言うため（`probe_ime_pairs`
        の但し書きと同じ。**静かに0件と言わない**）。
        """
        return self._existed

    def stamp(self):
        """
        **解析結果の控えの見分け**に混ぜる値（項目48-BN と同じ形）。

        この置き場は**メモから育つ**ので、`ENGINE_STAMP` を上げなくても
        中身が変わる。控えたまま使うと、育つ前の判断が残る。

        戻り値: [表記の数, 読みののべ数, 中身を畳んだ値]
        """
        import zlib
        mixed = 0
        n = 0
        for surface, readings in self._pairs.items():
            n += len(readings)
            mixed ^= zlib.crc32(
                (surface + '\t' + '\t'.join(readings)).encode('utf-8',
                                                              'ignore'))
        return [len(self._pairs), n, mixed]
