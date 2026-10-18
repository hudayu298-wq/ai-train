const $ = s => document.querySelector(s);
let catalog, plans = [];
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
 const [p,t,m,media]=await Promise.all([api('/plans'),api('/training'),api('/meals'),api('/media')]);plans=p;
 $('#training-count').textContent=t.length;const now=new Date();const today=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');const meals=m.filter(x=>x.day===today);
 $('#calories').innerHTML=`${Math.round(meals.reduce((sum,x)=>sum+x.nutrients.kcal,0))} <i>kcal</i>`;
 $('#plan-overview').innerHTML=planMarkup();$('#plan-detail').innerHTML=planMarkup();
 $('#training-list').innerHTML=t.length?t.map(x=>`<div class="row"><b>${escapeText(catalog.exercises.find(e=>e.id===x.exercise_id)?.name||x.exercise_id)}</b><div>${x.weight_kg} kg · ${x.sets} × ${x.reps} · RPE ${x.rpe}<br><small>${escapeText(x.day)} · ${escapeText(x.feedback)}</small></div></div>`).join(''):'还没有训练记录。';
 $('#meal-list').innerHTML=meals.length?meals.map(x=>`<div class="row"><div><b>${escapeText(x.name)}</b><br><small>${x.grams} g · 蛋白质 ${x.nutrients.protein} g · 碳水 ${x.nutrients.carbs} g · 脂肪 ${x.nutrients.fat} g</small></div><div>${x.nutrients.kcal} kcal <button data-delete="${x.id}">删除</button></div></div>`).join(''):'今天还没有饮食记录。';
 document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=async()=>{try{await api('/meals/'+b.dataset.delete,{method:'DELETE'});await refresh();}catch(e){notice(e.message,true);}});
 $('#media-list').innerHTML=media.length?media.map(x=>`<div class="row"><b>${x.kind==='video'?'训练录像':'餐食照片'}</b><div>${(x.bytes/1024/1024).toFixed(1)} MB<br><small>${escapeText(x.message)}</small></div></div>`).join(''):'还没有上传文件。';
}
bindForm('#profile-form',async f=>{const p=Object.fromEntries(f);['age','height_cm','weight_kg','days'].forEach(k=>p[k]=Number(p[k]));await api('/profile',jsonOptions('PUT',p));notice('画像已保存。可以生成起始计划。');});
$('#generate').onclick=async()=>{const b=$('#generate');b.disabled=true;try{await api('/plans',{method:'POST'});await refresh();show('training');notice('已生成起始模板，请复核后使用。');}catch(e){notice(e.message,true);}finally{b.disabled=false;}};
bindForm('#training-form',async f=>{const t=Object.fromEntries(f);['weight_kg','sets','reps','rpe'].forEach(k=>t[k]=Number(t[k]));t.pain=f.has('pain');await api('/training',jsonOptions('POST',t));notice(t.pain?'记录已保存。出现不适时请暂停加重并寻求专业评估。':'训练已记录。');});
bindForm('#meal-form',async f=>{await api('/meals',jsonOptions('POST',{food_id:f.get('food_id'),grams:Number(f.get('grams'))}));notice('饮食已记录。');});
for(const [id,kind]of [['#meal-upload','meal'],['#video-upload','video']])bindForm(id,async f=>{f.set('kind',kind);const r=await api('/media',{method:'POST',body:f});notice(r.message);});
async function init(){catalog=await api('/catalog');$('#today').textContent=new Date().toLocaleDateString('zh-CN');$('#exercise-cards').innerHTML=catalog.exercises.map((e,i)=>`<article class="exercise-card"><b>0${i+1}</b><h3>${escapeText(e.name)}</h3><p>${escapeText(e.view)}</p></article>`).join('');document.querySelectorAll('.exercise-select').forEach(s=>s.innerHTML=catalog.exercises.map(e=>`<option value="${e.id}">${escapeText(e.name)}</option>`).join(''));$('#food-select').innerHTML=catalog.foods.map(f=>`<option value="${f.id}">${escapeText(f.name)}</option>`).join('');const guide=()=>$('#view-guide').textContent=catalog.exercises.find(e=>e.id===$('#video-exercise').value).view;$('#video-exercise').onchange=guide;guide();const p=await api('/profile');if(p)for(const [key,value]of Object.entries(p)){const input=$('#profile-form').elements.namedItem(key);if(input)input.value=value;}await refresh();}
init().catch(e=>notice('服务连接失败：'+e.message,true));
