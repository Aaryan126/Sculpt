"""End-to-end review transitions with a deterministic AI boundary and isolated storage."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import guided_service as service
import guided_tailoring as engine
import staged_generation as staged
import knowledge
from tailor import AIServiceError, TailorError, ROOT
from test_guided import MASTER, JD, ANALYSIS, SNAPSHOT, fixture, Handler


class DraftReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'content').mkdir()
        shutil.copyfile(ROOT/'content/master.yaml',self.root/'content/master.yaml')
        for target,name,value in [(service,'RUNS',self.root/'runs'),(service,'ROOT',self.root),
                                  (knowledge,'KNOWLEDGE_DIR',self.root/'knowledge')]:
            handle=patch.object(target,name,value);handle.start();self.addCleanup(handle.stop)
        self.run={'run_id':'20261021-000000-abcdef','revision':0,'master_hash':service.master_snapshot()[1],
                  'rules_hash':engine.rules_digest(),'parsed_jd':JD,'analysis':deepcopy(ANALYSIS),
                  'knowledge':deepcopy(SNAPSHOT),'answers':{},'decisions':{},'stage':'questions',
                  'task':{'state':'done','operation':'analysis'}}
        service.save_run(self.run)
        self.draft=fixture()
        self.key='project:proj1:'+self.draft['structure']['bullet_ids']['project:proj1'][0]
        self.draft['fields'][self.key]['text']+=' Improved the workflow.'
        self.finding={'field':self.key,'kind':'factual','reason':'The claimed improvement is not supported.'}

    def build(self,content,directory):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        (directory/'resume.pdf').write_bytes(b'%PDF-test')
        return [],[]

    def save(self,**updates):
        self.run.update(updates);service.save_run(self.run)

    def review(self,issues=None):
        self.save(draft=deepcopy(self.draft),stage='review')
        with patch.object(engine,'build_pdf',side_effect=self.build), \
             patch.object(engine,'_json_call',return_value={'issues':issues or []}):
            self.run.update(service.check_worker(self.run,lambda _:None))
        self.run['task']={'state':'done','operation':'check'}
        service.save_run(self.run)

    def approve(self):
        self.run['decisions']={c['id']:{'action':'accept'} for c in engine.changes_for(MASTER,self.run['draft'])}

    def post(self,path,expected=200,**body):
        current=service.read_run(self.run['run_id']);handler=Handler()
        service.post(handler,path,{'run_id':current['run_id'],'revision':current['revision'],**body})
        self.assertEqual(handler.status,expected,handler.body)
        self.run=service.read_run(self.run['run_id'])
        return handler.body

    def test_two_calls_publish_before_check_and_factual_flags_are_not_failures(self):
        calls=[]
        def model(prompt,payload,*args,**kwargs):
            calls.append(prompt)
            if prompt==staged.DRAFT_PROMPT:return deepcopy(self.draft)
            self.assertEqual(prompt,staged.CHECK_PROMPT)
            visible=service.read_run(self.run['run_id'])
            self.assertEqual(visible['stage'],'review')
            self.assertEqual(visible['draft'],self.draft)
            self.assertEqual(visible['task']['operation'],'check')
            return {'issues':[self.finding]}
        with patch.object(engine,'_json_call',side_effect=model),patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.draft_worker(self.run,lambda _:None)
        self.run.update(result)
        self.assertEqual(len(calls),2)
        self.assertEqual(result['stage'],'review')
        self.assertIn(self.finding,service.review_state(self.run)[2])
        self.assertEqual(service.review_state(self.run)[3],[])

    def test_stream_failure_keeps_draft_and_retry_only_checks(self):
        with patch.object(engine,'generate',return_value=self.draft) as writer, \
             patch.object(engine,'_json_call',side_effect=AIServiceError('Disconnected')), \
             patch.object(engine,'build_pdf',side_effect=self.build):
            with self.assertRaises(AIServiceError):service.draft_worker(self.run,lambda _:None)
        self.run=service.read_run(self.run['run_id'])
        self.assertEqual(self.run['draft'],self.draft)
        self.assertEqual(self.run['task']['operation'],'check')
        with patch.object(engine,'generate') as writer,patch.object(engine,'_json_call',return_value={'issues':[]}) as checker, \
             patch.object(engine,'build_pdf',side_effect=self.build):
            service.check_worker(self.run,lambda _:None)
            writer.assert_not_called();self.assertEqual(checker.call_count,1)

    def test_accept_cannot_bypass_fact_flag_and_keep_original_resolves_it(self):
        self.review([self.finding]);self.approve()
        with self.assertRaisesRegex(TailorError,'factual'):service.finish_worker(self.run,lambda _:None)
        self.run['decisions'][self.key]={'action':'keep'}
        self.assertFalse(service.review_state(self.run)[2])
        with patch.object(engine,'_json_call') as model,patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.finish_worker(self.run,lambda _:None)
            model.assert_not_called();self.assertEqual(result['stage'],'final')

    def test_suggestions_do_not_block_export(self):
        self.review([{**self.finding,'kind':'suggestion','reason':'Consider reducing duplication.'}]);self.approve()
        with patch.object(engine,'_json_call') as model,patch.object(engine,'build_pdf',side_effect=self.build):
            self.assertEqual(service.finish_worker(self.run,lambda _:None)['stage'],'final')
            model.assert_not_called()

    def test_manual_edit_requires_check_of_only_edited_passage(self):
        self.review();self.approve()
        self.run['decisions'][self.key]={'action':'edit','text':'Revised and unsupported claim.'}
        self.assertEqual(service.review_state(self.run)[3],[self.key])
        with self.assertRaisesRegex(TailorError,'Check edited'):service.finish_worker(self.run,lambda _:None)
        with patch.object(engine,'_json_call',return_value={'issues':[self.finding]}) as model, \
             patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.check_worker(self.run,lambda _:None)
        self.assertEqual(model.call_args.args[1]['check_fields'],[self.key])
        self.run.update(result)
        self.assertIn(self.finding,service.review_state(self.run)[2])

    def test_confirmation_is_explicit_exact_scoped_and_persisted(self):
        self.review([self.finding]);self.approve();service.save_run(self.run)
        text=self.draft['fields'][self.key]['text']
        self.post('/api/guided/confirm',expected=400,change_id=self.key,text=text,confirmed=False)
        self.post('/api/guided/confirm',expected=400,change_id=self.key,text='Yes',confirmed=True)
        self.post('/api/guided/confirm',change_id=self.key,text=text,confirmed=True)
        saved=knowledge.read_knowledge()[0]['entries'][0]
        self.assertEqual(saved['text'],text);self.assertEqual(saved['scope'],'project:proj1')
        self.assertTrue(saved['confirmed_passage'])
        self.assertFalse(service.review_state(self.run)[2]);self.assertFalse(service.review_state(self.run)[3])
        effective=engine.apply_review(MASTER,self.run['draft'],self.run['decisions'])
        self.assertEqual(effective['fields'][self.key]['source_ids'],[saved['id']])

    def test_confirmation_of_edit_uses_edited_text_and_reedit_invalidates_it(self):
        self.review([self.finding])
        self.post('/api/guided/decision',change_id=self.key,action='edit',text='I designed evaluation prompts.')
        self.post('/api/guided/confirm',change_id=self.key,text='I designed evaluation prompts.',confirmed=True)
        self.assertFalse(service.review_state(self.run)[3])
        self.post('/api/guided/decision',change_id=self.key,action='edit',text='A different new claim.')
        self.assertEqual(service.review_state(self.run)[3],[self.key])

    def test_targeted_repair_preserves_unrelated_proposals_and_decisions(self):
        self.review([self.finding]);self.approve()
        self.run['repair_fields']=[self.key]
        original=deepcopy(self.run)
        replacement=deepcopy(self.draft['fields'][self.key]);replacement['text']='Reframed supported work.'
        def model(prompt,payload,*args,**kwargs):
            if prompt==staged.REPAIR_PROMPT:
                self.assertEqual(payload['requested_fields'],[self.key]);return {'fields':{self.key:replacement}}
            self.assertEqual(payload['check_fields'],[self.key]);return {'issues':[]}
        with patch.object(engine,'_json_call',side_effect=model) as call,patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.repair_worker(self.run,lambda _:None)
        self.assertEqual(call.call_count,2)
        for key,field in original['draft']['fields'].items():
            if key!=self.key:self.assertEqual(result['draft']['fields'][key],field)
        self.assertNotIn(self.key,result['decisions'])
        self.assertEqual(result['decisions'],{k:v for k,v in original['decisions'].items() if k!=self.key})

    def test_repair_cannot_overwrite_unselected_fields(self):
        evidence=engine.evidence_catalog(MASTER,SNAPSHOT)
        with patch.object(engine,'_json_call',return_value={'fields':self.draft['fields']}) as model:
            with self.assertRaises(TailorError):
                staged.repair_fields(self.draft,[self.key],JD,evidence,ANALYSIS,[],'',None,lambda _:None)
            self.assertEqual(model.call_count,2,'Only one schema correction; no rewrite loop')

    def test_layout_failure_returns_review_without_regenerating(self):
        self.review();self.approve()
        with patch.object(engine,'_json_call') as model, \
             patch.object(engine,'build_pdf',return_value=(['summary: 5 lines, maximum 4'],[])):
            result=service.finish_worker(self.run,lambda _:None)
        self.assertEqual(result['stage'],'review');self.assertEqual(result['layout_state'],'failed')
        self.assertIsNone(result['final_path']);model.assert_not_called()

    def test_knowledge_changes_block_export_and_recheck_uses_latest(self):
        self.review();self.approve()
        knowledge.save_entries([{'scope':'general','kind':'limitation','text':'No production deployment.'}],MASTER)
        with self.assertRaisesRegex(TailorError,'knowledge changed'):service.finish_worker(self.run,lambda _:None)
        with patch.object(engine,'_json_call',return_value={'issues':[]}) as model,patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.check_worker(self.run,lambda _:None)
        self.assertEqual(result['knowledge']['revision'],knowledge.knowledge_snapshot(MASTER)['revision'])
        self.assertTrue(any(v['text']=='No production deployment.' for v in model.call_args.args[1]['evidence'].values()))

    def test_knowledge_change_during_final_build_blocks_export(self):
        self.review();self.approve()
        def build(*args):
            knowledge.save_entries([{'scope':'general','kind':'limitation','text':'New correction.'}],MASTER)
            return [],[]
        with patch.object(engine,'build_pdf',side_effect=build):
            with self.assertRaisesRegex(TailorError,'Knowledge changed while'):service.finish_worker(self.run,lambda _:None)
        self.assertFalse((self.root/'content/tailored').exists())

    def test_legacy_failed_candidate_is_recovered_without_writer(self):
        directory=service.RUNS/self.run['run_id']/'proposals'/'old';directory.mkdir(parents=True)
        (directory/'attempts.json').write_text(json.dumps([{'draft':self.draft,'state':'failed'}]))
        with patch.object(engine,'generate') as writer,patch.object(engine,'_json_call',return_value={'issues':[self.finding]}) as check, \
             patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.draft_worker(self.run,lambda _:None)
        writer.assert_not_called();self.assertEqual(check.call_count,1)
        self.assertEqual(result['draft'],self.draft)

    def test_cached_new_draft_takes_precedence_over_failed_legacy_candidate(self):
        old=service.RUNS/self.run['run_id']/'proposals'/'old';old.mkdir(parents=True)
        (old/'attempts.json').write_text(json.dumps([{'draft':fixture(),'state':'failed'}]))
        key=staged.generation_key(JD,MASTER,SNAPSHOT,ANALYSIS,'',None)
        staged.save_json(service.RUNS/self.run['run_id']/'proposals'/key/'draft.json',self.draft)
        with patch.object(engine,'_json_call',return_value={'issues':[]}) as model,patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.draft_worker(self.run,lambda _:None)
        self.assertEqual(result['draft'],self.draft)
        self.assertEqual(model.call_count,1)
        self.assertEqual(model.call_args.args[0],staged.CHECK_PROMPT)

    def test_validated_schema_repair_is_cached_under_original_request(self):
        def validate(value):
            if not value.get('ok'):raise TailorError('Invalid schema')
        with patch.object(engine,'_json_call',side_effect=[{}, {'ok':True}]) as model:
            for _ in range(2):staged.checked_call('prompt',{},'test',self.root/'cache',validate,lambda _:None)
        self.assertEqual(model.call_count,2)

    def test_compound_yes_is_preserved_but_not_citable_fact(self):
        snapshot=deepcopy(SNAPSHOT)
        snapshot['entries']=[{'id':'kb-yes','text':'Yes.','kind':'fact','scope':'work:0',
                             'question':'Did you run sessions or write documentation?'}]
        evidence=engine.evidence_catalog(MASTER,snapshot)
        self.assertEqual(evidence['kb-yes']['kind'],'uncertain')
        self.assertEqual(snapshot['entries'][0]['kind'],'fact','Raw saved answer is not silently rewritten')
        field=deepcopy(self.draft['fields'][self.key]);field['source_ids']=['kb-yes']
        with self.assertRaisesRegex(TailorError,'confirmed facts'):
            engine.validate_fields({'work:0:new1':field},{'work:0:new1'},evidence,ANALYSIS)

    def test_omitted_unchanged_fields_expand_and_unsupported_numbers_become_flags(self):
        draft={'structure':self.draft['structure'],'fields':{}}
        evidence=engine.evidence_catalog(MASTER,SNAPSHOT)
        expanded=staged.expand_draft(draft,MASTER,evidence,ANALYSIS)
        self.assertEqual(expanded['fields']['summary']['text'],MASTER['summary'].strip())
        expanded['fields'][self.key]['text']='Improved accuracy by 999999%.'
        engine.validate_draft(expanded,MASTER,evidence,ANALYSIS,grounded=False)
        self.assertTrue(any(i['field']==self.key for i in staged.local_issues(expanded,MASTER,evidence,ANALYSIS)))

    def test_saved_check_is_reused_and_does_not_duplicate_provider_call(self):
        self.review([self.finding])
        with patch.object(engine,'_json_call') as model,patch.object(engine,'build_pdf',side_effect=self.build):
            result=service.check_worker(self.run,lambda _:None)
        model.assert_not_called();self.run.update(result)
        self.assertIn(self.finding,service.review_state(self.run)[2])

    def test_new_skill_needs_explicit_evidence_even_when_model_passes(self):
        key='skills:Agentic AI & LLM'
        self.draft['fields'][key]['text']+='\nPrompt engineering'
        self.draft['fields'][key]['source_ids']=['skills:Agentic AI & LLM','proj1-b3','proj4-b3']
        self.review();self.approve()
        findings=service.review_state(self.run)[2]
        self.assertTrue(any(i['field']==key and 'Prompt engineering' in i['reason'] for i in findings))
        with self.assertRaisesRegex(TailorError,'factual'):service.finish_worker(self.run,lambda _:None)
        self.run['decisions'][key]={'action':'keep'}
        self.assertFalse(any(i['field']==key for i in service.review_state(self.run)[2]))

    def test_generation_cache_invalidates_inputs_and_model(self):
        def key(**kw):
            values={'jd':JD,'master':MASTER,'snapshot':SNAPSHOT,'analysis':ANALYSIS,'feedback':'','previous':None}
            values.update(kw);return staged.generation_key(**values)
        with patch.object(staged,'provider',return_value={'model':'one'}):
            original=key()
            self.assertNotEqual(original,key(snapshot={'entries':[],'revision':'changed'}))
            self.assertNotEqual(original,key(feedback='New direction'))
        with patch.object(staged,'provider',return_value={'model':'two'}):self.assertNotEqual(original,key())


if __name__=='__main__':unittest.main()
