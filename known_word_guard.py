# -*- coding: utf-8 -*-
# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""打った平仮名の並びの中で、格子がふだん使う漢字の名詞（きっさてん → 喫茶店・しごと → 仕事）と切れる所を、補正が別の
読みに書き換えたら（はっさてん・ごと）、その行の書き換えを採らない。

なぜ
----
正しい語を打ち違いと見て別の読みに替える直しは、紫より悪い（うにの決まり）。2026-11-21 補正担当の作り例（正しいかなの文
148 行）で、きっさてん→はっさてん・しごと→ごと・すこし→ひと のように、語として切れる並びを書き換えていた（Fable 5.2 の意見 C:
元の所が既に語で切れているなら触らない）。

どうやって
----------
既存のファイルは変えない。install() が correction_entry.correct_line を外から包む（かな入力の行だけ）。
1. 打った行の平仮名の並びを格子（reading_lattice.best）で切り、読み3字以上の名詞で、ふだん使う漢字の表記
   （last_keystroke の置き方の候補と身近さの門）がある語の所を「守る語」とする。
2. 答えの読み（解析の読み）を打った行と比べ、読みの替わった所が守る語の中にあれば、その行は打った行のまま返す。
   紫は打った行の紫（入口の紫）を残す。守る語の中でない書き換え（ほかの所の打ち違いの直し）は今まで通り。
切り替え: 2026-11-22 から既定で止める（CN_KNOWN_WORD_GUARD=1 で使う）。後から入れた rival_exit_guard が同じ誤りを
紫にし、こちらは格子が誤りから切った語（ひ｜らん の 欄・もみ の 籾）を守って、前は直っていた行（うに 147・167・197 行の
報告）を戻していた。止めても、作り例でこちらが戻していた誤った書き換え 12 行は rival_exit_guard が紫にした。
特定の語や文字列には合わせない。
"""
import difflib
import functools
import os
import re

_orig = {}
_HIRA = re.compile('[ぁ-ゖー]{3,}')
_KT = {c: c - 0x60 for c in range(0x30A1, 0x30F7)}


def _reading(text):
    from morphology import tokenize
    return ''.join((t.reading if t.has_reading else t.surface) for t in tokenize(text)).translate(_KT)


def _kept_words(line, store, dict_index):
    """[(start, end)] 打った行の中の、格子がふだんの漢字の名詞と切る所"""
    import reading_lattice as lat
    import last_keystroke as LK
    out = []
    for m in _HIRA.finditer(line):
        r = lat.best(m.group())
        if r is None or not r.words:
            continue
        at = m.start()
        ws = list(r.words)
        for k, (face, rd, pos, _ed) in enumerate(ws):
            s, e = at, at + len(rd)
            at = e
            if pos != '名詞' or len(rd) < 2 or not any('一' <= c <= '鿿' for c in face):
                continue
            # 語が文節の中で1つで立っている（すぐ後ろが助詞・助動詞）ときだけ守る。後ろに別の名詞が続く切り方（いてん｜さつ）
            # や並びの終わりの語（おくりま｜はた の 端）は格子の読みが怪しい。表記は漢字だけの名詞（削い のような送りの付く
            # 表記は除く）
            if k + 1 >= len(ws) or ws[k + 1][2] not in ('助詞', '助動詞'):
                continue
            if not all('一' <= c <= '鿿' or c in '々ヶ' for c in face):
                continue
            try:
                faces = LK._kanji_choices(rd, store, dict_index)
            except Exception:
                faces = []
            if face in faces[:3] and not LK._not_everyday_kango(face):
                out.append((s, e, tuple(faces[:3])))
        if at != m.end():
            return []
    return out


def guard(line, result, store, dict_index):
    if os.environ.get('CN_KNOWN_WORD_GUARD') != '1' or not isinstance(result, dict):
        return result
    out = result.get('corrected') or line
    if out == line or not _HIRA.search(line):
        return result
    try:
        rd = _reading(out)
        ops = [o for o in difflib.SequenceMatcher(None, line, rd, autojunk=False).get_opcodes() if o[0] != 'equal']
        if not ops:
            return result
        kept = _kept_words(line, store, dict_index)
    except Exception:
        return result
    # 守る語が答えのどこにも（読みのかなでも漢字の表記でも）残っていなければ、書き換えに消された語。解析の読みの違い
    # （明日＝あす）で読みの比べが外れても、語が残っていれば書き換えではない
    words = [(s, e) for s, e, faces in kept
             if line[s:e] not in out and not any(f in out for f in faces)
             and any(s <= o[1] and max(o[2], o[1] + 1) <= e for o in ops)]
    if not words:
        return result
    back = dict(result)
    back.update({'corrected': line, 'changed': False, 'spans': [], 'original_spans': [], 'details': []})
    # 紫は守った語に掛からないものだけ残す（守った語は正しい語）
    # 補正は打ち違いと見たので、守った語の所は紫にする（迷ったら紫。格子が誤りから出来た語を読んだこともある: ほぞ｜しんて）
    odd = [tuple(x[:2]) for x in result.get('odd_spans') or () if not any(x[0] < e and s < x[1] for s, e in words)]
    why = [tuple(x) for x in result.get('odd_reasons') or () if not any(x[0] < e and s < x[1] for s, e in words)]
    for s, e in words:
        odd.append((s, e))
        why.append((s, e, '直し先を決められず元の語に戻しました。打ち違いかもしれません'))
    # 守る語の外の書き換えも一緒に戻したので、その所は紫にする（打ち違いの直しを捨てたまま紫も無い行にしない）
    for o in ops:
        if not any(s <= o[1] and max(o[2], o[1] + 1) <= e for s, e in words):
            a_, b_ = o[1], max(o[2], o[1] + 1)
            if not any(x[0] < b_ and a_ < x[1] for x in odd):
                odd.append((a_, b_))
                why.append((a_, b_, '直し先を決められず元の語に戻しました。打ち違いかもしれません'))
    for i, ch in enumerate(line):
        if ch in '゛゜' and not any(x[0] <= i < x[1] for x in odd):
            odd.append((i, i + 1))
            why.append((i, i + 1, '直前の文字に付かない濁点・半濁点が語の途中に残っています'))
    back['odd_spans'] = sorted(odd)
    back['odd_reasons'] = why
    return back


def correct_line(line, store, *a, **k):
    r = _orig['correct_line'](line, store, *a, **k)
    if os.environ.get('CN_KNOWN_WORD_GUARD') != '1' or not isinstance(line, str):
        return r
    im = k.get('input_method', a[2] if len(a) > 2 else 'kana')
    if im != 'kana':
        return r
    di = k.get('dict_index', a[4] if len(a) > 4 else None)
    return guard(line, r, store, di)


def install():
    if _orig or os.environ.get('CN_KNOWN_WORD_GUARD') == '0':
        return bool(_orig)
    import correction_entry
    _orig['correct_line'] = correction_entry.correct_line
    functools.update_wrapper(correct_line, _orig['correct_line'])
    correction_entry.correct_line = correct_line
    return True


def uninstall():
    if not _orig:
        return
    import correction_entry
    correction_entry.correct_line = _orig.pop('correct_line')
