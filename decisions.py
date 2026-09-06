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
ユーザーが明示した「これは正しい」「これは誤りだ」という判断の記憶。

補正エンジンは統計と辞書だけで動くため、
固有名詞・俗語・専門語（「縦シュー」など）を誤って補正することが避けられない。
取りこぼしは我慢できるが、正しく書いたものを毎回壊されるのは我慢できない。

そこでユーザーが補正結果をクリックして
「この補正は不要だ」と伝えられるようにし、その判断をここに残す。
一度伝えた判断は二度と覆らない。

補正エンジン側からの問い合わせ口は blocks() ひとつだけにしてある。
（判断経路を増やさないという設計方針のため。SPEC.md 参照）

保存形式 (decisions.json):
    {
      "rejected":  [{"original": "縦シュー", "corrected": "縦周", ...}, ...],
      "protected": [{"word": "縦シュー", ...}, ...]
    }
"""

import json
import os
import time


class DecisionStore:
    """
    ユーザーの判断を覚えておく。

    2種類ある:

    rejected  この置換をやめる（元の語 → 補正後の語 の組で覚える）
              「この補正は不要」とだけ言われた場合。
              同じ語に対する別の補正までは禁じない。

    protected この語には今後いっさい触らない（元の語だけで覚える）
              「これは正しい語だ」と言われた場合。
              固有名詞・俗語を登録するのに使う。
    """

    def __init__(self, path=None):
        self.path = path
        # (original, corrected) -> 記録
        self._rejected = {}
        # word -> 記録
        self._protected = {}
        # word -> 記録。**紫を下げるだけ**（補正は止めない・項目48-QU）
        self._odd_only = {}
        if path and os.path.exists(path):
            self.load()

    # ------------------------------------------------------------
    # 記録する
    # ------------------------------------------------------------
    def reject(self, original, corrected):
        """この置換（original → corrected）を今後行わない。"""
        if not original or not corrected:
            return False
        key = (original, corrected)
        if key in self._rejected:
            return False
        self._rejected[key] = {
            'original': original,
            'corrected': corrected,
            'added': time.time(),
        }
        return True

    def protect(self, word):
        """この語には今後いっさい触らない。"""
        # 1文字の語を守ると、それを含む広い範囲まで巻き添えで
        # 補正できなくなるため受け付けない
        if not word or len(word) < 2:
            return False
        if word in self._protected:
            return False
        self._protected[word] = {'word': word, 'added': time.time()}
        return True

    def leave_odd_alone(self, word):
        """
        **この文字列に紫を付けない**（補正は止めない・項目48-QU）。

        `protect` とは別の台帳にする。理由は、**入口が違うから**:

            `protect`          候補一覧の「今後直さない」
                               → 食わせるのは**打ち間違いの塊**
                               （`奥悠久子帝` のような、その人しか
                               打たない並び）
            `leave_odd_alone`  紫の右クリック「この文字列は正しい」
                               → 食わせるのは**日本語として真っ当な
                               短い並び**

        `blocks()` は**部分一致**で止める（`縦シュー` を守ったら
        `縦シューが` も止める）。そこへ真っ当な2〜3字を入れると、
        **それを含む行の補正が全部止まる**。紫の範囲は
        `oddness.odd_spans` が返す形態素の連なりなので、
        **2字の断片がふつうに出る**。

        だから**紫を下げる口（`left_alone_texts`）にだけ混ぜて、
        補正を止める口（`blocks`）からは見ない**。
        利用者の意図（「紫が邪魔」）とも、そちらのほうが合う。
        """
        if not word or len(word) < 2:
            return False
        if word in self._odd_only or word in self._protected:
            return False
        self._odd_only[word] = {'word': word, 'added': time.time()}
        return True

    # ------------------------------------------------------------
    # 取り消す
    # ------------------------------------------------------------
    def unreject(self, original, corrected):
        return self._rejected.pop((original, corrected), None) is not None

    def unprotect(self, word):
        gone = self._protected.pop(word, None) is not None
        return self._odd_only.pop(word, None) is not None or gone

    # ------------------------------------------------------------
    # 問い合わせ（補正エンジンからはここだけを見る）
    # ------------------------------------------------------------
    def blocks(self, original, corrected):
        """
        この置換（original → corrected）は、ユーザーの判断により
        禁じられているか。

        補正エンジンからの唯一の問い合わせ口。
        判断の理由（reject か protect か）は呼び出し側に見せない。
        """
        if (original, corrected) in self._rejected:
            return True
        # 守るべき語が置換範囲に含まれているなら触らせない。
        # 「縦シュー」を守った場合、「縦シューが」のように
        # 助詞を巻き込んだ範囲の補正も止める必要がある。
        for word in self._protected:
            if word in original:
                return True
        # `_odd_only` は**見ない**（項目48-QU）。あれは紫を下げる
        # だけの台帳で、補正を止める判断ではない。
        return False

    def is_protected(self, word):
        return word in self._protected

    def left_alone_texts(self):
        """
        **「もう直さない」と決められた文字列**（2026-08-28・
        うにさんの指定「候補の一番下から、もう直さないと選択学習
        したものは、**紫の色がつかないように**して」）。

        候補一覧のいちばん下の2つが、どちらもこの意味になる:

            「この補正は不要（X のまま）」   → reject（X のまま）
            「「X」は今後直さない」          → protect

        **紫は「異様だと判定した」という印**（CLAUDE.md ★★）なので、
        うにさんが「これでよい」と決めた文字列に立て続けるのは、
        判定としても間違っている。**決めた側が上**。

        使うのは `corrector._odd_spans_for_line`。
        """
        out = set(self._protected) | set(self._odd_only)
        for original, _corrected in self._rejected:
            if original:
                out.add(original)
        return out

    def is_rejected(self, original, corrected):
        return (original, corrected) in self._rejected

    # ------------------------------------------------------------
    # 一覧・保存
    # ------------------------------------------------------------
    def rejected_list(self):
        return sorted(self._rejected.values(),
                      key=lambda e: e.get('added', 0), reverse=True)

    def protected_list(self):
        return sorted(self._protected.values(),
                      key=lambda e: e.get('added', 0), reverse=True)

    def odd_only_list(self):
        return sorted(self._odd_only.values(),
                      key=lambda e: e.get('added', 0), reverse=True)

    def __len__(self):
        return (len(self._rejected) + len(self._protected)
                + len(self._odd_only))

    def save(self, path=None):
        path = path or self.path
        if not path:
            return
        data = {
            'rejected': self.rejected_list(),
            'protected': self.protected_list(),
            'odd_only': self.odd_only_list(),
        }
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    def load(self, path=None):
        path = path or self.path
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            # 壊れていても起動を止めない。判断が消えるだけ。
            return
        self._rejected.clear()
        self._protected.clear()
        self._odd_only.clear()
        for e in data.get('rejected', []):
            o, c = e.get('original'), e.get('corrected')
            if o and c:
                self._rejected[(o, c)] = e
        for e in data.get('protected', []):
            w = e.get('word')
            if w:
                self._protected[w] = e
        for e in data.get('odd_only', []):
            w = e.get('word')
            if w and w not in self._protected:
                self._odd_only[w] = e
