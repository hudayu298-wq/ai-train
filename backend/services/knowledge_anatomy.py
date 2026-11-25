"""Source-checked anatomy expansion, with editorial exercise roles kept explicit.

Facts are original Chinese summaries; no atlas images or publisher tables are bundled.
This module does not constitute independent professional review.
"""

BASE = 'https://medicine.uams.edu/neuroscience/education/medical-school-courses/human-structure-module/anatomy-tables/muscle-tables/'


def install_anatomy(sources, nodes):
    def source(key, title, url, section, edition='在线教学表；2026-10-22核对'):
        sources.append(dict(id=key, title=title, url=url, edition=edition, section=section,
            accessed_on='2026-10-22', content_use='paraphrased_facts',
            publisher='UAMS' if key.startswith('uams-') else 'OpenStax' if key.startswith('openstax-') else 'Sports Physical Therapy Section',
            evidence_type='original_study' if key=='konor-2012' else 'textbook',
            licensing_note=('原创事实概要；不复制正文或图表。OpenStax当前网页标注CC BY-NC-SA及AI/商用许可限制；来源链接不是商业图谱授权。'
                if key.startswith('openstax-') else '仅用原创中文概述事实；未复制原表、图谱或连续正文。来源链接不是转载授权，未声称已获专业审核。')))
    source('uams-back', 'UAMS 背部肌肉解剖表', BASE+'muscles-of-the-back-region/', '按英文肌肉名定位')
    source('uams-abdomen', 'UAMS 腹部肌肉解剖表', BASE+'muscles-of-the-abdominal-region/', '按英文肌肉名定位')
    for key, section, slug in [('pectoral','8.1','the-pectoral-girdle'), ('upper-bones','8.2','bones-of-the-upper-limb'),
            ('pelvis','8.3','the-pelvic-girdle-and-pelvis'), ('lower-bones','8.4','bones-of-the-lower-limb')]:
        source('openstax-'+key, 'OpenStax Anatomy and Physiology 2e：'+section,
            'https://openstax.org/books/anatomy-and-physiology-2e/pages/'+section.replace('.','-')+'-'+slug, section, '2e')
    source('konor-2012', 'Konor et al. Reliability of Three Measures of Ankle Dorsiflexion Range of Motion',
        'https://pmc.ncbi.nlm.nih.gov/articles/PMC3362988/', 'Methods—Procedures；Table 3；Discussion', 'Int J Sports Phys Ther. 2012;7(3):279–287; PMID 22666642')
    source('openstax-spine', 'OpenStax Anatomy and Physiology 2e：脊柱',
        'https://openstax.org/books/anatomy-and-physiology-2e/pages/7-3-the-vertebral-column', '7.3：Intervertebral Discs / Articulations', '2e')

    def add(key, kind, title, summary, facts, refs, aliases=(), exercises=(), limitations=()):
        nodes.append(dict(id=key, kind=kind, title=title, summary=summary, facts=facts, aliases=list(aliases),
            population=['一般成人；解剖学习与训练说明'], exercise_ids=list(exercises),
            references=[dict(source_id=s, locator=loc) for s,loc in refs], evidence_status='source_checked',
            limitations=list(limitations) or ['主要结构的简化概述，未经过独立专业审核；不用于损伤诊断、肌电或受力推断。']))

    action_defs = [
        ('shoulder_internal_rotation','shoulder','肩内旋','transverse','上臂绕自身长轴向内旋转','shoulder_external_rotation'),
        ('shoulder_external_rotation','shoulder','肩外旋','transverse','上臂绕自身长轴向外旋转','shoulder_internal_rotation'),
        ('scapular_retraction','scapulothoracic','肩胛后缩','transverse','肩胛骨沿胸廓向后内方移动','scapular_protraction'),
        ('scapular_protraction','scapulothoracic','肩胛前伸','transverse','肩胛骨沿胸廓向前外方移动','scapular_retraction'),
        ('scapular_elevation','scapulothoracic','肩胛上提','frontal','肩胛骨向头侧移动','scapular_depression'),
        ('scapular_depression','scapulothoracic','肩胛下沉','frontal','肩胛骨向足侧移动','scapular_elevation'),
        ('scapular_upward_rotation','scapulothoracic','肩胛上回旋','frontal','肩胛骨转动使关节盂更多朝上','scapular_downward_rotation'),
        ('scapular_downward_rotation','scapulothoracic','肩胛下回旋','frontal','肩胛骨转动使关节盂更多朝下','scapular_upward_rotation'),
        ('trunk_flexion','vertebral_column','躯干屈曲','sagittal','脊柱相关节段向前屈曲','trunk_extension'),
        ('trunk_extension','vertebral_column','躯干伸展','sagittal','脊柱相关节段向后伸展','trunk_flexion'),
        ('trunk_lateral_flexion','vertebral_column','躯干侧屈','frontal','躯干向一侧弯曲',None),
        ('hip_internal_rotation','hip','髋内旋','transverse','股骨相对骨盆绕长轴向内旋转','hip_external_rotation'),
        ('hip_external_rotation','hip','髋外旋','transverse','股骨相对骨盆绕长轴向外旋转','hip_internal_rotation'),
    ]
    for key,joint,title,plane,definition,opposite in action_defs:
        facts=dict(joint_id=joint, plane=plane, definition=definition)
        if opposite:
            facts['opposite_id']=opposite
        add(key,'joint_action',title,definition+'；解剖动作名称不直接表示某一训练阶段的肌肉收缩方式。',facts,
            [('openstax-movement','9.5：Rotation / Elevation and Depression / Protraction and Retraction / Lateral Flexion')],aliases=[key.replace('_',' ')])
    for key,title,jtype,ref in [
            ('scapulothoracic','肩胛胸廓功能性联系','功能性接触与滑动；并非独立的真性滑膜关节','openstax-pectoral'),
            ('vertebral_column','脊柱关节复合体','椎体间纤维软骨联合与椎间关节等组成的多节段复合体','openstax-spine')]:
        add(key,'joint',title,title+'用于组织动作与稳定关系，不代表单个可由二维视频精确测量的关节。',
            dict(joint_type=jtype,region='肩带' if key=='scapulothoracic' else '躯干',
                action_ids=[r[0] for r in action_defs if r[1]==key],
                rom_reference='未建立该结构的个体角度常模；相机外观不能替代规范测量。',use_as_video_threshold=False),
            [(ref,'8.1：Scapula / Clavicle' if key=='scapulothoracic' else '7.3：Intervertebral Discs；articular processes')],aliases=[key])
    # Existing joint nodes must declare newly added actions as well.
    for node in nodes:
        if node['kind']=='joint':
            node['facts']['action_ids']=list(dict.fromkeys([*node['facts']['action_ids'],*[r[0] for r in action_defs if r[1]==node['id']]]))
            if node['id']=='ankle':
                node['facts']['rom_reference']='提供wblt-knee-wall-cm-v1主动负重墙距手动测量，单位cm；不是常模角度或摄像头合格阈值。'

    landmarks = [
        ('scapular_spine','肩胛冈','肩胛骨','肩带','肩胛骨后面的横向骨嵴','openstax-pectoral','8.1 Scapula：spine'),
        ('acromion','肩峰','肩胛骨','肩带','肩胛冈向外延续的突起，与锁骨相接','openstax-pectoral','8.1 Scapula：acromion'),
        ('coracoid','喙突','肩胛骨','肩带','肩胛骨前上方的突起，是多条肌腱的附着区域','openstax-pectoral','8.1 Scapula：coracoid process'),
        ('greater_tubercle','肱骨大结节','肱骨','上臂','近端肱骨外侧的骨性隆起','openstax-upper-bones','8.2 Humerus：greater tubercle'),
        ('lesser_tubercle','肱骨小结节','肱骨','上臂','近端肱骨前侧的较小隆起','openstax-upper-bones','8.2 Humerus：lesser tubercle'),
        ('iliac_crest','髂嵴','髋骨髂骨部','骨盆','髂骨上缘的弧形骨嵴','openstax-pelvis','8.3 Ilium：iliac crest'),
        ('asis','髂前上棘','髋骨髂骨部','骨盆','髂嵴前端的骨性突起','openstax-pelvis','8.3 Ilium：anterior superior iliac spine'),
        ('ischial_tuberosity','坐骨结节','髋骨坐骨部','骨盆','坐骨后下方承担坐位支撑的粗隆','openstax-pelvis','8.3 Ischium：ischial tuberosity'),
        ('greater_trochanter','股骨大转子','股骨','髋部','股骨近端外侧的隆起','openstax-lower-bones','8.4 Femur：greater trochanter'),
        ('adductor_tubercle','收肌结节','股骨','膝内侧','股骨内侧髁上方附近的附着标志','openstax-lower-bones','8.4 Femur：adductor tubercle'),
        ('tibial_tuberosity','胫骨粗隆','胫骨','小腿','胫骨近端前面的粗隆，为髌韧带附着点','openstax-lower-bones','8.4 Tibia：tibial tuberosity'),
        ('calcaneus','跟骨','跟骨','后足','后足的跗骨；后部为跟腱附着区域','openstax-lower-bones','8.4 Tarsal Bones：calcaneus'),
    ]
    for key,title,bone,region,location,ref,loc in landmarks:
        add(key,'bone_landmark',title,location+'；用于理解肌肉附着与测量位置。',
            dict(bone=bone,region=region,location=location,
                clinical_boundary='不从穿衣录像自动定位此骨点；可触及性和表面外观存在个体差异，不能据此诊断。'),[(ref,loc)],aliases=[key.replace('_',' ')])

    def muscle(key,title,origin,insertion,joints,actions,ref,english,parts=(),landmarks=(),exercises=()):
        add(key,'muscle',title,title+'的主要附着与解剖作用；训练中的稳定或动力角色需结合阶段和外部负荷。',
            dict(origin=[origin],insertion=[insertion],joint_ids=joints,action_ids=actions,
                attachment_scope='主要附着概述；未穷尽束向、个体变异或全部功能。',parts=list(parts),landmark_ids=list(landmarks)),
            [(ref,english)],aliases=[english],exercises=exercises)
    for row in [
        ('supraspinatus','冈上肌','肩胛骨冈上窝','肱骨大结节上部',['shoulder_abduction'],'supraspinatus','greater_tubercle'),
        ('infraspinatus','冈下肌','肩胛骨冈下窝','肱骨大结节中部',['shoulder_external_rotation'],'infraspinatus','greater_tubercle'),
        ('teres_minor','小圆肌','肩胛骨外侧缘上部','肱骨大结节下部',['shoulder_external_rotation'],'teres minor','greater_tubercle'),
        ('subscapularis','肩胛下肌','肩胛骨肩胛下窝','肱骨小结节',['shoulder_internal_rotation','shoulder_extension'],'subscapularis','lesser_tubercle'),
    ]:
        key,title,origin,insertion,actions,english,landmark=row
        muscle(key,title,origin,insertion,['shoulder'],actions,'uams-upper',english,
            ['肩袖四肌之一；稳定盂肱关节不等于可从训练录像测出其激活或损伤。'],[landmark],['bench'])
    muscle('trapezius','斜方肌','枕骨项部、项韧带及C7–T12棘突','锁骨外侧段、肩峰及肩胛冈',['scapulothoracic'],
        ['scapular_elevation','scapular_depression','scapular_retraction','scapular_upward_rotation'],'uams-back','trapezius',
        ['上、中、下部纤维作用不同；不能假定每部分均完成全部列出的动作。'],['acromion','scapular_spine'],['bench','squat','deadlift'])
    for key,title,origin,insertion,english in [
            ('rhomboid_major','大菱形肌','T2–T5棘突','肩胛冈以下的肩胛骨内侧缘','rhomboideus major'),
            ('rhomboid_minor','小菱形肌','项韧带下部及C7–T1棘突','肩胛冈根部的肩胛骨内侧缘','rhomboideus minor')]:
        muscle(key,title,origin,insertion,['scapulothoracic'],['scapular_retraction','scapular_elevation','scapular_downward_rotation'],
            'uams-back',english,landmarks=['scapular_spine'],exercises=['bench','deadlift'])
    muscle('serratus_anterior','前锯肌','第1–8或9肋外侧面','肩胛骨内侧缘的胸廓面',['scapulothoracic'],
        ['scapular_protraction','scapular_upward_rotation'],'uams-back','serratus anterior',
        ['下部纤维参与肩胛上回旋；卧推中角色随肩胛策略及阶段而变。'],exercises=['bench'])
    muscle('erector_spinae','竖脊肌群','髂嵴、骶骨及脊柱后方附着等','肋角、上方椎骨及颅骨后部等',['vertebral_column'],
        ['trunk_extension','trunk_lateral_flexion'],'uams-back','erector spinae',
        ['包括髂肋肌、最长肌和棘肌等多段肌束；负重下可抵抗躯干屈曲，不意味着硬拉应主动大幅后仰。'],['iliac_crest'],['squat','deadlift','romanian_deadlift'])
    muscle('multifidus','多裂肌','骶骨及椎骨横突等','起点上方约2–4节段的棘突',['vertebral_column'],
        ['trunk_extension','trunk_lateral_flexion'],'uams-back','multifidus',
        ['多节段肌束；稳定作用不能用二维录像单独定量。'],exercises=['squat','deadlift'])
    for key,title,origin,insertion,english,actions in [
        ('rectus_abdominis','腹直肌','耻骨及耻骨联合','剑突和第5–7肋软骨','rectus abdominis',['trunk_flexion']),
        ('external_oblique','腹外斜肌','下位8根肋骨','腹白线、耻骨及髂嵴等','external abdominal oblique',['trunk_flexion','trunk_lateral_flexion']),
        ('internal_oblique','腹内斜肌','胸腰筋膜、髂嵴及腹股沟韧带等','下位肋骨、腹白线及耻骨嵴等','internal abdominal oblique',['trunk_flexion','trunk_lateral_flexion']),
        ('transversus_abdominis','腹横肌','下位6肋、胸腰筋膜、髂嵴及腹股沟韧带等','腹白线及耻骨附近','transversus abdominis',[]),
    ]:
        muscle(key,title,origin,insertion,['vertebral_column'] if actions else [],actions,'uams-abdomen',english,
            ['腹壁协同支持躯干与腹部；腹横肌的压缩腹部作用不伪装为某一关节运动。'],exercises=['bench','squat','deadlift'])
    muscle('adductor_magnus','大收肌','耻骨坐骨支与坐骨结节','股骨粗线及收肌结节',['hip'],
        ['hip_adduction','hip_flexion','hip_extension','hip_internal_rotation'],'uams-lower','adductor magnus',
        ['内收部与坐骨髁部作用不同；伸髋主要对应坐骨髁部，不将全部肌束归为同一种作用。'],['ischial_tuberosity','adductor_tubercle'],['squat','deadlift'])
    for key,title,origin,insertion,english in [
        ('adductor_longus','长收肌','耻骨上支附近','股骨粗线','adductor longus'),
        ('adductor_brevis','短收肌','耻骨下支','股骨耻骨肌线及粗线','adductor brevis')]:
        muscle(key,title,origin,insertion,['hip'],['hip_adduction','hip_flexion','hip_internal_rotation'],'uams-lower',english,exercises=['squat','deadlift'])
    muscle('gracilis','股薄肌','耻骨联合及耻骨下支','胫骨近端内侧鹅足区',['hip','knee'],
        ['hip_adduction','hip_flexion','knee_flexion'],'uams-lower','gracilis',
        ['跨髋膝两个关节；不同于不跨膝的长收肌、短收肌和大收肌。'],exercises=['squat'])
    muscle('gluteus_minimus','臀小肌','髂骨外侧面前下方','股骨大转子',['hip'],
        ['hip_abduction','hip_internal_rotation'],'uams-lower','gluteus minimus',landmarks=['greater_trochanter'],exercises=['squat'])
    muscle('iliopsoas','髂腰肌','髂窝及腰椎椎体、横突等','股骨小转子',['hip','vertebral_column'],
        ['hip_flexion','trunk_flexion','trunk_lateral_flexion'],'uams-lower','iliopsoas',
        ['髂肌与腰大肌的合称；跨腰椎的描述对应腰大肌，不能套用于全部髂肌纤维。'],exercises=['squat','deadlift'])

    # Phase notes are editorial applications, not findings of a lift-specific EMG trial.
    phase_notes = {
        'bench': ['准备与下降：设置保护，保持可重复肩胛和躯干支撑；胸大肌、三角肌与肱三头肌在外负荷下共同控制下降。',
            '推起：主要为肩水平内收和伸肘；肩袖及肩带肌协同稳定，不能由录像量化各肌贡献。',
            '结束：在可控范围回到支撑位置；肩胛策略因变式和个体而异，无统一强制角度。'],
        'squat': ['下降：髋膝屈曲与踝背屈增加，髋膝伸肌群控制外负荷；躯干肌协同支撑。',
            '转折与起身：髋膝共同伸展，大收肌坐骨髁部可参与伸髋；作用随髋位、站距与负荷变化。',
            '站立：回到可控直立；髋内收肌参与不代表应主动让膝内扣，也不能从膝轨迹诊断某肌无力。'],
        'deadlift': ['准备与离地：传统地面起拉，髋膝伸肌共同工作；背阔肌与躯干肌协同控制杠铃和躯干位置。',
            '过膝至站立：继续伸髋，按可控技术结束；竖脊肌抵抗屈曲不等于要求腰椎主动大幅伸展。',
            '下放：可控髋铰链与屈膝配合；不把罗马尼亚硬拉起始姿势套用于地面起拉。'],
        'romanian_deadlift': ['下降：从站立持杠开始，以髋屈曲为主，髋伸肌在外负荷下控制动作；膝保持可控弯曲。',
            '返回：以伸髋回到站立；躯干协同稳定，不凭肌肉拉伸感推断组织损伤。'],
    }
    for node in nodes:
        if node['kind']!='exercise_guide':
            continue
        eid=node['facts']['exercise_id']
        node['facts']['phase_notes']=phase_notes.get(eid,[])
        if eid=='bench':
            node['facts']['joint_ids']+=['scapulothoracic','vertebral_column']
            node['facts']['stabilizer_muscle_ids']+=['supraspinatus','infraspinatus','teres_minor','subscapularis','trapezius','rhomboid_major','serratus_anterior','rectus_abdominis']
            node['facts']['landmark_ids']=['scapular_spine','acromion','greater_tubercle']
        else:
            node['facts']['joint_ids']+=['vertebral_column']
            node['facts']['stabilizer_muscle_ids']+=['erector_spinae','multifidus','rectus_abdominis','external_oblique','internal_oblique','transversus_abdominis']
            node['facts']['landmark_ids']=['iliac_crest','ischial_tuberosity','greater_trochanter','tibial_tuberosity']
            if eid in ('squat','deadlift'):
                node['facts']['assisting_muscle_ids']+=['adductor_magnus']
        node['references'].append(dict(source_id='uams-back',locator='肌肉行：erector spinae / trapezius；动作阶段角色为练伴编辑说明，非肌电结论'))

    add('wblt_protocol','measurement_principle','负重膝触墙测量协议',
        '用尺记录大脚趾至墙的距离cm；它是特定负重姿势下的距离记录，不等于摄像机测角或单个关节的诊断。',
        dict(principle='同侧、同协议、同条件重复记录后观察个人趋势。',
            recommendations=['膝沿第二趾方向触墙且脚跟贴地；每侧先练习再正式测3次，记录均值。',
                '出现疼痛立即停止。研究的重复性结果来自特定样本和训练过的测量者，不证明本App自测有效性。',
                '不把距离统一换算成角度；不把10cm当作人人合格线或自动调整训练负荷。'],governing_service='mobility.py / wblt-knee-wall-cm-v1'),
        [('konor-2012','Methods—Procedures；Discussion：distance-to-wall与角度的换算限制'),
         ('lianban-policy','产品适配：疼痛停止与复测提示；尚无App自测验证')],exercises=['squat','deadlift'],
        limitations=['原研究20名健康成人，单次内重复测量；不能外推至伤病诊断、康复处方、无人监督自测的可靠性或长期最小可检测变化。'])
