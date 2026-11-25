"""Benchmark fresh drafting/checking without modifying saved runs or knowledge."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import guided_service as service
import guided_tailoring as engine
from staged_generation import save_json
from tailor import ROOT, load_env


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--trials',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.trials<=10:parser.error('--trials must be between 1 and 10')
    original=service.read_run(args.run_id)
    snapshot=deepcopy(original['knowledge'])
    model=load_env()['SOCLAAS_MODEL']
    directory=ROOT/'output'/'benchmarks'/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    directory.mkdir(parents=True)
    service.knowledge_snapshot=lambda master:deepcopy(snapshot)
    real_call=engine._json_call
    real_publish=service.publish_review
    results=[]
    print('Model:',model,'Results:',directory,flush=True)
    for trial in range(1,args.trials+1):
        service.RUNS=directory/f'trial-{trial}'/'runs'
        run=deepcopy(original)
        for key in ('draft','checks','suggestions','error','proposal_path','final_path'):run.pop(key,None)
        run.update(direction='',decisions={},stage='questions',task={'state':'running','operation':'draft'})
        service.save_run(run)
        started=time.monotonic();calls=[];visible=[]
        def call(prompt,payload,operation,**kwargs):
            begin=time.monotonic()
            record={'operation':operation,'payload_bytes':len(json.dumps(payload,ensure_ascii=False).encode())}
            calls.append(record)
            try:return real_call(prompt,payload,operation,**kwargs)
            finally:record['seconds']=round(time.monotonic()-begin,2)
        def publish(state,**updates):
            real_publish(state,**updates)
            if not visible:
                visible.append(round(time.monotonic()-started,2))
                print('DRAFT VISIBLE:',visible[0],'seconds',flush=True)
        engine._json_call=call;service.publish_review=publish
        record={'trial':trial,'model':model,'calls':calls}
        try:
            updates=service.draft_worker(run,lambda msg:print(f'Trial {trial}: {msg}',flush=True))
            run.update(updates)
            _,_,findings,pending=service.review_state(run)
            record.update(layout_state=run['layout_state'],layout_issues=run['layout_issues'],
                          factual=sum(i['kind']=='factual' for i in findings),suggestions=sum(i['kind']=='suggestion' for i in findings),
                          unchecked=len(pending),fields=len(run['draft']['fields']))
            run['task']={'state':'done','operation':'check'}
            service.save_run(run)
        except KeyboardInterrupt:
            record['interrupted']=True
        except Exception as error:record['error']=str(error)
        record.update(draft_seconds=visible[0] if visible else None,total_seconds=round(time.monotonic()-started,2))
        results.append(record)
        save_json(directory/'results.json',{'source_run':args.run_id,'model':model,'knowledge_revision':snapshot['revision'],
                  'master_hash':original['master_hash'],'rules_hash':original['rules_hash'],'trials':results})
        print('RESULT:',json.dumps(record),flush=True)
        if record.get('interrupted'):break
    engine._json_call=real_call;service.publish_review=real_publish


if __name__=='__main__':main()
