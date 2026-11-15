# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""ローマ字入力の打ちそこねた子音（作った例: 田m者）が、IME の確定の表記と読み（RESULTSTR・RESULTREADSTR）に英字の
まま残るかを確かめる、読むだけの記録（2026-11-13・確かめ用。既定はオフ、CN_IME_MIXED_PROBE=1 の時だけ書く）。

残すのは 時刻・入力方式・表記に英字があったか・読みに英字があったか・表記と読みの長さ・どの道で届いたか だけ。
**打った文字そのものは残さない。** 置き場は tools_local\\ime_mixed_probe_20261113\\log.jsonl（公開の写しの外）。
ime_readings の覚え方・補正の答えは何も変えない。
"""
import json
import os
import time
import unicodedata

ENV = 'CN_IME_MIXED_PROBE'
FOLDER = os.path.join('tools_local', 'ime_mixed_probe_20261113')


def enabled(environ=None):
    environ = os.environ if environ is None else environ
    return environ.get(ENV) == '1'


def has_letter(text):
    """半角・全角の英字（a〜z・A〜Z）が1字でもあるか。"""
    return any('a' <= c.lower() <= 'z' for c in unicodedata.normalize('NFKC', text or '') if c.isascii())


def record(surface, reading, input_method, fallback=False, now=None):
    """記録の1行（文字は入れない）。"""
    return dict(time=time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(now)) if now is not None
                else time.strftime('%Y-%m-%dT%H:%M:%S'),
                input_method=input_method or '', surface_letter=has_letter(surface),
                reading_letter=has_letter(reading), surface_len=len(surface or ''), reading_len=len(reading or ''),
                via='fallback' if fallback else 'result', reading_empty=not reading)


def note(base_dir, surface, reading, input_method, fallback=False, environ=None):
    """CN_IME_MIXED_PROBE=1 の時だけ、記録を1行足す。書けたら True。失敗しても補正には触らない。"""
    if not enabled(environ):
        return False
    try:
        folder = os.path.join(base_dir, FOLDER)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'log.jsonl'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(record(surface, reading, input_method, fallback), ensure_ascii=False) + '\n')
        return True
    except Exception:
        return False


def summary(path):
    """記録を読んで、件数と英字の入り方をまとめる（うにさんが打った後に読む）。"""
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    romaji = [r for r in rows if r.get('input_method') == 'romaji']
    return dict(rows=len(rows), romaji=len(romaji),
                surface_letter=sum(r['surface_letter'] for r in romaji),
                reading_letter=sum(r['reading_letter'] for r in romaji),
                both=sum(r['surface_letter'] and r['reading_letter'] for r in romaji),
                reading_only=sum(r['reading_letter'] and not r['surface_letter'] for r in romaji),
                surface_only=sum(r['surface_letter'] and not r['reading_letter'] for r in romaji))


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), FOLDER, 'log.jsonl')
    print(json.dumps(summary(target), ensure_ascii=False))
