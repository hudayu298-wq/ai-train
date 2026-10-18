const $ = s => document.querySelector(s);
let catalog, plans = [], nutrition;
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
function planMarkup(){if(!plans.length)return '尚未生成计划，请先保存画像。';const p=plans[0];return `<p class="muted">${escapeText(p.note)}</p><div class="pill">目标 ${p.nutrition.kcal} kcal · 蛋白质 ${p.nutrition.protein}g · 脂肪 ${p.nutrition.fat}g · 碳水 ${p.nutrition.carbs}g</div>`+p.days.map(d=>`<div class="row"><b>${escapeText(d.name)}</b><div>${d.exercises.map(e=>`${escapeText(e.name)} · ${e.sets} × ${escapeText(e.reps)} · 休息 ${e.rest_seconds} 秒`).join('<br>')}<br><small>${escapeText(d.rest_note)}；选择可控重量，保留约3次余力</small></div></div>`).join('');}
async function refresh(){
 const [p,t,n,media]=await Promise.all([api('/plans'),api('/training'),api('/nutrition/today'),api('/media')]);plans=p;nutrition=n;
 $('#training-count').textContent=t.length;
 $('#calories').innerHTML=`${n.totals.kcal} <i>kcal</i>`;
 $('#plan-overview').innerHTML=planMarkup();$('#plan-detail').innerHTML=planMarkup();
 $('#training-list').innerHTML=t.length?t.map(x=>`<div class="row"><b>${escapeText(catalog.exercises.find(e=>e.id===x.exercise_id)?.name||x.exercise_id)}</b><div>${x.weight_kg} kg · ${x.sets} × ${x.reps} · RPE ${x.rpe}<br><small>${escapeText(x.day)} · ${escapeText(x.feedback)}</small></div></div>`).join(''):'还没有训练记录。';
 renderNutrition(n);
 document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=async()=>{try{await api('/meals/'+b.dataset.delete,{method:'DELETE'});await refresh();}catch(e){notice(e.message,true);}});
 $('#media-list').innerHTML=media.length?media.map(x=>`<div class="row"><b>${x.kind==='video'?'训练录像':'餐食照片'}</b><div>${(x.bytes/1024/1024).toFixed(1)} MB<br><small>${escapeText(x.message)}</small></div></div>`).join(''):'还没有上传文件。';
}
function renderNutrition(n){
 const targetMessage=n.target_status==='ready'?'目标来自当前计划；摄入数据来自你确认的每餐份量。':n.target_status==='stale'?'画像已修改，请重新生成计划以更新目标。':'先保存画像并生成计划，才能对比每日目标。';
 $('#daily-summary').innerHTML=`<h2>${escapeText(n.day)} · 当天营养</h2><p class="muted">${targetMessage}</p><div class="nutrient-grid">`+Object.entries({kcal:'热量',protein:'蛋白质',fat:'脂肪',carbs:'碳水'}).map(([key,label])=>{
  const m=n.comparison[key],unit=key==='kcal'?'kcal':'g',hasTarget=m.target!==null;
  return `<div><small>${label}</small><h3>${m.consumed} <small>${unit}</small></h3><p class="muted">${hasTarget?'目标 '+m.target+' '+unit:'目标未设置'}</p>${hasTarget?`<progress max="100" value="${Math.min(100,m.percent||0)}" class="${m.excess>0?'over':''}" aria-label="${label}目标完成度"></progress><p>${m.excess>0?'超出目标 '+m.excess:'距目标还差 '+m.remaining} ${unit}</p>`:''}</div>`;
 }).join('')+'</div>';
 $('#meal-list').innerHTML=n.groups.map(g=>`<div class="meal-group"><h3>${g.label} · ${g.totals.kcal} kcal</h3><p class="muted">蛋白质 ${g.totals.protein} g · 脂肪 ${g.totals.fat} g · 碳水 ${g.totals.carbs} g</p>`+(g.items.length?g.items.map(x=>`<div class="row"><div><b>${escapeText(x.name)}</b><br><small>${x.grams} g · 蛋白质 ${x.nutrients.protein} g · 碳水 ${x.nutrients.carbs} g · 脂肪 ${x.nutrients.fat} g</small></div><div>${x.nutrients.kcal} kcal <button data-delete="${x.id}">删除</button></div></div>`).join(''):'<p class="muted">这餐还没有记录</p>')+'</div>').join('');
}
bindForm('#profile-form',async f=>{const p=Object.fromEntries(f);['age','height_cm','weight_kg','days'].forEach(k=>p[k]=Number(p[k]));await api('/profile',jsonOptions('PUT',p));notice('画像已保存。可以生成起始计划。');});
$('#generate').onclick=async()=>{const b=$('#generate');b.disabled=true;try{await api('/plans',{method:'POST'});await refresh();show('training');notice('已生成起始模板，请复核后使用。');}catch(e){notice(e.message,true);}finally{b.disabled=false;}};
bindForm('#training-form',async f=>{const t=Object.fromEntries(f);['weight_kg','sets','reps','rpe'].forEach(k=>t[k]=Number(t[k]));t.pain=f.has('pain');await api('/training',jsonOptions('POST',t));notice(t.pain?'记录已保存。出现不适时请暂停加重并寻求专业评估。':'训练已记录。');});
bindForm('#meal-form',async f=>{await api('/meals',jsonOptions('POST',{food_id:f.get('food_id'),grams:Number(f.get('grams')),meal_type:f.get('meal_type')}));notice('饮食已记录，当天汇总已更新。');});
for(const [id,kind]of [['#meal-upload','meal'],['#video-upload','video']])bindForm(id,async f=>{f.set('kind',kind);const r=await api('/media',{method:'POST',body:f});notice(r.message);});
async function init(){catalog=await api('/catalog');$('#today').textContent=new Date().toLocaleDateString('zh-CN');$('#exercise-cards').innerHTML=catalog.exercises.map((e,i)=>`<article class="exercise-card"><b>0${i+1}</b><h3>${escapeText(e.name)}</h3><p>${escapeText(e.view)}</p></article>`).join('');document.querySelectorAll('.exercise-select').forEach(s=>s.innerHTML=catalog.exercises.map(e=>`<option value="${e.id}">${escapeText(e.name)}</option>`).join(''));$('#food-select').innerHTML=catalog.foods.map(f=>`<option value="${f.id}">${escapeText(f.name)}</option>`).join('');const guide=()=>$('#view-guide').textContent=catalog.exercises.find(e=>e.id===$('#video-exercise').value).view;$('#video-exercise').onchange=guide;guide();const p=await api('/profile');if(p)for(const [key,value]of Object.entries(p)){const input=$('#profile-form').elements.namedItem(key);if(input)input.value=value;}await refresh();}
init().catch(e=>notice('服务连接失败：'+e.message,true));
setInterval(()=>{if(!document.hidden)refresh().catch(e=>notice('当天数据刷新失败：'+e.message,true));},60000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh().catch(e=>notice(e.message,true));});
