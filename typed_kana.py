# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""打鍵の記録（stroke_keys・shift_slip が確定ごとに残す、押したキーの字と時刻・Shift を押していた間）から、打ったかなを作る
（2026-11-22 02:51Z うにさん「再入力変換は、実際にどのキーを押したかという情報から、平仮名にしてください。打ったばかり
なので、記録が残っている」）。
・かな入力: JIS かな配列（いま選んでいるかな配列の表 kana_layout）でキーをかなに。Shift を押していた間のキーは Shift の面
  （っ・ゃ・を など）。゛・゜ のキーは前の字と組み合わせる（か＋゛→が）
・ローマ字入力: キーの並びをローマ字としてかなに（halfwidth.romaji_to_kana）。全部かなにできた時だけ
・字でないキー: 記録に種類の名前がある時（stroke_keys.NonChar・2026-11-22 から）は、BackSpace で打った字を1つ消す
  （かな入力は1字。ローマ字はかなになっていない字があればその1字、無ければかな1字）。変換の Space・Enter・
  変換／無変換・F6〜F10 は並びを変えない。字の位置を動かすキー（矢印・Home・End）・Delete・Esc・その他は、
  打ったかなが分からなくなるので None。変換の Space の後の BackSpace も（変換の取り消しか字の削除か分からない）None。
  種類の無い古い記録（空の字）は前と同じく並びから外すだけ（呼ぶ側で確定の読みと字数を比べて使う）
作れなければ None。読むだけで、どこにも書かない。CN_TYPED_KANA_KINDS=0 で種類を見ない前の形。
"""

KEEPS = frozenset(('space', 'Return', 'Convert', 'NonConvert', 'F6', 'F7', 'F8', 'F9', 'F10'))
CONVERTS = frozenset(('space', 'Convert', 'F6', 'F7', 'F8', 'F9', 'F10'))


def _key_table():
    import kana_layout
    keys = getattr(kana_layout, '_KEYS', None) or kana_layout._JIS_KEYS
    table = {}
    for entry in keys:
        plain, shift, kana, shift_kana = (tuple(entry) + ('', '', '', ''))[:4]
        if plain and plain not in table:
            table[plain] = (kana, shift_kana or kana)
    return table


def _voiced():
    import kana_layout
    out = {}
    for voiced, mark in kana_layout.MARK_OF.items():
        base = kana_layout.DAKUTEN_BASE.get(voiced)
        if base:
            out[(base, mark)] = voiced
    return out


def _shifted(at, shifts):
    return any(down <= at <= up for down, up in shifts or ())


def _kind(key):
    """字でないキーの種類（stroke_keys.NonChar.name）。古い記録の空の字・字のキーは None。"""
    import os
    if key or os.environ.get('CN_TYPED_KANA_KINDS') == '0':
        return None
    return getattr(key, 'name', None)


def _events(strokes):
    """[(キーの字, 押した ms, 種類)]。種類の無い字でないキーは外す。並びが読めないキーがあれば None。"""
    out = []
    converted = False
    for k, t in strokes or ():
        kind = _kind(k)
        if k:
            out.append((k, t, None))
            continue
        if kind is None:
            continue                     # 古い記録: 前と同じく外すだけ
        if kind in KEEPS:
            converted = converted or kind in CONVERTS
            continue
        if kind == 'BackSpace' and not converted:
            out.append(('', t, 'BackSpace'))
            continue
        return None                      # 矢印・Delete・Esc・変換の後の BackSpace など
    return out


def from_keys(strokes, shifts=(), method='kana'):
    """打鍵の記録 [(キーの字, 押した ms)]・Shift の間 [(押し, 離し)] → 打ったかな（平仮名）。作れなければ None。"""
    keys = _events(strokes)
    if not keys or not any(k for k, _t, _kind in keys):
        return None
    if method == 'romaji':
        return _romaji(keys)
    table = _key_table()
    voiced = _voiced()
    out = []
    for key, at, kind in keys:
        if kind == 'BackSpace':
            if not out:
                return None              # 確定の外の字を消した
            out.pop()
            continue
        got = table.get(key)
        if got is None:
            return None                  # かなの無いキー
        kana = got[1] if _shifted(at, shifts) else got[0]
        if kana in ('゛', '゜'):
            if not out or (out[-1], kana) not in voiced:
                return None
            out[-1] = voiced[(out[-1], kana)]
            continue
        out.append(kana)
    text = ''.join(out)
    return text if _all_kana(text) else None


def _romaji(keys):
    import halfwidth

    def kana_of(letters):
        try:
            return halfwidth.romaji_to_kana(''.join(letters))[0]
        except Exception:
            return None
    letters = []
    for key, _at, kind in keys:
        if kind != 'BackSpace':
            letters.append(key)
            continue
        if not letters:
            return None
        now = kana_of(letters)
        if now is None:
            return None
        if now and not _all_kana(now[-1]):
            letters.pop()                # かなになっていないローマ字の1字
            continue
        want = now[:-1]                  # かな1字を消す: そのかなになる所までローマ字を戻す
        for cut in range(len(letters) - 1, -1, -1):
            if kana_of(letters[:cut]) == want:
                letters = letters[:cut]
                break
        else:
            return None
    kana = kana_of(letters)
    return kana if kana and _all_kana(kana) else None   # ローマ字が残っていれば（かなにできなかった）使わない


def _all_kana(text):
    return bool(text) and all('ぁ' <= c <= 'ゟ' or c == 'ー' for c in text)
