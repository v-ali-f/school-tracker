const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clean = s => String(s ?? '').trim().replace(/\s+/g,' ');
const key = (c,n) => `${clean(c).toUpperCase()}|${clean(n).toLocaleLowerCase('ru')}`;
const fmt = n => Number.isFinite(n) ? n.toFixed(2) : '—';
let raw, roster=[], byStudent=new Map(), activeView='dashboard';
const root=document.querySelector('#quality-app');

function subjectName(source){
  const s=clean(source).toLocaleLowerCase('ru');
  if(/^рус/.test(s))return 'Русский язык';
  if(/^матем/.test(s))return 'Математика';
  if(/^физик/.test(s))return 'Физика';
  if(/^информ/.test(s))return 'Информатика';
  if(/^биолог/.test(s))return 'Биология';
  if(/^хим/.test(s))return 'Химия';
  if(/^истор/.test(s))return 'История';
  if(/^общест/.test(s))return 'Обществознание';
  if(/^географ/.test(s))return 'География';
  if(/^англ/.test(s))return 'Английский язык';
  if(/^литератур/.test(s))return 'Литература';
  return clean(source).replace(/\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\..*$/,'');
}
function journalSubject(source){
  if(['Алгебра','Геометрия','Вероятность и статистика','Математика'].includes(source))return 'Математика';
  return source;
}
function build(){
  byStudent=new Map();
  for(const e of raw.gia?.students||[]){
    const id=key(e.class,e.name);
    byStudent.set(id,{class:e.class,name:e.name,choices:(e.choices||[]).map(x=>({subject:subjectName(x.subject),level:x.level||''})),journals:[]});
  }
  for(const rec of raw.journals?.records||[]){
    const id=key(rec.class,rec.name);
    if(!byStudent.has(id))byStudent.set(id,{class:rec.class,name:rec.name,choices:[],journals:[],missingGia:true});
    byStudent.get(id).journals.push(rec);
  }
  roster=[...byStudent.values()].sort((a,b)=>a.class.localeCompare(b.class,'ru')||a.name.localeCompare(b.name,'ru'));
  if(!$('#from').value)$('#from').value=`${String(raw.year||'').slice(0,4)||new Date().getFullYear()}-09-01`;
  if(!$('#to').value)$('#to').value=raw.journals?.snapshot||new Date().toISOString().slice(0,10);
  $('#source').textContent=`Журналы: ${raw.journals?.snapshot||'не загружены'} · ГИА: ${raw.gia?.asOf||'не загружена'}`;
  updateFilters();render();
}
function selection(){return {grade:$('#grade').value,cls:$('#class').value,subject:$('#subject').value,search:clean($('#student-search').value).toLocaleLowerCase('ru'),from:$('#from').value,to:$('#to').value,attention:$('#attention').checked};}
function filteredMarks(items,from,to){return items.filter(x=>(!from||x.date>=from)&&(!to||x.date<=to));}
function summarize(student,filter){
  const chosen=student.choices.filter(x=>!filter.subject||x.subject===filter.subject);
  const wanted=new Set(chosen.map(x=>x.subject));
  const recs=student.journals.filter(x=>wanted.has(journalSubject(x.subject)));
  const marks=recs.flatMap(x=>filteredMarks(x.marks||[],filter.from,filter.to));
  const absences=recs.flatMap(x=>filteredMarks((x.absences||[]).map(date=>({date})),filter.from,filter.to));
  const avg=marks.length?marks.reduce((s,x)=>s+x.grade,0)/marks.length:NaN;
  const twos=marks.filter(x=>x.grade===2).length;
  const reasons=[];
  if(student.missingGia)reasons.push('Нет в таблице ГИА');
  if(!chosen.length)reasons.push('Экзамены не указаны');
  if(student.class.startsWith('9')&&!filter.subject&&chosen.length<4)reasons.push('Указано менее 4 экзаменов');
  if(marks.length>=3&&avg<3.5)reasons.push('Низкий средний балл');
  if(twos>=2)reasons.push('Две и более оценки «2»');
  for(const choice of chosen){
    const inSubject=recs.filter(x=>journalSubject(x.subject)===choice.subject).flatMap(x=>filteredMarks(x.marks||[],filter.from,filter.to));
    if(!inSubject.length)reasons.push(`Нет отметок: ${choice.subject}`);
  }
  return {...student,chosen,marks,absences,avg,twos,reasons:[...new Set(reasons)]};
}
function filtered(){
  const f=selection();
  return roster.filter(s=>s.class.startsWith(f.grade)&&(!f.cls||s.class===f.cls)&&(!f.subject||s.choices.some(x=>x.subject===f.subject))&&(!f.search||s.name.toLocaleLowerCase('ru').includes(f.search))).map(s=>summarize(s,f)).filter(s=>!f.attention||s.reasons.length);
}
function updateFilters(){
  const grade=$('#grade').value, prevClass=$('#class').value,prevSubject=$('#subject').value;
  const list=roster.filter(x=>x.class.startsWith(grade));
  const classes=[...new Set(list.map(x=>x.class))].sort((a,b)=>a.localeCompare(b,'ru'));
  const subjects=[...new Set(list.flatMap(x=>x.choices.map(y=>y.subject)))].sort((a,b)=>a.localeCompare(b,'ru'));
  $('#class').innerHTML='<option value="">Все классы</option>'+classes.map(x=>`<option>${esc(x)}</option>`).join('');
  $('#subject').innerHTML='<option value="">Все предметы</option>'+subjects.map(x=>`<option>${esc(x)}</option>`).join('');
  if(classes.includes(prevClass))$('#class').value=prevClass;
  if(subjects.includes(prevSubject))$('#subject').value=prevSubject;
}
function pills(choices){return choices.length?choices.map(x=>`<span class="q-pill">${esc(x.subject)}${x.level?' · '+esc(x.level):''}</span>`).join(''):'<span class="q-pill warn">Нет выбора</span>';}
function studentRow(s){
  return `<tr><td><button class="q-person" data-person="${esc(key(s.class,s.name))}">${esc(s.name)}</button></td><td>${esc(s.class)}</td><td>${pills(s.chosen)}</td><td>${fmt(s.avg)}</td><td>${s.twos}</td><td>${s.absences.length}</td><td>${s.reasons.length?s.reasons.map(x=>`<span class="q-pill warn">${esc(x)}</span>`).join(''):'<span class="q-pill good">Без сигналов</span>'}</td></tr>`;
}
function render(){
  const data=filtered(), f=selection(), all=roster.filter(x=>x.class.startsWith(f.grade)&&(!f.cls||x.class===f.cls));
  const avgMarks=data.flatMap(x=>x.marks),avg=avgMarks.length?avgMarks.reduce((s,x)=>s+x.grade,0)/avgMarks.length:NaN;
  const flagged=data.filter(x=>x.reasons.length);
  $('#kpis').innerHTML=[
    ['Учеников в выборке',data.length,'bi-people',''],
    ['Сигналы внимания',flagged.length,'bi-exclamation-circle','is-warning'],
    ['Средний балл по выбранным экзаменам',fmt(avg),'bi-bar-chart',''],
    ['Зафиксировано пропусков',data.reduce((s,x)=>s+x.absences.length,0),'bi-calendar-x','']
  ].map(([label,value,icon,tone])=>`<div class="ws-metric ${tone}"><span class="ws-metric-icon"><i class="bi ${icon}" aria-hidden="true"></i></span><span class="ws-metric-copy"><span class="ws-metric-label">${esc(label)}</span><strong class="ws-metric-value">${value}</strong></span></div>`).join('');
  const counts=new Map();
  for(const s of data)for(const c of s.chosen)counts.set(c.subject,(counts.get(c.subject)||0)+1);
  const sorted=[...counts].sort((a,b)=>b[1]-a[1]),max=Math.max(1,...sorted.map(x=>x[1]));
  $('#bars').innerHTML=sorted.length?sorted.map(([sub,n])=>`<div class="q-bar"><span>${esc(sub)}</span><div class="q-track"><div class="q-fill" style="width:${Math.round(n/max*100)}%"></div></div><strong>${n}</strong></div>`).join(''):'<div class="empty">В выбранной группе нет отмеченных экзаменов.</div>';
  const reasonCounts=new Map();for(const s of flagged)for(const r of s.reasons)reasonCounts.set(r,(reasonCounts.get(r)||0)+1);
  $('#signals').innerHTML=reasonCounts.size?[...reasonCounts].sort((a,b)=>b[1]-a[1]).slice(0,7).map(([r,n])=>`<div class="row" style="border-bottom:1px solid #e5ebf1;padding:8px 0"><span>${esc(r)}</span><strong>${n}</strong></div>`).join(''):'<div class="empty">Сигналов нет.</div>';
  $('#dashboard-rows').innerHTML=flagged.slice(0,40).map(studentRow).join('')||'<tr><td colspan="7" class="empty">В этой выборке нет сигналов внимания.</td></tr>';
  $('#student-rows').innerHTML=data.map(studentRow).join('')||'<tr><td colspan="7" class="empty">Нет учеников для выбранных фильтров.</td></tr>';
  $('#student-count').textContent=`Показано ${data.length} из ${all.length}`;
  $('#exam-heading').textContent=f.grade==='9'?'Выбор ОГЭ':'Выбор ЕГЭ';
  $('#exam-rows').innerHTML=data.map(s=>`<tr><td><button class="q-person" data-person="${esc(key(s.class,s.name))}">${esc(s.name)}</button></td><td>${esc(s.class)}</td><td>${pills(s.chosen)}</td><td>${s.chosen.length}</td><td>${s.missingGia?'<span class="q-pill bad">Нет в ГИА</span>':s.class.startsWith('9')&&s.chosen.length<4?'<span class="q-pill warn">Проверить выбор</span>':'<span class="q-pill good">Загружено</span>'}</td></tr>`).join('');
  renderMatching();
}
function renderMatching(){
  if(!$('#matching'))return;
  const onlyJournal=roster.filter(x=>x.missingGia),onlyGia=roster.filter(x=>!x.missingGia&&!x.journals.length);
  $('#matching').innerHTML=`<p><strong>${onlyJournal.length}</strong> учеников есть в журналах, но нет в таблице ГИА; <strong>${onlyGia.length}</strong> есть в ГИА, но нет в журналах.</p>`+
    (onlyJournal.length?`<p><strong>Только в журналах:</strong> ${onlyJournal.map(x=>esc(x.class+' · '+x.name)).join('; ')}</p>`:'')+
    (onlyGia.length?`<p><strong>Только в ГИА:</strong> ${onlyGia.map(x=>esc(x.class+' · '+x.name)).join('; ')}</p>`:'')+
    '<p class="small">Сопоставление выполняется по классу и полному ФИО. Расхождения требуют ручной проверки.</p>';
}
function openPerson(id){
  const s=byStudent.get(id);if(!s)return;
  const d=summarize(s,selection());
  $('#drawer-name').textContent=s.name;$('#drawer-sub').textContent=`${s.class} · ${s.class.startsWith('9')?'ОГЭ':'ЕГЭ'}`;
  const subjects=[...new Set([...s.choices.map(x=>x.subject),...s.journals.map(x=>journalSubject(x.subject))])].sort((a,b)=>a.localeCompare(b,'ru'));
  $('#drawer-body').innerHTML=`<div class="q-detail"><div>Средний балл<strong>${fmt(d.avg)}</strong></div><div>Оценок «2»<strong>${d.twos}</strong></div><div>Пропуски<strong>${d.absences.length}</strong></div></div><h3>Выбранные экзамены</h3><p>${pills(s.choices)}</p><h3>Предметы журнала</h3>`+
    subjects.map(sub=>{const rs=s.journals.filter(x=>journalSubject(x.subject)===sub),marks=rs.flatMap(x=>filteredMarks(x.marks||[],selection().from,selection().to)),abs=rs.flatMap(x=>filteredMarks((x.absences||[]).map(date=>({date})),selection().from,selection().to)),mean=marks.length?marks.reduce((a,x)=>a+x.grade,0)/marks.length:NaN;return `<div class="q-subject-card"><div class="row"><strong>${esc(sub)}</strong><span>${fmt(mean)}</span></div><small>${marks.length} отметок · ${abs.length} пропусков${s.choices.some(x=>x.subject===sub)?' · выбран для ГИА':''}</small></div>`}).join('')+
    `<p class="small">Период: ${esc(selection().from||'начало года')} — ${esc(selection().to||raw.journals?.snapshot||'сегодня')}. Среднее рассчитано по текущим отметкам журнала.</p>`;
  $('#drawer').classList.add('open');
}
async function upload(type,input){
  const file=$(input).files[0],status=$('#import-status');
  if(!file){status.textContent='Сначала выберите файл.';return;}
  status.textContent='Проверяю и обновляю данные…';
  try{const form=new FormData();form.append('file',file);const response=await fetch(`${root.dataset.importPrefix}${type}`,{method:'POST',headers:{'X-CSRFToken':document.querySelector('meta[name="csrf-token"]').content},body:form,credentials:'same-origin'});const result=await response.json();if(!response.ok)throw Error(result.error||'Ошибка загрузки');status.textContent=`Данные обновлены: ${result.records} записей.`;await load();}
  catch(err){status.textContent=`Не удалось обновить: ${err.message}`;}
}
async function load(){const r=await fetch(root.dataset.api,{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw Error('Не удалось прочитать данные');raw=await r.json();build();}
document.addEventListener('click',e=>{const tab=e.target.closest('[data-view]');if(tab){activeView=tab.dataset.view;document.querySelectorAll('.q-tabs button').forEach(x=>x.classList.toggle('active',x.dataset.view===activeView));document.querySelectorAll('.q-view').forEach(x=>x.classList.toggle('active',x.id===activeView));}const person=e.target.closest('[data-person]');if(person)openPerson(person.dataset.person);});
$('#grade').addEventListener('change',()=>{updateFilters();render()});
for(const id of ['class','subject','from','to','attention'])$('#'+id).addEventListener('change',render);
$('#student-search').addEventListener('input',render);
$('#show-all').addEventListener('click',()=>document.querySelector('.q-tabs [data-view="students"]').click());
$('#close-drawer').addEventListener('click',()=>$('#drawer').classList.remove('open'));
$('#drawer').addEventListener('click',e=>{if(e.target.id==='drawer')$('#drawer').classList.remove('open')});
document.addEventListener('keydown',e=>{if(e.key==='Escape')$('#drawer').classList.remove('open')});
if($('#upload-journals'))$('#upload-journals').addEventListener('click',()=>upload('journals','#journal-file'));
if($('#upload-gia'))$('#upload-gia').addEventListener('click',()=>upload('gia','#gia-file'));
load().catch(err=>{$('#dashboard').innerHTML=`<div class="card">${esc(err.message)}</div>`});
