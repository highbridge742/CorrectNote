"""ひらがなのまま通す語の一覧（2026-11-14 補正担当・仕様 /mnt/project-files/correctnote_20261114_kana_keep/SPEC_v1.md）。

うにさん 11-14 10:44Z: 特定の語だけひらがなのままにする一覧が要る。きれい はひらがなのままでよい。オプションの別ウインドウで
個別に付け足し・無効にできる。品詞による決まりはオン／オフできる。ユーザーが きれい を消したら きれい は漢字になる。

置き場
------
- 初めの一覧（同梱・読むだけ）: kana_keep_default.json
  {"version": 1, "rules": [{"id", "label", "label_en", "on"}...], "words": ["きれい", ...]}
- ユーザーの分（データの置き場・個人の設定）: kana_keep_user.json。初めの一覧との差だけを書く。
  {"version": 1, "rules_off": [], "rules_on": [], "words_added": [], "words_off": [], "words_removed": []}
  置き場は set_user_dir(フォルダ) で決める（アプリは app_dir() を渡す）。渡されなければ環境変数 CN_KANA_KEEP_USER_DIR、
  それも無ければこのファイルと同じフォルダ。

部品の関数（挙動関連担当のウインドウはこれだけを使う。名前と書式は仕様の 3 のとおり）
  load() / words() / rule_on(id) / version() / set_word(語, 有効) / add_word(語) / remove_word(語) /
  set_rule(id, on) / reset() / entries()（語の行）/ rules()（決まりの3行: 名前・説明・対象の語・オンか）
読み込みは1回。ファイルの更新時刻が変わった時だけ読み直す（解析の子も同じ部品で読む）。

一番外の守り（install()）
-----------------------
correct_line の答えの書き換えのうち、一覧の有効な語（読みが一覧の語と同じ語。活用する語は基本形の読み）を漢字で書いた所を、
かなに戻す。打ち違いを直してその語になった所も、かなで書く（直した後の形がかなのまま）。元の行で本人が漢字で書いていた所
（書き換えていない所）は触らない。語の途中（きれいごと の きれい）には当てない。CN_KANA_KEEP_LIST=0 で無効。
"""
import functools
import hashlib
import json
import os
import sys
import threading

DEFAULT_NAME = 'kana_keep_default.json'
USER_NAME = 'kana_keep_user.json'

_lock = threading.RLock()
_state = {'user_dir': None, 'stamp': None, 'default': None, 'user': None, 'words': frozenset(), 'version': ''}
_orig = {}


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def _default_path():
    base = getattr(sys, '_MEIPASS', None)
    if base and os.path.exists(os.path.join(base, DEFAULT_NAME)):
        return os.path.join(base, DEFAULT_NAME)
    return os.path.join(_here(), DEFAULT_NAME)


def default_available():
    """同梱の kana_keep_default.json が読めたか（bundle_manifest の確かめ用）"""
    d = _read(_default_path())
    return bool(d.get('rules')) and isinstance(d.get('words'), list)


def set_user_dir(path):
    """ユーザーの分のファイルを置くフォルダ（アプリは app_dir()）。次の読み込みから効く"""
    with _lock:
        _state['user_dir'] = path
        _state['stamp'] = None


def _user_path():
    d = _state.get('user_dir') or os.environ.get('CN_KANA_KEEP_USER_DIR') or _here()
    return os.path.join(d, USER_NAME)


def _mtime(p):
    try:
        st = os.stat(p)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


# 同梱の初めの一覧が読めない時の写し（kana_keep_default.json と同じ中身。どちらかを変えたら両方）
BUILTIN_DEFAULT = {
    'version': 1,
    'rules': [
        {'id': 'wago_kana', 'label': '和語の名詞・形容詞はかなのまま', 'label_en': 'Keep native Japanese nouns and adjectives in kana',
         'on': True, 'members': ['wago_noun', 'wago_katakana', 'wago_respell', 'lattice_wago_noun']},
        {'id': 'function_kana', 'label': '形式名詞・補助の動詞・接続詞はかなのまま',
         'label_en': 'Keep formal nouns, auxiliary verbs and conjunctions in kana',
         'on': True, 'members': ['function_word', 'aux_verb'],
         'targets_from': ['wago_verb._KANA_VERBS', 'correction_entry._FORMAL_KANA_NOUNS']},
        {'id': 'verb_kanji', 'label': '和語の動詞は漢字にする', 'label_en': 'Turn native Japanese verbs into kanji',
         'on': True, 'members': ['wago_verb_kanji']},
    ],
    'words': [
        'あなた', 'あまい', 'あらかじめ', 'ありがとう', 'あるいは', 'あんこ', 'いう', 'いく', 'いたす', 'いただく', 'いちご', 'いちばん', 'いったん',
        'いろいろ', 'いわし', 'うどん', 'うなぎ', 'うまい', 'うれしい', 'えのき', 'おいしい', 'おおきい', 'おかげ', 'おかゆ', 'おかわり', 'おしえる',
        'おでん', 'おにぎり', 'おめでとう', 'おもしろい', 'おもち', 'カタカナ', 'かつお', 'かなしい', 'からあげ', 'からい', 'かわいい', 'きく', 'きれい',
        'くる', 'こども', 'ごはん', 'ごま', 'ごめんなさい', 'さすが', 'さっそく', 'さつまいも', 'さば', 'さびしい', 'さまざま', 'さらに', 'さんま',
        'しいたけ', 'しめじ', 'しょうゆ', 'しょっぱい', 'しれない', 'じゃがいも', 'すいか', 'すきやき', 'すぎない', 'すこし', 'すごい', 'すっぱい', 'すでに',
        'せんべい', 'そうめん', 'そば', 'たくさん', 'ただし', 'たとえば', 'たのしい', 'たべる', 'たまねぎ', 'ため', 'だいふく', 'だれ', 'ちがいない',
        'ちなみに', 'ちょうど', 'ちょっと', 'つけもの', 'てんぷら', 'できる', 'とおり', 'とき', 'ところ', 'ともだち', 'とりあえず', 'どこ', 'なお', 'なに',
        'にがい', 'にんじん', 'にんにく', 'のむ', 'ひらがな', 'ふりかけ', 'ぶどう', 'ぶり', 'ほうれんそう', 'ほか', 'ほしい', 'ほとんど', 'まいる', 'まさに',
        'ますます', 'まるで', 'まんじゅう', 'みかん', 'みそ', 'みそしる', 'みりん', 'みる', 'みんな', 'むしろ', 'むずかしい', 'むだ', 'もっとも', 'もつ',
        'もも', 'やきとり', 'やさしい', 'ようかん', 'よろしく', 'りんご', 'わかめ', 'わかる', 'わけ', 'わさび', 'わずか', 'わたし',
    ],
}


def _read(p):
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _empty_user():
    return {'version': 1, 'rules_off': [], 'rules_on': [], 'words_added': [], 'words_off': [], 'words_removed': []}


def _norm(w):
    """語はひらがなで持つ（片仮名で打たれても ひらがな に）。前後の空白は落とす"""
    w = (w or '').strip()
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in w)


def load(force=False):
    """一覧を読む（更新時刻が変わった時だけ読み直す）。有効な語の集まりを返す"""
    with _lock:
        dp, up = _default_path(), _user_path()
        stamp = (dp, _mtime(dp), up, _mtime(up))
        if not force and stamp == _state['stamp']:
            return _state['words']
        default = _read(dp) or BUILTIN_DEFAULT
        user = dict(_empty_user(), **_read(up))
        base = [_norm(w) for w in default.get('words') or () if _norm(w)]
        removed = {_norm(w) for w in user.get('words_removed') or ()}
        off = {_norm(w) for w in user.get('words_off') or ()}
        added = [_norm(w) for w in user.get('words_added') or () if _norm(w)]
        words = [w for w in base if w not in removed] + [w for w in added if w not in base and w not in removed]
        _state.update(stamp=stamp, default=default, user=user,
                      words=frozenset(w for w in words if w not in off))
        blob = json.dumps({'d': default, 'u': user}, ensure_ascii=False, sort_keys=True).encode('utf-8')
        _state['version'] = hashlib.sha256(blob).hexdigest()[:16]
        return _state['words']


def words():
    """有効な語の集まり（ひらがな）"""
    return load()


def version():
    """中身のハッシュ（解析の控えの鍵に入れる）。一覧が変われば変わる"""
    load()
    return _state['version']


def _targets(refs):
    """決まりの「対象の語」（コードに在る一覧: wago_verb._KANA_VERBS など）。読めなければ空"""
    out = []
    for ref in refs or ():
        mod, _, name = str(ref).partition('.')
        try:
            m = sys.modules.get(mod) or __import__(mod)
            for w in getattr(m, name, ()) or ():
                if w not in out:
                    out.append(w)
        except Exception:
            continue
    return sorted(out)


def rules():
    """[{'id', 'label', 'label_en', 'description', 'description_en', 'on', 'default_on', 'members', 'targets'}]
    （ウインドウの上の段。決まりは3つ: wago_kana・function_kana・verb_kanji）"""
    load()
    user = _state['user'] or _empty_user()
    out = []
    for r in (_state['default'] or {}).get('rules') or ():
        if not isinstance(r, dict) or not r.get('id'):
            continue
        rid = r['id']
        on = bool(r.get('on', True))
        if rid in (user.get('rules_off') or ()):
            on = False
        elif rid in (user.get('rules_on') or ()):
            on = True
        out.append({'id': rid, 'label': r.get('label', rid), 'label_en': r.get('label_en', r.get('label', rid)),
                    'description': r.get('description', ''), 'description_en': r.get('description_en', ''),
                    'on': on, 'default_on': bool(r.get('on', True)), 'members': list(r.get('members') or ()),
                    'targets': _targets(r.get('targets_from'))})
    return out


def rule_on(rid):
    """決まり id（ウインドウの3つ）か、その中の id（wago_noun・aux_verb など）の向き。どこにも無い id は True。
    CN_KANA_KEEP_LIST=0 の時は全部 True（今までどおり）"""
    if os.environ.get('CN_KANA_KEEP_LIST') == '0':
        return True
    load()
    user = _state['user'] or _empty_user()
    if not (user.get('rules_off') or user.get('rules_on')):
        # ユーザーが決まりを替えていない時は、同梱の向きだけ見る（行ごとに呼ばれるので軽く）
        for r in (_state['default'] or {}).get('rules') or ():
            if isinstance(r, dict) and (r.get('id') == rid or rid in (r.get('members') or ())):
                return bool(r.get('on', True))
        return True
    for r in (_state['default'] or {}).get('rules') or ():
        if isinstance(r, dict) and (r.get('id') == rid or rid in (r.get('members') or ())):
            on = bool(r.get('on', True))
            if r['id'] in (user.get('rules_off') or ()):
                on = False
            elif r['id'] in (user.get('rules_on') or ()):
                on = True
            return on
    return True


def entries():
    """[{'word', 'enabled', 'default'}]（ウインドウの下の段。初めからの語が先、付け足した語が後）"""
    load()
    user = _state['user'] or _empty_user()
    # 窓に出す語は書いたとおりの形（カタカナ）。比べるのはひらがなにした形（2026-11-15 挙動関連担当: 窓の試験で
    # カタカナ が かたかな と出ていた）
    base = [(w or '').strip() for w in (_state['default'] or {}).get('words') or () if _norm(w)]
    removed = {_norm(w) for w in user.get('words_removed') or ()}
    off = {_norm(w) for w in user.get('words_off') or ()}
    out, seen = [], set()
    for w in base:
        k = _norm(w)
        if k not in removed and k not in seen:
            seen.add(k)
            out.append({'word': w, 'enabled': k not in off, 'default': True})
    for w in user.get('words_added') or ():
        w = (w or '').strip()
        k = _norm(w)
        if k and k not in removed and k not in seen:
            seen.add(k)
            out.append({'word': w, 'enabled': k not in off, 'default': False})
    return out


def _save(user):
    p = _user_path()
    tmp = p + '.tmp'
    os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(user, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    load(force=True)


def _user():
    load()
    u = _empty_user()
    for k, v in (_state['user'] or {}).items():
        u[k] = list(v) if isinstance(v, list) else v
    return u


def _drop(lst, w):
    return [x for x in lst if _norm(x) != w]


def set_word(word, enabled):
    """語を有効／無効にする（一覧に無い語なら付け足す）"""
    w = _norm(word)
    if not w:
        return
    with _lock:
        u = _user()
        if w not in {e['word'] for e in entries()}:
            u['words_removed'] = _drop(u['words_removed'], w)
            u['words_added'] = _drop(u['words_added'], w) + [w]
        u['words_off'] = _drop(u['words_off'], w) + ([] if enabled else [w])
        _save(u)


def add_word(word):
    set_word(word, True)


def remove_word(word):
    """語を一覧から消す（初めからの語なら words_removed に書く）"""
    w = _norm(word)
    if not w:
        return
    with _lock:
        u = _user()
        base = {_norm(x) for x in (_state['default'] or {}).get('words') or ()}
        u['words_added'] = _drop(u['words_added'], w)
        u['words_off'] = _drop(u['words_off'], w)
        if w in base:
            u['words_removed'] = _drop(u['words_removed'], w) + [w]
        _save(u)


def set_rule(rid, on):
    with _lock:
        u = _user()
        u['rules_off'] = [x for x in u['rules_off'] if x != rid]
        u['rules_on'] = [x for x in u['rules_on'] if x != rid]
        default_on = next((r['default_on'] for r in rules() if r['id'] == rid), True)
        if bool(on) != default_on:
            (u['rules_on'] if on else u['rules_off']).append(rid)
        _save(u)


def reset():
    """初めの状態に戻す（ユーザーの分を消す）"""
    with _lock:
        p = _user_path()
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        load(force=True)


# ---- 一番外の守り ----------------------------------------------------------------------------------

def _hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in (s or ''))


def _has_kanji(s):
    return any('一' <= c <= '鿿' or c == '々' for c in s)


def _map_by_reading(line, text, s0, e0):
    """text の s0:e0 に当たる line の範囲。語の読みの並びで突き合わせる（字の並びだと ともだち｜と の と を取り違える）"""
    import difflib
    from morphology import tokenize
    lt, tt = list(tokenize(line)), list(tokenize(text))
    key = lambda t: _hira(t.reading or t.surface)
    sm = difflib.SequenceMatcher(None, [key(t) for t in lt], [key(t) for t in tt], autojunk=False)
    a0 = b0 = None
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        for j in range(j1, j2):
            t = tt[j]
            if not (t.start < e0 and s0 < t.end):
                continue
            if tag == 'equal':
                u = lt[i1 + (j - j1)]
                a, b = u.start, u.end
            elif i1 < i2:
                a, b = lt[i1].start, lt[i2 - 1].end
            else:
                continue
            a0 = a if a0 is None else min(a0, a)
            b0 = b if b0 is None else max(b0, b)
    if a0 is None:
        return s0, s0
    return a0, b0


def _src_reading(src):
    try:
        from morphology import tokenize
        out = ''
        for t in tokenize(src):
            if not t.reading:
                return None
            out += _hira(t.reading)
        return out
    except Exception:
        return None


def _base_reading(t):
    try:
        from morphology import tokenize
        b = getattr(t, 'base_form', '') or ''
        if not b or b == '*':
            return None
        if not _has_kanji(b):
            return _hira(b)
        parts = list(tokenize(b))
        if len(parts) == 1 and parts[0].reading:
            return _hira(parts[0].reading)
    except Exception:
        pass
    return None


def keep(line, result):
    if os.environ.get('CN_KANA_KEEP_LIST') == '0' or not isinstance(line, str) or not isinstance(result, dict):
        return result
    text = result.get('corrected')
    if not isinstance(text, str) or text == line:
        return result
    ws = words()
    if not ws:
        return result
    import difflib
    try:
        from morphology import tokenize
        toks = list(tokenize(text))
    except Exception:
        return result
    ops = [o for o in difflib.SequenceMatcher(None, line, text, autojunk=False).get_opcodes() if o[0] != 'equal']
    if not ops:
        return result
    repl = []
    for t in toks:
        if not _has_kanji(t.surface) or not t.reading:
            continue
        # 書き換えた所に掛かる語だけ（本人が漢字で書いていた所は触らない）
        if not any(j1 < t.end and t.start < max(j2, j1 + 1) for _tag, _i1, _i2, j1, j2 in ops):
            continue
        rd = _hira(t.reading)
        if rd in ws or _base_reading(t) in ws:
            repl.append((t.start, t.end, rd))
    if os.environ.get('CN_KANA_KEEP_PHRASE') != '0':
        # 語2つ以上で1つの言い方（知れ｜ない・違い｜ない・過ぎ｜ない）は、続く語の読みをつないだ形が一覧に在れば
        # まとめてかなに戻す（2026-11-15 うにの追加: しれない・ちがいない・すぎない）。CN_KANA_KEEP_PHRASE=0 で前のまま
        taken = {(a, b) for a, b, _r in repl}
        for i, t in enumerate(toks):
            if not _has_kanji(t.surface) or not t.reading or any(a <= t.start < b for a, b in taken):
                continue
            if not any(j1 < t.end and t.start < max(j2, j1 + 1) for _tag, _i1, _i2, j1, j2 in ops):
                continue
            joined = ''
            for j in range(i, min(len(toks), i + 4)):
                u = toks[j]
                if j > i and u.start != toks[j - 1].end:
                    break
                r = _hira(u.reading) if u.reading else (_hira(u.surface) if not _has_kanji(u.surface) else None)
                if r is None:
                    break
                joined += r
                if j > i and joined in ws:
                    repl.append((t.start, u.end, joined))
                    taken.add((t.start, u.end))
                    break
    if os.environ.get('CN_KANA_KEEP_TYPED_WORD') != '0':
        # かなで打った一覧の語そのものに、読みの違う漢字を置いた所（ぶり → 振り: 解析の読みは ふり）も、打った語へ戻す。
        # 元の行の解析で一覧の語とちょうど重なる書き換えだけ（打ち違いを直した所は元の語が一覧に無いので触らない）。
        # CN_KANA_KEEP_TYPED_WORD=0 で前のまま
        try:
            ltoks = list(tokenize(line))
            taken = {(a, b) for a, b, _r in repl}
            for tag, i1, i2, j1, j2 in ops:
                if tag != 'replace' or not _has_kanji(text[j1:j2]):
                    continue
                cov = [u for u in ltoks if u.start < i2 and i1 < u.end]
                if not cov or any(u.start != v.end for u, v in zip(cov[1:], cov)):
                    continue
                a0, b0 = cov[0].start, cov[-1].end
                w = line[a0:b0]
                if _has_kanji(w) or _hira(w) not in ws:
                    continue
                # 書き換えた所が、その語の範囲の外へはみ出さないこと
                if i1 < a0 or i2 > b0:
                    continue
                s0, e0 = j1 - (i1 - a0), j2 + (b0 - i2)
                if text[s0:j1] != line[a0:i1] or text[j2:e0] != line[i2:b0]:
                    continue
                if any(x < e0 and s0 < y for x, y in taken):
                    continue
                repl.append((s0, e0, w))
                taken.add((s0, e0))
        except Exception:
            pass
    if not repl:
        return result
    if os.environ.get('CN_KANA_KEEP_TYPED_KANJI') != '0':
        # 書き手が漢字を交えて打った所（友だち → 友達）は、かなにせず打った形へ戻す（うに 11-14 13:21Z「漢字にしたものを
        # ひらがなに補正する必要はない」。2026-11-15 ともだち を一覧に足した時に 友だち が ともだち になった）
        try:
            fixed = []
            for s0, e0, rd in repl:
                a0, b0 = _map_by_reading(line, text, s0, e0)
                src = line[a0:b0]
                if not _has_kanji(src) and _hira(src) == rd:
                    fixed.append((s0, e0, rd))          # かなで打った語はかなのまま
                elif _has_kanji(src) and _src_reading(src) == rd:
                    fixed.append((s0, e0, src))         # 漢字を交えて同じ語を打った所（友だち）は打った形
                # ほかは打ち違いを直した所（友ｄｓ値 → 友達・い人 → 少し）。直しはそのまま（打ち違いへ戻さない、
                # かなにもしない）。2026-11-15 作った誤字692行の8行で、一覧の語の直しが打ち違いへ戻っていた
            repl = fixed
        except Exception:
            pass
    new = text
    for s, e, rd in sorted(repl, reverse=True):
        new = new[:s] + rd + new[e:]
    out = dict(result)
    ops2 = [o for o in difflib.SequenceMatcher(None, line, new, autojunk=False).get_opcodes() if o[0] != 'equal']
    out.update({'corrected': new, 'changed': bool(ops2), 'spans': [[o[3], o[4]] for o in ops2],
                'original_spans': [[o[1], o[2]] for o in ops2]})
    if not ops2:
        out['details'] = []
        # 行が元のとおりに戻ったなら、書き換えが在ったから付いた紫（直した後の文の費用・直しの崩れ）も外す
        # （2026-11-14 補正担当: 星がきれいで の行で 綺麗 を戻した後も、離れた所に「直した後も…」の紫が残った）
        why = set()
        for mod in ('fixed_still_odd', 'rewrite_doubt'):
            try:
                why.add(__import__(mod).REASON)
            except Exception:
                pass
        drop = [tuple(r[:2]) for r in result.get('odd_reasons') or () if len(r) > 2 and r[2] in why]
        if drop:
            rest = [r for r in result.get('odd_reasons') or () if not (len(r) > 2 and r[2] in why)]
            keep_sp = {tuple(r[:2]) for r in rest}
            out['odd_reasons'] = rest
            out['odd_spans'] = [x for x in result.get('odd_spans') or () if tuple(x[:2]) not in drop or tuple(x[:2]) in keep_sp]
    else:
        out['details'] = [d for d in result.get('details') or ()
                          if not (isinstance(d, (list, tuple)) and len(d) >= 2 and isinstance(d[1], str)
                                  and d[1] and d[1] not in new)]
    return out


def drop_weak(line, result):
    """一覧の有効な語は、かなのままが正しい形。元の行でかなで打たれたその語に掛かる紫のうち、理由が弱いもの
    （品詞として識別できない・組が例文に無い・あまり使わない語 など、odd_reason_fill の弱い理由）だけを外す。
    隣のキー・抜けなど具体の見立ての理由が1つでも掛かる紫は残す（2026-11-14 全体評価: かなだけの行の いちばん・
    おしえる の行の紫）。CN_KANA_KEEP_LIST_WEAK=0 で前のまま。"""
    if (os.environ.get('CN_KANA_KEEP_LIST') == '0' or os.environ.get('CN_KANA_KEEP_LIST_WEAK') == '0'
            or not isinstance(line, str) or not isinstance(result, dict) or not result.get('odd_spans')):
        return result
    ws = words()
    if not ws:
        return result
    try:
        from morphology import tokenize
        import odd_reason_fill as F
        hits = [(t.start, t.end) for t in tokenize(line)
                if not _has_kanji(t.surface) and t.surface and (_hira(t.reading or t.surface) in ws or _base_reading(t) in ws)]
    except Exception:
        return result
    if not hits:
        return result
    reasons = [r for r in result.get('odd_reasons') or () if len(r) > 2]

    def drop(x):
        a, b = x[0], x[1]
        # 紫が一覧の語の中に収まる時だけ（語の外まで広がる紫は打ち違いの印: 2026-11-15 よろしく を足した時、
        # よろしく｜お願い位下ます に掛かる紫を外して誤字の印を失った）。CN_KANA_KEEP_WEAK_INSIDE=0 で前のまま（重なれば外す）
        if os.environ.get('CN_KANA_KEEP_WEAK_INSIDE') != '0':
            if not any(s <= a and b <= e for s, e in hits):
                return False
        elif not any(s < b and a < e for s, e in hits):
            return False
        over = [r[2] for r in reasons if r[0] < b and a < r[1]]
        return bool(over) and F._all_weak(over)
    gone = [tuple(x[:2]) for x in result['odd_spans'] if drop(x)]
    if not gone:
        return result
    out = dict(result)
    out['odd_spans'] = [x for x in result['odd_spans'] if tuple(x[:2]) not in gone]
    out['odd_reasons'] = [r for r in result.get('odd_reasons') or ()
                          if not any(r[0] < b and a < r[1] for a, b in gone)]
    return out


def correct_line(line, *args, **kwargs):
    result = _orig['correct_line'](line, *args, **kwargs)
    try:
        result = keep(line, result)
    except Exception:
        pass
    try:
        return drop_weak(line, result)
    except Exception:
        return result


def install():
    import correction_entry as ce
    if 'correct_line' in _orig:
        return
    _orig['correct_line'] = ce.correct_line
    functools.update_wrapper(correct_line, ce.correct_line)
    ce.correct_line = correct_line


def uninstall():
    import correction_entry as ce
    fn = _orig.pop('correct_line', None)
    if fn is not None and ce.correct_line is correct_line:
        ce.correct_line = fn
    correct_line.__dict__.pop('__wrapped__', None)
