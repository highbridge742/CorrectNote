# -*- coding: utf-8 -*-
"""Each Worker owns one isolated correction process. State and text stay in memory; no store saves.

The child calls correction_entry.correct_line, also exported by app.correct_line.
A queue feeder serializes requests outside Tk; newer requests supersede queued
work. Results carry request ids and are accepted by the UI's document checks.
"""
import multiprocessing as mp
from contextlib import contextmanager
import sys
import keyboard_layout
import queue
import time
import traceback
from collections import defaultdict


def state_key(app):
    store=getattr(app,'store',None);choices=getattr(app,'choices',None)
    decisions=getattr(app,'decisions',None);decided=getattr(decisions,'revision',None)
    return (id(store),store.revision() if store is not None else 0,
            # 選び直しの記憶と補正の判断（2026-11-01: 判断も「動いたもの」として、その語を含む行だけやり直す）
            (choices.revision() if choices is not None else 0,decided() if decided is not None else 0),
            getattr(app,'_analysis_state_revision',0), id(getattr(app,'dict_index',None)),
            bool(getattr(getattr(app,'dict_index',None),'ready',False)),
            id(getattr(app,'context_vec',None)),
            # 入力方式とキーボードの配列・形（項目48-KB）は1つの要素に
            # まとめる（same_model_state は要素数 10 を見る）
            ((app.settings.get('input_method') or 'kana'),keyboard_layout.spec(app.settings)),
            tuple(app.recent_words.words()) if getattr(app,'recent_words',None) is not None else (),
            (id(getattr(app,'ime_readings',None)),
             app.ime_readings.revision() if getattr(app,'ime_readings',None) is not None else 0))


# state_key: 0 id(store) 1 store.revision 2 choices.revision 3 _analysis_state_revision 4 id(dict_index)
# 5 dict_index.ready 6 id(context_vec) 7 (input method, keyboard) 8 recent_words 9 (id(ime), ime revision)
_FIXED=(0,3,4,5,6,7)
VOCAB,CHOICE,RECENT=1,2,8


def same_model_state(previous,current):
    """Rows may be checked one by one: the same stores and settings. The vocabulary, the choice memory and the
    recent words may have moved (each row says what it used: used_keys, 2026-10-24); the IME readings too."""
    return bool(previous is not None and len(previous)==len(current)==10
                and all(previous[i]==current[i] for i in _FIXED) and previous[-1][0]==current[-1][0])


def only_ime_moved(previous,current):
    """Only the saved IME readings differ (the worker may update them in place; anything else is a full reset
    of its stores — the vocabulary and the choice memory too)."""
    return bool(previous is not None and len(previous)==len(current)==10
                and previous[:-1]==current[:-1] and previous[-1][0]==current[-1][0])


def choices_moved(previous,current):
    """The choice memory moved: kept corrections stay, but their display units are built again (units read
    the choices outside correct_line, so used_keys does not see them — 2026-10-24)."""
    return bool(previous is not None and len(previous)==len(current)==10 and previous[CHOICE]!=current[CHOICE])


def model_moved(previous,current):
    """The vocabulary or the choice memory moved (not only IME readings or recent words)."""
    return bool(previous is not None and len(previous)==len(current)==10
                and (previous[VOCAB]!=current[VOCAB] or previous[CHOICE]!=current[CHOICE]))


def result_compatible(app,result,previous,current=None):
    current=state_key(app) if current is None else current
    if previous==current:return True
    if not same_model_state(previous,current):return False
    if result is None:return False
    if result.get('original')=='':return True
    if any(previous[i]!=current[i] for i in (VOCAB,CHOICE,RECENT)) and not _keys_unchanged(app,result,previous,current):
        return False
    if previous[-1][1]==current[-1][1]:return True
    reads=result.get('_ime_evidence')
    if reads is None:return False
    ime=getattr(app,'ime_readings',None)
    return all(tuple(ime.readings_for(surface) if ime is not None else ())==values
               for surface,values in reads)


def _choice_part(value):
    """状態の鍵の選び直しの欄（選び直しの版, 判断の版）の、選び直しの版（古い形は数1つ）。"""
    return value[0] if isinstance(value,tuple) else value


def _decision_part(value):
    return value[1] if isinstance(value,tuple) and len(value)>1 else None


def _keys_unchanged(app,result,previous,current):
    """The row did not use what moved (used_keys of correction_entry, used_changes in this process)."""
    used=result.get('used_keys')
    if not isinstance(used,dict) or used.get('whole'):return False
    if previous[RECENT]!=current[RECENT] and used.get('recent'):return False
    import used_changes
    evidence=result.get('_context_evidence')
    if previous[CHOICE]!=current[CHOICE]:
        before,after=_decision_part(previous[CHOICE]),_decision_part(current[CHOICE])
        if before!=after:
            # 補正の判断は行の元の文字列に掛かる（直さない置換の元・触らない語・紫を付けない語）。
            # 変わった語を含まない行の答えは変わらない
            words=used_changes.changed(getattr(app,'decisions',None),before,after)
            if words is None or before is None or after is None:return False
            original=result.get('original') or ''
            if any(word in original for word in words):return False
    for index,attribute,kind in ((VOCAB,'store','vocab'),(CHOICE,'choices','choice')):
        if previous[index]==current[index]:continue
        old,new=previous[index],current[index]
        if index==CHOICE:
            old,new=_choice_part(old),_choice_part(new)
            if old==new:continue
        keys=used_changes.changed(getattr(app,attribute,None),old,new)
        if keys is None:return False
        if index==CHOICE:
            # 前後の語ごとの選び直しは、その並びが現れる行だけ
            places,keys=used_changes.split_context_keys(keys)
            texts=(result.get('original') or '',result.get('corrected') or '')
            if any(place in text for place in places for text in texts):return False
        # 子は語彙のキーを篩（vocab_bloom）で返すことがある（used_keys.keys_hit・2026-10-31）。keys_hit の無い
        # used_keys.py では従来どおり一覧と突き合わせる
        import used_keys
        hit=getattr(used_keys,'keys_hit',None)
        if hit is None and used.get(kind+'_bloom') is not None:return False    # 篩を読めない版では、やり直す側に
        if (hit(used,kind,keys) if hit is not None else keys.intersection(used.get(kind) or ())):return False
        # the loanword / English tables (used_keys loan, 2026-10-24): only a changed word that can be in them
        # (a katakana or English spelling, an en: reading) redoes the row
        if used.get('loan'):
            import used_keys
            if any(used_keys.is_loan_change(key,key) for key in keys):return False
        if index==VOCAB:
            # the context vocabulary is built from the store (読み → 表記): a row that read a changed reading
            # there, or all of it, is redone too
            if not isinstance(evidence,dict) or evidence.get('whole') or keys.intersection(evidence.get('keys') or ()):
                return False
            # 語彙の中を探した引き（似た読み・崩した読みなど）は、何を探したかと答えの指紋を queries に残す
            # （used_keys・2026-10-31）。今の語彙で探し直して指紋が同じなら、その行は動いたものを使っていない
            if used.get('queries'):
                import used_keys
                check=getattr(used_keys,'queries_unchanged',None)
                if check is None or not check(getattr(app,'store',None),used['queries']):return False
    return True


try:
    import used_changes as _used_changes
    _used_changes.install()          # note which keys change in this process (memory only)
except Exception:
    pass


def snapshot(app):
    index=getattr(app,'dict_index',None)
    import os
    cache=getattr(index,'cache_path',None)
    ready=bool(index is not None and index.ready)
    index_state=dict(cache_path=cache,ready=ready,empty=ready and not index._by_reading,
                     band={k:set(v) for k,v in (index._band or {}).items()} if index is not None else None)
    if ready and index._by_reading and not (cache and os.path.isfile(cache)):
        index_state['by_reading']={k:list(v) for k,v in index._by_reading.items()}
        index_state['by_surface']={k:list(v) for k,v in index._by_surface.items()}
        index_state['world']=set(index._world or ())
        index_state['inflected']={k:list(v) for k,v in index._inflected.items()}
    cv=getattr(app,'context_vec',None);choices=getattr(app,'choices',None)
    decisions=getattr(app,'decisions',None);ime=getattr(app,'ime_readings',None)
    import charngram
    return dict(entries=[dict(x) for x in app.store.to_list()],
        revision=app.store.revision(),index=index_state,
        context=({k:dict(v) for k,v in cv._co.items()} if cv is not None else None),
        context_seeded=getattr(cv,'seeded',False),context_seed_version=getattr(cv,'seed_version',0),
        decisions={name:{k:dict(v) for k,v in getattr(decisions,name,{}).items()}
                   for name in ('_rejected','_protected','_odd_only')},
        # 前後の語ごと覚えた同音の語（_contexts）も渡す（2026-11-01: 渡していなかったので、子の補正と表示に効かなかった）
        choices={name:dict(getattr(choices,name,{})) for name in ('_readings','_units','_contexts')},
        choice_revision=choices.revision() if choices is not None else 0,
        ime={k:list(v) for k,v in getattr(ime,'_pairs',{}).items()},
        charngram=dict(charngram._LEARNED or {}))


_FALLBACK_ROWS=[0]

# 途中の紫（early_marks・2026-11-05 うにさん「紫だけ先に」）。補正の1段目が済んだ所で、その行の紫だけを本体へ送る。
# correction_entry は変えず、その最初の補正（_correct_line_halfwidth）をこの子の中でだけ包む
_EARLY=dict(sink=None,line=None,row=None,sent=True)


def _early_install():
    import correction_entry
    if getattr(correction_entry._correct_line_halfwidth,'_correctnote_early',False):return
    first=correction_entry._correct_line_halfwidth
    def first_answer(text,*args,**kwargs):
        out=first(text,*args,**kwargs)
        try:
            # 行そのものの最初の補正だけ（あとの候補の試しの行は送らない）
            if not _EARLY['sent'] and _EARLY['sink'] is not None and text==_EARLY['line'] and isinstance(out,dict):
                _EARLY['sent']=True
                odd=[tuple(x[:2]) for x in (out.get('odd_spans') or ())]
                if odd:
                    outbox,identifier=_EARLY['sink']
                    outbox.put((('partial',identifier),dict(line=text,row=_EARLY['row'],odd=odd),None))
        except Exception:
            pass
        return out
    first_answer._correctnote_early=True
    correction_entry._correct_line_halfwidth=first_answer


def _early_begin(line,row=None):
    import os
    if os.environ.get('CN_EARLY_ODD')=='0' or _EARLY['sink'] is None:return
    try:_early_install()
    except Exception:return
    _EARLY.update(line=line,row=row,sent=False)


def _early_end():
    _EARLY['sent']=True


def _early_send(line,odd_spans):
    """correction_entry.correct_line の on_early_odd（batch275・2026-11-07）: 入口が紫を決めた直後、直しの段の前に呼ばれる。
    送るのは first_answer と同じ形（行そのものの紫・1度だけ）。最後の答えの紫で置き換わる（early_marks）。"""
    try:
        if _EARLY['sent'] or _EARLY['sink'] is None or line!=_EARLY.get('line'):return
        _EARLY['sent']=True
        odd=[tuple(x[:2]) for x in (odd_spans or ())]
        if odd:
            outbox,identifier=_EARLY['sink']
            outbox.put((('partial',identifier),dict(line=line,row=_EARLY['row'],odd=odd),None))
    except Exception:
        pass


def _early_hook(function):
    """correct_line に渡す on_early_odd（受けない correct_line・途中の紫を切った時は無し）。"""
    import os
    if os.environ.get('CN_EARLY_ODD')=='0' or _EARLY['sink'] is None or _EARLY['sent']:return {}
    if function not in _TAKES_EARLY:
        try:
            import inspect
            _TAKES_EARLY[function]='on_early_odd' in inspect.signature(function).parameters
        except (TypeError,ValueError):
            _TAKES_EARLY[function]=False
    return dict(on_early_odd=_early_send) if _TAKES_EARLY[function] else {}


_TAKES_EARLY={}


def _native_rows(tokens):
    """The kept form of a line's native tokens (Runtime.line_tokens)."""
    return tuple((t.surface,t.pos,t.base_form,t.reading,t.start,t.end,
                  t.has_reading,t.pos_sub,t.infl_form) for t in tokens)


def _count_fallback_rows():
    """Count rows the simple splitter parsed (janome failed on them).

    morphology falls back silently; a row parsed that way is not what a new
    process would parse, so Runtime must not keep it across a reset. The
    count wraps the function from here: morphology.py itself stays as it is
    (public_nominal_cache pins its SHA-256). Behaviour is unchanged."""
    import morphology
    original=morphology._tokenize_fallback
    if getattr(original,'_correctnote_counted',False):return
    def counted(line):
        _FALLBACK_ROWS[0]+=1
        return original(line)
    counted._correctnote_counted=True
    morphology._tokenize_fallback=counted


def _fast_path_cost():
    """morphology.path_cost を同じ答えの速い版に差し替える（path_cost_fast、2026-11-07 挙動関連担当が作り、
    janome と 20,250件で不一致0）。morphology.py は CODE_SHA256 で固定なので、子の中で外から差し替える。
    naturalness は読み込んだ時に path_cost を名前で持つので、それも向け直す。CN_FAST_PATH_COST=0 で前の形。"""
    import os
    if os.environ.get('CN_FAST_PATH_COST')=='0':return False
    try:
        import morphology,path_cost_fast
        if not path_cost_fast.install(morphology):return False
        import sys
        natural=sys.modules.get('naturalness')
        if natural is not None and getattr(natural,'_raw_path_cost',None) is getattr(morphology.path_cost,'__wrapped__',None):
            natural._raw_path_cost=morphology.path_cost
        return True
    except Exception:
        return False


class Runtime:
    def __init__(self):
        _count_fallback_rows()
        _fast_path_cost()
        self.prepared={}
        self.context_lines={}
        self.content_words={}
        # Native parse rows per line. morphology.tokenize reads only the
        # versioned public dictionaries, never the vocabulary store, so a
        # learned word must not throw these away (48-speed: 3000 lines took
        # 4.4 s to parse again after each automatic learning).
        self.line_tokens={}
        # Lines parsed by the simple splitter after a janome failure: a new
        # process would parse them again, so a reset forgets them.
        self.unsteady=set()
        # Native parses kept across row requests (2026-10-17, speed): while a
        # row is typed, each keystroke parsed the same fragments again (35-46%
        # of a typed row's time). morphology.tokenize reads only the public
        # dictionaries, so a kept parse is the parse a new request would make.
        # morphology bounds both maps (2048 entries, oldest first).
        self._parses=({},{})
        self._parse_lines=frozenset()
        self._parked=[]
        self.index_key=None
        self.index=None
        self._state_identity=None

    def set_state(self,data):
        identity=data.get('_state_identity')
        # only_ime_moved, not same_model_state: rows may be kept across a vocabulary change (used_keys), but the
        # worker's own stores must be the new ones (2026-10-24)
        if identity is not None and only_ime_moved(self._state_identity,identity):
            # Saved input readings affect correction evidence, not the native
            # document context extractors. Keep those unchanged rows while
            # applying the complete latest reading map before the next task.
            import kanji_guess
            from last_choice import set_active
            set_active(self.choices)
            self.ime._pairs=data['ime']
            kanji_guess.set_ime_readings_provider(self._read_ime)
            self._state_identity=identity
            return
        # Untagged callers and every other model change retain a full reset.
        # A failed reset must never authorize later partial state reuse.
        self._state_identity=None
        import contextual_repair
        contextual_repair.clear_grammar_memo()   # a new model: forget the remembered grammar answers (2026-10-30)
        from vocabulary import VocabularyStore
        from dict_index import DictIndex
        from decisions import DecisionStore
        from last_choice import LastChoiceStore,set_active
        from ime_readings import IMEReadings
        from context_vec import ContextVectorStore
        import kanji_guess,charngram,corrector
        self.store=VocabularyStore()
        for entry in data['entries']:
            self.store._by_reading[entry['reading']][entry['surface']]=dict(entry)
        self.store._revision=data['revision']
        self.store._shape_revision=data['revision']
        self.store._shape_revision_ja=data['revision']
        spec=data['index']
        key=(spec['cache_path'],spec['ready'],spec['empty'],repr(spec.get('by_reading')))
        if self.index is None or self.index_key!=key:
            self.index=DictIndex(spec['cache_path'])
            if spec['ready']:
                if spec['empty']:
                    self.index._by_reading={};self.index._by_surface={}
                elif 'by_reading' in spec:
                    self.index._by_reading=spec['by_reading'];self.index._by_surface=spec['by_surface']
                    self.index._world=spec['world']
                elif not self.index._load_cache():
                    # This is a derived public dictionary index. Building here
                    # never calls _save_cache and never writes to the app folder.
                    self.index._build(None)
            self.index_key=key
        # The in-memory branch carries the same native inflection table
        # as the public disk cache. Restore it on every state update.
        if 'inflected' in spec:self.index._inflected=spec['inflected']
        self.index._band=spec['band']
        self.decisions=DecisionStore()
        for name,value in data['decisions'].items():setattr(self.decisions,name,value)
        self.choices=LastChoiceStore()
        for name,value in data['choices'].items():setattr(self.choices,name,value)
        self.choices._revision=data['choice_revision'];self.choices.bind(self.store,self.index)
        set_active(self.choices)
        self.ime=IMEReadings();self.ime._pairs=data['ime']
        kanji_guess.set_ime_readings_provider(self._read_ime)
        self.context_vec=None
        if data['context'] is not None:
            self.context_vec=ContextVectorStore()
            self.context_vec._co=defaultdict(lambda:defaultdict(int),
                {k:defaultdict(int,v) for k,v in data['context'].items()})
            self.context_vec._totals=defaultdict(int,{k:sum(v.values()) for k,v in data['context'].items()})
            self.context_vec.seeded=data['context_seeded'];self.context_vec.seed_version=data['context_seed_version']
        charngram._LEARNED=data['charngram'];charngram._SEEN=set()
        charngram._TABLE=None;charngram._CONTEXT=None;charngram._DIRTY=False
        self.tokenize=corrector.make_tokenizer(self.store);self.store._tokenize_fn=self.tokenize
        self.prepared.clear()
        self.context_lines.clear()
        from morphology import HAS_JANOME
        if not HAS_JANOME:
            # The fallback splitter asks the store, so its rows follow it.
            self.content_words.clear();self.line_tokens.clear()
        for line in self.unsteady:
            self.content_words.pop(line,None);self.line_tokens.pop(line,None)
        self.unsteady=set()
        self._state_identity=identity

    def _forget_parses(self):
        for kept in self._parses:kept.clear()

    # The rows of a tab left behind, packed, for when it comes back (2026-11-03): after going to another tab and
    # back, the first key in a 3,600-line tab parsed 1,600 rows again (6.7 s before the row was looked at). They read
    # only the public dictionaries (line_tokens), so they are the rows prepare would make. In this process's memory only.
    PARK_TABS = 2
    PARK_MIN_LINES = 300

    def _pack_rows(self):
        if len(self.line_tokens)<self.PARK_MIN_LINES:return None
        import pickle,zlib
        words={line:self.content_words[line] for line in self.line_tokens if line in self.content_words}
        return zlib.compress(pickle.dumps((self.line_tokens,words),protocol=pickle.HIGHEST_PROTOCOL),1)

    def _unpack_rows(self,blob,current):
        import pickle,zlib
        rows,words=pickle.loads(zlib.decompress(blob))
        for line,value in rows.items():
            if line in current:self.line_tokens.setdefault(line,value)
        for line,value in words.items():
            if line in current:self.content_words.setdefault(line,value)

    def _park_parses(self):
        blob=self._pack_rows()
        if blob is None:return
        self._parked.append((frozenset(self.line_tokens),blob))
        del self._parked[:-self.PARK_TABS]

    def _take_parked(self,current):
        for index,(lines,blob) in enumerate(self._parked):
            if len(current&lines)*2>=len(current):
                del self._parked[index]
                self._unpack_rows(blob,current)
                return

    @contextmanager
    def _kept_parses(self):
        """Let this request's tokenization scope use the kept parses."""
        import morphology
        if not morphology.HAS_JANOME:
            yield;return
        failures=_FALLBACK_ROWS[0]
        token=morphology._TOKENIZATION_CACHE.set(self._parses[0])
        native=morphology._NATIVE_TOKENIZATION_CACHE.set(self._parses[1])
        try:yield
        finally:
            morphology._NATIVE_TOKENIZATION_CACHE.reset(native)
            morphology._TOKENIZATION_CACHE.reset(token)
            # A row janome failed on was parsed by the simple splitter; a new
            # request would try janome again, so nothing of it is kept.
            if _FALLBACK_ROWS[0]!=failures:self._forget_parses()

    def prepare(self,lines):
        key=tuple(lines)
        current=frozenset(lines)
        if len(current&self._parse_lines)*2<len(current):
            # Another text (a tab switch): its fragments are not kept.
            self._forget_parses()
            from morphology import HAS_JANOME
            if HAS_JANOME:
                self._park_parses()
                self._take_parked(current)
        self._parse_lines=current
        if key in self.prepared:return self.prepared[key]
        from literal_lines import literal_only,prepared
        if all(literal_only(line) for line in lines):return prepared(lines)
        from vocabulary import build_context_vocab_cached
        from context_vec import extract_content_words
        # Keep line extraction across local edits. The vocabulary helper checks
        # the store shape and prunes deleted lines; set_state clears both maps.
        attested={};words={};rows_by_line={}
        from morphology import tokenize,tokenization_scope,Token,HAS_JANOME
        unsteady={line for line in self.unsteady if line in self.content_words}
        def parse_context_line(line):
            # Both context vocab and content words use the same native parse,
            # through their original extractors. Release raw tokens per row.
            rows=self.line_tokens.get(line) if HAS_JANOME else None
            if rows is not None and line in self.content_words:
                rows_by_line[line]=rows
                return [Token(*row) for row in rows]
            failures=_FALLBACK_ROWS[0]
            with tokenization_scope():
                tokens=tokenize(line)
                if line not in self.content_words:
                    words[line]=extract_content_words(self.tokenize,line)
                if _FALLBACK_ROWS[0]!=failures:unsteady.add(line)
                elif HAS_JANOME:rows_by_line[line]=_native_rows(tokens)
                return tokens
        from literal_lines import literal_only
        ordinary=[]
        for line in lines:
            if literal_only(line):
                if line.strip():words[line]=[]
            else:ordinary.append(line)
        context=build_context_vocab_cached(ordinary,self.store,self.context_lines,
                    attested_out=attested,tokenize_fn=parse_context_line)
        from analysis_context import check_current_request
        for line in dict.fromkeys(lines):
            # Each check reads the request queue (about 14us); one row a time
            # cost a 3000-row prepare 40ms of its 110ms per keystroke. The
            # request's 5ms cadence still notices a newer request in time.
            check_current_request(frequent=True)
            if line.strip() and line not in words:
                if line in self.content_words:words[line]=self.content_words[line]
                else:
                    failures=_FALLBACK_ROWS[0]
                    words[line]=extract_content_words(self.tokenize,line)
                    if _FALLBACK_ROWS[0]!=failures:unsteady.add(line)
        self.content_words=words
        # Keep rows only for the lines in use, like content_words. A line the
        # context cache did not need to parse keeps its earlier rows.
        for line in ordinary:
            if line not in rows_by_line and line in self.line_tokens:
                rows_by_line[line]=self.line_tokens[line]
        self.line_tokens=rows_by_line
        self.unsteady={line for line in unsteady if line in words}
        for line in self.unsteady:self.line_tokens.pop(line,None)
        value=dict(context=context,attested=attested,words=words)
        self.prepared[key]=value
        while len(self.prepared)>4:self.prepared.pop(next(iter(self.prepared)))
        return value

    def warm_lines(self,lines):
        """Parse the open tab's lines while the app waits for its start (2026-11-01, speed).

        The first prepare of a 3,600-line tab spent 2.9 s in janome after the
        English relearning answered, with this child idle before it. The rows
        and content words read only the public dictionaries (see line_tokens),
        so they are the ones prepare would make; prepare then reuses them.
        A real request interrupts this; the lines parsed so far are kept.
        """
        from morphology import HAS_JANOME,tokenize,tokenization_scope
        if not HAS_JANOME:return
        from literal_lines import literal_only
        from context_vec import extract_content_words
        from analysis_context import check_current_request
        import corrector
        native=getattr(self,'tokenize',None) or corrector.make_tokenizer(None)
        for line in dict.fromkeys(lines):
            check_current_request(frequent=True)
            if (not line.strip() or literal_only(line) or line in self.unsteady
                    or (line in self.line_tokens and line in self.content_words)):continue
            failures=_FALLBACK_ROWS[0]
            with tokenization_scope():
                rows=_native_rows(tokenize(line))
                words=extract_content_words(native,line)
            # A janome failure fell back to the simple splitter: prepare tries again.
            if _FALLBACK_ROWS[0]!=failures:continue
            self.line_tokens[line]=rows;self.content_words[line]=words

    def _read_ime(self,surface):
        values=self.ime.readings_for(surface)
        queries=getattr(self,'_ime_queries',None)
        if queries is not None:queries[surface]=tuple(values)
        return values

    def quick(self,task):
        # Preserve quick input's context and unit policy. Native interfaces live
        # for one line, as at the main correction entry, then close in the child.
        # メモ欄と同じ入口（2026-11-05 補正の担当: correction_entry の段が簡易入力で効いていなかった）
        from correction_entry import correct_line
        from tab_context import tab_has_kana
        tab_kana=tab_has_kana(chr(10).join(task['lines']))
        from ime_session import resource_scope
        from ime_colloquial import source_tokenizer
        keyboard_layout.apply_spec(task.get('keyboard'))   # 変わらなければ無料
        from morphology import tokenization_scope
        from quote_calculator import apply_to_result
        from units import build_line_units,build_suspect_units
        known=set(task.get('attested',()))
        def known_kana(text):
            return bool(text and len(text)>=2 and
                        (self.store.has_reading(text) or text in known))
        from analysis_work import current_input
        results=[];original_units=[];corrected_units=[];navigation={}
        from text_navigation import plans
        def collect_navigation(line,corrected):
            texts=(line,corrected[0]) if corrected is not None else (line,)
            missing=[text for text in dict.fromkeys(texts) if text not in navigation]
            navigation.update(plans(missing,self.tokenize))
        from analysis_context import check_current_request
        from quick_row_reuse import restored
        for index,line in enumerate(task['lines']):
            check_current_request()
            reused=restored(task,index)
            if reused is not None:
                result,units,corrected=reused
                with tokenization_scope(),resource_scope():
                    collect_navigation(line,corrected)
                results.append(result);original_units.append(units);corrected_units.append(corrected)
                continue
            if not line:
                results.append(None);original_units.append([]);corrected_units.append(None)
                continue
            from literal_lines import literal_only,result as literal_result,units as literal_units
            if literal_only(line):
                results.append(literal_result(line));original_units.append([]);corrected_units.append(literal_units(line))
                continue
            with tokenization_scope(),resource_scope():
                with current_input(line,task.get('readings',{}).get(index,())):
                    # The same source-local native lemma/inflection proof as the
                    # main entry. It never changes tokenization of trial outputs.
                    tokenize=source_tokenizer(line,self.tokenize)
                    readings=task.get('readings',{}).get(index,())
                    _early_begin(line,index)
                    result=correct_line(line,self.store,decisions=self.decisions,
                        input_method=task['input_method'],context_vec=self.context_vec,
                        dict_index=self.index,occurrence_readings=readings,
                        occurrence_strokes=occurrence_strokes(readings),
                        tab_has_kana=tab_kana,previous_line=(task['lines'][index-1] if index else None),
                        defer_heavy=bool(task.get('defer_heavy')),**_early_hook(correct_line))
                    _early_end()
                    result.pop('used_keys',None)    # 裏のタブのやり直し用。簡易入力では使わない
                    result=apply_to_result(result,task['calculations'].get(index,()),
                                         self.decisions,tokenize,self.index)
                    from colloquial_pos import pos_tokenizer   # 品詞の表示だけ（おもしれえ・2026-11-09）
                    original_units.append(build_suspect_units(result,pos_tokenizer(tokenize),
                                          self.choices,known_kana)[1])
                    corrected_units.append(build_line_units(result,pos_tokenizer(tokenize),
                                           self.choices,known_kana))
                    results.append(result)
                # Reuse the same native row scope after original-input evidence
                # ends. Navigation uses the ordinary tokenizer, as before.
                collect_navigation(line,corrected_units[-1])
        return dict(results=results,units=original_units,corrected_units=corrected_units,
                    navigation=navigation)

    def prepare_tables(self):
        if getattr(self,'tables_ready',False):return
        from analysis_context import check_current_request
        from corrector import _table_readings_for_surface
        from familiar_nominal import families
        import oddness,seed_japanese
        # Keep common preparation small. Optional language resources retain
        # their ordinary demand loaders when a particular row needs them.
        for load in (families,lambda:_table_readings_for_surface(''),
                     seed_japanese.available,oddness._load):
            check_current_request()
            load()
        self.tables_ready=True

    def _english_relearn(self,task):
        """起動時の英単語の覚え直しを、この子で（本体の窓を止めない・2026-10-31）。本体の語彙と最後の選択の写しで
        loanword.relearn_english_from_texts を回し、覚えた順の (読み, 語, 回数) を返す（本体は同じ足し方をなぞる）。
        求めに warm があれば、そのあと表の先読み（warmup と同じ）もする（子は新しい求めで古い求めを捨てるので）。"""
        from vocabulary import VocabularyStore
        from last_choice import LastChoiceStore,set_active
        import loanword
        store=VocabularyStore()
        for entry in task['entries']:
            store._by_reading[entry['reading']][entry['surface']]=dict(entry)
        revision=task.get('revision',0)
        store._revision=store._shape_revision=store._shape_revision_ja=revision
        choices=LastChoiceStore()
        for name,value in (task.get('choices') or {}).items():setattr(choices,name,value)
        choices._revision=task.get('choice_revision',0);choices.bind(store,None)
        previous=getattr(self,'choices',None)
        set_active(choices)
        record=[]
        try:
            loanword.relearn_english_from_texts(task['texts'],store,record=record)
        finally:
            set_active(previous)
        if task.get('warm'):
            try:self.execute(dict(kind='warmup'))
            except Exception:traceback.print_exc()
        return dict(record=record)

    def execute(self,task):
        kind=task['kind']
        if kind=='quick':return self.quick(task)
        if kind=='quick_prepare':
            from analysis_context import check_current_request
            from familiar_nominal import families
            import oddness
            check_current_request()
            families()
            from corrector import _table_readings_for_surface
            check_current_request()
            _table_readings_for_surface('')
            check_current_request()
            oddness._load()
            return None
        if kind=='initial_dictionary':
            from janome_import import collect_import_entries
            return collect_import_entries()
        if kind=='english_relearn':
            return self._english_relearn(task)
        if kind in ('warmup','prepare'):
            # The cache limits it sets on morphology: before this child's first tokens, not after them (the
            # limit only drops one entry per new one, so a cache already past it would stay that size)
            import correction_entry  # noqa: F401
        if kind=='warmup':
            try:
                self.prepare_tables()
                # What every first row of a child reads and nothing loaded ahead (2026-11-07, speed): the kana
                # rules (pos_seq_odd, 3.5 s to read the cost table) and the classified-word index (collocation
                # repair, 0.9 s). Public tables only; the row would load the same ones itself.
                from analysis_context import check_current_request
                import kana_rules,semantic_class
                for load in (kana_rules._load,semantic_class._data):
                    check_current_request()
                    load()
                # This optional public index runs only in prewarm. A real
                # request interrupts its dictionary walk; normal preparation
                # never waits for an index the current text may not need.
                from analysis_context import check_current_request
                import loanword,reading_likelihood
                for load in (loanword._english_seed,reading_likelihood._distributions):
                    check_current_request()
                    load()
                check_current_request()
                from contextual_repair import _native_written_nominal_readings,_seed_context
                from ngram_yomi import _bigram_counts
                _native_written_nominal_readings()
                for load in (_bigram_counts,_seed_context):
                    check_current_request()
                    load()
            except Exception:traceback.print_exc()  # Real preparation retries and reports failures.
            try:
                # The reading lattice (kana_lattice_place) loads its saved table here while no line is waiting;
                # a failure only means the first line loads it (2026-10-25). Only a saved table: making it reads
                # janome.sysdic.entries(), after which a DictIndex built in this process comes out empty
                # (tools_local/lattice_memtest_20261025), so the warmup never makes it
                from analysis_context import check_current_request
                check_current_request()
                import reading_lattice
                reading_lattice.load(build=False)
            except Exception:pass
            if task.get('lines'):
                try:self.warm_lines(task['lines'])
                except Exception:traceback.print_exc()  # prepare parses what is left
            try:
                # What the reconversion list reads and this child does not have yet (ask_child); a row interrupts it
                from analysis_context import check_current_request
                check_current_request()
                import synonyms
                table=synonyms.load_table()
                if table:table.by_reading('')
                check_current_request()
                synonyms.synonyms('見る')
            except Exception:pass
            return dict(ready=getattr(self,'tables_ready',False))
        if kind=='candidates':
            # The reconversion list, here where the tables are (analysis_async.ask_child, 2026-11-02)
            from candidates import build_candidates,build_range_candidates
            from vocabulary import find_known_readings_flex
            options=dict(dict_index=self.index,context_vec=self.context_vec,**task['options'])
            if task.get('segments') is not None:
                return build_range_candidates(task['segments'],self.store,find_known_readings_flex,**options)
            return build_candidates(task['surface'],task['reading'],self.store,find_known_readings_flex,**options)
        if kind=='particle_choices':
            from candidates import particle_intrusion_candidates
            return particle_intrusion_candidates(task['text'],task['start'],task['end'],self.index)
        if kind=='suspect_units':
            # The word units of a row not analysed yet, for F5 and the right-click list (app._editor_line_units)
            from units import build_suspect_units
            known=set(task['attested'])
            def known_kana(text):
                return bool(text and len(text)>=2 and (self.store.has_reading(text) or text in known))
            from colloquial_pos import pos_tokenizer
            return build_suspect_units(task['result'],pos_tokenizer(self.tokenize),self.choices,known_kana)[1]
        if kind=='packed_rows':
            # This child is about to be given back: the window keeps the rows for the next one (analysis_async.keep_rows)
            self._park_parses()
            return dict(tabs=self._parked)
        if kind=='plans':
            # Sizes and stops of rows on screen still waiting for their analysis (boundary_colors, 2026-11-03)
            from text_navigation import plans
            return plans(task['texts'],self.tokenize)
        if kind=='synonyms':
            import synonyms
            return synonyms.synonyms(task['text'])
        if kind=='odd_run':
            import corrector
            return corrector.lu_run_candidates(task['run'],self.store,self.index,self.tokenize,input_method=task['input_method'])
        if kind=='explain_pos':
            import explain
            return explain.pos_lines(task['text'],self.tokenize,store=self.store,dict_index=self.index,**task['options'])
        if kind=='explain_reason':
            import explain
            return explain.reason_lines(task['typed'],task['fixed'],unit=task['unit'],line=task['line'],
                                        input_method=task['input_method'],tokenize_fn=self.tokenize,store=self.store,
                                        dict_index=self.index,choices=self.choices,recorded=task['recorded'])
        if kind=='parse_lines':
            # A short-lived startup child parses part of the open tab (analysis_async.start_startup_parse).
            self.warm_lines(task['lines'])
            # One block of bytes: the app passes it on without unpacking the rows (0.3 s of its window, 2026-11-01)
            import pickle
            return dict(blob=pickle.dumps((self.line_tokens,self.content_words),protocol=pickle.HIGHEST_PROTOCOL))
        if kind=='prepare':
            parsed=task.get('parsed')
            if parsed:
                # Lines the startup children parsed: the rows prepare would make (warm_lines)
                import pickle
                for blob in parsed['blobs']:
                    rows,words=pickle.loads(blob)
                    for line,value in rows.items():self.line_tokens.setdefault(line,value)
                    for line,value in words.items():self.content_words.setdefault(line,value)
            if task.get('packed') is not None:
                from morphology import HAS_JANOME
                if HAS_JANOME:self._unpack_rows(task['packed'],frozenset(task['lines']))
            from literal_lines import literal_only
            if any(not literal_only(line) for line in task['lines']):self.prepare_tables()
            return self.prepare(task['lines'])
        from morphology import tokenization_scope
        from ime_session import resource_scope,run_activity
        # The same input row produces correction and display units. Reuse
        # read-only resources through both phases, then release them together.
        # Rows corrected one after another share the native IME's answers
        # (ime_session.run_activity: a pause ends the run, 2026-11-01).
        run_activity(True)
        try:
            with self._kept_parses(),tokenization_scope(),resource_scope():
                return self._line_task(task)
        finally:
            run_activity(False)

    def _line_task(self,task):
        kind=task['kind']
        prepared=self.prepare(task['lines']) if kind=='units' and task.get('lines') is not None else None
        tracked=None;ime_evidence=None
        nearby=task.get('nearby',())
        context=task.get('context')
        if kind=='line' and context is None and task.get('lines') is not None:
            # A row sent ahead with its whole text (2026-10-17: the row being
            # composed in the IME, before the commit). Prepare first, then
            # take the context and the nearby words from that preparation,
            # as the UI does after the same prepare (_nearby_words_for).
            prepared=self.prepare(task['lines'])
            context=prepared['context']
            if nearby is None:
                from context_vec import build_nearby_words,extract_content_words
                lines=task['lines'];words=prepared['words']
                def words_of(k):
                    got=words.get(lines[k])
                    return got if got is not None else extract_content_words(self.tokenize,lines[k])
                nearby=build_nearby_words(len(lines),task['row'],words_of)
        if kind=='line':
            from correction_entry import correct_line
            from analysis_context import Reads
            tracked=Reads(context)
            keyboard_layout.apply_spec(task.get('keyboard'))   # 配列・形（48-KB）
            self._ime_queries={}
            try:
                # Whether the file tab has kana (half-width -> full-width only then, 2026-10-26), passed when
                # correct_line takes it (tab_context); None or an older correct_line: as before
                tab_kana=task.get('tab_has_kana')
                extra=dict(tab_has_kana=tab_kana) if tab_kana is not None and _takes_tab_has_kana(correct_line) else {}
                # The row above, for a row that opens on a particle (correction_entry, 2026-11-02)
                if task.get('previous_line') is not None and _takes_previous_line(correct_line):
                    extra['previous_line']=task['previous_line']
                if task.get('defer_heavy') and _takes_defer_heavy(correct_line):
                    extra['defer_heavy']=True
                _early_begin(task['line'])
                extra.update(_early_hook(correct_line))
                result=correct_line(task['line'],self.store,context_vocab=tracked,
                    decisions=self.decisions,input_method=task['input_method'],
                    context_vec=self.context_vec,dict_index=self.index,
                    nearby_words=nearby,recent_words=task.get('recent',()),
                    occurrence_readings=task.get('readings',()),
                    occurrence_calculations=task.get('calculations',()),
                    occurrence_strokes=occurrence_strokes(task.get('readings',())),**extra)
                _early_end()
                if isinstance(result,dict) and result.get('deferred_stages'):
                    # Not final, redone when the typing stops: nothing may keep it across a model change
                    result=dict(result);result.pop('used_keys',None)
                if tab_kana is not None and isinstance(result,dict):
                    # which tab state made this row: the app redoes it when the tab gains or loses its kana
                    result=dict(result,_tab_has_kana=tab_kana)
                ime_evidence=tuple(sorted(self._ime_queries.items()))
            finally:
                self._ime_queries=None
        elif kind=='units':result=task['result']
        else:raise ValueError('Unknown analysis task: '+str(kind))
        from units import build_line_units,build_suspect_units
        known=set(prepared['attested'] if prepared is not None else task.get('attested',()))
        unit_keys={}
        def known_kana(text):
            if not text or len(text)<2:return False
            if self.store.has_reading(text):return True
            present=text in known;unit_keys[text]=present
            return present
        from colloquial_pos import pos_tokenizer       # 品詞の表示だけ（おもしれえ・2026-11-09）
        _pos_fn=pos_tokenizer(self.tokenize)
        corrected_units=build_line_units(result,_pos_fn,self.choices,known_kana)
        original_units=build_suspect_units(result,_pos_fn,self.choices,known_kana)
        evidence=tracked.evidence(unit_keys.items()) if tracked is not None else None
        if evidence is None and result.get('_context_evidence') is not None:
            evidence=dict(result['_context_evidence'],unit_keys=tuple(sorted(unit_keys.items())))
        from analysis_context import signature
        inputs=(signature(nearby,task.get('readings',()),task.get('calculations',()),task.get('previous_line'))
                if kind=='line' else result.get('_input_signature'))
        from text_navigation import plans
        navigation=plans((result['original'],result['corrected'],original_units[0],corrected_units[0]),self.tokenize)
        return dict(result=result,prepared=prepared,context_evidence=evidence,input_signature=inputs,
                    ime_evidence=ime_evidence,
                    navigation=navigation,
                    corrected_units=corrected_units,original_units=original_units)


_TAKES_TAB_KANA={}
_TAKES_PREVIOUS={}
_TAKES_DEFER={}


def _takes_tab_has_kana(function):
    """Whether correct_line has the tab_has_kana parameter (it comes with tab_context, 2026-10-26)."""
    key=function            # the function itself (an id could be reused by another function later)
    if key not in _TAKES_TAB_KANA:
        try:
            import inspect
            _TAKES_TAB_KANA[key]='tab_has_kana' in inspect.signature(function).parameters
        except (TypeError,ValueError):
            _TAKES_TAB_KANA[key]=False
    return _TAKES_TAB_KANA[key]


def _takes_previous_line(function):
    """Whether correct_line has the previous_line parameter (correction_entry, 2026-11-02)."""
    if function not in _TAKES_PREVIOUS:
        try:
            import inspect
            _TAKES_PREVIOUS[function]='previous_line' in inspect.signature(function).parameters
        except (TypeError,ValueError):
            _TAKES_PREVIOUS[function]=False
    return _TAKES_PREVIOUS[function]


def _takes_defer_heavy(function):
    """Whether correct_line has the defer_heavy parameter (correction_entry, 2026-11-02)."""
    if function not in _TAKES_DEFER:
        try:
            import inspect
            _TAKES_DEFER[function]='defer_heavy' in inspect.signature(function).parameters
        except (TypeError,ValueError):
            _TAKES_DEFER[function]=False
    return _TAKES_DEFER[function]


def occurrence_strokes(readings):
    """The commits whose keys are known, as correction_entry.correct_line takes them:
    [(start, end, surface, reading, strokes, shifts)] (shift_slip.ShiftStrokeClock.take)."""
    return [(x.start,x.end,x.surface,x.reading,tuple(x.strokes),tuple(getattr(x,'shifts',()))) for x in readings or ()
            if getattr(x,'strokes',())]


def _take_usage():
    """How the correction stages were used since the last answer (numbers only, usage_counts), or None."""
    try:
        import usage_counts
        return usage_counts.take()
    except Exception:
        return None


def respell_setting():
    """In the main process: the respell debug values to send with each request (odd_respell's switches in this
    process, set by the debug menu): (rank stats on, attempt limit). None while odd_respell is not loaded here."""
    module=sys.modules.get('odd_respell')
    if module is None:return None
    return (bool(getattr(module,'RANK_STATS_ON',False)),int(getattr(module,'ATTEMPT_LIMIT',0) or 0))


def _apply_respell(setting):
    """In the child: take the main process's respell debug values (2026-11-10 うにさん: rank stats, attempt limit)."""
    if setting is None and 'odd_respell' not in sys.modules:return
    try:
        import odd_respell
        # 本体に値が無い頼み（本体で odd_respell を読んでいない）は、この子の odd_respell の既定のまま
        # （上限を 0＝上限なしへ落とさない。2026-11-10 既定を 6 にした時）
        if not hasattr(odd_respell,'_CN_DEFAULT_LIMIT'):
            odd_respell._CN_DEFAULT_LIMIT=int(getattr(odd_respell,'ATTEMPT_LIMIT',0) or 0)
        on,limit=setting if setting is not None else (False,odd_respell._CN_DEFAULT_LIMIT)
        odd_respell.set_rank_stats(on)
        odd_respell.set_attempt_limit(limit)
    except Exception:
        pass


def _take_respell():
    module=sys.modules.get('odd_respell')
    take=getattr(module,'take_rank_stats',None)
    if take is None:return None
    try:return take()
    except Exception:return None


def merge_usage(result):
    """In the main process: add a child's numbers once (the answer no longer carries them)."""
    if isinstance(result,dict) and 'respell' in result:
        stats=result.pop('respell')
        if stats:
            try:
                import respell_stats
                respell_stats.merge(stats)
            except Exception:
                pass
    if isinstance(result,dict) and 'usage' in result:
        usage=result.pop('usage')
        if usage:
            try:
                import usage_counts
                usage_counts.merge(usage)
            except Exception:
                pass


def _exit_with_parent():
    """End this process when the main window's process is gone (2026-10-23 うにさん: a child kept ~600-850 MB
    after its parent was killed or crashed). `daemon=True` covers only a parent that exits normally. With
    `spawn` the child already holds a handle to its parent (`multiprocessing.parent_process()`, opened at
    start, so a reused process id cannot fool it); a thread waits on it and ends the process when it fires."""
    import os
    import threading
    parent=mp.parent_process()
    if parent is None:return None
    def watch():
        try:parent.join()
        except Exception:return
        os._exit(0)
    thread=threading.Thread(target=watch,name='exit-with-parent',daemon=True)
    thread.start()
    return thread


def _serve(inbox,outbox,pause_flag=None):
    _exit_with_parent()
    from tsf_worker import worker_connection_scope
    # Native IME answers are kept per typed line for this worker's life
    # (ime_session.line_answers_scope, 2026-10-17 speed).
    from ime_session import line_answers_scope
    with worker_connection_scope() as connection_owner,line_answers_scope():
        _serve_requests(inbox,outbox,connection_owner,pause_flag)


PAUSE_MAX_S=30.0     # 親が戻し忘れても、これより長くは止まらない


WARM_AGAIN_MAX=6     # 割り込まれた先読みをやり直す回数の上限（打ち続けても回り続けない）
POLL_GAP_S=0.002     # 解いている間に新しい頼みを見に行く間（パイプを見るのは1回27マイクロ秒）
WARM_IDLE_S=0.3      # やり直すのは、これだけ求めが来なかった時（行の答えの直後に次の行が来る間は割り込まない）
# 打っている間はやり直さない（2026-11-07）: 0.3秒では打鍵の合い間に始めて次の行で捨てる形が続いていた（PC の作り物の打鍵で
# 6回・1〜2秒の子の時間）。行が読む表は行そのものが読むので、やり直しの残りは任意の表だけ。手が止まって 2秒から。
# CN_WARM_IDLE_S で変えられる（0.3 で前の形）
try:
    import os as _os
    WARM_IDLE_S=float(_os.environ.get('CN_WARM_IDLE_S','2.0'))
except ValueError:
    WARM_IDLE_S=2.0


def _serve_requests(inbox,outbox,connection_owner,pause_flag=None):
    from analysis_context import request_scope,check_current_request,SupersededAnalysis
    runtime=Runtime();no_request=object();pending=no_request
    # The warmup a newer request took over (2026-11-07, speed): the app's prewarm is followed within 0.5 s by
    # its first request, which dropped the warmup before it read a table; the child then sat idle for 3 s and
    # paid 7 s on its first row. It runs again once nothing waits. A row interrupts it as before.
    warm_again=None;warm_tries=0;ran_through=False
    poll_after=[0.0]
    def keep_warmup(old):
        nonlocal warm_again
        if old is not None and old['task'].get('kind')=='warmup' and warm_tries<WARM_AGAIN_MAX:
            # quiet: its answer is not sent (the id is the app's earlier request; nobody waits for it)
            warm_again=dict(old,state=None,quiet=True)
    while True:
        if not connection_owner.pump():return
        if pending is no_request and warm_again is not None:
            request=no_request;until=time.monotonic()+WARM_IDLE_S
            while time.monotonic()<until:
                if not connection_owner.pump():return
                try:request=inbox.get(timeout=.02);break
                except queue.Empty:pass
            if request is no_request:request,warm_again=warm_again,None;warm_tries+=1
        else:
            request=connection_owner.get(inbox) if pending is no_request else pending
        pending=no_request
        if request is None:return
        pending_state=request.get('state')
        while True:
            try:newer=inbox.get_nowait()
            except queue.Empty:break
            if newer is None:return
            if newer.get('state') is not None:pending_state=newer['state']
            keep_warmup(request)
            request=newer
        def superseded():
            nonlocal pending
            if pending is no_request:
                # Look at the pipe at most every POLL_GAP_S (2026-11-07, speed): a row asked this 62,676 times in 17 s,
                # 27 us each on Windows (1.7 s). A newer request is seen at most 2 ms later; answers are the same.
                # The pause (pause_flag) is still honoured on every call.
                now=time.monotonic()
                if now<poll_after[0] and (pause_flag is None or not pause_flag.value):return False
                poll_after[0]=now+POLL_GAP_S
                until=None
                while True:
                    try:pending=inbox.get_nowait()
                    except queue.Empty:
                        if pause_flag is None or not pause_flag.value:return False
                        now=time.monotonic()
                        if until is None:until=now+PAUSE_MAX_S
                        elif now>=until:return False
                        time.sleep(.01)
                        continue
                    break
            return True
        ran_through=False
        try:
            if pending_state is not None:runtime.set_state(pending_state)
            # The store is built: the message's copy of the vocabulary need not stay until the next request (18 MB)
            pending_state=None;request.pop('state',None)
            if request['task']['kind']=='cancel':continue
            _apply_respell(request.get('respell'))
            _EARLY['sink']=(outbox,request['id']);_EARLY['sent']=True
            if request['task']['kind'] in ('quick','quick_prepare','line','units','prepare','warmup','candidates','plans','synonyms','explain_pos','explain_reason','odd_run'):
                # Preserve the next request/state while the old read-only
                # correction unwinds its owned resources and context scopes.
                with request_scope(superseded,poll_interval=.005):
                    result=runtime.execute(request['task'])
                    ran_through=True
                    check_current_request()
            else:result=runtime.execute(request['task'])
            if request['task']['kind']=='english_relearn' and request['task'].get('warm_after'):
                # The app keeps this child for rows (memory high's prefetch child): its tables, once idle
                warm_again=dict(id=request['id'],task=dict(kind='warmup'),state=None,quiet=True)
            if request.get('quiet'):continue
            if request.get('usage') and isinstance(result,dict) and request['task']['kind'] in ('line','units'):
                # how the correction stages were used (numbers only, usage_counts): sent with the answer when the
                # app's Worker asked for it, kept out of Runtime.execute's own answer (2026-10-24)
                usage=_take_usage()
                if (request['task'].get('defer_heavy') and isinstance(result.get('result'),dict)
                        and result['result'].get('deferred_stages')):
                    # 打った行の軽い答え（重い段を外した形）は数えない。重い段のやり直しの答えで1回数える
                    # （2026-11-07 うにさん「軽い答えではカウントしない」）。やり直しの要らない行は、この答えで1回
                    usage=None
                result=dict(result,usage=usage)
            if isinstance(result,dict):
                # 候補の何回目を採ったかの集計（odd_respell・デバッグ・既定オフ）。オフなら何も無い
                stats=_take_respell()
                if stats:result=dict(result,respell=stats)
            outbox.put((request['id'],result,None))
        except SupersededAnalysis:
            # A warmup that ran to its end is not kept (only the last check saw the newer request)
            if not ran_through:keep_warmup(request)
            continue
        except BaseException:
            outbox.put((request['id'],None,traceback.format_exc()))


class _WindowsQueueSender:
    """Keep the queue's named-pipe write interruptible during disposal."""
    def __init__(self,writer,context):
        import _winapi,threading
        self.api=_winapi;self.writer=writer;self.closed=False
        self.lock=threading.Lock()
        self.signal=context.Semaphore(0)
        self.event=self.signal._semlock.handle

    def cancel(self):
        with self.lock:
            if self.closed:return
            self.closed=True
            if self.signal is not None:self.signal.release()

    def dispose(self):
        with self.lock:
            if self.event is not None:
                self.event=None;self.signal=None
            if self.closed:self.writer.close()

    def __del__(self):
        try:self.dispose()
        except Exception:pass

    def send(self,buf):
        import errno
        if self.closed:
            self.dispose()
            raise BrokenPipeError(errno.EPIPE,'Analysis queue disposed')
        api=self.api
        ov,error=api.WriteFile(self.writer.fileno(),buf,overlapped=True)
        cancelled=False
        try:
            if error==api.ERROR_IO_PENDING:
                status=api.WaitForMultipleObjects([ov.event,self.event],False,0xFFFFFFFF)
                if status==1:
                    cancelled=True;ov.cancel()
                else:assert status==0
        except BaseException:
            ov.cancel();raise
        finally:
            try:written,error=ov.GetOverlappedResult(True)
            finally:
                if self.closed:self.dispose()
        if cancelled or self.closed:
            raise BrokenPipeError(errno.EPIPE,'Analysis queue disposed')
        assert error==0 and written==len(buf)


class WorkerExitedError(RuntimeError):
    """The transport lost its process, distinct from an engine exception."""


class Worker:
    """Nonblocking request/response transport; this class never touches Tk."""
    def __init__(self):
        context=mp.get_context('spawn')
        self.inbox=context.Queue();self.outbox=context.Queue()
        # These channels belong only to this disposable process. As in
        # Python's ProcessPoolExecutor, stop a feeder when its peer exits
        # instead of printing errors for deliberately discarded requests.
        # Unexpected process loss still raises WorkerExitedError in poll.
        self.inbox._ignore_epipe=True;self.outbox._ignore_epipe=True
        # 打った行を解いている間だけ立つ（裏の子は止まって待つ・打ち切らない）。本文は通らない
        self.pause_flag=context.RawValue('b',0)
        self.process=context.Process(target=_serve,args=(self.inbox,self.outbox,self.pause_flag),daemon=True)
        self.process.start()
        self.serial=0;self.ready={};self.closed=False;self.partials={}
        self.sender=None
        if sys.platform=='win32':
            self.sender=_WindowsQueueSender(self.inbox._writer,context)
            self.inbox._send_bytes=self.sender.send
    def submit(self,task,state=None):
        if self.closed:raise RuntimeError('Analysis worker is closed')
        self.serial+=1
        self.inbox.put_nowait(dict(id=self.serial,task=task,state=state,usage=True,respell=respell_setting()))
        return self.serial
    def poll(self,request_id):
        while True:
            try:identifier,result,error=self.outbox.get_nowait()
            except queue.Empty:break
            if isinstance(identifier,tuple):
                # 途中の紫（early_marks）: 答えではない。新しい求めの分だけ残す
                self.partials.setdefault(identifier[1],[]).append(result)
                continue
            merge_usage(result)      # counted when it arrives, even when the answer is not used
            self.ready[identifier]=(result,error)
        value=self.ready.pop(request_id,None)
        # Requests superseded by edits or another tab are never retained as text history.
        self.ready={k:v for k,v in self.ready.items() if k>=request_id}
        if value is not None:
            result,error=value
            if error:raise RuntimeError(error)
            return result
        if not self.closed and not self.process.is_alive():
            raise WorkerExitedError('Analysis process exited before returning a result')
        return None
    def take_partial(self,request_id):
        """この求めの途中の紫（届いた順）。答えが来た後や古い求めの分は捨てる。"""
        partials=getattr(self,'partials',None)
        if not partials:return ()
        got=partials.pop(request_id,())
        for k in [k for k in partials if k<request_id]:partials.pop(k,None)
        return got

    def trim_memory(self):
        """Hand the idle child's resident memory back to Windows (EmptyWorkingSet, 2026-11-01). The process
        stays, so the next row needs no new child: Task Manager's memory 501 -> 57MB, the first typed row 0.33s
        (a new child: 5.6s). Pages come back as the next row touches them. True when done."""
        if self.closed or sys.platform!='win32' or not self.process.is_alive():return False
        try:
            import ctypes
            kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=ctypes.c_void_p
            handle=kernel.OpenProcess(0x0100|0x0400,False,self.process.pid)  # SET_QUOTA | QUERY_INFORMATION
            if not handle:return False
            try:
                trim=ctypes.windll.psapi.EmptyWorkingSet;trim.argtypes=[ctypes.c_void_p]
                return bool(trim(handle))
            finally:kernel.CloseHandle(ctypes.c_void_p(handle))
        except Exception:
            return False
    def close(self):
        if self.closed:return
        self.closed=True
        try:self.inbox.put_nowait(None)
        except Exception:pass
        self.process.join(timeout=0.05)
        if self.process.is_alive():self.process.terminate()
        self.process.join(timeout=0.2)
        if self.sender is not None:
            with self.inbox._notempty:self.inbox._buffer.clear()
            self.sender.cancel()
        for channel in (self.inbox,self.outbox):
            channel.cancel_join_thread();channel.close()
        if self.sender is not None:
            feeder=self.inbox._thread
            if feeder is not None:feeder.join(timeout=0.02)
            if feeder is None or not feeder.is_alive():
                self.inbox._reader.close();self.inbox._writer.close()
                self.sender.dispose()
        self.ready.clear()
