# -*- coding: utf-8 -*-
"""Each Worker owns one isolated correction process. State and text stay in memory; no store saves.

The child calls app.correct_line, the same entry used by synchronous checks.
A queue feeder serializes requests outside Tk; newer requests supersede queued
work. Results carry request ids and are accepted by the UI's document checks.
"""
import multiprocessing as mp
import sys
import queue
import traceback
from collections import defaultdict


def state_key(app):
    store=getattr(app,'store',None);choices=getattr(app,'choices',None)
    return (id(store),store.revision() if store is not None else 0,
            choices.revision() if choices is not None else 0,
            getattr(app,'_analysis_state_revision',0), id(getattr(app,'dict_index',None)),
            bool(getattr(getattr(app,'dict_index',None),'ready',False)),
            id(getattr(app,'context_vec',None)),
            (app.settings.get('input_method') or 'kana'),
            tuple(app.recent_words.words()) if getattr(app,'recent_words',None) is not None else (),
            (id(getattr(app,'ime_readings',None)),
             app.ime_readings.revision() if getattr(app,'ime_readings',None) is not None else 0))


def same_model_state(previous,current):
    """Only saved IME readings may differ; all other correction inputs match."""
    return bool(previous is not None and len(previous)==len(current)==10
                and previous[:-1]==current[:-1] and previous[-1][0]==current[-1][0])


def result_compatible(app,result,previous,current=None):
    current=state_key(app) if current is None else current
    if previous==current:return True
    if not same_model_state(previous,current):return False
    if result is None:return False
    if result.get('original')=='':return True
    reads=result.get('_ime_evidence')
    if reads is None:return False
    ime=getattr(app,'ime_readings',None)
    return all(tuple(ime.readings_for(surface) if ime is not None else ())==values
               for surface,values in reads)


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
        choices={name:dict(getattr(choices,name,{})) for name in ('_readings','_units')},
        choice_revision=choices.revision() if choices is not None else 0,
        ime={k:list(v) for k,v in getattr(ime,'_pairs',{}).items()},
        charngram=dict(charngram._LEARNED or {}))


class Runtime:
    def __init__(self):
        self.prepared={}
        self.context_lines={}
        self.content_words={}
        self.index_key=None
        self.index=None

    def set_state(self,data):
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
        self.content_words.clear()

    def prepare(self,lines):
        key=tuple(lines)
        if key in self.prepared:return self.prepared[key]
        from vocabulary import build_context_vocab_cached
        from context_vec import extract_content_words
        # Keep line extraction across local edits. The vocabulary helper checks
        # the store shape and prunes deleted lines; set_state clears both maps.
        attested={}
        context=build_context_vocab_cached(lines,self.store,self.context_lines,attested_out=attested)
        words={line:(self.content_words[line] if line in self.content_words else
                     extract_content_words(self.tokenize,line))
               for line in set(lines) if line.strip()}
        self.content_words=words
        value=dict(context=context,attested=attested,words=words)
        self.prepared[key]=value
        while len(self.prepared)>4:self.prepared.pop(next(iter(self.prepared)))
        return value

    def _read_ime(self,surface):
        values=self.ime.readings_for(surface)
        queries=getattr(self,'_ime_queries',None)
        if queries is not None:queries[surface]=tuple(values)
        return values

    def quick(self,task):
        # Preserve quick input's context and unit policy. Native interfaces live
        # for one line, as at the main correction entry, then close in the child.
        import corrector
        from vocabulary import find_known_readings_flex
        from ime_session import resource_scope
        from ime_colloquial import source_tokenizer
        from quote_calculator import apply_to_result
        from units import build_line_units,build_suspect_units
        known=set(task.get('attested',()))
        def known_kana(text):
            return bool(text and len(text)>=2 and
                        (self.store.has_reading(text) or text in known))
        from analysis_work import current_input
        results=[];original_units=[];corrected_units=[]
        from analysis_context import check_current_request
        for index,line in enumerate(task['lines']):
            check_current_request()
            if not line:
                results.append(None);original_units.append([]);corrected_units.append(None)
                continue
            with resource_scope(), current_input(line,task.get('readings',{}).get(index,())):
                # The same source-local native lemma/inflection proof as the
                # main entry. It never changes tokenization of trial outputs.
                tokenize=source_tokenizer(line,self.tokenize)
                result=corrector.correct_line(line,self.store,tokenize,
                    find_known_readings_flex,decisions=self.decisions,
                    input_method=task['input_method'],context_vec=self.context_vec,
                    dict_index=self.index)
                result=apply_to_result(result,task['calculations'].get(index,()),
                                     self.decisions,tokenize,self.index)
                original_units.append(build_suspect_units(result,tokenize,
                                      self.choices,known_kana)[1])
                corrected_units.append(build_line_units(result,tokenize,
                                       self.choices,known_kana))
                results.append(result)
        return dict(results=results,units=original_units,corrected_units=corrected_units)

    def execute(self,task):
        kind=task['kind']
        if kind=='quick':return self.quick(task)
        if kind=='quick_prepare':
            from familiar_nominal import families
            import oddness
            families()
            from corrector import _table_readings_for_surface
            _table_readings_for_surface('')
            oddness._load()
            return None
        if kind=='initial_dictionary':
            from janome_import import collect_import_entries
            return collect_import_entries()
        if kind=='prepare':return self.prepare(task['lines'])
        prepared=self.prepare(task['lines']) if kind=='units' and task.get('lines') is not None else None
        tracked=None;ime_evidence=None
        if kind=='line':
            from app import correct_line
            from analysis_context import Reads
            tracked=Reads(task['context'])
            self._ime_queries={}
            try:
                result=correct_line(task['line'],self.store,context_vocab=tracked,
                    decisions=self.decisions,input_method=task['input_method'],
                    context_vec=self.context_vec,dict_index=self.index,
                    nearby_words=task.get('nearby',()),recent_words=task.get('recent',()),
                    occurrence_readings=task.get('readings',()),
                    occurrence_calculations=task.get('calculations',()))
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
        corrected_units=build_line_units(result,self.tokenize,self.choices,known_kana)
        original_units=build_suspect_units(result,self.tokenize,self.choices,known_kana)
        evidence=tracked.evidence(unit_keys.items()) if tracked is not None else None
        if evidence is None and result.get('_context_evidence') is not None:
            evidence=dict(result['_context_evidence'],unit_keys=tuple(sorted(unit_keys.items())))
        from analysis_context import signature
        inputs=(signature(task.get('nearby',()),task.get('readings',()),task.get('calculations',()))
                if kind=='line' else result.get('_input_signature'))
        return dict(result=result,prepared=prepared,context_evidence=evidence,input_signature=inputs,
                    ime_evidence=ime_evidence,
                    corrected_units=corrected_units,original_units=original_units)


def _serve(inbox,outbox):
    from analysis_context import request_scope,check_current_request,SupersededAnalysis
    runtime=Runtime();no_request=object();pending=no_request
    while True:
        request=inbox.get() if pending is no_request else pending
        pending=no_request
        if request is None:return
        pending_state=request.get('state')
        while True:
            try:newer=inbox.get_nowait()
            except queue.Empty:break
            if newer is None:return
            if newer.get('state') is not None:pending_state=newer['state']
            request=newer
        def superseded():
            nonlocal pending
            if pending is no_request:
                try:pending=inbox.get_nowait()
                except queue.Empty:return False
            return True
        try:
            if pending_state is not None:runtime.set_state(pending_state)
            if request['task']['kind']=='cancel':continue
            if request['task']['kind']=='quick':
                # Preserve the next request/state while the old read-only
                # correction unwinds its owned resources and context scopes.
                with request_scope(superseded):
                    result=runtime.execute(request['task'])
                    check_current_request()
            else:result=runtime.execute(request['task'])
            outbox.put((request['id'],result,None))
        except SupersededAnalysis:
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
        self.process=context.Process(target=_serve,args=(self.inbox,self.outbox),daemon=True)
        self.process.start()
        self.serial=0;self.ready={};self.closed=False
        self.sender=None
        if sys.platform=='win32':
            self.sender=_WindowsQueueSender(self.inbox._writer,context)
            self.inbox._send_bytes=self.sender.send
    def submit(self,task,state=None):
        if self.closed:raise RuntimeError('Analysis worker is closed')
        self.serial+=1
        self.inbox.put_nowait(dict(id=self.serial,task=task,state=state))
        return self.serial
    def poll(self,request_id):
        while True:
            try:identifier,result,error=self.outbox.get_nowait()
            except queue.Empty:break
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