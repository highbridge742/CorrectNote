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
**最後にどの変換をしたか、1枠だけ覚える**（項目48-QH・2026-09-05）。

うにさんの指定（2026-09-05）:

    「変換の根拠に、履歴が影響した、履歴に何回あったという表示が
      ありました。**履歴として記録されることをユーザは望みません。**
      人に見られたくないデータが保存されている。
      この回数を記録する仕組みを削除します。
      代わりに同音異義語の一覧表を作成し、**最後にどの変換をしたか、
      それぞれ履歴1回分記録します。**
      同音異義語ではない単語の回数は残しません」

### 持つもの（`last_choice.json`）

    {"readings": {読み: 最後に選んだ表記, ...},
     "units":    {元の語: 最後に選んだ表記, ...}}

**それだけ。** 回数も、時刻も、前後の文脈も持たない。
上書きしかしないので、**書いた本人が読んでも「いつ・何回」は分からない**。

    readings … 同音異義語の読みだけ（`homophones.is_homophone_reading`）。
               `こうえん` を `講演` に選んだ → 次から `こうえん` は `講演`
    units    … 選び直しの1件（旧 `choices.json` の畳んだ姿）。
               画面で `たんご → 単語` と選び直したら `単語`

### 何を捨てたか（うにさんの裁可済み・指示書 §2.4）

旧 `choices.json` は **前後の語**とセットで覚えていたので、
「明日のこうえん＝公園／大学のこうえん＝講演」を**文脈ごとに**
覚え分けられた。**その記憶は消える**——「それぞれ履歴1回分」の帰結。
文脈の判断そのものは `homophone_pairs.py`（AI が焼いた対の表）と
文脈の点が引き続き担う。

### 自動補正の結果では更新しない

エンジンが自分で決めた変換をここへ書き戻すと、**自分の答えを自分で
補強する**（`context_vec` が誤変換の議論から共起を育てて壊した
項目48-IQ と同じ形）。書き込む口は3つだけ:

    ① IME の確定（本人がそう変換した）
    ② 候補一覧での選び直し（本人がそう選んだ）
    ③ 「覚える」ダイアログ（本人がそう指定した）
"""

import json
import os


# ============================================================
# **いま効いている枠**（差し込む口はここ1か所・項目48-QH）
# ============================================================
#
# `kanji_guess.set_ime_readings_provider`（項目48-HA）と同じ形。
# 枠を読む場所は `vocabulary.lookup` の並びと corrector の同音の道の
# 2か所あるが、**どちらも同じ1本を通す**（学び22——片方だけに置くと、
# そちらを迂回して素通りする／48-GN——同じ判定を2回書くと食い違う）。
#
# 差すのは `app.py` の起動処理だけ。**測る道具は差さない**ので、
# 初期状態の測定は今までどおり枠の影響を受けない。
_ACTIVE = None


def set_active(store):
    """このプロセスで効かせる枠を差す（`None` で外す）。"""
    global _ACTIVE
    _ACTIVE = store


def active():
    return _ACTIVE


def frame_revision():
    """
    **いま効いている枠が変わった回数**（枠が無ければ 0）。

    `loanword` の控えは語彙の版だけを見ていたので、**本人が選び直しても
    直し先の表が古いまま**だった（項目48-QQ・`cachecheck.py` 第2節）。
    引き当ての内側から呼ばれるので**例外を外へ出さない**。
    """
    st = _ACTIVE
    if st is None:
        return 0
    try:
        return st.revision()
    except Exception:
        return 0


def surface_for_reading(reading):
    """
    **その読みで最後に選んだ表記**（枠が差されていなければ None）。

    引き当ての内側から呼ばれるので**例外を外へ出さない**。
    """
    st = _ACTIVE
    if st is None or not reading:
        return None
    try:
        return st.surface_for_reading(reading)
    except Exception:
        return None


class LastChoiceStore:
    """最後に選んだ表記を、読みごと・語ごとに1枠だけ持つ。"""

    def __init__(self, path=None):
        self.path = path
        self._readings = {}
        self._units = {}
        # 枠が変わった回数（項目48-QQ）。`loanword` の控えの見分けに使う
        # ——語彙が動かなくても**枠が変われば直し先の中身は変わる**。
        self._revision = 0
        # 同音異義語かを判定する材料（`bind` で渡す）。
        # **持ち回らないと、呼ぶ側 20 か所に引数が生える**（学び22 の
        # 「同じことを2か所に書かない」）。
        self._store = None
        self._dict_index = None
        if path and os.path.exists(path):
            self.load()

    def bind(self, store=None, dict_index=None):
        """同音異義語の判定に使う材料を預ける（app が起動時に1度）。"""
        if store is not None:
            self._store = store
        if dict_index is not None:
            self._dict_index = dict_index

    # ------------------------------------------------------------
    # 覚える
    # ------------------------------------------------------------
    def record(self, original, chosen, reading=None, prev=None, next=None):
        """
        旧 `ChoiceStore.record` と同じ呼び方の口（`prev`/`next` は見ない）。

        戻り値: 何か書いたら True（旧 `record` は「新規なら True」を
        返していたが、読んでいる側は無い）。
        """
        return self.remember(original, chosen, reading)

    def remember(self, original, chosen, reading=None,
                 store=None, dict_index=None):
        """
        **本人が選んだ表記**を覚える（上書き）。

        `original` は選び直しの元の語（無ければ None でよい）。
        `reading` がその表記の読みで、**同音異義語の読みなら**
        読みの枠も更新する。

        戻り値: 何か書いたら True。
        """
        if not isinstance(chosen, str) or not chosen:
            return False
        wrote = False
        if isinstance(original, str) and original:
            if original == chosen:
                # **元の形そのものを選んだ**＝「やっぱりこれでよい」。
                # 枠を残すと、古い選び直しが効き続けてしまう
                # （`こうえん → 講演` を覚えたまま `こうえん` を選んでも
                #   画面が `講演` のままになる）。**消すのが正しい。**
                wrote = self._units.pop(original, None) is not None
            elif self._units.get(original) != chosen:
                self._units[original] = chosen
                wrote = True
        if isinstance(reading, str) and reading:
            try:
                from homophones import is_homophone_reading
                homo = is_homophone_reading(
                    reading,
                    self._store if store is None else store,
                    self._dict_index if dict_index is None else dict_index)
            except Exception:
                homo = False
            if homo and self._readings.get(reading) != chosen:
                self._readings[reading] = chosen
                wrote = True
        if wrote:
            self._revision += 1
        return wrote

    def revision(self):
        """枠が変わった回数（項目48-QQ・`loanword._store_revision`）。"""
        return self._revision

    def forget_reading(self, reading):
        gone = self._readings.pop(reading, None) is not None
        if gone:
            self._revision += 1
        return gone

    def forget_unit(self, original):
        gone = self._units.pop(original, None) is not None
        if gone:
            self._revision += 1
        return gone

    # 旧 `ChoiceStore` と同じ呼び方の口（前後の語は持たないので見ない）
    def forget(self, original, prev=None, next=None):
        return self.forget_unit(original)

    def forget_all(self, original):
        return self.forget_unit(original)

    def forget_record(self, rec):
        """一覧から選んだ1件を消す（読みの枠も語の枠もここから）。"""
        if not isinstance(rec, dict):
            return False
        if rec.get('kind') == 'reading':
            return self.forget_reading(rec.get('original'))
        return self.forget_unit(rec.get('original'))

    # ------------------------------------------------------------
    # 引く
    # ------------------------------------------------------------
    def surface_for_reading(self, reading):
        """その読みで**最後に選んだ表記**（無ければ None）。"""
        if not reading:
            return None
        return self._readings.get(reading)

    def lookup(self, original, prev=None, next=None):
        """
        その語を、本人は最後に何へ選び直したか（無ければ None）。

        `prev` / `next` は受け取るが**見ない**——前後の語は
        持たなくなった（§ 冒頭「何を捨てたか」）。呼び出し側の形を
        変えずに済むように引数だけ残してある。

        **1文字の語には返さない**（旧 `ChoiceStore` の理由のまま）。
        「し」のような1文字は文章のあらゆる場所に現れるので、
        文脈の裏付けなしに置き換えると無関係な箇所まで巻き添えになる。
        """
        if not isinstance(original, str) or len(original) <= 1:
            return None
        return self._units.get(original)

    def has(self, original):
        return original in self._units

    def originals(self):
        return list(self._units.keys())

    def readings(self):
        return dict(self._readings)

    def all_records(self):
        """
        画面（学習メニュー「補正の判断…」）と見分け（`analysis_cache`）
        のための一覧。

        **並びは決定的**（読み・語の辞書順）——控えの見分けに使うので、
        同じ中身なら必ず同じ並びになること。旧 `ChoiceStore` と同じ
        鍵（`original` / `chosen`）を持たせて、画面の側を変えずに済ませる。
        `prev` / `next` は**持たない**（前後の文脈は覚えない）。
        """
        out = []
        for rd in sorted(self._readings):
            out.append({'kind': 'reading', 'original': rd,
                        'chosen': self._readings[rd]})
        for og in sorted(self._units):
            out.append({'kind': 'unit', 'original': og,
                        'chosen': self._units[og]})
        return out

    def __len__(self):
        return len(self._readings) + len(self._units)

    # ------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------
    def save(self, path=None):
        path = path or self.path
        if not path:
            return
        data = {
            'readings': {k: self._readings[k] for k in sorted(self._readings)},
            'units': {k: self._units[k] for k in sorted(self._units)},
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
            return          # 壊れていても起動は止めない
        if not isinstance(data, dict):
            return
        self._readings = {k: v for k, v in (data.get('readings') or {}).items()
                          if isinstance(k, str) and isinstance(v, str) and v}
        self._units = {k: v for k, v in (data.get('units') or {}).items()
                       if isinstance(k, str) and isinstance(v, str) and v}
        self._revision += 1


def migrate_from_choices(choices_path, out_path, store=None,
                         dict_index=None, remove_source=True):
    """
    **旧 `choices.json` を1枠へ畳む**（項目48-QI・移行）。

    各 `original` について**いちばん新しい記録**（`updated` 最大）を
    1件だけ残す。読みが同音異義語なら読みの枠にも写す。
    畳み終わったら `choices.json` を**消す**——残すと
    「人に見られたくないデータが保存されている」ままになる
    （回数・時刻・前後の本文がそこに書いてある）。

    戻り値: (畳んだ語の数, 読みの枠の数)。元が無ければ (0, 0)。
    """
    if not choices_path or not os.path.exists(choices_path):
        return (0, 0)
    try:
        with open(choices_path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = []

    def _upd(rec):
        # `updated` が文字列でも落ちないこと。**ここで落ちると
        # 移行が途中で止まり `choices.json` が消えずに残る**＝
        # 回数も時刻も前後の本文も残ってしまう（依頼の目的に反する）。
        try:
            return float(rec.get('updated') or 0)
        except (TypeError, ValueError):
            return 0.0

    best = {}
    for rec in data if isinstance(data, list) else []:
        if not isinstance(rec, dict):
            continue
        og, ch = rec.get('original'), rec.get('chosen')
        if not isinstance(og, str) or not isinstance(ch, str) or not og \
                or not ch:
            continue
        cur = best.get(og)
        if cur is None or _upd(rec) > _upd(cur):
            best[og] = rec
    lc = LastChoiceStore(out_path if os.path.exists(out_path or '') else None)
    lc.path = out_path
    # ★★ **古い順に入れる**——`readings` は読みごとに1枠しかないので、
    # **同じ読みの語が2つ以上あると、あとに入れたほうが勝つ**。
    # 旧 `choices.json` は新しい順に並んでいる（`all_records()` が
    # `updated` の降順）ので、そのまま回すと**いちばん古い選択が
    # 読みの枠を取る**（実測で再現した）。`updated` の昇順にすれば
    # 最後に入るのがいちばん新しい選択になる。
    for og, rec in sorted(best.items(),
                          key=lambda kv: (_upd(kv[1]), kv[0])):
        lc.remember(og, rec.get('chosen'), rec.get('reading'),
                    store=store, dict_index=dict_index)
    if best:
        lc.save()
    if remove_source:
        try:
            os.remove(choices_path)
        except Exception:
            pass
    return (len(best), len(lc.readings()))
