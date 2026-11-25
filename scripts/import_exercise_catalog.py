"""Build a pinned, licensed full catalog; no Gym visual media is downloaded."""
import argparse,concurrent.futures,csv,hashlib,io,json,re,sys,time
from collections import Counter
from pathlib import Path
import httpx
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.exercise_taxonomy import classify
from backend.external_exercises import display_name as localized_name
DATA_REV='7455efae41b330c265e7cd4b78dfa848e7ce5ebd'
GUIDE_REV='aac599224bb9780305239607ef98540b7e0ce389'
REPOS={'dataset':('hasaneyldrm/exercises-dataset',DATA_REV),'guide':('bryllim/workout-guide',GUIDE_REV)}
EQUIP={'barbell':'杠铃','dumbbell':'哑铃','cable':'绳索','body weight':'自重','bodyweight':'自重','band':'弹力带','leverage machine':'固定器械','machine':'固定器械','smith machine':'史密斯机','kettlebell':'壶铃','ez barbell':'曲杆杠铃','weighted':'额外负重','stability ball':'健身球','bosu ball':'波速球','roller':'滚轮','medicine ball':'药球','rope':'绳','wheel roller':'腹肌轮'}
MUSCLES={'pectorals':'胸大肌','chest':'胸大肌','biceps':'肱二头肌','triceps':'肱三头肌','delts':'三角肌','shoulders':'三角肌','lats':'背阔肌','upper back':'上背肌群','traps':'斜方肌','glutes':'臀大肌','quads':'股四头肌','quadriceps':'股四头肌','hamstrings':'腘绳肌','calves':'小腿肌群','abs':'腹肌','forearms':'前臂肌群','spine':'竖脊肌群','adductors':'髋内收肌群','abductors':'髋外展肌群','serratus anterior':'前锯肌','levator scapulae':'肩胛提肌','cardiovascular system':'全身循环'}
REGIONS={'chest':'胸部','upper arms':'手臂','lower arms':'前臂','shoulders':'肩部','back':'背部','upper legs':'腿部','lower legs':'小腿','waist':'核心','neck':'颈部','cardio':'全身'}
NAME_TERMS={'single leg':'单腿','one arm':'单臂','two arm':'双臂','close grip':'窄握','wide grip':'宽握',
 'bench press':'卧推','chest press':'推胸','shoulder press':'肩推','overhead press':'过顶推举','floor press':'地板推举',
 'front squat':'前蹲','split squat':'分腿蹲','deadlift':'硬拉','hip thrust':'臀推','glute bridge':'臀桥',
 'lateral raise':'侧平举','front raise':'前平举','reverse fly':'反向飞鸟','face pull':'面拉','fly':'飞鸟',
 'leg extension':'腿屈伸','leg curl':'腿弯举','calf raise':'提踵','hip abduction':'髋外展','hip adduction':'髋内收',
 'pull up':'引体向上','pull-up':'引体向上','chin up':'反握引体','chin-up':'反握引体','pulldown':'下拉','push up':'俯卧撑','push-up':'俯卧撑',
 'biceps curl':'二头弯举','triceps extension':'三头伸展','hammer curl':'锤式弯举','romanian':'罗马尼亚',
 'smith machine':'史密斯机','leverage machine':'固定器械','body weight':'自重','bodyweight':'自重',
 'stability ball':'健身球','exercise ball':'健身球','medicine ball':'药球','ez barbell':'曲杆杠铃',
 'barbell':'杠铃','dumbbell':'哑铃','kettlebell':'壶铃','cable':'绳索','band':'弹力带',
 'incline':'上斜','decline':'下斜','seated':'坐姿','standing':'站姿','lying':'卧姿','assisted':'辅助',
 'weighted':'额外负重','squat':'深蹲','lunge':'弓步','row':'划船','curl':'弯举','plank':'平板支撑','crunch':'卷腹','stretch':'拉伸',
 'sumo':'相扑式','goblet':'高脚杯','triceps':'肱三头肌','biceps':'肱二头肌','hip':'髋','knee':'膝','wrist':'腕','neck':'颈部'}


def display_name(name):
    value=name.lower()
    for term,translation in sorted(NAME_TERMS.items(),key=lambda p:-len(p[0])):
        value=re.sub(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',translation,value)
    return value if re.search('[\u4e00-\u9fff]',value) else name
LEGACY={
 'bench':('barbell bench press','bench-press'),'deadlift':('barbell deadlift','deadlift'),
 'incline_barbell_bench':('barbell incline bench press','incline-bench-press'),
 'dumbbell_bench':('dumbbell bench press','dumbbell-bench-press'),
 'incline_dumbbell_bench':('dumbbell incline bench press',None),
 'barbell_row':('barbell bent over row',None),'dumbbell_row':('dumbbell one arm row',None),
 'lat_pulldown':('cable lat pulldown',None),'front_squat':('barbell front squat','front-squat'),
 'romanian_deadlift':('barbell romanian deadlift','romanian-deadlift'),
 'goblet_squat':('kettlebell goblet squat',None),'barbell_hip_thrust':('barbell hip thrust','hip-thrust'),
 'barbell_curl':('barbell curl','barbell-curl'),'dumbbell_curl':('dumbbell biceps curl',None),
 'hammer_curl':('dumbbell hammer curl','hammer-curl'),'standing_calf_raise':(None,None),
 'pushup':('push-up','push-up'),'pullup':('pull-up','pull-up'),
 'bodyweight_squat':('bodyweight squat','bodyweight-squat'),'plank':('front plank','plank'),
 'side_plank':('side plank','side-plank'),'glute_bridge':('glute bridge','glute-bridge'),
}

def norm(name,equipment=''):
    n=re.sub(r'[^a-z0-9 ]',' ',name.lower());n=' '.join(n.split())
    eq=equipment.lower()
    if eq in ('bodyweight','body weight'):eq=''
    if eq and eq in ('barbell','dumbbell','cable','kettlebell','band') and not n.startswith(eq+' '):n=eq+' '+n
    return n


def fetch(client,url,path):
    if path.exists():return path.read_bytes()
    for attempt in range(4):
        try:
            response=client.get(url);response.raise_for_status();data=response.content
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return data
        except (httpx.HTTPError,OSError):
            if attempt==3:raise
            time.sleep(1+attempt)


def build(*,media=True):
    cache=ROOT/'.tools/exercise-import/pinned';cache.mkdir(parents=True,exist_ok=True)
    out=ROOT/'backend/data/exercises_external.json'
    with httpx.Client(follow_redirects=True,timeout=60,limits=httpx.Limits(max_connections=10)) as client:
        source={};provenance={}
        for key,file in [('dataset','data/exercises.json'),('guide','packages/workout-guide/manifest.json')]:
            repo,rev=REPOS[key];url=f'https://raw.githubusercontent.com/{repo}/{rev}/{file}'
            data=fetch(client,url,cache/(key+'-'+rev+'.json'));source[key]=json.loads(data)
            provenance[key]={'repository':'https://github.com/'+repo,'revision':rev,'url':url,'sha256':hashlib.sha256(data).hexdigest()}
        assert len(source['dataset'])==1324 and len(source['guide'])==302
        legacy=json.loads((ROOT/'backend/data/exercises.json').read_text(encoding='utf8'))
        rows={};by_key={};upstream_map={};legacy_bindings={};base_names={e['id']:e['name'] for e in legacy}
        legacy_dataset={norm(v[0]):k for k,v in LEGACY.items() if v[0]}
        legacy_guide={v[1]:k for k,v in LEGACY.items() if v[1]}
        def base(key,name,equipment,target,secondary,region,kind):
            eq=equipment.lower();n=name.lower()
            bodyweight=eq in ('body weight','bodyweight','none','pull-up bar','bench','wall','chair','doorway','towel','box','assisted')
            mobility=any(w in n for w in ('stretch',' pose','forward fold','cat-cow'))
            cardio=eq in ('cardio','stationary bike','upper body ergometer','skierg machine','elliptical machine','stepmill machine') or n.startswith(('running','wind sprint','walking on','stationary bike'))
            training_type='mobility' if mobility else 'cardio' if cardio else 'bodyweight' if bodyweight else 'weighted'
            anatomy=classify(name,target,eq)
            weight_basis={
              'barbell':'含杆总重量；包括杆和两侧杠铃片，同一杆型与变式分别比较。',
              'ez barbell':'曲杆含杆总重量；曲杆型号与直杆分开比较。',
              'dumbbell':'记录单只哑铃重量；单侧与双侧执行分别记录。',
              'kettlebell':'记录单只壶铃重量；单壶与双壶执行分别记录。',
              'band':'记录弹力带型号、阻力等级和拉伸条件；不把阻力等级等同kg或计算RM。',
              'weighted':'记录额外负重；体重与附加重量分开，不与辅助器械混用。',
            }.get(eq,'按同一器械显示重量和设置记录；不同器械、阻力来源和变式不直接比较。')
            return {'id':key,'name':localized_name(key,base_names.get(key,display_name(name))),'original_name':name,'aliases':list(dict.fromkeys([name,EQUIP.get(eq,equipment)])),
              'category':region,'type':training_type,'equipment':EQUIP.get(eq,equipment),
              'difficulty':'intermediate','summary':'外部动作资料；关节动作分类为规则推断，教学内容待审核。',
              'weight_basis':('不记录额外负重；加重或辅助变式需分开建立记录' if bodyweight else
                weight_basis),
              'view':'暂未支持该外部条目的实时动作纠错；演示仅作姿势参考。',
              'realtime_supported':False,'rm_supported':False,'source_kind':'external_catalog',
              'source_label':'外部开放数据与练伴分类规则；未经过逐项专业审核','review_status':'imported_unreviewed',
              'movement_pattern':anatomy['joint_action_categories'][0],**anatomy,
              'primary_muscles':[MUSCLES.get(target.lower(),target)],
              'secondary_muscles':[MUSCLES.get(t.lower(),t) for t in secondary], 'body_regions':[region],
              'content_version':'external-catalog-20261024-v1','upstream_refs':[],
              'technique':{'execution':[],'cautions':['出现疼痛或无法控制负重时停止本组。','演示和开放教学文案不作为动作评分阈值。'],
                'common_errors':[],'sources':[],'review_status':'draft_not_validated','book_full_text_verified':False},
              'media_status':'no_licensed_matching_demo'}
        for item in source['dataset']:
            key=legacy_dataset.get(norm(item['name'])) or 'ed_'+item['id']
            region=REGIONS.get(item['body_part'],'全身')
            row=base(key,item['name'],item['equipment'],item['target'],item.get('secondary_muscles',[]),region,'dataset')
            steps=item.get('instruction_steps',{}).get('zh') or [item['instructions']['zh']]
            row['technique']['execution']=steps[:15]
            row['technique']['sources']=[{'title':'Exercises Dataset 开放教学文案（待审核）','kind':'external_unreviewed','url':provenance['dataset']['url']}]
            row['upstream_refs']=[{'provider':'exercises-dataset','id':item['id'],'name':item['name'],'revision':DATA_REV,'license':'MIT (non-media only)'}]
            # Do not retain Gym visual URLs as usable assets.
            row['media_status']='gymvisual_not_imported_requires_own_license'
            rows[key]=row;by_key[norm(item['name'],item['equipment'])]=key;upstream_map['dataset:'+item['id']]=key
        for item in source['guide']:
            key=legacy_guide.get(item['slug']) or by_key.get(norm(item['name'],item['equipment'])) or 'wg_'+item['slug'].replace('-','_')
            if key not in rows:
                target=item['primaryMuscle'];region={'Chest':'胸部','Back':'背部','Shoulders':'肩部','Biceps':'手臂','Triceps':'手臂','Quadriceps':'腿部','Hamstrings':'腿部','Glutes':'臀部','Calves':'小腿','Core':'核心','Abs':'核心','Full Body':'全身','Forearms':'前臂'}.get(target,'全身')
                rows[key]=base(key,item['name'],item['equipment'],target,item['secondaryMuscles'],region,'guide')
            row=rows[key];row['upstream_refs'].append({'provider':'workout-guide','id':item['id'],'name':item['name'],'revision':GUIDE_REV,'license':'CC BY-SA 4.0 (artwork)'})
            row['demo']={'url':'/assets/exercise-demos/external/'+item['slug']+'.gif',
              'poster_url':'/assets/exercise-demos/external/'+item['slug']+'.png','aspect_ratio':1.0,
              'label':'三帧姿势示意 · 非连续录像，不用于动作评分',
              'attribution':'Everkinetic (https://github.com/everkinetic/data); Bryl Lim (https://bryllim.com). CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). 练伴改为白底深色线稿，三帧合成为循环GIF。',
              'license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/',
              'source_url':f'https://github.com/bryllim/workout-guide/tree/{GUIDE_REV}/packages/workout-guide/assets/'+item['slug'],
              'upstream_attribution':item['attribution'],'changes':'Source alpha masks recolored dark on white, then three poses sequenced 1-2-3-2 as GIF; no pose interpolation.'}
            row['media_status']='licensed_three_frame_demo';upstream_map['guide:'+item['id']]=key
        for key,row in rows.items():
            region_map={'shoulder':'肩部','elbow':'手臂','forearm':'前臂','wrist':'前臂','finger':'手部',
                'hip':'臀部','knee':'腿部','ankle':'小腿','trunk':'核心','neck':'颈部','scapular':'背部'}
            row['body_regions']=list(dict.fromkeys([*row['body_regions'],*[region_map[k.split('_')[0]]
                for k in row['joint_action_ids'] if k.split('_')[0] in region_map]]))
            if key in base_names:legacy_bindings[key]=row
        # Store a single immutable generated seed, leaving legacy identity and authored references intact.
        out.write_text(json.dumps({'version':'external-catalog-20261024-v1','sources':provenance,'upstream_counts':{'dataset':1324,'guide':302},
            'source_record_map':upstream_map,'legacy_bindings':legacy_bindings,
            'items':[r for k,r in rows.items() if k not in base_names]},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        license_dir=ROOT/'backend/assets/exercise-demos/external';license_dir.mkdir(parents=True,exist_ok=True)
        for key,path,target in [('dataset','LICENSE','DATA-LICENSE.txt'),('dataset','NOTICE.md','DATA-MEDIA-NOTICE.md'),('guide','LICENSE','CODE-LICENSE.txt'),('guide','LICENSE-ASSETS','LICENSE-ASSETS.txt'),('guide','ATTRIBUTION.md','ATTRIBUTION.md')]:
            repo,rev=REPOS[key];data=fetch(client,f'https://raw.githubusercontent.com/{repo}/{rev}/{path}',cache/(key+'-'+target))
            (license_dir/target).write_bytes(data)
        if media:
            def render(item):
                destination=license_dir/(item['slug']+'.gif');poster=license_dir/(item['slug']+'.png')
                frames=[];hashes=[]
                for frame in item['frames']:
                    path=frame['path'].replace('.svg','.png')
                    raw=fetch(client,f'https://raw.githubusercontent.com/bryllim/workout-guide/{GUIDE_REV}/packages/workout-guide/'+path,cache/'frames'/item['slug']/(str(frame['index'])+'.png'))
                    im=Image.open(io.BytesIO(raw)).convert('RGBA');assert im.size==(512,512)
                    canvas=Image.new('RGB',im.size,'white')
                    canvas.paste(Image.new('RGB',im.size,'#243448'),mask=im.getchannel('A'))
                    frames.append(canvas)
                    hashes.append(hashlib.sha256(raw).hexdigest())
                frames[0].save(poster,optimize=True)
                seq=[frames[0],frames[1],frames[2],frames[1]]
                seq[0].save(destination,save_all=True,append_images=seq[1:],duration=[600,450,600,450],loop=0,optimize=False)
                return {'slug':item['slug'],'source_png_sha256':hashes,'gif_sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
            media_report=list(concurrent.futures.ThreadPoolExecutor(8).map(render,source['guide']))
            (license_dir/'PROVENANCE.json').write_text(json.dumps({'revision':GUIDE_REV,'assets':media_report},indent=2)+'\n',encoding='utf8')
        summary={'source_records':len(upstream_map),'new_entries':len(rows)-len(legacy_bindings),'legacy_bindings':len(legacy_bindings),
            'total_entries':len(rows)-len(legacy_bindings)+len(legacy),'demos':len(list(license_dir.glob('*.gif'))),
            'classification_methods':dict(Counter(r['classification']['method'] for r in rows.values())),
            'needs_review':[{'id':r['id'],'name':r['original_name'],'groups':r['joint_action_categories']} for r in rows.values() if r['classification']['status']=='needs_review']}
        (ROOT/'.tools/exercise-import/report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({k:v for k,v in summary.items() if k!='needs_review'},ensure_ascii=True),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--skip-media',action='store_true');args=parser.parse_args();build(media=not args.skip_media)
