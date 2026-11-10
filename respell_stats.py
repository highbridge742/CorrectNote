# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""紫の所の読み直しで、候補の何回目を採ったかの集計（デバッグ・2026-11-10 うにさん「デバッグメニューにチェックボックス
を用意。デフォルトはオフ。オンにすると、候補11回の何回目を採用したかの集計を始める。8回以上で採用された場合は、
原文も記録する」）。

数えるのは odd_respell（set_rank_stats でオン・オフ、take_rank_stats で受け取る）。解析の子の分は答えに載って届き
（analysis_worker.merge_usage）、本体で補正した分は保存の時に本体の odd_respell から受け取る。ここは足し込んで、
usage_counts.json と同じ持ち方の別ファイル（respell_rank_stats.json・個人ファイル）に書くだけ。
形 {'rank': {'何回目': 行数, '?': n}, 'tried': {'通した回数': 行数}, 'late': [[何回目, 通した回数, 元の行, 採った行], …]}。
late（8回目以降・原文入り）は新しいものから LATE_MAX 件だけ残す。
"""
import json
import os

LATE_MAX = 200
SETTING = 'debug_respell_stats'      # 設定の鍵（既定 False）

_rank = {}
_tried = {}
_late = []


def _key(k):
    return str(k)


def merge(data):
    """子・本体の take_rank_stats() の形（None・壊れた形は読み飛ばす）を足す。"""
    if not isinstance(data, dict):
        return
    for name, into in (('rank', _rank), ('tried', _tried)):
        part = data.get(name)
        if isinstance(part, dict):
            for k, n in part.items():
                if isinstance(n, int):
                    into[_key(k)] = into.get(_key(k), 0) + n
    late = data.get('late')
    if isinstance(late, list):
        _late.extend(list(x) for x in late if isinstance(x, (list, tuple)) and len(x) >= 4)
        del _late[:-LATE_MAX]


def take_local():
    """本体の odd_respell が数えた分を受け取って足す（読み込まれていなければ何もしない）。"""
    import sys
    module = sys.modules.get('odd_respell')
    take = getattr(module, 'take_rank_stats', None)
    if take is not None:
        try:
            merge(take())
        except Exception:
            pass


def snapshot():
    return {'rank': dict(_rank), 'tried': dict(_tried), 'late': [list(x) for x in _late]}


def empty():
    return not (_rank or _tried or _late)


def clear():
    _rank.clear()
    _tried.clear()
    del _late[:]


def load(path):
    clear()
    try:
        with open(path, encoding='utf-8') as f:
            merge(json.load(f))
    except Exception:
        pass


def save(path):
    """いまの集計を書く。空なら前のファイルを消す（消すボタンのあと）。"""
    try:
        if empty():
            if os.path.exists(path):
                os.remove(path)
            return
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(snapshot(), f, ensure_ascii=False, indent=0, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        pass


def _order(k):
    return (1, 0) if k == '?' else (0, int(k)) if k.lstrip('-').isdigit() else (2, 0)


def text():
    """窓に出す文（rank・tried の表と late の一覧）。"""
    if empty():
        return 'まだ集計はありません（チェックを入れてから補正した行から数えます）。'
    parts = ['何回目の候補を採ったか（行の数。? は採った行が通した候補と合わない形）']
    total = sum(_rank.values()) or 1
    for k in sorted(_rank, key=_order):
        parts.append('  %4s 回目  %7d  %5.1f%%' % (k, _rank[k], 100.0 * _rank[k] / total))
    parts += ['', 'その行で候補を何回通したか（行の数）']
    for k in sorted(_tried, key=_order):
        parts.append('  %4s 回  %7d' % (k, _tried[k]))
    parts += ['', '8回目以降で採った行（新しい順・最大 %d 件）  何回目/通した回数  元の行 → 採った行' % LATE_MAX]
    for rank, tried, source, chosen in reversed([x[:4] for x in _late]):
        parts.append('  %s/%s  %s → %s' % (rank, tried, source, chosen))
    return '\n'.join(parts)
