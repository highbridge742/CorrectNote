# -*- coding: utf-8 -*-
"""
補正の各段が「使われて効果があった／使われたが効果がなかった／使われていない」を数える（2026-10-24・うにさんの依頼）。

うにさん「使われていないものを外すと処理が軽くなるはず。各所に使われた・使われていないを測るものを入れておいて。
やや長期的に見ます」。数だけを持ち、文は持たない（行の中身・語・読みはどこにも残さない）。
補正の答えは1字も変えない: 包みは元の関数をそのまま呼び、戻り値をそのまま返す。

数える単位は**1行**（correction_entry.correct_line の1回）。同じ行の中で段が何度呼ばれても1回と数える
（補正は直した行で自分をもう一度呼ぶので、呼ばれた回数では膨らむ）。段ごとに3つの数を持つ:
    called  その段が呼ばれた行の数（処理の重さの目安）
    used    そのうち段が働いた行の数（直しを出した／答えか紫を変えた）
    effect  そのうち効果があった行の数
        直しの段（corrector の _xxx_fixes など）: 直しを出し、その直しが行の最後の答えに残った
            （出した直しの字が、元の行より多く答えに現れる。形の分からない返り値は、答えが変わったこと）
        行の結果を受け取って返す段（紫だけの段・語の組・ローマ字の入れ替わり）: 答えか紫を変えた
    使われていない = used が 0 の段（呼ばれても何も出さない段も入る。STAGES に名前があるので 0 のまま見える）

数は COUNTS（メモリ）にだけ足していく。書き出し・読み込みは snapshot()／merge() で呼び手（アプリ）がする。
"""

COUNTS = {}       # 段の名前 → [called, used, effect]
STAGES = []       # 包んだ段の名前（呼ばれなくても一覧に出すため）
_DONE = set()
_SCOPE = []       # 行の中: [{段: 出した直しの list か None（出さなかった）か True（結果の段で変えた）/False}]


def _note(name, value):
    if not _SCOPE:
        return
    seen = _SCOPE[-1]
    old = seen.get(name)
    if value is None or value is False:
        seen.setdefault(name, value)
    elif value is True:
        seen[name] = True
    else:
        seen[name] = (old if isinstance(old, list) else []) + [value]


def _result_changed(result, ret):
    try:
        if not isinstance(ret, dict) or not isinstance(result, dict):
            return ret is not result
        return (ret.get('corrected') != result.get('corrected')
                or list(ret.get('odd_spans') or ()) != list(result.get('odd_spans') or ()))
    except Exception:
        return False


def _kept(fixes, line, final):
    """出した直しが最後の答えに残ったか。"""
    if final == line:
        return False
    for ret in fixes:
        items = ret if isinstance(ret, (list, tuple)) else [ret]
        shaped = False
        for f in items:
            if isinstance(f, (list, tuple)) and len(f) >= 3 and isinstance(f[2], str) and f[2]:
                shaped = True
                if final.count(f[2]) > line.count(f[2]):
                    return True
        if not shaped:
            return True
    return False


def wrap(module, attr, kind='fixes', label=None):
    """module.attr を数える包みに替える。kind: 'fixes'（直しを返す段）／'result'（行の結果を受け取って返す段）。"""
    name = label or f'{module.__name__}.{attr}'
    if name in _DONE:
        return
    fn = getattr(module, attr, None)
    if fn is None or not callable(fn):
        return
    if kind == 'result':
        def counted(line, result, *a, **k):
            ret = fn(line, result, *a, **k)
            _note(name, _result_changed(result, ret))
            return ret
    else:
        def counted(*a, **k):
            ret = fn(*a, **k)
            _note(name, ret if ret else None)
            return ret
    counted.__wrapped__ = fn
    counted._usage_counts = True
    counted.__name__ = getattr(fn, '__name__', attr)
    counted.__doc__ = getattr(fn, '__doc__', None)
    setattr(module, attr, counted)
    _DONE.add(name)
    STAGES.append(name)


def _wrap_entry(module):
    """行の入口。いちばん外の1回だけを1行として数える。"""
    fn = getattr(module, 'correct_line', None)
    if fn is None or getattr(fn, '_usage_counts', False):
        return

    def counted(line, *a, **k):
        outer = not _SCOPE
        if outer:
            _SCOPE.append({})
        try:
            ret = fn(line, *a, **k)
        except BaseException:
            if outer:
                _SCOPE.pop()
            raise
        if outer:
            seen = _SCOPE.pop()
            try:
                final = ret.get('corrected', line) if isinstance(ret, dict) else line
                for name, v in seen.items():
                    c = COUNTS.get(name)
                    if c is None:
                        c = COUNTS[name] = [0, 0, 0]
                    c[0] += 1
                    if v is True or isinstance(v, list):
                        c[1] += 1
                    if v is True or (isinstance(v, list) and _kept(v, line, final)):
                        c[2] += 1
            except Exception:
                pass
        return ret
    counted.__wrapped__ = fn
    counted._usage_counts = True
    counted.__name__ = 'correct_line'
    counted.__doc__ = fn.__doc__
    module.correct_line = counted


# corrector.correct_line から直に呼ばれる直しの段（2026-10-24 の corrector から拾った名前。無い名前は飛ばす）
CORRECTOR_STAGES = (
    '_abab_repair', '_adjective_tail_fixes', '_compose_kana_run_fixes', '_design35_fix', '_head_typo_fixes',
    '_ime_exact_respell', '_ime_one_key_respell', '_inflection_tail_fixes', '_kana_run_hand_fixes',
    '_kango_kana_fixes', '_katakana_go_after_fixes', '_katakana_modifier_fixes', '_known_head_intrusion_fixes',
    '_lagged_dakuten_fixes', '_misplaced_dakuten_fixes', '_misplaced_large_kana_fixes',
    '_misplaced_long_vowel_fixes', '_misplaced_small_kana_fixes', '_onbin_dakuten_fixes', '_parallel_pair_fixes',
    '_partial_loanword_fixes', '_particle_boundary_fixes', '_particle_merge_fixes', '_person_object_fixes',
    '_renyou_no_polite_fixes', '_reopen_mixed_run_fixes', '_resegment_fixes', '_run_reading_merge_fixes',
    '_sahen_homophone_fixes', '_scoped_tail_fix', '_shortcut_case_fixes', '_word_born_particle_fix',
)


# corrector.correct_line の中で直しを出す置き場（replacements.append の行）。鍵はその行のコードの字と、同じ字が
# 何度目か（#2 など）なので、corrector のほかの所を直しても鍵は変わらない。数えるのは置き場が直しを出した行と、
# その直しが最後の答えに残った行。段の名前の一覧に出すため、置き場は呼ばれなくても STAGES に入れる。
SITES = {}        # corrector の行番号 → 置き場の名前


def _site_names(module):
    import inspect
    try:
        src, first = inspect.getsourcelines(module)
    except Exception:
        return {}
    out, seen = {}, {}
    for k, text in enumerate(src):
        t = text.strip()
        if t.startswith('replacements.append('):
            seen[t] = seen.get(t, 0) + 1
            out[max(first, 1) + k] = '本体 ' + t + (f' #{seen[t]}' if seen[t] > 1 else '')
    return out


class _SiteList(list):
    def append(self, item):
        list.append(self, item)
        if _SCOPE:
            try:
                import sys
                name = SITES.get(sys._getframe(1).f_lineno)
                if name is not None:
                    _note(name, [item])
            except Exception:
                pass


def _wrap_sites(module):
    if getattr(module, '_usage_site_list', None) is None or getattr(module._usage_site_list, '_usage_counts', False):
        return
    SITES.update(_site_names(module))
    for name in sorted(set(SITES.values())):
        if name not in _DONE:
            _DONE.add(name)
            STAGES.append(name)

    names = tuple(sorted(set(SITES.values())))

    def make():
        if _SCOPE:
            seen = _SCOPE[-1]
            for n in names:
                seen.setdefault(n, None)      # 呼ばれた（置き場の前まで来たかは問わない。本体が回った行）
        return _SiteList()
    make._usage_counts = True
    make.__wrapped__ = module._usage_site_list
    module._usage_site_list = make


def install():
    """補正の段を包む。何度呼んでも1回だけ。失敗しても補正には触らない。"""
    try:
        import corrector
        for attr in CORRECTOR_STAGES:
            wrap(corrector, attr)
        _wrap_sites(corrector)
    except Exception:
        pass
    try:
        import last_keystroke
        wrap(last_keystroke, 'repair')
        wrap(last_keystroke, 'repair_ime_clause')
        # correction_entry は呼ぶたびに `from last_keystroke import …` で引くので、モジュールの名前を包めば数えられる
        wrap(last_keystroke, 'mark_stray_kanji', kind='result')
        wrap(last_keystroke, 'mark_impossible_kana', kind='result')
    except Exception:
        pass
    for mod in ('collocation_repair', 'romaji_swap_repair'):
        try:
            wrap(__import__(mod), 'apply', kind='result')
        except Exception:
            pass
    try:
        import correction_entry
        for attr in ('_mark_impossible_connections', '_mark_leftover_letters'):
            wrap(correction_entry, attr, kind='result')
        _wrap_entry(correction_entry)
    except Exception:
        pass


def snapshot():
    """いまの数（段 → [called, used, effect]）。呼ばれていない段も [0, 0, 0] で入れる。"""
    out = {n: [0, 0, 0] for n in STAGES}
    for n, c in COUNTS.items():
        out[n] = list(c)
    return out


def take():
    """いまの数を渡して、手元の数を 0 に戻す（書き出すたびに足し込む呼び手向け。二重に数えない）。
    数えた行が無ければ None（worker の答えに毎行載せても荷を増やさない）。"""
    if not COUNTS:
        return None
    out = {n: list(c) for n, c in COUNTS.items()}
    COUNTS.clear()
    return out


def merge(saved):
    """前に書き出した数を足し込む（数だけ。知らない形は読まない）。"""
    if not isinstance(saved, dict):
        return
    for n, c in saved.items():
        if (isinstance(n, str) and isinstance(c, (list, tuple)) and len(c) == 3
                and all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in c) and c[2] <= c[1] <= c[0]):
            cur = COUNTS.setdefault(n, [0, 0, 0])
            for i in range(3):
                cur[i] += c[i]


def table():
    """3つに分けた一覧: (効果があった, 使われたが効果がなかった, 使われていない) それぞれ [(段, called, used, effect)]。"""
    snap = snapshot()
    eff = sorted(((n, c, u, e) for n, (c, u, e) in snap.items() if e > 0), key=lambda x: -x[3])
    none = sorted(((n, c, u, e) for n, (c, u, e) in snap.items() if u > 0 and e == 0), key=lambda x: -x[2])
    unused = sorted(((n, c, u, e) for n, (c, u, e) in snap.items() if u == 0), key=lambda x: -x[1])
    return eff, none, unused
