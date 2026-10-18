const $ = s => document.querySelector(s);
let catalog, plans = [], nutrition, draftEntries = [], draftLoaded = false, editingEntry = null, generationId = null;
const escapeText = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(text, error=false){$('#notice').textContent=text;$('#notice').className=error?'error':'';$('#notice').hidden=false;}
async function api(path, options={}){
 const response=await fetch('/api'+path, options);
 const data=await response.json();
 if(!response.ok) throw Error(typeof data.detail==='string'?data.detail:'输入不符合要求，请检查数值范围。');
 return data;
}
function show(tab){document.querySelectorAll('.page').forEach(p=>p.hidden=p.id!==tab);document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));}
document.querySelectorAll('[data-tab],[data-go]').forEach(b=>b.onclick=()=>show(b.dataset.tab||b.dataset.go));
function jsonOptions(method,payload){return {method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)};}
function bindForm(id, action){$(id).onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await action(new FormData(e.target));await refresh();}catch(err){notice(err.message,true);}finally{b.disabled=false;}};}
function assessmentMarkup(a){return `<p class="muted">${escapeText(a.note)}</p>`+a.items.map(x=>`<div class="row"><b>${escapeText(x.day)} · ${escapeText(catalog.exercises.find(e=>e.id===x.exercise_id)?.name||x.exercise_id)}</b><div>${x.load_percent===null?'暂无RM评估':`${x.load_percent}% 1RM参考 · ${x.reference_1rm_kg}kg`}<br><small>${escapeText(x.message)}</small></div></div>`).join('');}
function planMarkup(){if(!plans.length)return '先保存画像，再到训练页生成AI计划并确认保存。';const p=plans[0];return `<h3>${escapeText(p.name)}</h3><p class="muted">${escapeText(p.note)}</p>`+p.days.map(d=>`<div class="row"><b>${escapeText(d.name)}</b><div>${d.exercises.map(e=>`${escapeText(e.name)} · ${e.weight_kg===null?'重量待确认':e.weight_kg+' kg'} · ${e.sets} × ${e.reps} · 休息 ${e.rest_seconds} 秒`).join('<br>')}</div></div>`).join('')+assessmentMarkup(p.assessment);}
async function refresh(){
 const [p,t,n,media,rm]=await Promise.all([api('/plans'),api('/training'),api('/nutrition/today'),api('/media'),api('/rm')]);plans=p;nutrition=n;
 $('#rm-list').innerHTML=rm.length?rm.map(r=>`<div class="row"><b>${escapeText(catalog.exercises.find(e=>e.id===r.exercise_id)?.name)} · ${r.weight_kg}kg × ${r.reps}RM</b><div>${escapeText(r.measured_on)}<br><small>${r.reference_1rm_kg===null?'未确认最大次数，暂不评估':`${r.reps===1?'用户提供':'估算'}1RM ${r.reference_1rm_kg}kg`}</small></div></div>`).join(''):'还没有RM数据。';
 if(!draftLoaded){draftLoaded=true;if(p.length){generationId=p[0].generation_id;$('#plan-name').value=p[0].name;draftEntries=p[0].days.flatMap(d=>d.exercises.map(e=>({day:d.name,...e})));}renderDraft();}
 $('#training-count').textContent=t.length;
 $('#calories').innerHTML=`${n.totals.kcal} <i>kcal</i>`;
 $('#plan-overview').innerHTML=planMarkup();$('#plan-detail').innerHTML=planMarkup();
 $('#training-list').innerHTML=t.length?t.map(x=>`<div class="row"><b>${escapeText(catalog.exercises.find(e=>e.id===x.exercise_id)?.name||x.exercise_id)}</b><div>${x.weight_kg} kg · ${x.sets} × ${x.reps} · RPE ${x.rpe}<br><small>${escapeText(x.day)} · ${escapeText(x.feedback)}</small></div></div>`).join(''):'还没有训练记录。';
 renderNutrition(n);
 document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=async()=>{try{await api('/meals/'+b.dataset.delete,{method:'DELETE'});await refresh();}catch(e){notice(e.message,true);}});
 $('#media-list').innerHTML=media.length?media.map(x=>`<div class="row"><b>${x.kind==='video'?'训练录像':'餐食照片'}</b><div>${(x.bytes/1024/1024).toFixed(1)} MB<br><small>${escapeText(x.message)}</small></div></div>`).join(''):'还没有上传文件。';
}
function renderNutrition(n){
 const targetMessage=n.target_status==='ready'?'营养目标根据当前画像估算；摄入数据来自你确认的每餐份量。':'先保存画像，才能估算每日营养目标。';
 $('#daily-summary').innerHTML=`<h2>${escapeText(n.day)} · 当天营养</h2><p class="muted">${targetMessage}</p><div class="nutrient-grid">`+Object.entries({kcal:'热量',protein:'蛋白质',fat:'脂肪',carbs:'碳水'}).map(([key,label])=>{
  const m=n.comparison[key],unit=key==='kcal'?'kcal':'g',hasTarget=m.target!==null;
  return `<div><small>${label}</small><h3>${m.consumed} <small>${unit}</small></h3><p class="muted">${hasTarget?'目标 '+m.target+' '+unit:'目标未设置'}</p>${hasTarget?`<progress max="100" value="${Math.min(100,m.percent||0)}" class="${m.excess>0?'over':''}" aria-label="${label}目标完成度"></progress><p>${m.excess>0?'超出目标 '+m.excess:'距目标还差 '+m.remaining} ${unit}</p>`:''}</div>`;
 }).join('')+'</div>';
 $('#meal-list').innerHTML=n.groups.map(g=>`<div class="meal-group"><h3>${g.label} · ${g.totals.kcal} kcal</h3><p class="muted">蛋白质 ${g.totals.protein} g · 脂肪 ${g.totals.fat} g · 碳水 ${g.totals.carbs} g</p>`+(g.items.length?g.items.map(x=>`<div class="row"><div><b>${escapeText(x.name)}</b><br><small>${x.grams} g · 蛋白质 ${x.nutrients.protein} g · 碳水 ${x.nutrients.carbs} g · 脂肪 ${x.nutrients.fat} g</small></div><div>${x.nutrients.kcal} kcal <button data-delete="${x.id}">删除</button></div></div>`).join(''):'<p class="muted">这餐还没有记录</p>')+'</div>').join('');
}
bindForm('#profile-form',async f=>{const p=Object.fromEntries(f);['age','height_cm','weight_kg','days'].forEach(k=>p[k]=Number(p[k]));await api('/profile',jsonOptions('PUT',p));notice('画像已保存，营养目标已更新。可以在训练页生成AI计划。');});
bindForm('#rm-form',async f=>{await api('/rm',jsonOptions('POST',{exercise_id:f.get('exercise_id'),weight_kg:Number(f.get('weight_kg')),reps:Number(f.get('reps')),measured_on:f.get('measured_on'),confirmed_maximum:f.has('confirmed_maximum')}));$('#draft-assessment').innerHTML='RM已更新，请重新评估草稿。';notice('RM数据已保存。');});
function renderDraft(){
 $('#draft-list').innerHTML=draftEntries.length?draftEntries.map((e,i)=>`<div class="row"><b>${escapeText(e.day)} · ${escapeText(catalog.exercises.find(x=>x.id===e.exercise_id)?.name)}</b><div>${e.weight_kg===null?'重量待确认':e.weight_kg+'kg'} · ${e.sets} × ${e.reps} · 休息${e.rest_seconds}秒 <button type="button" data-edit-entry="${i}">编辑</button><button type="button" data-remove-entry="${i}">移除</button></div></div>`).join(''):'草稿为空，请添加动作。';
 document.querySelectorAll('[data-remove-entry]').forEach(b=>b.onclick=()=>{draftEntries.splice(Number(b.dataset.removeEntry),1);editingEntry=null;renderDraft();$('#draft-assessment').innerHTML='草稿已修改，请重新评估。';});
 document.querySelectorAll('[data-edit-entry]').forEach(b=>b.onclick=()=>{editingEntry=Number(b.dataset.editEntry);const e=draftEntries[editingEntry],form=$('#plan-entry-form');for(const key of ['day','exercise_id','weight_kg','sets','reps','rest_seconds'])form.elements.namedItem(key).value=e[key]??'';$('#add-entry').textContent='更新该动作';});
 if(editingEntry===null)$('#add-entry').textContent='添加到计划';
}
bindForm('#plan-entry-form',async f=>{const e=Object.fromEntries(f);e.day=e.day.trim();if(!e.day)throw Error('请填写训练日名称');['sets','reps','rest_seconds'].forEach(k=>e[k]=Number(e[k]));e.weight_kg=e.weight_kg.trim()?Number(e.weight_kg):null;if(editingEntry===null)draftEntries.push(e);else draftEntries[editingEntry]=e;editingEntry=null;renderDraft();$('#draft-assessment').innerHTML='草稿已修改，请重新评估。';});
function planPayload(){if(editingEntry!==null)throw Error('请先更新正在编辑的动作');const name=$('#plan-name').value.trim();if(!name||!draftEntries.length)throw Error('请填写计划名称并添加动作');const days=new Map();for(const e of draftEntries){if(!days.has(e.day))days.set(e.day,[]);const {day,...rest}=e;const item={};for(const key of ['exercise_id','weight_kg','sets','reps','rest_seconds'])item[key]=rest[key];days.get(day).push(item);}return {name,...(generationId?{generation_id:generationId}:{}),days:Array.from(days,([name,exercises])=>({name,exercises}))};}
bindForm('#user-plan-form',async()=>{const p=await api('/plans',jsonOptions('POST',planPayload()));$('#draft-assessment').innerHTML=assessmentMarkup(p.assessment);notice('你的计划已保存，RM评估已更新。');});
$('#assess-draft').onclick=async()=>{const b=$('#assess-draft');b.disabled=true;try{const a=await api('/plans/assess',jsonOptions('POST',planPayload()));$('#draft-assessment').innerHTML=assessmentMarkup(a);}catch(e){notice(e.message,true);}finally{b.disabled=false;}};
bindForm('#training-form',async f=>{const t=Object.fromEntries(f);['weight_kg','sets','reps','rpe'].forEach(k=>t[k]=Number(t[k]));t.pain=f.has('pain');await api('/training',jsonOptions('POST',t));notice(t.pain?'记录已保存。出现不适时请暂停加重并寻求专业评估。':'训练已记录。');});
bindForm('#meal-form',async f=>{await api('/meals',jsonOptions('POST',{food_id:f.get('food_id'),grams:Number(f.get('grams')),meal_type:f.get('meal_type')}));notice('饮食已记录，当天汇总已更新。');});
for(const [id,kind]of [['#meal-upload','meal'],['#video-upload','video']])bindForm(id,async f=>{f.set('kind',kind);const r=await api('/media',{method:'POST',body:f});notice(r.message);});
async function init(){catalog=await api('/catalog?extended=true');$('#today').textContent=new Date().toLocaleDateString('zh-CN');$('#exercise-cards').innerHTML=catalog.exercises.filter(e=>e.realtime_supported).map((e,i)=>`<article class="exercise-card"><b>0${i+1}</b><h3>${escapeText(e.name)}</h3><p>${escapeText(e.view)}</p></article>`).join('');document.querySelectorAll('.exercise-select').forEach(s=>s.innerHTML=catalog.exercises.filter(e=>e.type==='weighted').map(e=>`<option value="${e.id}">${escapeText(e.name)}</option>`).join(''));$('#food-select').innerHTML=catalog.foods.map(f=>`<option value="${f.id}">${escapeText(f.name)}</option>`).join('');const guide=()=>$('#view-guide').textContent=catalog.exercises.find(e=>e.id===$('#video-exercise').value).view;$('#video-exercise').onchange=guide;guide();const p=await api('/profile');if(p)for(const [key,value]of Object.entries(p)){const input=$('#profile-form').elements.namedItem(key);if(input)input.value=value;}await refresh();}
init().catch(e=>notice('服务连接失败：'+e.message,true));
setInterval(()=>{if(!document.hidden)refresh().catch(e=>notice('当天数据刷新失败：'+e.message,true));},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh().catch(e=>notice(e.message,true));});

$('#generate-plan').onclick=async()=>{const b=$('#generate-plan');b.disabled=true;b.textContent='AI生成中…';try{const p=await api('/plans/generate',jsonOptions('POST',{}));generationId=p.generation_id;$('#plan-name').value=p.name;draftEntries=p.days.flatMap(d=>d.exercises.map(e=>({day:d.name,...e})));editingEntry=null;renderDraft();$('#ai-plan-notes').innerHTML=['rationale','warmup','recovery','progression'].map((k,i)=>`<p><b>${['制定理由','热身','恢复','调整建议'][i]}：</b>${escapeText(p[k])}</p>`).join('');$('#draft-assessment').innerHTML=assessmentMarkup(p.assessment);notice('AI草稿已生成，请检查并确认保存。');}catch(e){notice(e.message,true);}finally{b.disabled=false;b.textContent='根据画像生成 AI 计划';}};
