"""Run with .venv/bin/python -m unittest discover -s tests -v."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

import guided_service as service
import guided_tailoring as engine
import knowledge
import staged_generation as staged
from tailor import ROOT, AIServiceError, TailorError


MASTER = yaml.safe_load((ROOT / 'content/master.yaml').read_text())
JD = {'company':'Example', 'role':'ML Engineer', 'jd_text':'Build and evaluate machine learning systems with Python.'}
SNAPSHOT = {'revision':knowledge.revision({'version':1,'entries':[]}), 'entries':[]}
ANALYSIS = {
    'strategy':'Emphasize demonstrated model evaluation.',
    'requirements':[{'id':'r1','quote':JD['jd_text'],'priority':'required','category':'responsibility',
                     'status':'transferable','source_ids':['proj1-b1'],'reason':'Relevant project evidence.'}],
    'questions':[{'id':'q1','scope':'project:proj1','requirement_ids':['r1'],'question':'How did you evaluate the model?',
                  'why':'Clarify evaluation methodology.','existing_source_ids':[]}],
    'recommendations':[],
}


def fixture():
    fields = {}
    def add(key, text, source):
        fields[key] = {'text':text.strip(),'source_ids':[source],'requirement_ids':[],'reason':'Retained supported evidence.'}
    add('summary', MASTER['summary'], 'master:summary')
    structure = {'section_order':['experience','education','projects','skills'],
                 'project_ids':[p['id'] for p in MASTER['projects'][:5]], 'bullet_ids':{},
                 'skill_categories':list(MASTER['skills'])}
    entries = engine.entry_map(MASTER)
    active = [f'work:{i}' for i in range(len(MASTER['experience']))]+['project:'+p for p in structure['project_ids']]
    for scope in active:
        entry = entries[scope]
        add(scope+':tech', entry.get('tech',''), scope+':tech')
        if scope.startswith('project:'): add(scope+':title',entry['name'],scope+':title')
        structure['bullet_ids'][scope] = [b['id'] for b in entry['bullets'][:3]]
        for bullet in entry['bullets'][:3]: add(scope+':'+bullet['id'],bullet['text'],bullet['id'])
    for name, items in MASTER['skills'].items(): add('skills:'+name,'\n'.join(items),'skills:'+name)
    return {'structure':structure,'fields':fields}


class KnowledgeTests(unittest.TestCase):
    def test_exact_persistence_manual_edit_history_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            entry = {'id':'kb-eval','scope':'project:proj1','kind':'fact',
                     'question':'How evaluated?', 'text':'Held-out evaluation.\nI did not run production A/B tests.'}
            saved, rev = knowledge.save_entries([entry], MASTER, directory=temp)
            self.assertEqual(knowledge.read_knowledge(temp)[0],saved)
            self.assertEqual(saved['entries'][0]['text'],entry['text'])
            saved['entries'][0]['text']='Corrected manually.'
            path=Path(temp)/'knowledge.json'
            path.write_text(json.dumps(saved))
            self.assertEqual(knowledge.knowledge_snapshot(MASTER,temp)['entries'][0]['text'],'Corrected manually.')
            with self.assertRaises(TailorError): knowledge.save_entries([entry],MASTER,rev,temp)
            _, rev=knowledge.read_knowledge(temp)
            knowledge.save_entries([{**entry,'archived':True}],MASTER,rev,temp)
            self.assertEqual(knowledge.knowledge_snapshot(MASTER,temp)['entries'],[])
            self.assertEqual(len(list((Path(temp)/'history').glob('*.json'))),2)

    def test_unknown_scope_and_broken_manual_json_do_not_disappear(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'knowledge.json'
            path.write_text('{"version":1,"entries":[{"id":"kb-x","scope":"project:missing","kind":"fact","text":"x"}]}')
            with self.assertRaises(TailorError): knowledge.knowledge_snapshot(MASTER,temp)
            path.write_text('invalid json')
            with self.assertRaises(TailorError): knowledge.read_knowledge(temp)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.draft=fixture()
        self.evidence=engine.evidence_catalog(MASTER,SNAPSHOT)

    def test_full_knowledge_is_read_before_questions(self):
        snapshot=deepcopy(SNAPSHOT)
        snapshot['entries']=[{'id':'kb-eval','scope':'project:proj1','kind':'limitation','text':'No production A/B testing.'}]
        with patch.object(engine,'_json_call',return_value=deepcopy(ANALYSIS)) as call:
            engine.analyze(JD,MASTER,snapshot)
            payload=call.call_args.args[1]
            self.assertEqual(payload['saved_knowledge'],snapshot['entries'])
            self.assertEqual(payload['evidence']['kb-eval']['kind'],'limitation')

    def test_schema_scopes_numbers_and_future_work(self):
        engine.validate_draft(self.draft,MASTER,self.evidence,ANALYSIS)
        key='project:proj1:'+self.draft['structure']['bullet_ids']['project:proj1'][0]
        for sources,text in [(['proj2-b1'],'Implemented the model.'),
                             (['proj1-b1'],'Improved accuracy by 999999%.'),
                             (['kb-future'],'Implemented the model.')]:
            draft=deepcopy(self.draft)
            draft['fields'][key].update(source_ids=sources,text=text)
            evidence={**self.evidence,'kb-future':{'kind':'planned','scope':'project:proj1','text':text}}
            with self.assertRaises(TailorError): engine.validate_draft(draft,MASTER,evidence,ANALYSIS)
        self.draft['structure']['project_ids'].pop()
        with self.assertRaises(TailorError): engine.validate_draft(self.draft,MASTER,self.evidence,ANALYSIS)

    def test_requirement_quotes_must_exist(self):
        analysis=deepcopy(ANALYSIS)
        analysis['requirements'][0]['quote']='Requires finance experience not actually in the posting.'
        with self.assertRaises(TailorError): engine.validate_analysis(analysis,JD,MASTER,self.evidence)

    def test_passage_reference_supplies_verbatim_quote(self):
        jd={**JD,'jd_text':'Requirements:\n  Python, C++ and distributed systems — experience preferred.\nTesting & reliability.'}
        analysis=deepcopy(ANALYSIS)
        requirement=analysis['requirements'][0]
        requirement.update(passage_id='jd2',quote='Invented or paraphrased wording.')
        result=engine.validate_analysis(analysis,jd,MASTER,self.evidence)
        self.assertEqual(result['requirements'][0]['quote'],'Python, C++ and distributed systems — experience preferred.')
        self.assertIn(result['requirements'][0]['quote'],jd['jd_text'])
        for invalid in ['jd999',None,['jd2']]:
            requirement['passage_id']=invalid
            with self.assertRaisesRegex(TailorError,'select a passage_id'):
                engine.validate_analysis(analysis,jd,MASTER,self.evidence)

    def test_passage_split_preserves_long_and_unicode_source(self):
        for text in ['  Python\u00a0and C++ — testing.\r\n\n ML & data. ', 'x'*4001, 'word '*1200]:
            passages=engine.jd_passages({'jd_text':text})
            self.assertTrue(passages)
            self.assertTrue(all(value in text and len(value)<=1500 for value in passages.values()))
            self.assertEqual(''.join(''.join(passages.values()).split()),''.join(text.split()))

    def test_analysis_repair_has_original_response_and_exact_passages(self):
        invalid=deepcopy(ANALYSIS)
        invalid['requirements'][0].update(id='r14',quote='A paraphrase not present in the posting.')
        invalid['questions'][0]['requirement_ids']=['r14']
        corrected=deepcopy(invalid)
        corrected['requirements'][0]['passage_id']='jd1'
        with patch.object(engine,'_json_call',side_effect=[invalid,corrected]) as call:
            result=engine.analyze(JD,MASTER,SNAPSHOT)
        repair=call.call_args.args[1]
        self.assertIn('r14',repair['validation_feedback'])
        self.assertEqual(repair['previous_response']['requirements'][0]['id'],'r14')
        self.assertEqual(repair['jd_passages'],{'jd1':JD['jd_text']})
        self.assertEqual(result['requirements'][0]['quote'],JD['jd_text'])
        self.assertEqual(result['questions'][0]['requirement_ids'],['r14'])

    def test_analysis_transport_failure_does_not_trigger_content_repair(self):
        with patch.object(engine,'_json_call',side_effect=AIServiceError('Disconnected')) as call:
            with self.assertRaises(AIServiceError): engine.analyze(JD,MASTER,SNAPSHOT)
            self.assertEqual(call.call_count,1)

    def test_review_gate_omission_keep_and_user_edit(self):
        key='project:proj1:'+self.draft['structure']['bullet_ids']['project:proj1'][0]
        original=self.draft['fields'][key]['text']
        self.draft['fields'][key]['text']='Proposed replacement.'
        with self.assertRaises(TailorError): engine.apply_review(MASTER,self.draft,{})
        decisions={c['id']:{'action':'accept'} for c in engine.changes_for(MASTER,self.draft)}
        decisions[key]={'action':'keep'}
        reviewed=engine.apply_review(MASTER,self.draft,decisions)
        self.assertEqual(reviewed['fields'][key]['text'],original)
        omissions=[c for c in engine.changes_for(MASTER,self.draft) if not c['suggested']]
        self.assertTrue(omissions)
        omitted=omissions[0]['id']
        decisions[omitted]={'action':'keep'}
        reviewed=engine.apply_review(MASTER,self.draft,decisions)
        self.assertEqual(reviewed['fields'][omitted]['text'],omissions[0]['original'])
        decisions[key]={'action':'edit','text':'My supported edit.'}
        self.assertEqual(engine.apply_review(MASTER,self.draft,decisions)['fields'][key]['text'],'My supported edit.')

    def test_new_bullet_ids_are_unique_across_entries(self):
        for scope in ['work:0','project:proj1']:
            self.draft['structure']['bullet_ids'][scope].append('new1')
            self.draft['fields'][scope+':new1']=deepcopy(self.draft['fields'][scope+':tech'])
        composed=engine.compose(MASTER,self.draft)
        ids=[b['id'] for e in composed['experience']+composed['projects'] for b in e['bullets']]
        self.assertEqual(len(ids),len(set(ids)))



class Handler:
    def _json(self,status,body): self.status,self.body=status,body


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.patches=[patch.object(service,'RUNS',self.directory/'runs'),
                      patch.object(knowledge,'KNOWLEDGE_DIR',self.directory/'knowledge')]
        for p in self.patches: p.start();self.addCleanup(p.stop)
        self.run={'run_id':'20261020-000000-abcdef','version':2,'master_hash':service.master_snapshot()[1],
                  'rules_hash':engine.rules_digest(),'parsed_jd':JD,'knowledge':SNAPSHOT,'analysis':ANALYSIS,
                  'answers':{},'decisions':{},'stage':'questions','task':{'state':'done','operation':'analysis'}}
        service.save_run(self.run)

    def post(self,path,**body):
        handler=Handler()
        run=service.read_run(self.run['run_id'])
        service.post(handler,path,{'run_id':run['run_id'],'revision':run['revision'],**body})
        self.assertEqual(handler.status,200,handler.body)
        return handler.body

    def test_answers_persist_without_model_and_upsert_on_resave(self):
        answer={'q1':{'kind':'limitation','text':'I did not perform production testing.'}}
        with patch.object(engine,'_json_call') as call:
            self.post('/api/guided/answers',answers=answer)
            first_revision=knowledge.read_knowledge()[1]
            self.post('/api/guided/answers',answers=answer)
            self.assertEqual(knowledge.read_knowledge()[1],first_revision,'Unchanged answers preserve generation checkpoints')
            call.assert_not_called()
        document,_=knowledge.read_knowledge()
        self.assertEqual(len(document['entries']),1)
        self.assertEqual(document['entries'][0]['text'],answer['q1']['text'])
        self.assertEqual(service.read_run(self.run['run_id'])['answers'],answer)
        with patch.object(engine,'_json_call',return_value=deepcopy(ANALYSIS)) as call:
            service.analysis_worker(service.read_run(self.run['run_id']),lambda _:None)
            self.assertEqual(call.call_args.args[1]['saved_knowledge'][0]['text'],answer['q1']['text'])

    def test_restart_retains_retry_operation_and_stale_edit_rejected(self):
        self.run['task']={'state':'running','operation':'draft'}
        service.save_run(self.run)
        handler=Handler()
        service.get(handler,'/api/guided/run/'+self.run['run_id'])
        self.assertEqual(handler.body['task']['operation'],'draft')
        self.assertEqual(handler.body['task']['state'],'error')
        with self.assertRaises(TailorError): service.ensure_editable(handler.body,{'revision':0})

    def test_changed_knowledge_prevents_stale_finalization(self):
        knowledge.save_entries([{'scope':'general','kind':'limitation','text':'A correction.'}],MASTER)
        with self.assertRaisesRegex(TailorError,'knowledge changed'):
            service.finish_worker(self.run,lambda _:None)



if __name__=='__main__': unittest.main()
