"""
文脈の骨組み（2026-10-26・うにさんの案）。

    「家族で週末に出掛けた」→ (I) went out with 家族 over the 週末.

名詞は日本語のまま、文の形（誰が・何をした・誰と・どこで・いつ）だけを英語で
組み立てる。翻訳が目的ではない。**アプリが文をどう読んだか**を見せるための形で、
助詞の役割（で＝一緒に／場所／手段／理由）・省かれた主語・時制の読み違いが
そのまま英語に表れる。

材料:
- janome の区切りと品詞・活用
- 名詞の意味の分類（分類語彙表の「体」の類。全体の表 wlsp_synonyms.json.gz を synonyms.load_table で引く。人・時・場所・乗り物…）
- 動詞・形容詞の英語（JMdict のよく使う語から作った jm_pred.json.gz）
- 英語の動詞の活用（lemminflect で作った表 en_infl.json.gz。アプリは lemminflect を持たない）

補正の判定には使っていない（補正の結果は変わらない）。
"""

import gzip
import json
import os
import re
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=1)
def _tokenizer():
    from janome.tokenizer import Tokenizer
    return Tokenizer()


@lru_cache(maxsize=1)
def _wlsp():
    """分類語彙表の「体」の類: 見出し → [読み, [分類番号…]]。表は全体の表（synonyms.load_table・
    wlsp_synonyms.json.gz・2026-10-26 に1つにそろえた。前の wlsp_nouns.json.gz と同じ形で返す）。"""
    try:
        from synonyms import load_table
        table = load_table()
    except Exception:
        return {}
    out = {}
    for word, entries in table.words():
        codes = []
        for klass, code, _para, _sub in entries:
            if klass == '体' and code not in codes:
                codes.append(code)
        if codes:
            reads = table.readings(word)
            out[word] = [reads[0] if reads else '', codes]
    return out


@lru_cache(maxsize=1)
def _glosses():
    try:
        with gzip.open(os.path.join(_HERE, 'jm_pred.json.gz'), 'rt',
                       encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _jm_nouns():
    """分類語彙表に無い JMdict の名詞 → 種類（WordNet の上位語から。jm_noun_kind.json.gz）。"""
    try:
        with gzip.open(os.path.join(_HERE, 'jm_noun_kind.json.gz'), 'rt',
                       encoding='utf-8') as f:
            kinds = json.load(f)['kinds']
    except Exception:
        return {}
    out = {}
    for k, words in kinds.items():
        k = '' if k in ('-', 'thing') else k
        for w in words.split('\n'):
            out[w] = k
    return out


@lru_cache(maxsize=1)
def _infl():
    try:
        with gzip.open(os.path.join(_HERE, 'en_infl.json.gz'), 'rt',
                       encoding='utf-8') as f:
            return json.load(f)['words']
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _follow():
    """英語の2語の並びの数（SymSpell の bigram から、後ろが前置詞・限定詞・代名詞のものだけ）。"""
    try:
        with gzip.open(os.path.join(_HERE, 'en_follow.json.gz'), 'rt',
                       encoding='utf-8') as f:
            return json.load(f)['bi']
    except Exception:
        return {}


def is_noun_word(word):
    return word in _wlsp() or word in _jm_nouns()


# ------------------------------------------------------------
# 名詞の意味の分類 → 役割の手がかり
# ------------------------------------------------------------

def noun_kind(word):
    """'time' / 'person' / 'place' / 'vehicle' / 'tool' / 'cause' / 'thing' / ''"""
    codes = (_wlsp().get(word) or [None, []])[1]
    kinds = []
    for c in codes:
        if c.startswith('1.16'):
            kinds.append('time')
        elif c[:4] in ('1.20', '1.21', '1.22', '1.23', '1.24'):
            kinds.append('person')
        elif c[:4] in ('1.17', '1.25', '1.26', '1.27', '1.47', '1.52', '1.44'):
            kinds.append('place')
        elif c[:5] in ('1.465', '1.466', '1.467'):
            kinds.append('vehicle')
        elif c[:4] in ('1.45', '1.46'):
            kinds.append('tool')
        elif c[:4] in ('1.51', '1.57'):
            kinds.append('cause')
        elif c.startswith('1.3'):
            kinds.append('activity')
        else:
            kinds.append('thing')
    for k in ('time', 'person', 'vehicle', 'place', 'tool', 'cause', 'activity', 'thing'):
        if k in kinds:
            return k
    # 分類語彙表に無い語は JMdict の英語の WordNet 上の上位語で決める
    return _jm_nouns().get(word, '')


# 時を表す語（分類に無い・数の付いた形）
_TIME_WORDS = {'今日', '明日', '昨日', '今朝', '今夜', '毎日', '毎朝', '毎晩', '今週',
               '来週', '先週', '今年', '去年', '来年', '朝', '昼', '夜', '夕方',
               'きょう', 'あした', 'きのう', 'あさ', 'よる'}
_TIME_RX = re.compile(r'^[0-9０-９一二三四五六七八九十]+(時|分|日|月|年|曜日)')

_MOTION = {'go', 'come', 'go out', 'return', 'walk', 'run', 'move', 'travel',
           'arrive', 'head', 'drive', 'fly', 'get', 'leave', 'enter', 'ride',
           'commute', 'visit'}
# 「人に」が出どころになる動詞（友達に借りる＝友達から借りる）
_RECEIVE = {'borrow', 'receive', 'learn', 'be taught', 'get', 'hear'}
# 「Nと一緒に」「Nのために」のように、助詞の前の名詞が副詞のはたらきをするもの
_ADVERBIAL_NOUNS = {'一緒', 'ため', '代わり'}

_EXIST = {'be', 'live', 'stay', 'exist', 'remain', 'stand', 'sit', 'wait'}


def _time_prep(np):
    if np.endswith(('時', '時半')) or np in ('夜', '昼'):
        return 'at'
    if np.endswith(('年', '月', '夏', '冬', '春', '秋')) or np in ('朝', '午前', '午後', '夕方'):
        return 'in'
    return 'on'


def _is_time(np):
    return (noun_kind(np) == 'time' or np in _TIME_WORDS or bool(_TIME_RX.match(np))
            or np.endswith(('曜日', '時', '時間後')))


# ------------------------------------------------------------
# 述語の英語
# ------------------------------------------------------------

def _clean_gloss(g, kind=''):
    g = re.sub(r'\s*\([^)]*\)', '', g).strip()
    g = re.sub(r'^to ', '', g)
    g = g.split(';')[0].strip()
    head, sp, rest = g.partition(' ')
    if kind == 'suru' and head.endswith('ing'):
        g = (_infl().get(head) or {}).get('LEMMA', head) + sp + rest
    return g


# 可能動詞（話せる）→ もとの動詞（話す）
_POTENTIAL = dict(zip('えけげせてねべめれ', 'うくぐすつぬぶむる'))


def potential_base(base):
    if len(base) >= 3 and base.endswith('る') and base[-2] in _POTENTIAL:
        return base[:-2] + _POTENTIAL[base[-2]]
    return None


# かなで書く語は、辞書の別の語（いる＝射る）に当たるので先に決めておく
_COMMON = {'いる': ('be', 'v'), 'ある': ('be', 'v'), 'する': ('do', 'v'),
           'なる': ('become', 'v'), 'くる': ('come', 'v'), '来る': ('come', 'v'),
           'いく': ('go', 'v'), '行く': ('go', 'v'), 'できる': ('can do', 'v'),
           '好き': ('like', 'like'), '嫌い': ('dislike', 'like'), 'わかる': ('understand', 'v'),
           '分かる': ('understand', 'v'), 'ほしい': ('want', 'like'), '欲しい': ('want', 'like'),
           'もらう': ('receive', 'v'), 'くれる': ('give', 'v'), 'あげる': ('give', 'v'),
           '上手': ('good at', 'goodat'), '下手': ('bad at', 'goodat'),
           '得意': ('good at', 'goodat'), '苦手': ('bad at', 'goodat'),
           '帰る': ('go home', 'v'), '出掛ける': ('go out', 'v'), '出かける': ('go out', 'v')}


def predicate_english(base, kind_hint=None):
    """述語の原形 → (英語, 種類 'v'/'adj'/'na'/'suru')。分からなければ (None, None)。"""
    if base in _COMMON:
        return _COMMON[base]
    entry = _glosses().get(base) or {}
    order = (kind_hint,) if kind_hint else ()
    for k in order + ('v', 'adj', 'na', 'suru', 'adv'):
        if k and entry.get(k):
            return _clean_gloss(entry[k][0], k), k
    return None, None


def _inflect(verb_phrase, tag):
    head, _, rest = verb_phrase.partition(' ')
    if head == 'be':
        form = {'VBD': 'was', 'VBG': 'being', 'VBZ': 'is', 'VBN': 'been'}.get(tag, head)
    else:
        form = (_infl().get(head) or {}).get(tag, head)
    return (form + (' ' + rest if rest else '')).strip()


# ------------------------------------------------------------
# 文を塊に分ける
# ------------------------------------------------------------

class Chunk:
    def __init__(self):
        self.content = ''       # 名詞の並び・述語の表層
        self.base = ''          # 述語の原形
        self.kind = ''          # 'np' / 'pred'
        self.particles = []
        self.aux = []           # 助動詞・接続の並び（た・ない・ます・て・いる…）
        self.pos = ''
        self.adverbial = False

    def __repr__(self):
        return f'<{self.kind} {self.content} {self.particles} {self.aux}>'


def chunks(text):
    out = []
    cur = None
    for t in _tokenizer().tokenize(text):
        major, *subs = t.part_of_speech.split(',')
        surf = t.surface
        if major == '記号':
            cur = None
            continue
        if major in ('名詞', '接頭詞') and not (subs and subs[0] in ('非自立',) and cur and cur.kind == 'pred'):
            if subs and subs[0] == '接尾' and cur is not None and cur.kind == 'np' and not cur.particles:
                cur.content += surf
                continue
            if (cur is not None and cur.kind == 'np' and not cur.particles
                    and (not cur.adverbial or (subs and subs[0] == '数'))):
                cur.content += surf
                cur.adverbial = bool(subs and subs[0] == '副詞可能')
                continue
            if major == '名詞' and subs and subs[0] == 'サ変接続':
                cur = Chunk(); cur.kind = 'np'; cur.content = surf; cur.pos = 'sahen'
                out.append(cur)
                continue
            cur = Chunk(); cur.kind = 'np'; cur.content = surf
            cur.adverbial = bool(subs and subs[0] == '副詞可能')
            out.append(cur)
            continue
        if major in ('動詞', '形容詞'):
            if subs and subs[0] in ('非自立', '接尾') and cur is not None and cur.kind == 'pred':
                cur.aux.append(t.base_form if t.base_form != '*' else surf)
                continue
            if (major == '動詞' and t.base_form == 'する' and cur is not None
                    and cur.kind == 'np' and not cur.particles):
                cur.kind = 'pred'; cur.base = cur.content + 'する'; cur.pos = 'suru'
                continue
            cur = Chunk(); cur.kind = 'pred'; cur.content = surf
            cur.base = t.base_form if t.base_form != '*' else surf
            cur.pos = 'v' if major == '動詞' else 'adj'
            out.append(cur)
            continue
        if major == '助動詞':
            if cur is not None and cur.kind == 'np' and not cur.particles and t.base_form in ('だ', 'です'):
                cur.kind = 'pred'; cur.base = cur.content; cur.pos = 'copula'
                cur.aux.append(t.base_form)
                continue
            if cur is not None:
                cur.aux.append(t.base_form if t.base_form != '*' else surf)
            continue
        if major == '助詞':
            if cur is None:
                continue
            if cur.kind == 'pred':
                cur.aux.append(surf)
            else:
                cur.particles.append(surf)
            continue
        if major == '副詞':
            cur = Chunk(); cur.kind = 'adv'; cur.content = surf; cur.base = surf
            out.append(cur)
            continue
        cur = None
    return _join_compounds(out)


def _join_compounds(cs):
    """「朝」「ご飯」のように切れた名詞の続きが辞書の1語（朝ご飯）なら1つにする。"""
    out = []
    for c in cs:
        prev = out[-1] if out else None
        if (prev is not None and prev.kind == 'np' and c.kind == 'np' and not prev.particles
                and is_noun_word(prev.content + c.content)):
            prev.content += c.content
            prev.particles = c.particles
            prev.adverbial = c.adverbial
            continue
        out.append(c)
    return out


# ------------------------------------------------------------
# 組み立て
# ------------------------------------------------------------

_OBJ_FOLLOW = ('the', 'a', 'an', 'my', 'his', 'her', 'him', 'them', 'your', 'our',
               'their', 'me', 'us', 'this', 'these', 'those')
_PREPS = ('from', 'at', 'in', 'to', 'with', 'for', 'about', 'on', 'into', 'by')


def _verb_forms(verb):
    head = verb.split(' ')[0]
    forms = {head}
    forms.update(v for k, v in (_infl().get(head) or {}).items() if k.startswith('VB'))
    return forms


def _follow_count(words, nxt):
    bi = _follow()
    return sum((bi.get(w) or {}).get(n, 0) for w in words for n in nxt)


def takes_direct_object(verb):
    """英語でその動詞のすぐ後ろに目的語が来る方が「to」より多いか（meet 友達・ask 先生）。"""
    if ' ' in verb:
        return False
    forms = _verb_forms(verb)
    return _follow_count(forms, _OBJ_FOLLOW) > 5 * _follow_count(forms, ('to',))


def best_preposition(word, choices=_PREPS):
    """「be absent」のような形容詞の後ろに最も多く来る前置詞（absent from）。"""
    bi = _follow().get(word) or {}
    got = max(choices, key=lambda p: bi.get(p, 0))
    return got if bi.get(got) else ''


def _role(np, particle, verb, ctx=None):
    """名詞＋助詞 → (役割, 前置詞)。ctx: 文の他の手がかり（has_obj・passive）。"""
    ctx = ctx or {}
    k = noun_kind(np)
    if particle in ('が',):
        return 'subj', ''
    if particle in ('は',):
        return 'topic', ''
    if particle == 'を':
        if verb in _MOTION and k in ('place', ''):
            return 'path', 'through'
        if verb.startswith('be ') and verb.count(' ') == 1:
            # 「be absent」には目的語が直接付かない → その語に多く続く前置詞
            prep = best_preposition(verb.split(' ')[1])
            if prep:
                return 'from' if prep == 'from' else 'loc', prep
        return 'obj', ''
    if particle in ('に',):
        if _is_time(np):
            return 'time', _time_prep(np)
        if verb == 'become':
            return 'comp', ''
        if np in _ADVERBIAL_NOUNS:
            return 'skip', ''
        if k == 'person':
            if ctx.get('passive'):
                return 'agent', 'by'
            if verb.split(' ')[0] in _RECEIVE:
                return 'from', 'from'
            if not ctx.get('has_obj') and takes_direct_object(verb):
                return 'obj', ''
            return 'to', 'to'
        if k == 'activity' and verb in _MOTION:
            return 'purpose', 'for'
        if verb in _EXIST:
            return 'loc', 'in'
        if verb in _MOTION or k == 'place':
            return 'goal', 'to'
        return 'goal', 'to'
    if particle == 'へ':
        return 'goal', 'to'
    if particle == 'で':
        if _is_time(np):
            return 'time', 'in'
        if k == 'person':
            return 'with', 'with'
        if k == 'vehicle':
            return 'means', 'by'
        if k == 'place':
            return 'loc', 'at'
        if k == 'cause':
            return 'cause', 'because of'
        if k == 'tool':
            return 'means', 'with'
        return 'loc', 'at'
    if particle == 'と':
        return 'with', 'with'
    if particle == 'から':
        return 'from', 'from'
    if particle == 'まで':
        return 'until' if _is_time(np) else 'goal', 'until' if _is_time(np) else 'to'
    if particle == 'より':
        return 'than', 'than'
    return 'other', ''


def _noun_phrase(c, chunk_list, i):
    """「AのB」→「B of A」。"""
    text = c.content
    return text


def skeleton(text):
    """文1つ → 骨組みの英語（読めないときは None）。"""
    cs = chunks(text)
    preds = [c for c in cs if c.kind == 'pred']
    if not preds:
        return None
    pred = preds[-1]
    for c in preds[:-1]:
        if c.pos == 'adj' and not c.aux and not c.particles:
            c.kind = 'adv'
            # 名詞の前の形容詞（大きい箱）は名詞に付ける: big 箱（2026-10-26 挙動関連担当
            # 「Ate 箱 big. は形容詞の位置がおかしい」）
            k = cs.index(c)
            nxt = cs[k + 1] if k + 1 < len(cs) else None
            if nxt is not None and nxt.kind == 'np':
                eng, ek = predicate_english(c.base)
                if eng and ek in ('adj', 'na') and ' ' not in eng:
                    nxt.content = f'{eng} {nxt.content}'
                    c.kind = 'mod'
    # 述語の英語
    if pred.pos == 'copula':
        verb, vk = 'be', 'cop'
        g, gk = predicate_english(pred.base)
        if gk in ('na', 'like', 'goodat'):
            verb, vk = g, gk
    else:
        verb, vk = predicate_english(pred.base, 'suru' if pred.pos == 'suru' else None)
        if verb is None and pred.pos == 'suru':
            verb, vk = predicate_english(pred.base[:-2])
            if verb is not None:
                vk = 'v'
        potential = False
        if verb is None and pred.pos == 'v' and potential_base(pred.base):
            verb, vk = predicate_english(potential_base(pred.base))
            potential = verb is not None
        if verb is None:
            verb, vk = f'[{pred.base}]', 'v'
    aux = pred.aux
    past = 'た' in aux or (pred.pos in ('v', 'suru') and 'だ' in aux)
    neg = any(a in ('ない', 'ぬ', 'ん') for a in aux)
    prog = (any(a in ('て', 'で') for a in aux) and 'いる' in aux) or any(a in ('てる', 'でる') for a in aux)
    want = 'たい' in aux
    rareru = any(a in ('れる', 'られる') for a in aux)
    ni_person = any(c.kind == 'np' and c.particles[:1] == ['に'] and noun_kind(c.content) == 'person'
                    for c in cs if c is not pred)
    # れる・られる＋「人に」→ 受け身（先生に褒められた）。人が無ければ可能として読む
    passive = rareru and ni_person and pred.pos in ('v', 'suru')
    can = ((rareru and not passive) or 'できる' in aux or
           (pred.pos != 'copula' and locals().get('potential', False))) and not past
    ctx = {'passive': passive,
           'has_obj': any(c.kind == 'np' and c.particles[:1] == ['を'] for c in cs)}
    # 名詞の役割
    args = []
    pending_no = []
    for c in cs:
        if c is pred:
            break
        if c.kind == 'np':
            if c.particles == ['の']:
                pending_no.append(c.content)
                continue
            np = c.content
            if pending_no:
                np = f'{np} of ' + ' of '.join(reversed(pending_no))
                pending_no = []
            p = c.particles[0] if c.particles else ''
            if not p:
                if _is_time(c.content):
                    args.append(('time', '', np))
                continue
            role, prep = _role(c.content, p, verb, ctx)
            args.append((role, prep, np))
        elif c.kind == 'adv':
            g, _k = predicate_english(c.base, 'adv')
            if g is None or _k not in ('adv', 'adj'):
                g = c.content
            args.append(('adv', '', g))
    subj = next((a for a in args if a[0] == 'subj'), None)
    topic = next((a for a in args if a[0] == 'topic'), None)
    head = ''
    if vk in ('like', 'goodat') and subj is not None:
        # 「AはBが好き」: B は好きの相手（目的語）、A が主語
        args = [a for a in args if a is not subj] + [('obj', '', subj[2])]
        subj = None
    if subj is None and topic is not None and not _is_time(topic[2]):
        # が の無い文の「は」は主語として読む（「会議は三時に始まる」）
        subj, topic = topic, None
    if topic is not None:
        if _is_time(topic[2]):
            args.append(('time', '', topic[2]))
        else:
            head = f'As for {topic[2]}, '
    subject = subj[2] if subj else '(I)'
    third = subj is not None
    if subject in ('私', '僕', '俺', 'わたし', 'ぼく'):
        subject, third = 'I', False
    # 動詞の形
    if vk == 'like':
        vk = 'v'
    elif vk == 'goodat':
        vk = 'na'
    if vk in ('adj', 'na') or vk == 'cop':
        if subject == '私':
            subject, third = 'I', False
        be = 'was' if past else ('am' if subject in ('(I)', 'I') else 'is')
        if neg:
            be += ' not'
        adj = verb
        if any(a[0] == 'than' for a in args) and vk == 'adj' and ' ' not in verb:
            adj = (_infl().get(verb) or {}).get('JJR', verb)
        vp = be if vk == 'cop' else f'{be} {adj}'
        if vk == 'cop':
            vp = f'{be} {pred.base}'
    else:
        if passive:
            be = 'was' if past else ('is' if third else 'am')
            vp = f'{be}{" not" if neg else ""} {_inflect(verb, "VBN")}'
        elif want:
            vp = ('wanted to ' if past else 'want to ') + verb
            if neg:
                vp = ("didn't want to " if past else "don't want to ") + verb
        elif prog:
            be = ('was' if past else ('is' if third else 'am'))
            vp = f'{be}{" not" if neg else ""} {_inflect(verb, "VBG")}'
        elif can:
            vp = ("can't " if neg else 'can ') + verb
        elif neg:
            vp = ("didn't " if past else ("doesn't " if third else "don't ")) + verb
        elif past:
            vp = _inflect(verb, 'VBD')
        else:
            vp = _inflect(verb, 'VBZ') if third else verb
    obj = [a[2] for a in args if a[0] == 'obj']
    order = ('comp', 'purpose', 'to', 'path', 'goal', 'with', 'means', 'loc', 'from', 'until', 'than', 'agent', 'cause', 'time')
    tail = []
    for r in order:
        for a in args:
            if a[0] == r:
                tail.append(f'{a[1]} {a[2]}'.strip())
    advs = [a[2] for a in args if a[0] == 'adv']
    if vk in ('adj', 'na', 'cop') and advs:
        # 「とても甘い」→ is very sweet
        be, _, rest = vp.partition(' ')
        if be in ('is', 'am', 'was') and rest.startswith('not '):
            be, rest = be + ' not', rest[4:]
        vp = ' '.join([be] + advs + ([rest] if rest else []))
        advs = []
    parts = [subject, vp] + obj + tail + advs
    s = head + ' '.join(p for p in parts if p) + '.'
    return s[0].upper() + s[1:] if s[0].isalpha() and s[0].islower() else s
