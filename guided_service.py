"""Versioned guided runs and background jobs for the local HTTP server."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import uuid

import yaml

import guided_tailoring as engine
import staged_generation as drafting
from knowledge import knowledge_snapshot, read_knowledge, save_entries, scopes, storage_notice
from tailor import ROOT, TailorError, normalize_parsed_jd

RUNS = ROOT / 'output' / 'tailored'
LOCK = threading.RLock()
JOBS = set()


def master_snapshot():
    raw = (ROOT / 'content/master.yaml').read_bytes()
    return yaml.safe_load(raw), hashlib.sha256(raw).hexdigest()


def path_for(run_id):
    import re
    if not isinstance(run_id, str) or not re.fullmatch(r'\d{8}-\d{6}-[0-9a-f]{6}', run_id):
        raise TailorError('Invalid run ID.')
    return RUNS / run_id / 'guided.json'


def read_run(run_id):
    path = path_for(run_id)
    if not path.is_file(): raise TailorError('This guided run was not found.')
    run = json.loads(path.read_text(encoding='utf-8'))
    if run['master_hash'] != master_snapshot()[1]:
        raise TailorError('The master resume changed. Start a new run; saved knowledge is retained.')
    if run['rules_hash'] != engine.rules_digest():
        raise TailorError('Resume rules or template changed. Start a new run to validate against them.')
    return run


def save_run(run):
    run['revision'] = run.get('revision', 0) + 1
    path = path_for(run['run_id'])
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(run, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def public(run):
    result = deepcopy(run)
    for key in ['master_hash','rules_hash','proposal_path','final_path','attempts']:
        result.pop(key, None)
    if run.get('draft'):
        master = master_snapshot()[0]
        result['changes'] = engine.changes_for(master, run['draft'])
        effective,_,findings,pending = review_state(run)
        result['current_draft']=effective
        result['resume_content']=engine.compose(master,effective)
        result['findings']=findings
        result['unchecked_fields']=pending
        result['knowledge_changed']=knowledge_snapshot(master)['revision']!=run['knowledge']['revision']
        result['entry_labels'] = scopes(master)
        result['evidence'] = engine.evidence_catalog(master, run['knowledge'])
        result['proposal_url'] = f"/api/guided/pdf/{run['run_id']}/proposal?v={run['revision']}" if run.get('proposal_path') else None
    result['final_url'] = f"/api/guided/pdf/{run['run_id']}/final?v={run['revision']}" if run.get('final_path') else None
    return result


def launch(run, operation, worker):
    identifier = run['run_id']
    if identifier in JOBS: raise TailorError('A task is already running for this resume.')
    JOBS.add(identifier)
    run['task'] = {'state':'running','operation':operation,'message':'Starting…'}
    run.pop('error', None)
    try:
        save_run(run)
    except Exception:
        JOBS.discard(identifier)
        raise
    def progress(message):
        with LOCK:
            current = read_run(identifier)
            current['task']['message'] = message
            save_run(current)
    def execute():
        try:
            updates = worker(deepcopy(run), progress)
            with LOCK:
                current = read_run(identifier)
                if operation == 'finish' and knowledge_snapshot(master_snapshot()[0])['revision'] != current['knowledge']['revision']:
                    raise TailorError('Knowledge changed while the final PDF was being checked. Check the draft with the latest facts before finishing.')
                current.update(updates)
                current['task'] = {'state':'done','operation':operation,'message':'Ready'}
                save_run(current)
        except Exception as error:
            with LOCK:
                # Preserve drafts/answers even if the master changes during a job.
                path = path_for(identifier)
                current = json.loads(path.read_text())
                current['task'] = {'state':'error','operation':operation,'message':str(error)}
                current['error'] = str(error)
                save_run(current)
        finally:
            with LOCK: JOBS.discard(identifier)
    threading.Thread(target=execute, daemon=True).start()


def ensure_editable(run, body):
    if run['run_id'] in JOBS: raise TailorError('Wait for the current task to finish.')
    if body.get('revision') != run['revision']:
        raise TailorError('This run changed in another tab. Reload the saved run before editing.')


def analysis_worker(run, progress):
    progress('Reading the master resume and saved knowledge before asking questions')
    master = master_snapshot()[0]
    snapshot = knowledge_snapshot(master)
    analysis = engine.analyze(run['parsed_jd'], master, snapshot, run.get('skipped_questions', []), progress=progress)
    return {'knowledge':snapshot,'analysis':analysis,'stage':'questions','answers':{},'draft':None,'decisions':{},'proposal_path':None,'final_path':None}


def review_state(run):
    master=master_snapshot()[0]
    draft=engine.apply_review(master,run['draft'],run.get('decisions',{}),False)
    evidence=engine.evidence_catalog(master,run['knowledge'])
    findings=drafting.local_issues(draft,master,evidence,run['analysis'])
    pending=[]
    for key,field in draft['fields'].items():
        if drafting.trusted_field(key,field,evidence): continue
        record=run.get('checks',{}).get(key)
        if not record or record['signature']!=drafting.field_signature(field): pending.append(key)
        else: findings.extend(record['issues'])
    findings.extend(run.get('suggestions',[]))
    return draft,evidence,findings,pending


def publish_review(run, **updates):
    """Publish a complete candidate before waiting for the evidence service."""
    run.update(updates)
    run['stage']='review'
    run['task']={'state':'running','operation':'check','message':'Draft ready · checking evidence and layout'}
    with LOCK:
        current=read_run(run['run_id'])
        current.update({key:value for key,value in run.items() if key!='revision'})
        save_run(current)


def draft_worker(run, progress):
    master=master_snapshot()[0]
    snapshot=knowledge_snapshot(master)
    previous=engine.apply_review(master,run['draft'],run.get('decisions',{}),False) if run.get('draft') else None
    key=drafting.generation_key(run['parsed_jd'],master,snapshot,run['analysis'],run.get('direction',''),previous)
    directory=RUNS/run['run_id']/'proposals'/key
    draft=None
    # Recover an already-written legacy candidate instead of spending another generation call.
    if previous is None and not run.get('direction') and not (directory/'draft.json').exists():
        legacy=sorted((RUNS/run['run_id']/'proposals').glob('*/attempts.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        for path in legacy:
            records=json.loads(path.read_text())
            candidate=next((r['draft'] for r in reversed(records) if r.get('draft')),None)
            if candidate:
                try: engine.validate_draft(candidate,master,engine.evidence_catalog(master,snapshot),run['analysis'],grounded=False)
                except TailorError: continue
                draft=candidate
                progress('Recovered your saved draft · no new writing request needed')
                break
    if draft is None:
        draft=engine.generate(run['parsed_jd'],master,snapshot,run['analysis'],directory,
                              run.get('direction',''),previous,progress)
    drafting.save_json(directory/'draft.json',draft)
    old={c['id']:c for c in engine.changes_for(master,run['draft'])} if run.get('draft') else {}
    decisions={c['id']:run['decisions'][c['id']] for c in engine.changes_for(master,draft)
               if c['id'] in run.get('decisions',{}) and c==old.get(c['id'])}
    publish_review(run,draft=draft,knowledge=snapshot,decisions=decisions,checks={},suggestions=[],
                   proposal_path=None,final_path=None,layout_issues=[],warnings=[],layout_state='pending')
    return check_worker(run,progress)


def check_worker(run, progress):
    master=master_snapshot()[0]
    snapshot=knowledge_snapshot(master)
    if snapshot['revision']!=run['knowledge']['revision']:
        run.update(knowledge=snapshot,checks={},suggestions=[])
    draft,evidence,_,pending=review_state(run)
    engine.validate_draft(draft,master,evidence,run['analysis'],grounded=False)
    directory=RUNS/run['run_id']/'review-checks'
    progress('Checking physical PDF limits locally')
    pdf_dir=directory/drafting.digest(draft)[:24]
    layout,warnings=engine.build_pdf(engine.compose(master,draft),pdf_dir)
    pdf=pdf_dir/'resume.pdf'
    publish_review(run,proposal_path=str(pdf) if pdf.exists() else None,layout_issues=layout,
                   warnings=warnings,layout_state='failed' if layout else 'passed',final_path=None)
    # A single whole-resume check initially; subsequent checks inspect changed passages only.
    issues=drafting.check_draft(draft,run['parsed_jd'],evidence,run['analysis'],pending,directory,progress)
    checks=deepcopy(run.get('checks',{}))
    for key in pending:
        checks[key]={'signature':drafting.field_signature(draft['fields'][key]),
                     'issues':[i for i in issues if i['field']==key]}
    suggestions=[i for i in issues if i['field']=='structure'] if pending else run.get('suggestions',[])
    return {'draft':run['draft'],'knowledge':snapshot,'decisions':run.get('decisions',{}),'checks':checks,
            'suggestions':suggestions,'stage':'review','proposal_path':run.get('proposal_path'),
            'layout_issues':layout,'layout_state':'failed' if layout else 'passed','warnings':warnings,'final_path':None}


def repair_worker(run, progress):
    master=master_snapshot()[0]
    snapshot=knowledge_snapshot(master)
    if snapshot['revision']!=run['knowledge']['revision']:
        run.update(knowledge=snapshot,checks={},suggestions=[])
    current,evidence,findings,_=review_state(run)
    keys=run['repair_fields']
    directory=RUNS/run['run_id']/'repairs'/drafting.digest({'draft':current,'keys':keys,
              'knowledge':snapshot,'direction':run.get('direction',''),'findings':findings,
              'layout':run.get('layout_issues',[])})[:24]
    revised=drafting.repair_fields(current,keys,run['parsed_jd'],evidence,run['analysis'],
                                  findings+run.get('layout_issues',[]),run.get('direction',''),directory,progress)
    # Patch only selected proposals; keep every unrelated proposal and decision byte-for-byte.
    draft=deepcopy(run['draft'])
    decisions=deepcopy(run['decisions'])
    for key in keys:
        draft['fields'][key]=revised['fields'][key]
        decisions.pop(key,None)
    publish_review(run,draft=draft,decisions=decisions,proposal_path=None,final_path=None,layout_state='pending')
    return check_worker(run,progress)


def confirm_passage(run, body, master):
    if knowledge_snapshot(master)['revision']!=run['knowledge']['revision']:
        raise TailorError('Knowledge changed. Check the draft with the latest knowledge before confirming.')
    draft,_,_,_=review_state(run)
    key=body.get('change_id')
    if key not in draft['fields'] or body.get('confirmed') is not True:
        raise TailorError('Explicitly confirm one complete passage.')
    text=engine._text(body.get('text'),'Confirmed passage',2000)
    if text!=draft['fields'][key]['text']:
        raise TailorError('The passage changed. Save your edit, then confirm the displayed text.')
    scope=':'.join(key.split(':')[:2]) if key.startswith(('work:','project:')) else 'general'
    changes={c['id']:c for c in engine.changes_for(master,run['draft'])}
    if key not in changes: raise TailorError('Only proposed changes need confirmation.')
    kb_id='kb-'+drafting.digest({'run':run['run_id'],'field':key,'text':text})[:20]
    save_entries([{'id':kb_id,'scope':scope,'kind':'fact','text':text,'confirmed_passage':True,
                   'question':'Explicitly confirmed the complete resume passage, including its attribution and outcomes.',
                   'run_id':run['run_id']}],master,run['knowledge']['revision'])
    run['knowledge']=knowledge_snapshot(master)
    decision=deepcopy(run['decisions'].get(key,{'action':'accept'}))
    decision['source_ids']=[kb_id]
    run['decisions'][key]=decision
    run['final_path']=None
    return run


def finish_worker(run, progress):
    master=master_snapshot()[0]
    if knowledge_snapshot(master)['revision']!=run['knowledge']['revision']:
        raise TailorError('Your saved knowledge changed. Check the draft with the latest facts before finishing.')
    draft=engine.apply_review(master,run['draft'],run['decisions'])
    _,evidence,findings,pending=review_state(run)
    if pending: raise TailorError('Check edited passages before exporting.')
    if any(i['kind']=='factual' for i in findings): raise TailorError('Resolve the highlighted factual concerns before exporting.')
    engine.validate_draft(draft,master,evidence,run['analysis'])
    progress('Building your approved PDF · checking all physical layout limits')
    directory=RUNS/run['run_id']/'final'/uuid.uuid4().hex[:12]
    issues,warnings=engine.build_pdf(engine.compose(master,draft),directory)
    if issues:
        return {'stage':'review','layout_issues':issues,'layout_state':'failed','final_path':None,'warnings':warnings}
    if knowledge_snapshot(master)['revision']!=run['knowledge']['revision']:
        raise TailorError('Knowledge changed while the final PDF was being checked. Check the draft again.')
    target=ROOT/'content/tailored'/(run['run_id']+'.yaml')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(yaml.safe_dump(engine.compose(master,draft),sort_keys=False,allow_unicode=True))
    return {'stage':'final','final_path':str(directory/'resume.pdf'),'warnings':warnings,'layout_issues':[],'layout_state':'passed'}


def get(handler, request_path):
    if request_path == '/api/knowledge':
        try:
            data, digest = read_knowledge()
            handler._json(200, {'document':data,'revision':digest,'scopes':scopes(master_snapshot()[0]),
                                'storage':storage_notice()})
        except TailorError as error: handler._json(400, {'error':str(error)})
        return True
    if request_path == '/api/knowledge/export':
        try:
            data, _ = read_knowledge()
            handler._send(200, (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode(), 'application/json; charset=utf-8')
        except TailorError as error: handler._json(400, {'error':str(error)})
        return True
    if request_path.startswith('/api/guided/run/'):
        try:
            with LOCK:
                run = read_run(request_path.rsplit('/',1)[1])
                if run.get('task', {}).get('state') == 'running' and run['run_id'] not in JOBS:
                    run['task'] = {**run['task'], 'state':'error','message':'The server restarted during generation. Saved knowledge and decisions are intact; retry the task.'}
                    run['error'] = run['task']['message']
                    save_run(run)
                handler._json(200, public(run))
        except (TailorError, ValueError) as error: handler._json(404, {'error':str(error)})
        return True
    if request_path.startswith('/api/guided/pdf/'):
        try:
            pieces = request_path.split('/')
            if len(pieces) != 6 or pieces[-1] not in {'proposal','final'}: raise TailorError('Invalid PDF request.')
            with LOCK: run = read_run(pieces[-2])
            path = run.get(pieces[-1] + '_path')
            if not path or not Path(path).is_file(): raise TailorError('This PDF is not ready.')
            handler._send(200, Path(path).read_bytes(), 'application/pdf')
        except TailorError as error: handler._json(404, {'error':str(error)})
        return True
    return False


POST_PATHS = {'/api/knowledge/save','/api/guided/start','/api/guided/analyze','/api/guided/answers',
              '/api/guided/draft','/api/guided/decision','/api/guided/finish',
              '/api/guided/check','/api/guided/repair','/api/guided/confirm'}


def post(handler, request_path, body):
    if request_path not in POST_PATHS: return False
    try:
        with LOCK:
            master, master_hash = master_snapshot()
            if request_path == '/api/knowledge/save':
                entry = body.get('entry')
                if not isinstance(entry, dict): raise TailorError('Supply one knowledge entry.')
                # Clients cannot impersonate a generated source or set audit timestamps.
                entry = {k:v for k,v in entry.items() if k in {'id','scope','kind','text','question','archived'}}
                if not isinstance(body.get('revision'), str): raise TailorError('Reload knowledge before saving.')
                data, digest = save_entries([entry], master, body['revision'])
                handler._json(200, {'document':data,'revision':digest,'scopes':scopes(master)})
                return True
            if request_path == '/api/guided/start':
                jd = normalize_parsed_jd(body.get('parsed_jd'))
                run_id = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
                run = {'version':2,'run_id':run_id,'master_hash':master_hash,'rules_hash':engine.rules_digest(),
                       'parsed_jd':jd,'stage':'questions','knowledge':knowledge_snapshot(master),
                       'answers':{},'decisions':{},'warnings':[]}
                launch(run, 'analysis', analysis_worker)
            else:
                run = read_run(body.get('run_id'))
                ensure_editable(run, body)
                if request_path == '/api/guided/analyze':
                    launch(run, 'analysis', analysis_worker)
                elif request_path == '/api/guided/answers':
                    if run.get('draft'): raise TailorError('Use Knowledge to add facts, then Refine draft for this review.')
                    answers = body.get('answers')
                    if not isinstance(answers, dict): raise TailorError('Answers must be an object.')
                    questions = {q['id']:q for q in run['analysis']['questions']}
                    if set(answers) - set(questions): raise TailorError('Unknown question ID.')
                    records, skipped = [], []
                    for identifier, answer in answers.items():
                        if not isinstance(answer, dict): raise TailorError('Invalid answer.')
                        q = questions[identifier]
                        text = engine._text(answer.get('text',''), 'Answer', 8000, empty=True)
                        if not text:
                            skipped.append(q['question'])
                            continue
                        kind = answer.get('kind')
                        if kind not in {'fact','limitation','uncertain','planned'}: raise TailorError('Choose an answer type.')
                        kb_id = 'kb-' + hashlib.sha256((run['run_id']+identifier+q['question']).encode()).hexdigest()[:20]
                        records.append({'id':kb_id,'scope':q['scope'],'kind':kind,'text':text,'question':q['question'],
                                        'run_id':run['run_id'],'archived':False})
                    if records: save_entries(records, master)
                    run['answers'] = answers
                    run['skipped_questions'] = skipped
                    run['knowledge'] = knowledge_snapshot(master)
                    save_run(run)
                elif request_path == '/api/guided/draft':
                    if not run.get('analysis'): raise TailorError('Analyze the job before drafting.')
                    run['direction'] = engine._text(body.get('direction',''), 'Draft direction', 4000, empty=True)
                    launch(run, 'draft', draft_worker)
                elif request_path == '/api/guided/check':
                    if not run.get('draft'): raise TailorError('Generate a draft first.')
                    launch(run,'check',check_worker)
                elif request_path == '/api/guided/repair':
                    if not run.get('draft'): raise TailorError('Generate a draft first.')
                    draft,_,_,_=review_state(run)
                    run['repair_fields']=engine._ids(body.get('fields'),draft['fields'],'Passages to correct',1)
                    run['direction']=engine._text(body.get('direction',''),'Correction direction',4000,empty=True)
                    launch(run,'repair',repair_worker)
                elif request_path == '/api/guided/confirm':
                    confirm_passage(run,body,master)
                    run.pop('error',None)
                    run['task']={'state':'done','operation':'decision','message':'Passage confirmed and saved to knowledge'}
                    save_run(run)
                elif request_path == '/api/guided/decision':
                    if not run.get('draft'): raise TailorError('Generate a draft first.')
                    identifier = body.get('change_id')
                    changes = {x['id']:x for x in engine.changes_for(master, run['draft'])}
                    if identifier not in changes: raise TailorError('Unknown proposal.')
                    action = body.get('action')
                    if action not in {'accept','keep','edit'} or (identifier == 'structure' and action != 'accept'):
                        raise TailorError('Invalid review action.')
                    decision = {'action':action}
                    if action == 'edit': decision['text'] = engine._text(body.get('text'), 'Edited text', 2000)
                    run['decisions'][identifier] = decision
                    if action in {'keep','edit'}:
                        run['layout_state']='pending'
                        run['proposal_path']=None
                    run['stage'] = 'review'
                    run['final_path'] = None
                    run.pop('error', None)
                    run['task'] = {'state':'done','operation':'decision','message':'Decision saved'}
                    save_run(run)
                elif request_path == '/api/guided/finish':
                    engine.apply_review(master, run['draft'], run['decisions'])
                    launch(run, 'finish', finish_worker)
            handler._json(200, public(run))
    except (TailorError, ValueError, KeyError, TypeError) as error:
        handler._json(400, {'error':str(error)})
    return True
