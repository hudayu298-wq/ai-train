"""Author structured movement references; GIFs are original schematic diagrams, not recordings."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
items = json.loads((ROOT / 'backend/data/exercises.json').read_text(encoding='utf-8'))
SS = 'https://startingstrength.com/article/lifts/critical-technique-elements-part-4-the-bench-press'
DL = 'https://startingstrength.com/article/deadlift-mechanics-the-obvious-can-be-obscure'
ACE = 'https://www.acefitness.org/resources/everyone/exercise-library/'
# Mode, joint actions, primary/secondary muscles, regions, preparation, execution, visual cue.
patterns = {
 'horizontal_push': ('水平推', ['肩水平内收', '肘伸展'], ['胸大肌'], ['肱三头肌', '三角肌前束'], ['胸部','手臂'],
    '建立稳定支撑，握持器械，确认左右起始位置。', '控制下降后推回起始位置，避免用反弹完成动作。', '注意左右手与肘的运动是否明显不一致。'),
 'vertical_push': ('垂直推', ['肩屈曲/外展', '肘伸展'], ['三角肌前束/中束'], ['肱三头肌'], ['肩部','手臂'],
    '确认头顶空间与支撑位置，器械从肩附近开始。', '向上推举后控制回落；躯干避免明显后仰。', '观察推举时躯干是否出现明显后仰。'),
 'horizontal_pull': ('水平拉', ['肩伸展/水平外展', '肘屈曲'], ['背阔肌','菱形肌'], ['斜方肌中束','肱二头肌'], ['背部','手臂'],
    '稳固坐姿、胸托或支撑手，确认把手能自由运动。', '把手向躯干方向拉近，再控制回到起始位置。', '观察拉动前后躯干是否明显摆动。'),
 'vertical_pull': ('垂直拉', ['肩内收/伸展', '肘屈曲'], ['背阔肌'], ['肱二头肌','斜方肌'], ['背部','手臂'],
    '建立稳定支撑，确认把手或单杠握持位置。', '通过拉动把手或身体完成上下运动，再控制返回。', '观察躯干是否出现明显摇摆。'),
 'squat': ('蹲：髋膝屈伸', ['髋屈伸', '膝屈伸', '踝背屈/跖屈'], ['股四头肌','臀大肌'], ['内收肌','躯干稳定肌群'], ['腿部','臀部'],
    '建立完整足部支撑，确认站距和支架保护位置。', '髋膝共同弯曲后伸展站起，保持动作可控。', '观察足部支撑是否明显改变或脚跟明显抬起。'),
 'hinge': ('髋铰链：髋屈伸', ['髋屈伸', '膝轻度屈伸'], ['臀大肌','腘绳肌'], ['竖脊肌等躯干稳定肌群'], ['臀部','腿部','背部'],
    '确认握持和足部支撑；负重位置与身体保持接近。', '髋部向后移动再伸展髋站起，不用额外后仰完成顶部。', '观察负重是否明显远离身体。'),
 'hip_extension': ('髋伸展', ['髋屈伸'], ['臀大肌'], ['腘绳肌','躯干稳定肌群'], ['臀部','腿部'],
    '确认上背或地面支撑和双脚位置；杠铃臀推先做好髋部垫衬。', '抬高髋部后控制下降，避免把腰部后仰当作抬髋。', '观察抬髋顶部躯干与大腿的位置关系。'),
 'split_squat': ('分腿：髋膝屈伸', ['前腿髋膝屈伸', '后腿髋膝屈伸'], ['股四头肌','臀大肌'], ['内收肌','躯干稳定肌群'], ['腿部','臀部'],
    '前后脚分开，保留左右支撑宽度，确认平衡。', '控制下降，再通过前腿为主的支撑站起。', '观察下降或起身时是否明显失去平衡。'),
 'shoulder_adduction': ('肩水平内收', ['肩水平内收/外展', '肘保持轻屈'], ['胸大肌'], ['三角肌前束'], ['胸部','肩部'],
    '确认滑轮高度，保持肘部轻屈并建立稳定站姿。', '双臂向身前合拢，再控制张开；不追求疼痛范围。', '观察动作是否变成明显的屈伸肘推举。'),
 'shoulder_abduction': ('肩外展', ['肩外展/内收', '肘轻屈保持'], ['三角肌中束'], ['冈上肌','斜方肌'], ['肩部'],
    '站姿稳定，哑铃置于身体两侧，肘部自然轻屈。', '双臂向两侧抬起再控制下降，避免躯干借力摇摆。', '观察抬臂时躯干是否明显摆动。'),
 'face_pull': ('肩水平外展与外旋', ['肩水平外展', '肩外旋', '肘屈曲'], ['三角肌后束'], ['斜方肌中束','菱形肌','肩袖肌群'], ['肩部','背部'],
    '绳索位置接近上身高度，站姿稳定。', '拉近绳索并分开双手，再控制返回。', '观察拉动时躯干是否明显后仰。'),
 'elbow_flexion': ('肘屈曲', ['肘屈伸'], ['肱二头肌','肱肌'], ['肱桡肌'], ['手臂'],
    '握持器械，上臂保持相对稳定，手腕自然对齐前臂。', '弯曲肘关节抬起负重，再控制下降。', '观察弯举是否伴随明显躯干摆动或上臂前后移动。'),
 'elbow_extension': ('肘伸展', ['肘伸屈'], ['肱三头肌'], ['肩部稳定肌群'], ['手臂'],
    '绳索握持稳定，上臂靠近身体并保持位置。', '伸肘向下推，再控制回到肘屈曲位置。', '观察上臂是否明显随把手前后移动。'),
 'knee_extension': ('膝伸展', ['膝伸屈'], ['股四头肌'], [], ['腿部'],
    '调节座椅和滚垫，按器械说明对齐膝关节轴。', '伸膝抬起滚垫再控制返回；不使用冲击或反弹。', '观察动作时髋部是否明显离开座椅。'),
 'knee_flexion': ('膝屈曲', ['膝屈伸'], ['腘绳肌'], ['腓肠肌'], ['腿部'],
    '调节座椅与滚垫，按器械说明对齐膝关节轴。', '屈膝带动滚垫，再控制返回。', '观察髋部和躯干是否明显移动来带动负重。'),
 'ankle_extension': ('踝跖屈', ['踝跖屈/背屈'], ['腓肠肌','比目鱼肌'], [], ['小腿'],
    '建立前脚掌支撑并抓稳支撑点。', '抬高脚跟后控制下降，保持平衡。', '观察是否用明显屈伸膝代替脚跟上下运动。'),
 'anti_extension': ('核心抗伸展', ['躯干抗伸展', '肩髋稳定'], ['腹直肌','腹横肌'], ['臀肌','肩带稳定肌群'], ['核心'],
    '前臂和脚部稳定支撑，调整到可保持的姿势。', '维持躯干位置，不以腰部下沉维持更长时间。', '观察腰髋位置是否明显下沉。'),
 'anti_lateral': ('核心抗侧屈', ['躯干抗侧屈', '肩髋稳定'], ['腹斜肌'], ['臀中肌','肩带稳定肌群'], ['核心','臀部'],
    '侧卧，前臂或手与下肢建立稳定支撑。', '抬起骨盆并保持侧向躯干位置，控制结束动作。', '观察骨盆是否明显向地面下降。'),
}
groups = {
 'horizontal_push':['bench','incline_barbell_bench','dumbbell_bench','incline_dumbbell_bench','chest_press_machine','pushup'],
 'vertical_push':['barbell_overhead_press','seated_dumbbell_press'],
 'horizontal_pull':['barbell_row','dumbbell_row','seated_cable_row','chest_supported_row'],
 'vertical_pull':['lat_pulldown','pullup'],
 'squat':['squat','front_squat','low_bar_squat','goblet_squat','leg_press','bodyweight_squat'],
 'hinge':['deadlift','romanian_deadlift'],
 'hip_extension':['barbell_hip_thrust','glute_bridge'],
 'split_squat':['dumbbell_split_squat','lunge'],
 'shoulder_adduction':['cable_fly'], 'shoulder_abduction':['dumbbell_lateral_raise'],
 'face_pull':['cable_face_pull'], 'elbow_flexion':['barbell_curl','dumbbell_curl','hammer_curl'],
 'elbow_extension':['triceps_pushdown'], 'knee_extension':['leg_extension'], 'knee_flexion':['leg_curl'],
 'ankle_extension':['standing_calf_raise'], 'anti_extension':['plank'], 'anti_lateral':['side_plank'],
}
variants = {
 'bench':'杠铃握持采用拇指环握；臀部保持凳面接触。轨迹不要求完全竖直。',
 'incline_barbell_bench':'上斜凳与平凳变式分开记录；不要把平板卧推的触胸位置机械套用。',
 'dumbbell_bench':'分别控制两只哑铃，训练记录按单只重量；结束时控制哑铃放置。',
 'incline_dumbbell_bench':'固定上斜凳角度，两侧哑铃分别控制，记录单只重量。',
 'chest_press_machine':'先调整座椅和把手位置，以器械说明与舒适活动范围为准。',
 'cable_fly':'绳索交叉不是推胸；不要把肘伸展作为主要动作。',
 'barbell_row':'俯身角度保持可控；不要通过明显起身完成每次拉动。',
 'dumbbell_row':'支撑手和双脚形成稳定支撑，避免明显转动躯干。',
 'seated_cable_row':'允许自然肩胛运动，但不要用大幅度前后摇摆代替拉动。',
 'chest_supported_row':'保持胸部与胸托接触，座椅和胸托按器械说明调整。',
 'lat_pulldown':'调整腿垫，不把颈后下拉作为默认示范，握距因器械而异。',
 'barbell_overhead_press':'杠铃经过头部时留出空间；顶部不要用明显腰部后仰代替肩部运动。',
 'seated_dumbbell_press':'确认凳背与双脚支撑，两只哑铃分别控制。',
 'dumbbell_lateral_raise':'肘部保持轻屈，使用能控制的重量；不靠抛掷把哑铃带起。',
 'cable_face_pull':'手与肘的细节需正面或斜前方观察，单侧面不可判定完整外旋。',
 'barbell_curl':'保持相同握法记录RM，避免用明显髋部摆动带起杠铃。',
 'dumbbell_curl':'每侧单独控制，上臂相对稳定；单只重量不与杠铃总重混用。',
 'hammer_curl':'使用掌心相对的中立握法，不把它与旋后握弯举混为同一变式。',
 'triceps_pushdown':'上臂保持相对固定，主要由肘关节伸展带动把手。',
 'squat':'高杠位置在上背；不要套用低杠的固定躯干倾角。膝超过脚尖不自动视为错误。',
 'low_bar_squat':'低杠与高杠分开建档；前倾可因杠位和身体比例不同，不自动判错。',
 'front_squat':'建立前架位，保持器械支撑；不把前蹲与后蹲的躯干姿势混用。',
 'goblet_squat':'负重在身前，先确保能稳定握持；不要根据侧面截图判断完整左右对称。',
 'leg_press':'保持骨盆与靠背接触，不追求使骨盆明显离垫的深度；不同腿举机分别记录。',
 'leg_extension':'滚垫位置与器械转轴按设备说明调整；不通过甩动负重完成动作。',
 'leg_curl':'大腿压垫保持稳定，不通过大幅度髋部移动带动滚垫。',
 'deadlift':'从地面起拉；负重沿腿附近运动，顶部不需要额外后仰。',
 'romanian_deadlift':'从站姿开始，以髋后移控制下降，杠铃不必触地；与传统硬拉分开记录。',
 'barbell_hip_thrust':'保持上背稳定接触凳面，注意垫衬；髋伸展不等于腰部过度后仰。',
 'dumbbell_split_squat':'两腿保持前后错开，在同侧重复；负重按单只哑铃口径记录。',
 'standing_calf_raise':'保持前脚掌支撑，避免弹跳和明显膝屈伸代偿。',
 'pushup':'手和脚支撑，头、躯干和髋部作为整体控制；自重模块目前只作资料浏览。',
 'pullup':'握持单杠稳定，控制上下运动；不把摆荡引体与严格引体混为同一变式。',
 'bodyweight_squat':'自重屈伸髋膝，完整足部支撑；不因没有杠铃就改变动作分类。',
 'lunge':'示范为原地分腿动作，不等同于行走弓步；先确认平衡。',
 'glute_bridge':'上背保持地面支撑，与凳面支撑的臀推区分。',
 'plank':'是静态抗伸展示范；动画只表现建立姿势，不代表需要反复起落或计次。',
 'side_plank':'是静态抗侧屈示范；动画只表现建立姿势，不代表需要反复抬髋计次。',
}
result = {}
for item in items:
    key = item['id']; mode = next(k for k,v in groups.items() if key in v)
    label, joints, primary, secondary, regions, setup, execution, cue = patterns[mode]
    sources = [{'title':'项目整理的关节动作与教学草稿', 'kind':'project_draft', 'url':None}]
    if key == 'bench': sources.append({'title':'Starting Strength官方配套文章：卧推', 'kind':'companion_article', 'url':SS})
    if key == 'deadlift': sources.append({'title':'Starting Strength官方配套文章：传统硬拉', 'kind':'companion_article', 'url':DL})
    if key in ['seated_cable_row','chest_supported_row']:
        sources.append({'title':'ACE动作库：坐姿划船（器械变式参考）','kind':'reference_article','url':'https://www.acefitness.org/resources/everyone/exercise-library/168/seated-row/'})
    result[key] = {'movement_pattern': label, 'joint_actions': joints, 'primary_muscles': primary,
        'secondary_muscles': secondary, 'body_regions': regions, 'content_version':'movement-1.0',
        'technique': {'setup':[setup], 'execution':[execution], 'key_points':[variants[key]],
          'cautions':['出现疼痛或无法控制负重时停止本组并复核。','示意角度不等于通用合格角度；个人比例和器械会影响动作范围。'],
          'common_errors':[{'id':f'{key}_visible_control', 'description':cue,
              'guidance':execution, 'required_view':'front' if mode=='horizontal_push' and key!='pushup' else 'any', 'minimum_frames':2,
              'observability':'partial', 'validated':False}],
          'not_observable':['疼痛或受伤风险','真实肌肉激活程度','腹压','细微肩胛运动与完整三维脊柱曲度'],
          'sources':sources, 'review_status':'draft_not_validated', 'book_full_text_verified':False},
        'demo':{'url':f'/assets/exercise-demos/{key}.gif', 'kind':'original_schematic',
          'label':'关节动作示意 · 非真人标准动作', 'view':'front' if mode in ('shoulder_adduction','shoulder_abduction','face_pull') else 'side',
          'motion_profile':mode, 'validated':False}}
    if key=='deadlift':
        result[key]['joint_actions']=['髋屈伸','膝屈伸']
        result[key]['primary_muscles']=['臀大肌','股四头肌','腘绳肌']
    if key=='romanian_deadlift':
        result[key]['joint_actions']=['髋屈伸','膝保持轻屈（角度变化较小）']
    if key=='hammer_curl':
        result[key]['primary_muscles']=['肱肌','肱桡肌']
        result[key]['secondary_muscles']=['肱二头肌']
    if key.startswith('incline_'):
        result[key]['joint_actions']=['肩屈曲/水平内收','肘伸展']
book_rules = json.loads((ROOT/'docs/starting_strength_rules.json').read_text(encoding='utf-8'))['rules']
variant_ids = {'flat_barbell_bench':'bench', 'low_bar_barbell_squat':'low_bar_squat', 'conventional_barbell_deadlift':'deadlift'}
for rule in book_rules:
    key = variant_ids[rule['variant']]
    result[key]['technique']['common_errors'].append({'id':rule['id'], 'description':rule['point'],
        'guidance':rule['point'], 'required_view':'side','minimum_frames':2,
        'observability':'partial','validated':False,'usage':'reference_only',
        'requires':rule['requires'], 'limitation':rule['unavailable_reason']})
    result[key]['technique']['sources'].append({'title':'Starting Strength官方配套文章（书籍全文与页码未核验）',
        'kind':'companion_article','url':rule['source_url']})
(ROOT/'backend/data/exercise_content.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Built structured references for {len(result)} exercises, {len(patterns)} joint movement groups')
