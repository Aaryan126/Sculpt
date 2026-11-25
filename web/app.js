const $ = (id) => document.getElementById(id);
const node = (tag, className = '', text = '') => {
  const el = document.createElement(tag); el.className = className; el.textContent = text; return el;
};
const steps = {paste:[1,'Job description'], parsed:[2,'Job details'], questions:[3,'Useful questions'], review:[4,'Review resume'], final:[5,'Finished resume']};
let run = null, step = 'paste', busy = false, pollTimer, epoch = 0;
let knowledge = null, editingKnowledge = null, openChange = null;
const storage = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch {} },
  remove(key) { try { localStorage.removeItem(key); } catch {} },
};
const scrollBehavior = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth';
function status(text, error = false) {
  $('status').textContent = text; $('status').className = `status${error ? ' error' : ''}`; $('status').hidden = !text;
}
function setBusy(value) {
  busy = value; document.body.classList.toggle('is-busy', value);
  document.querySelectorAll('.wizard-screen').forEach(el => { el.inert = value && !(el.id === 'review-panel' && run?.draft); });
  document.querySelector('.editor').setAttribute('aria-busy', String(value));
}
function showStep(name, focus = true) {
  step = name; document.querySelector('.layout').dataset.step = name;
  for (const key of Object.keys(steps)) $(key === 'parsed' ? 'parsed-panel' : `${key}-panel`).hidden = name !== key;
  $('wizard-progress-label').textContent = `Step ${steps[name][0]} of 5 · ${steps[name][1]}`;
  $('wizard-progress-fill').style.width = `${steps[name][0] * 20}%`;
  $('job-context').hidden = ['paste','parsed'].includes(name);
  $('job-context-title').textContent = run ? [run.parsed_jd.role, run.parsed_jd.company].filter(Boolean).join(' at ') : '';
  if (focus) { const h = document.querySelector('.wizard-screen:not([hidden]) h2'); h.tabIndex = -1; h.focus({preventScroll:true}); window.scrollTo({top:0,behavior:scrollBehavior()}); }
}
async function request(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let data; try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Retry after checking the connection.'); }
  if (!response.ok) throw new Error(data.error || 'Request failed.'); return data;
}
async function action(path, payload = {}, message = '') {
  const version = epoch; setBusy(true); status(message); $('task-actions').hidden = true;
  try {
    const result = await request(path, {...(run ? {run_id:run.run_id, revision:run.revision} : {}),...payload});
    if (version !== epoch) return;
    if (result.run_id) receive(result); return result;
  } catch (error) { if (version === epoch) status(error.message,true); }
  finally { if (version === epoch && run?.task?.state !== 'running') setBusy(false); }
}
function receive(result, focus = true) {
  const previousStep = step;
  run = result; storage.set('sculptGuidedRunId', run.run_id);
  fillJob(run.parsed_jd);
  const running = run.task?.state === 'running';
  setBusy(running);
  if (run.draft) renderReview();
  else renderQuestions();
  const target = run.stage === 'final' ? 'final' : run.draft ? 'review' : 'questions';
  showStep(target, focus && previousStep !== target);
  if (run.stage === 'final') {
    $('download-final-pdf').href = run.final_url;
    $('warnings').replaceChildren(...(run.warnings || []).map(w => node('p','',w)));
    if (previousStep !== 'final') showPdf(run.final_url,'Reviewed final PDF');
  }
  $('task-actions').hidden = running || run.task?.state !== 'error';
  $('retry-button').textContent = run.task?.operation === 'draft' ? 'Resume draft' : run.task?.operation === 'check' ? 'Resume evidence check' : 'Retry task';
  status(running ? run.task.message : run.error || '', Boolean(run.error));
  clearTimeout(pollTimer);
  if (running) pollTimer = setTimeout(poll, 1500);
}
async function poll() {
  const version = epoch;
  try { const next = await request(`/api/guided/run/${run.run_id}`); if (version === epoch) receive(next,false); }
  catch (error) { if (version === epoch) { status(`${error.message} Reconnecting…`,true); pollTimer=setTimeout(poll,3500); } }
}
function fillJob(data) { for (const key of ['company','role','jd_text']) $(key).value=data[key] || ''; }
function jobFields() { return Object.fromEntries(['company','role','jd_text'].map(key=>[key,$(key).value.trim()])); }
function showPdf(url, caption) {
  if (!url) return;
  $('pdf-preview').src=url; $('pdf-link').href=url; $('preview-caption').textContent=caption;
  $('preview-panel').hidden=false; document.querySelector('.layout').classList.add('has-preview');
  $('master-preview-button').setAttribute('aria-expanded','true');
  if (matchMedia('(max-width:1200px)').matches) $('preview-panel').scrollIntoView({behavior:scrollBehavior()});
}
function closePdf() { $('preview-panel').hidden=true; $('pdf-preview').src='about:blank'; document.querySelector('.layout').classList.remove('has-preview'); $('master-preview-button').setAttribute('aria-expanded','false'); }
$('master-preview-button').onclick=()=>showPdf('/api/master.pdf','Master resume');
$('close-preview').onclick=closePdf;
$('view-final-pdf').onclick=()=>showPdf(run.final_url,'Reviewed final PDF');
$('proposal-preview').onclick=()=>showPdf(run.proposal_url,'Proposal PDF · includes unreviewed suggestions');
$('back-to-review').onclick=()=>{ closePdf(); showStep('review'); };
$('back-to-jd').onclick=()=>{ closePdf(); showStep('paste'); };
$('back-to-parsed').onclick=()=>{ closePdf(); showStep('parsed'); };
$('jd').addEventListener('input',()=>{ $('jd-count').textContent=`${$('jd').value.length.toLocaleString()} / 30,000`; storage.set('sculptPastedJob',$('jd').value); });
$('parse-form').addEventListener('submit',async event=>{
  event.preventDefault(); if (busy) return;
  const result=await action('/api/parse',{jd:$('jd').value},'Reading the job posting…');
  if (result) { fillJob(result.parsed_jd); showStep('parsed'); status(''); }
});
$('plan-button').onclick=async()=>{
  if (busy) return;
  const fields=jobFields();
  if (run?.analysis && JSON.stringify(fields)===JSON.stringify(run.parsed_jd)) { showStep(run.draft?'review':'questions'); return; }
  await action('/api/guided/start',{parsed_jd:fields},'Checking the role against your resume and saved knowledge…');
};
function renderAnalysis(target, coverage=false) {
  const container=$(target); container.replaceChildren();
  if (!run.analysis) return;
  container.append(node('p','hint',run.analysis.strategy));
  for (const req of run.analysis.requirements) {
    const item=node('details','requirement');
    const covered=Object.entries(run.draft?.fields || {}).filter(([,f])=>f.requirement_ids.includes(req.id)).length;
    item.append(node('summary','',`${req.priority} · ${coverage ? (covered ? `${covered} proposed passages` : 'Not addressed in draft') : req.status} — ${req.label || req.quote}`));
    item.append(node('p','hint',`JD: ${req.quote}`));
    item.append(node('p','hint',req.reason));
    if (req.source_ids.length) item.append(node('p','hint',`Evidence: ${req.source_ids.join(', ')}`));
    container.append(item);
  }
}
function renderQuestions() {
  renderAnalysis('analysis-view');
  $('questions').replaceChildren();
  $('generate-button').hidden=!run.analysis;
  $('analysis-view').parentElement.hidden=!run.analysis;
  if (!run.analysis) {
    $('questions-title').textContent='Checking the role';
    $('question-intro').textContent=run.task?.state==='error' ? 'The role analysis could not finish. Retry below to continue. Your saved knowledge is retained.' : 'Reading the job description and your saved knowledge before asking questions.';
    $('save-answers').hidden=true;
    $('answer-status').textContent='';
    return;
  }
  $('questions-title').textContent='Fill the useful gaps';
  const questions=run.analysis.questions || [];
  $('question-intro').textContent=questions.length ? 'We checked your saved knowledge. Add any missing detail, or leave an answer blank to skip.' : 'Your available evidence is enough to draft. No additional questions are needed.';
  let local={}; try { local=JSON.parse(storage.get(`sculptAnswers:${run.run_id}`)||'{}'); } catch {}
  $('questions').replaceChildren();
  for (const q of questions) {
    const card=node('div','plan-card'); card.dataset.question=q.id;
    const label=node('label','',q.question), input=node('textarea','edit-field');
    input.id=`answer-${q.id}`; label.htmlFor=input.id; input.maxLength=8000;
    const answer=local[q.id] || run.answers?.[q.id] || {};
    input.value=answer.text || '';
    const kind=node('select'); kind.setAttribute('aria-label',`Answer type for ${q.question}`);
    for (const [value,text] of [['fact','Confirmed experience'],['limitation','Not done / limitation'],['uncertain','Uncertain'],['planned','Future plan']]) kind.add(new Option(text,value));
    kind.value=answer.kind || 'fact';
    card.append(label,node('p','hint',q.why));
    if (q.existing_source_ids?.length) card.append(node('p','hint',`Builds on saved evidence: ${q.existing_source_ids.join(', ')}`));
    card.append(input,kind); $('questions').append(card);
    for (const el of [input,kind]) el.addEventListener('input',()=>storage.set(`sculptAnswers:${run.run_id}`,JSON.stringify(answers())));
  }
  $('save-answers').hidden=!questions.length;
  $('generate-button').textContent=questions.length?'Save and generate draft':'Generate tailored draft';
  $('answer-status').textContent=Object.values(run.answers||{}).some(a=>a.text?.trim())?'Answers saved to knowledge.':'Answers are saved to your knowledge when you save or generate. Unsent text is recovered in this browser.';
}
function answers() { return Object.fromEntries([...document.querySelectorAll('[data-question]')].map(card=>[card.dataset.question,{text:card.querySelector('textarea').value,kind:card.querySelector('select').value}])); }
async function saveAnswers() {
  const result=await action('/api/guided/answers',{answers:answers()},'Saving answers to your readable knowledge base…');
  if (result) { storage.remove(`sculptAnswers:${run.run_id}`); $('answer-status').textContent='Saved to knowledge. These answers will be checked for future jobs.'; status(''); }
  return result;
}
$('save-answers').onclick=saveAnswers;
$('generate-button').onclick=async()=>{ if (busy || !run?.analysis) return; if ((run.analysis.questions||[]).length && !(await saveAnswers())) return; await action('/api/guided/draft',{},'Preparing a complete tailored draft…'); };
function changeLabel(change) {
  const key=change.id;
  if (key==='structure') return 'Included content and order';
  if (key==='summary') return 'Summary';
  if (key.startsWith('skills:')) return `Skills · ${key.slice(7)}`;
  const scope=key.split(':').slice(0,2).join(':'), tail=key.split(':').at(-1);
  const position=run.draft.structure.bullet_ids[scope]?.indexOf(tail) ?? -1;
  return `${run.entry_labels[scope] || scope} · ${tail==='title'?'Project title':tail==='tech'?'Technologies':position<0?'Omitted bullet':`Bullet ${position+1}`}`;
}
function structureView() {
  const box=node('div','structure-summary'); const s=run.draft.structure;
  box.append(node('p','',`Section order: ${s.section_order.join(' → ')}`));
  const list=node('ol'); for (const id of s.project_ids) list.append(node('li','',run.entry_labels[`project:${id}`] || id)); box.append(list);
  const omitted=Object.keys(run.entry_labels).filter(key=>key.startsWith('project:')&&!s.project_ids.includes(key.slice(8)));
  if(omitted.length) box.append(node('p','hint',`Projects omitted: ${omitted.map(key=>run.entry_labels[key]).join('; ')}`));
  box.append(node('p','hint',`Skill categories: ${s.skill_categories.join(' · ')}`));
  const omittedSkills=Object.keys(run.evidence).filter(key=>key.startsWith('skills:')&&!s.skill_categories.includes(key.slice(7)));
  if(omittedSkills.length)box.append(node('p','hint',`Skill categories omitted: ${omittedSkills.map(key=>key.slice(7)).join(' · ')}`));
  for (const [scope,ids] of Object.entries(s.bullet_ids)) box.append(node('p','hint',`${run.entry_labels[scope]}: ${ids.length} bullets`));
  return box;
}
function renderCompleteDraft(content) {
  const box=$('complete-draft');box.replaceChildren();
  if(!content)return;
  box.append(node('h3','',content.contact.name),node('p','hint',[content.contact.email,content.contact.phone].filter(Boolean).join(' · ')));
  box.append(node('h3','','Summary'),node('p','comparison-text',content.summary));
  const labels={experience:'Work experience',education:'Education',projects:'Projects',skills:'Skills'};
  for(const section of content.section_order || ['experience','education','projects','skills']) {
    box.append(node('h3','',labels[section]));
    if(section==='skills') {
      for(const [name,items] of Object.entries(content.skills))box.append(node('p','field-caption',name),node('p','comparison-text',items.join(', ')));
      continue;
    }
    for(const entry of content[section] || []) {
      box.append(node('p','field-caption',section==='experience'?`${entry.company} · ${entry.role}`:section==='education'?entry.institution:entry.name));
      if(entry.dates)box.append(node('p','hint',entry.dates));
      if(entry.tech)box.append(node('p','hint',entry.tech));
      if(section==='education') {
        box.append(node('p','comparison-text',[entry.degree,entry.specialisation,entry.honours,entry.gpa,...(entry.modules || [])].filter(Boolean).join('\n')));
      } else {
        const list=node('ul','');for(const bullet of entry.bullets || [])list.append(node('li','',bullet.text));box.append(list);
      }
    }
    if(section==='education')for(const entry of content.certifications || [])box.append(node('p','hint',`${entry.org} · ${entry.title}`));
  }
}
function renderReview() {
  const changes=run.changes || [], decisions=run.decisions || {};
  const pending=changes.filter(c=>!decisions[c.id]);
  $('review-progress').textContent=`${changes.length-pending.length} of ${changes.length} changes reviewed`;
  const findings=run.findings || [], unchecked=run.unchecked_fields || [];
  const blockers=findings.filter(f=>f.kind==='factual');
  $('finalize-button').disabled=busy || Boolean(pending.length || blockers.length || unchecked.length || run.knowledge_changed || run.layout_state!=='passed');
  $('check-summary').textContent=busy ? (run.task?.message || 'Checking…') : `${blockers.length} factual concerns · ${unchecked.length} passages need checking${run.knowledge_changed ? ' · Knowledge changed: check again' : ''}`;
  $('check-draft').hidden=!unchecked.length && !run.knowledge_changed && run.layout_state==='passed';
  $('check-draft').disabled=busy;
  $('layout-report').hidden=!(run.layout_issues || []).length;
  $('layout-details').textContent=(run.layout_issues || []).join('\n');
  const full=run.current_draft || run.draft;
  renderCompleteDraft(run.resume_content);
  const selected=new Set([...$('repair-fields').selectedOptions].map(o=>o.value));
  $('repair-fields').replaceChildren();
  for(const key of Object.keys(full.fields)) {
    const option=new Option(changeLabel({id:key}),key); option.selected=selected.has(key); $('repair-fields').add(option);
  }
  $('refine-button').disabled=busy;
  $('proposal-preview').disabled=!run.proposal_url;
  $('changes').replaceChildren();
  if (!openChange || !changes.some(c=>c.id===openChange)) openChange=pending[0]?.id || changes[0]?.id;
  for (const change of changes) {
    const flags=findings.filter(f=>f.field===change.id);
    if ($('pending-only').checked && decisions[change.id] && !flags.some(f=>f.kind==='factual') && !unchecked.includes(change.id)) continue;
    const card=node('details','review-group change-card'); card.dataset.change=change.id; card.open=change.id===openChange;
    card.addEventListener('toggle',()=>{ if(card.open)openChange=change.id; });
    const heading=node('summary','review-group-heading');
    const needsEvidence=flags.some(f=>f.kind==='factual');
    const badge=needsEvidence?'Needs evidence':unchecked.includes(change.id)?'Needs check':decisions[change.id]?.action || 'Pending';
    heading.append(node('span','',changeLabel(change)),node('span',`decision-badge ${needsEvidence?'needs-evidence':decisions[change.id]?.action || ''}`,badge));
    const body=node('div','edit-item-body');
    if (change.id==='structure') body.append(structureView());
    else {
      body.append(node('p','field-caption','Original'),node('p','comparison-text',change.original || 'New bullet'),node('p','field-caption','Proposed'),node('p','comparison-text proposed',change.suggested || 'Omit this bullet'));
      if(decisions[change.id]?.action==='edit') body.append(node('p','saved-decision',decisions[change.id].text));
    }
    for(const finding of flags) body.append(node('p',finding.kind==='factual'?'status error':'hint',`${finding.kind==='factual'?'Needs evidence':'Suggestion'}: ${finding.reason}`));
    if(unchecked.includes(change.id)) body.append(node('p','hint','This passage needs an evidence check before export.'));
    if(flags.length && change.id!=='structure') {
      const fix=node('button','secondary-button','Correct this passage');fix.disabled=busy;
      fix.onclick=()=>repair([change.id]);body.append(fix);
    }
    const current=full.fields[change.id];
    if(current && (flags.some(f=>f.kind==='factual') || unchecked.includes(change.id))) {
      const box=node('details','edit-options');box.append(node('summary','','Confirm a fact missing from my sources'));
      box.append(node('p','comparison-text',current.text));
      const label=node('label',''), checkbox=node('input');checkbox.type='checkbox';
      label.append(checkbox,document.createTextNode(' I confirm every claim in this exact passage, including who did it and its outcomes.'));
      const confirm=node('button','secondary-button','Confirm passage and save to knowledge');confirm.disabled=true;
      checkbox.onchange=()=>{confirm.disabled=busy || !checkbox.checked;};
      confirm.onclick=()=>action('/api/guided/confirm',{change_id:change.id,text:current.text,confirmed:true},'Saving the confirmed passage to knowledge…');
      box.append(label,confirm);body.append(box);
    }
    const evidence=node('details','evidence'); evidence.append(node('summary','','Why this change?'));
    evidence.append(node('p','',change.reason));
    for(const id of change.requirement_ids || []) {const req=run.analysis.requirements.find(r=>r.id===id);if(req)evidence.append(node('p','',`JD: ${req.quote}`));}
    for(const id of decisions[change.id]?.source_ids || change.source_ids || []) {const fact=run.evidence[id]; if(fact)evidence.append(node('p','',`${id}: ${fact.text}`));}
    body.append(evidence);
    const controls=node('div','action-grid');
    const options=change.required?[['accept','Approve included content']]:[['accept',change.suggested?'Accept proposal':'Approve omission'],['keep',change.original?'Keep original':'Omit new bullet']];
    for(const [actionName,label] of options){const button=node('button',actionName==='keep'?'secondary-button':'',label);button.type='button';button.disabled=busy;button.onclick=()=>decide(change.id,actionName);controls.append(button);}
    body.append(controls);
    if (!change.required && change.suggested) {
      const editBox=node('details','edit-options'); editBox.append(node('summary','','Edit this text'));
      const input=node('textarea','edit-field'); input.value=decisions[change.id]?.text || change.suggested; input.maxLength=2000; input.setAttribute('aria-label',`Edit ${changeLabel(change)}`);
      const save=node('button','secondary-button','Save my edit'); save.type='button';save.disabled=busy;save.onclick=()=>decide(change.id,'edit',input.value);
      editBox.append(input,node('p','hint','Save your edit, then check it against your evidence. If it adds a true fact, explicitly confirm the complete passage to save it to knowledge.'),save);body.append(editBox);
    }
    card.append(heading,body);$('changes').append(card);
  }
  if (!$('changes').children.length) $('changes').append(node('p','board-empty','All proposals are reviewed. Turn off Pending only to revisit them.'));
  renderAnalysis('coverage-view',true);
  $('recommendations').replaceChildren();
  const recommendations=run.analysis.recommendations || [];
  if(recommendations.length)$('recommendations').append(node('h3','','Future work · not included in your resume'));
  for(const rec of recommendations)$('recommendations').append(node('h3','',rec.title),node('p','hint',rec.detail));
}
async function decide(id, actionName, text='') {
  const result=await action('/api/guided/decision',{change_id:id,action:actionName,text},'Saving your decision…');
  if(result){closePdf();openChange=run.changes.find(c=>!run.decisions[c.id])?.id || id;renderReview();status('');const card=[...document.querySelectorAll('[data-change]')].find(c=>c.dataset.change===openChange);card?.querySelector('summary')?.focus();}
}
$('pending-only').onchange=renderReview;
async function repair(fields) {
  if(busy)return;
  if(!fields.length){status('Select the passages to change.',true);return;}
  closePdf();await action('/api/guided/repair',{fields,direction:$('direction').value},'Correcting only selected passages…');
}
$('refine-button').onclick=()=>repair([...$('repair-fields').selectedOptions].map(o=>o.value));
$('check-draft').onclick=()=>action('/api/guided/check',{},'Checking changed passages and PDF limits…');
$('finalize-button').onclick=()=>action('/api/guided/finish',{},'Checking your reviewed choices…');
$('retry-button').onclick=()=>{
  const operation=run.task?.operation;
  if(operation==='check')return action('/api/guided/check',{},'Resuming evidence check…');
  if(operation==='repair')return action('/api/guided/repair',{fields:run.repair_fields,direction:run.direction || ''},'Resuming selected corrections…');
  return action(operation==='finish'?'/api/guided/finish':operation==='draft'?'/api/guided/draft':'/api/guided/analyze', operation==='draft'?{direction:$('direction').value || run.direction || ''}:{} ,'Retrying…');
};
function reset(){epoch++;clearTimeout(pollTimer);run=null;openChange=null;storage.remove('sculptGuidedRunId');storage.remove('sculptPastedJob');$('parse-form').reset();fillJob({});$('jd-count').textContent='0 / 30,000';$('pending-only').checked=false;$('task-actions').hidden=true;setBusy(false);closePdf();showStep('paste');status('');}
$('reset-button').onclick=()=>{if(run || $('jd').value){$('reset-dialog').returnValue='';$('reset-dialog').showModal();}else reset();};
$('reset-dialog').addEventListener('close',()=>{if($('reset-dialog').returnValue==='reset')reset();});
async function loadKnowledge(){knowledge=await request('/api/knowledge');$('knowledge-storage').textContent=knowledge.storage || '';renderKnowledge();}
function kbStatus(message,error=false){$('knowledge-status').hidden=!message;$('knowledge-status').textContent=message;$('knowledge-status').className=`status${error?' error':''}`;}
function renderKnowledge(){
  $('knowledge-list').replaceChildren();
  const entries=knowledge.document.entries.filter(e=>!e.archived);
  if(!entries.length)$('knowledge-list').append(node('p','hint','No saved knowledge yet. Add information here or answer questions during tailoring.'));
  for(const entry of entries){
    const card=node('details','plan-card');card.append(node('summary','',`${knowledge.scopes[entry.scope] || entry.scope} · ${entry.kind}`));
    if(entry.question)card.append(node('p','hint',entry.question));card.append(node('p','knowledge-text',entry.text));
    const controls=node('div','action-grid'),edit=node('button','secondary-button','Edit'),archive=node('button','secondary-button','Archive');
    edit.onclick=()=>editKnowledge(entry);archive.onclick=()=>saveKnowledge({...entry,archived:true});controls.append(edit,archive);card.append(controls);$('knowledge-list').append(card);
  }
}
function editKnowledge(entry=null){
  editingKnowledge=entry;const select=$('knowledge-scope');select.replaceChildren();for(const [key,label] of Object.entries(knowledge.scopes))select.add(new Option(label,key));
  select.value=entry?.scope || 'general';$('knowledge-kind').value=entry?.kind || 'fact';$('knowledge-text').value=entry?.text || '';$('knowledge-form').hidden=false;$('knowledge-text').focus();
}
async function saveKnowledge(entry){
  const button=$('knowledge-form').querySelector('button');button.disabled=true;
  try{knowledge=await request('/api/knowledge/save',{entry,revision:knowledge.revision});renderKnowledge();$('knowledge-form').hidden=true;editingKnowledge=null;kbStatus('Saved to knowledge.json. Refine an existing draft to use updated facts.');}
  catch(error){kbStatus(error.message,true);await loadKnowledge().catch(()=>{});}finally{button.disabled=false;}
}
$('knowledge-button').onclick=async()=>{$('knowledge-dialog').showModal();kbStatus('Loading…');try{await loadKnowledge();kbStatus('');}catch(error){kbStatus(error.message,true);}};
$('close-knowledge').onclick=()=>$('knowledge-dialog').close();
$('new-knowledge').onclick=()=>{if(knowledge)editKnowledge();};
$('knowledge-form').addEventListener('submit',event=>{event.preventDefault();saveKnowledge({...editingKnowledge,scope:$('knowledge-scope').value,kind:$('knowledge-kind').value,text:$('knowledge-text').value,archived:false});});
async function restore(){
  $('legacy-link').hidden=!storage.get('resumeTailorReviewId');
  $('jd').value=storage.get('sculptPastedJob')||'';$('jd-count').textContent=`${$('jd').value.length.toLocaleString()} / 30,000`;
  const id=storage.get('sculptGuidedRunId');if(!id)return;const version=epoch;
  try{const saved=await request(`/api/guided/run/${encodeURIComponent(id)}`);if(version===epoch)receive(saved,false);}
  catch(error){if(version===epoch)status(error.message,true);}
}
showStep('paste',false);restore();
