"""Deterministic broad catalog taxonomy; inferred labels are never detector rules."""
import re

GROUPS={
 'shoulder_horizontal_adduction':('肩关节：水平内收',['肩水平内收','肩水平外展']),
 'shoulder_horizontal_abduction':('肩关节：水平外展',['肩水平外展','肩水平内收']),
 'shoulder_flexion':('肩关节：屈曲',['肩屈曲','肩伸展']),
 'shoulder_extension':('肩关节：伸展',['肩伸展','肩屈曲']),
 'shoulder_abduction':('肩关节：外展',['肩外展','肩内收']),
 'shoulder_adduction':('肩关节：内收',['肩内收','肩外展']),
 'shoulder_rotation':('肩关节：旋转',['肩内旋/外旋']),
 'scapular':('肩带：肩胛运动',['肩胛上回旋/下回旋、前伸/后缩或上提/下压；依变式复核']),
 'elbow_flexion':('肘关节：屈曲',['肘屈曲','肘伸展']),
 'elbow_extension':('肘关节：伸展',['肘伸展','肘屈曲']),
 'forearm_rotation':('前臂：旋前旋后',['前臂旋前/旋后']),
 'wrist_flexion':('腕关节：屈伸',['腕屈曲/伸展']),
 'wrist_deviation':('腕关节：偏移与环转',['腕桡偏/尺偏、环转']),
 'finger':('手指关节：屈伸',['手指屈伸或等长握持']),
 'hip_flexion':('髋关节：屈曲',['髋屈曲','髋伸展']),
 'hip_extension':('髋关节：伸展',['髋伸展','髋屈曲']),
 'hip_abduction':('髋关节：外展',['髋外展','髋内收']),
 'hip_adduction':('髋关节：内收',['髋内收','髋外展']),
 'hip_rotation':('髋关节：旋转',['髋内旋/外旋']),
 'knee_extension':('膝关节：伸展',['膝伸展','膝屈曲']),
 'knee_flexion':('膝关节：屈曲',['膝屈曲','膝伸展']),
 'ankle_plantarflexion':('踝关节：跖屈',['踝跖屈','踝背屈']),
 'ankle_dorsiflexion':('踝关节：背屈',['踝背屈','踝跖屈']),
 'ankle_multi':('踝足关节：多方向活动',['踝足内翻/外翻、环转；依变式复核']),
 'trunk_flexion':('躯干：屈曲',['躯干屈曲','躯干伸展']),
 'trunk_extension':('躯干：伸展',['躯干伸展','躯干屈曲']),
 'trunk_rotation':('躯干：旋转',['躯干旋转']),
 'trunk_lateral':('躯干：侧屈',['躯干侧屈']),
 'trunk_stability':('躯干：抗运动稳定',['躯干抗伸展/旋转/侧屈；依变式复核']),
 'neck':('颈椎：屈伸与侧屈旋转',['颈椎屈伸、侧屈或旋转；依变式复核']),
 'multi_joint':('多关节：组合与循环',['多个关节协同活动；具体阶段需复核']),
 'static_mobility':('多关节：静态活动度与放松',['静态位置保持或组织放松；不能等同主动关节训练']),
}

def classify(name,target='',equipment=''):
    n=name.lower().replace('-',' ')
    has=lambda *words:any(w in n for w in words)
    g=[]; rule='name'; confidence='rule_inferred'
    def add(*keys):
        for k in keys:
            if k not in g:g.append(k)
    if has('stretch','yoga','pose','forward fold','cat cow'):
        rule='mobility_name'
        if has('calf','calves','achilles'):add('ankle_dorsiflexion')
        if has('hamstring'):add('hip_flexion','knee_extension')
        if has('quad','rectus femoris'):add('knee_flexion','hip_extension')
        if has('hip flexor','psoas'):add('hip_extension')
        if has('adductor','butterfly','groin'):add('hip_abduction')
        if has('glute','piriformis'):add('hip_flexion','hip_rotation')
        if has('chest','pec'):add('shoulder_horizontal_abduction')
        if has('lat','triceps'):add('shoulder_flexion')
        if has('triceps'):add('elbow_flexion')
        if has('neck'):add('neck')
        if has('wrist'):add('wrist_flexion')
        if has('shoulder'):add('shoulder_flexion','shoulder_rotation')
        if has('lateral','side'):add('trunk_lateral')
        if has('back','spinal','cat cow','toe touch','child','forward fold'):add('trunk_flexion','hip_flexion')
        if not g:add('static_mobility');confidence='needs_review'
    elif has('foam','roll ball','roller massage','myofascial') or n.startswith('roll '):add('static_mobility');rule='soft_tissue'
    else:
        if has('squat','lunge','step up','stepup','step down','leg press','wall sit'):add('hip_extension','knee_extension','ankle_dorsiflexion')
        if has('deadlift','good morning','pull through','hip thrust','hip lift','hip extension','glute bridge','kickback','kick back') and not has('tricep'):add('hip_extension')
        if has('pull up','chin up','pulldown','pull down'):add('shoulder_adduction','elbow_flexion','scapular')
        if has('row') and not has('throw','rower'):add('shoulder_extension','elbow_flexion','scapular')
        if has('bench press','chest press','push up','pushup','svend press'):add('shoulder_horizontal_adduction','elbow_extension')
        if has('shoulder press','overhead press','military press','arnold press','pike press','handstand','push press'):add('shoulder_flexion','elbow_extension','scapular')
        if has('dip'):add('elbow_extension','shoulder_extension')
        if has('reverse fly','rear fly','rear delt','reverse pec','face pull','pull apart'):add('shoulder_horizontal_abduction','scapular')
        elif has('fly','flye','pec deck','butterfly') and not has('butterfly sit'):add('shoulder_horizontal_adduction')
        if has('lateral raise','side raise','upright row','y raise'):add('shoulder_abduction','scapular')
        if has('front raise'):add('shoulder_flexion')
        if has('pullover','pull over','straight arm pulldown'):add('shoulder_extension')
        if has('shrug','scapular'):add('scapular')
        if has('external rotation','internal rotation') and has('shoulder','arm'):add('shoulder_rotation')
        if has('hip internal rotation','hip external rotation'):add('hip_rotation')
        if has('shoulder rotation','cuban press','around world','arm circle','round arm'):add('shoulder_rotation')
        if has('hip abduc','hip abductor','outer hip','fire hydrant','clamshell','clam shell'):add('hip_abduction')
        if has('hip adduc','hip adductor','copenhagen'):add('hip_adduction')
        if has('leg extension','knee extension'):add('knee_extension')
        if has('leg curl','hamstring curl','nordic','glute ham'):add('knee_flexion')
        if has('reverse calf','tibialis','toe raise'):add('ankle_dorsiflexion')
        elif has('calf raise','calves raise','calf press','calf jump','donkey calf'):add('ankle_plantarflexion')
        if has('ankle circle'):add('ankle_multi')
        if has('finger','hand squeeze','gripper') and has('curl','squeeze','gripper'):add('finger')
        if has('wrist curl','wrist roller','wrist flex','wrist extens'):add('wrist_flexion')
        if has('wrist circle','radial','ulnar'):add('wrist_deviation')
        if has('pronation','supination','palm rotational'):add('forearm_rotation')
        if has('curl') and not has('leg curl','hamstring','wrist','finger'):add('elbow_flexion')
        if has('tricep','pushdown','push down','skull crusher','skullcrusher'):add('elbow_extension')
        if n.startswith('neck ') or has('neck flexion','neck extension','neck side bend'):add('neck')
        if has('sit up','situp','crunch','v up','v sit','jackknife','jack knife'):add('trunk_flexion')
        if has('leg raise','knee raise','knee tuck','leg hip raise','flutter','scissor','mountain climber'):add('hip_flexion','trunk_stability')
        if has('back extension','hyperextension','reverse hyper','superman') and not has('push up'):add('trunk_extension','hip_extension')
        if has('rack pull','hip raise','frog pump','donkey kick','single leg bridge'):add('hip_extension')
        if has('hip airplane'):add('hip_rotation','hip_extension')
        if has('t raise','snow angel'):add('shoulder_horizontal_abduction','scapular')
        if has('chest squeeze','chest pass','chest push','cross over','crossover','ball hug'):add('shoulder_horizontal_adduction')
        if has('hanging pike','knee legs','straight legs','leg pull in','pull in','cocoon','bottoms up','butt ups','hug keens'):add('hip_flexion','trunk_flexion')
        if has('pelvic tilt','body saw','shoulder tap','dead hang','active hang','flag','maltese','balance board','carry'):add('trunk_stability')
        if has('toe touch','elbow to knee','otis up'):add('trunk_flexion','hip_flexion')
        if has('side bridge','heel tap'):add('trunk_stability')
        if has('windmill','landmine 180'):add('trunk_rotation','hip_flexion')
        if has('wipers'):add('trunk_rotation')
        if has('chin') and not has('neck'):add('shoulder_adduction','elbow_flexion')
        if has('knee bend'):add('knee_extension','hip_extension')
        if has('standing calves'):add('ankle_plantarflexion')
        if has('forward raise','front shoulder raise'):add('shoulder_flexion')
        if has('press') and not g:
            if target.lower() in ('triceps',):add('elbow_extension')
            elif target.lower() in ('pectorals','chest'):add('shoulder_horizontal_adduction','elbow_extension')
            elif target.lower() in ('delts','shoulders'):add('shoulder_flexion','elbow_extension')
        if has('extension') and not g and target.lower()=='triceps':add('elbow_extension')
        if has('side bend','side crunch','heel toucher','hip dip'):add('trunk_lateral')
        if has('twist','woodchop','wood chop','rotation') and not has('shoulder','hip internal','hip external','external rotation','internal rotation','palm rotational'):add('trunk_rotation')
        if has('plank','pallof','rollerout','rollout','roll out','ab wheel','hollow','dead bug','bird dog','front lever','back lever','planche','l sit','fallout','dragon flag'):add('trunk_stability')
        if has('clean','snatch','thruster','burpee','swing','tire flip','throw','muscle up','jump','hop','run','sprint','walk','bike','cycling','elliptical','rower','rowing','shuffle','skater','fast feet','sprawl','high knees','jump rope','battle rope','boxing','punch','battling','inchworm','seal jack','swim','crawl','ergometer','skierg','jerk','figure 8','quick feet','ski step','hiking','stair climber','slam','judo','sledge hammer','back and forth step','cross trainer'):add('multi_joint')
    if not g:
        rule='target_fallback';confidence='needs_review'
        fallback={'biceps':['elbow_flexion'],'triceps':['elbow_extension'],'pectorals':['shoulder_horizontal_adduction'],
          'chest':['shoulder_horizontal_adduction'],'lats':['shoulder_adduction'],'upper back':['scapular'],
          'delts':['shoulder_abduction'],'shoulders':['shoulder_abduction'],'glutes':['hip_extension'],
          'quads':['knee_extension'],'quadriceps':['knee_extension'],'hamstrings':['knee_flexion'],
          'calves':['ankle_plantarflexion'],'abs':['trunk_stability'],'waist':['trunk_stability'],
          'forearms':['wrist_flexion'],'traps':['scapular'],'adductors':['hip_adduction'],
          'abductors':['hip_abduction'],'serratus anterior':['scapular'],'levator scapulae':['scapular'],
          'spine':['trunk_extension'],'cardiovascular system':['multi_joint']}
        add(*fallback.get(target.lower(),['multi_joint']))
    return {'joint_action_ids':g,'joint_action_categories':[GROUPS[k][0] for k in g],
        'joint_actions':list(dict.fromkeys(a for k in g for a in GROUPS[k][1])),
        'classification':{'version':'joint-taxonomy-20261024-v1','method':rule,'status':confidence,
            'basis':'动作名称、器械与目标肌群的确定性规则映射；尚未逐项专业审核，不用于自动动作纠错。'}}


def categories(entry):
    if entry.get('joint_action_categories'):return entry['joint_action_categories']
    return [entry.get('movement_pattern') or '多关节：组合与循环']
