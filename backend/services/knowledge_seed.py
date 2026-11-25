"""Small, paraphrased foundation; attachment descriptions are intentionally simplified.

This is a source-checked editorial seed, not a complete anatomy atlas or clinical
validation. Product decisions and exercise conventions are identified separately.
"""
try:
    from ..knowledge_models import Bundle
except ImportError:
    from knowledge_models import Bundle

VERSION = 'foundation-20261022-v2'
BASE = 'https://medicine.uams.edu/neuroscience/education/medical-school-courses/human-structure-module/anatomy-tables/muscle-tables/'


def seed():
    sources = []
    def source(key, title, url, section, edition='在线资料，2026-10-22核对', policy=False):
        sources.append(dict(id=key, title=title, url=url, edition=edition, section=section,
            accessed_on='2026-10-22', content_use='product_policy' if policy else 'paraphrased_facts',
            licensing_note='仅整理事实并用中文概述，未复制原表、插图或整段正文；来源链接供核对。'))
    source('uams-upper', 'UAMS 上肢肌肉解剖表', BASE+'muscles-of-the-upper-limb/', '按肌肉英文名定位')
    source('uams-lower', 'UAMS 下肢肌肉解剖表', BASE+'muscles-of-the-lower-limb/', '按肌肉英文名定位')
    source('openstax-movement', 'OpenStax Anatomy and Physiology 2e',
        'https://openstax.org/books/anatomy-and-physiology-2e/pages/9-5-types-of-body-movements', '9.5 Types of Body Movements', '2e')
    source('openstax-joints', 'OpenStax Anatomy and Physiology 2e：滑膜关节',
        'https://openstax.org/books/anatomy-and-physiology-2e/pages/9-6-anatomy-of-selected-synovial-joints', '9.6 Anatomy of Selected Synovial Joints', '2e')
    source('acsm-2026', 'ACSM 2026 抗阻训练立场更新说明', 'https://acsm.org/resistance-training-guidelines-update-2026/',
        'Consistency Over Complexity / Individualization')
    source('who-diet', 'WHO Healthy diet', 'https://www.who.int/en/news-room/fact-sheets/detail/healthy-diet',
        'Overview / Practical advice', '2026-01-26')
    source('usda-fdc', 'USDA FoodData Central 数据说明', 'https://fdc.nal.usda.gov/data-documentation/', 'Data types / Food descriptions')
    source('lianban-policy', '练伴产品约束与动作说明', 'https://github.com/hudayu298-wq/ai-train',
        'backend/exercise_content.py、backend/progression.py、backend/services/knowledge_seed.py', VERSION, True)
    nodes = []
    def item(key, kind, title, summary, facts, refs, aliases=(), exercise_ids=(), limitations=()):
        nodes.append(dict(id=key, kind=kind, title=title, aliases=list(aliases), summary=summary, facts=facts,
            references=[dict(source_id=s, locator=loc) for s, loc in refs], exercise_ids=list(exercise_ids),
            population=['一般成人；具体建议需结合个体画像'],
            limitations=list(limitations) or ['基础概述，未经过独立专业审核；不能替代个体评估。']))
    # Axis and movement labels describe anatomy, not camera-specific cutoffs.
    action_defs = [
        ('shoulder_flexion','shoulder','肩屈曲','sagittal','上臂向前抬起','shoulder_extension'),
        ('shoulder_extension','shoulder','肩伸展','sagittal','上臂向后移动','shoulder_flexion'),
        ('shoulder_horizontal_adduction','shoulder','肩水平内收','transverse','抬起的上臂向身体前方中线靠近','shoulder_horizontal_abduction'),
        ('shoulder_horizontal_abduction','shoulder','肩水平外展','transverse','抬起的上臂离开身体前方中线','shoulder_horizontal_adduction'),
        ('shoulder_abduction','shoulder','肩外展','frontal','上臂向身体侧方抬起','shoulder_adduction'),
        ('shoulder_adduction','shoulder','肩内收','frontal','上臂向躯干靠近','shoulder_abduction'),
        ('elbow_flexion','elbow','屈肘','sagittal','前臂与上臂夹角减小','elbow_extension'),
        ('elbow_extension','elbow','伸肘','sagittal','前臂与上臂夹角增大','elbow_flexion'),
        ('hip_flexion','hip','屈髋','sagittal','大腿与躯干前方靠近','hip_extension'),
        ('hip_extension','hip','伸髋','sagittal','由屈髋位向伸直方向移动','hip_flexion'),
        ('hip_abduction','hip','髋外展','frontal','大腿离开身体中线','hip_adduction'),
        ('hip_adduction','hip','髋内收','frontal','大腿向身体中线靠近','hip_abduction'),
        ('knee_flexion','knee','屈膝','sagittal','膝后方夹角减小','knee_extension'),
        ('knee_extension','knee','伸膝','sagittal','膝从弯曲向伸直移动','knee_flexion'),
        ('ankle_dorsiflexion','ankle','踝背屈','sagittal','足背向小腿前方靠近','ankle_plantarflexion'),
        ('ankle_plantarflexion','ankle','踝跖屈','sagittal','足尖朝远离小腿前方的方向移动','ankle_dorsiflexion'),
    ]
    for key,joint,title,plane,definition,opposite in action_defs:
        item(key,'joint_action',title,definition+'；负重动作中还需区分向心、离心和稳定作用。',
            dict(joint_id=joint, plane=plane, definition=definition, opposite_id=opposite),
            [('openstax-movement','9.5：'+title)], aliases=[key.replace('_',' ')])
    for key,title,jtype in [('shoulder','盂肱关节','球窝关节'),('elbow','肘关节','以屈伸为主的复合关节'),
            ('hip','髋关节','球窝关节'),('knee','膝关节','改良铰链关节'),('ankle','距小腿关节','以背屈跖屈为主的铰链关节')]:
        item(key,'joint',title,title+'的动作名称用于关联肌肉与训练动作，不给出统一合格角度。',
            dict(joint_type=jtype, action_ids=[a[0] for a in action_defs if a[1]==key],
                rom_reference='本库未建立个体活动度测量协议或常模；需要结合姿势、方法和个体测量。',use_as_video_threshold=False),
            [('openstax-joints','9.6：'+title),('openstax-movement','9.5：对应关节动作')], aliases=[key])
    def muscle(key,title,origin,insertion,joints,actions,english,upper=False,parts=(),aliases=()):
        item(key,'muscle',title,title+'：主要附着与作用的简化学习卡；不代表训练中该肌的激活程度。',
            dict(origin=origin,insertion=insertion,joint_ids=joints,action_ids=actions,
                attachment_scope='主要附着概述；未穷尽变异、纤维束及全部作用。',parts=list(parts)),
            [('uams-upper' if upper else 'uams-lower',english)],aliases=[english,*aliases],
            limitations=['解剖作用不等于单次动作中的肌电活动、受力比例或疼痛原因。'])
    muscle('pectoralis_major','胸大肌',['锁骨内侧段、胸骨及上部肋软骨等'],['肱骨结节间沟外侧唇'],['shoulder'],
        ['shoulder_horizontal_adduction','shoulder_adduction','shoulder_flexion'],'pectoralis major',True,parts=['锁骨部与胸肋部的作用随肩位变化。'])
    muscle('deltoid','三角肌',['锁骨外侧段、肩峰、肩胛冈'],['肱骨三角肌粗隆'],['shoulder'],
        ['shoulder_abduction','shoulder_flexion','shoulder_extension'],'deltoid',True,parts=['前束参与屈肩，中束参与外展，后束参与伸肩；并非每束都完成全部列出作用。'])
    muscle('triceps','肱三头肌',['长头起于肩胛骨盂下结节；另两头起于肱骨后面'],['尺骨鹰嘴'],['shoulder','elbow'],
        ['elbow_extension','shoulder_extension'],'triceps brachii',True,parts=['只有长头跨肩关节；不能把三头都当成双关节肌。'])
    muscle('latissimus','背阔肌',['下胸椎棘突、胸腰筋膜、髂嵴及下部肋骨等'],['肱骨结节间沟底'],['shoulder'],
        ['shoulder_extension','shoulder_adduction'],'latissimus dorsi',True)
    muscle('gluteus_maximus','臀大肌',['髂骨后部、骶尾骨及骶结节韧带等'],['髂胫束及股骨臀肌粗隆'],['hip'],['hip_extension'],'gluteus maximus')
    muscle('gluteus_medius','臀中肌',['髂骨外侧面'],['股骨大转子'],['hip'],['hip_abduction'],'gluteus medius')
    muscle('rectus_femoris','股直肌',['髂前下棘及髋臼上缘附近'],['经股四头肌腱至髌骨，再经髌韧带至胫骨粗隆'],
        ['hip','knee'],['hip_flexion','knee_extension'],'rectus femoris',aliases=['股四头肌'])
    for key,title,origin,english in [('vastus_lateralis','股外侧肌','股骨大转子及粗线外侧区域等','vastus lateralis'),
            ('vastus_medialis','股内侧肌','股骨粗线内侧等','vastus medialis'),('vastus_intermedius','股中间肌','股骨干前外侧面','vastus intermedius')]:
        muscle(key,title,[origin],['经股四头肌腱、髌骨和髌韧带至胫骨粗隆'],['knee'],['knee_extension'],english,aliases=['股四头肌'])
    muscle('biceps_femoris_long','股二头肌长头',['坐骨结节'],['腓骨头附近'],['hip','knee'],['hip_extension','knee_flexion'],
        'biceps femoris (long head)',aliases=['腘绳肌','股二头肌'])
    muscle('biceps_femoris_short','股二头肌短头',['股骨粗线及外侧髁上线区域'],['腓骨头附近'],['knee'],['knee_flexion'],
        'biceps femoris (short head)',parts=['不跨髋关节，不承担直接伸髋作用。'],aliases=['腘绳肌','股二头肌'])
    muscle('semitendinosus','半腱肌',['坐骨结节'],['胫骨近端内侧鹅足区'],['hip','knee'],['hip_extension','knee_flexion'],'semitendinosus',aliases=['腘绳肌'])
    muscle('semimembranosus','半膜肌',['坐骨结节'],['胫骨内侧髁后方'],['hip','knee'],['hip_extension','knee_flexion'],'semimembranosus',aliases=['腘绳肌'])
    muscle('gastrocnemius','腓肠肌',['股骨内外侧髁上方区域'],['经跟腱至跟骨'],['knee','ankle'],['knee_flexion','ankle_plantarflexion'],'gastrocnemius')
    muscle('soleus','比目鱼肌',['胫骨比目鱼肌线与腓骨近端等'],['经跟腱至跟骨'],['ankle'],['ankle_plantarflexion'],'soleus',parts=['不跨膝关节；不能把屈膝列为直接作用。'])
    def principle(key,kind,title,text,recs,service,source_id,locator):
        item(key,kind,title,text,dict(principle=text,recommendations=recs,governing_service=service),[(source_id,locator)])
    principle('individualization','training_principle','计划个体化','训练需匹配目标、训练经历、每周可用时间、器械与依从性。',
        ['先核对画像和力量基线；计划按可完成的每周安排设计。','ACSM该更新针对一般健康成人，不能直接当成伤病康复处方。'],'plan_validation','acsm-2026','Individualization / healthy adults')
    principle('consistency','training_principle','持续训练与恢复','长期规律和可坚持的训练安排是计划设计的基础。',
        ['结合训练完成度、主观费力与恢复反馈调整；没有记录不能假定训练已完成。'],'workout_memory','acsm-2026','Consistency Over Complexity')
    principle('progression_policy','training_principle','练伴渐进调整策略','加重或增加次数必须结合实际训练记录、负重口径、RPE与不适反馈。',
        ['两次不同训练日符合条件的工作组记录才允许进入当前渐进流程；这是练伴的保守产品策略。','热身组、辅助完成和不同器械口径不能混为进步依据；变化需向用户展示并提供修改与撤销入口。'],
        'progression.py','lianban-policy','backend/progression.py；不宣称这是ACSM规定的统一阈值')
    principle('risk_policy','training_principle','伤病风险提示','伤病信息用于提示风险和说明适用边界；仍可解释训练与进行有限评估。',
        ['不能从聊天或视频诊断损伤，也不能把疼痛自动归因于某块肌肉。','出现不适时暂停自动加重，建议根据症状寻求专业评估。'],
        'plan_validation / progression.py','lianban-policy','伤病风险、证据边界和计划确认约束')
    principle('rom_policy','measurement_principle','活动度与视频阈值','教材中的关节活动范围不等于每个人每个动作的统一合格角度。',
        ['需要说明测量方法、姿势与个体差异；本版没有常模角度表。','视频透视角度与遮挡会影响测量；未校准时不能给出临床活动度结论。'],
        'movement_analysis','lianban-policy','活动度测量边界')
    principle('vision_policy','measurement_principle','视频可见性边界','普通二维训练录像不能直接确定肌肉激活、脊柱负荷、内部关节力或损伤诊断。',
        ['仅对当前机位确实可见的轨迹、节奏和身体位置作描述。','无法观察时明确缺少证据，先调整机位再评价。'],'movement_analysis','lianban-policy','backend/exercise_content.py analysis_context')
    principle('wearable_policy','measurement_principle','设备数据是辅助信息','手表热量、体脂秤体脂与恢复分数含估计误差，需保留设备、方法与时间。',
        ['同设备同条件下看趋势；不根据单次读数直接增加训练或摄入。','用户未授权AI使用的健康数据不能进入提示词。'],'health_data.py','lianban-policy','健康数据授权和来源约束')
    principle('diet_quality','nutrition_principle','均衡与可持续饮食','饮食需要兼顾充足、均衡、适度和多样性，并适应个人条件。',
        ['结合饮食偏好、食物可得性与目标给建议；不把极端限制当成通用方案。'],'nutrition','who-diet','Overview：adequacy / balance / moderation / diversity')
    principle('food_state','nutrition_principle','食物状态与称重口径','同一种食物的生重、熟重和可食部不能直接混用；水分变化会改变每100克营养密度。',
        ['记录所用条目、克重、生熟状态及份量来源；按匹配条目的每100克数据计算。'],'nutrition_math','usda-fdc','Food descriptions / data types')
    principle('food_provenance','nutrition_principle','营养数值的来源','品牌标签、研究分析与汇总数据的来源不同，应保留条目标识与数据类型。',
        ['不能用模型的印象替换数据库数值；新建食物需要来源标注。'],'food_catalog','usda-fdc','Foundation / FNDDS / Branded Foods')
    principle('meal_estimate','nutrition_principle','照片营养是估算','单张食物照片不能确定真实克重、隐形用油和完整配方。',
        ['请用户确认食物和份量，再由数据库计算热量与三大营养。'],'meal_confirmation','lianban-policy','份量与正式记录确认')
    principle('diary_coverage','nutrition_principle','当天饮食覆盖度','仅有部分餐次时，累计摄入代表已记录部分，不能当成全天摄入结论。',
        ['先确认当天记录是否完整，再比较总量与需要量。'],'nutrition_diary','lianban-policy','当日饮食与完成状态')
    guides = [
        ('bench','平板杠铃卧推',['shoulder','elbow'],['shoulder_horizontal_adduction','elbow_extension'],['pectoralis_major'],['deltoid','triceps'],[],
            ['侧面约90°；全杠、双手、肘和胸部在画面内','斜前方约45°补充左右轨迹；避免支架干扰安全区'],
            ['设置保护杠或可靠保护者，先用可控重量','握距与触胸位置按个体和器械调整'],['向心阶段主要包含肩水平内收与伸肘；肩胛与躯干提供稳定。']),
        ('squat','高杠杠铃深蹲',['hip','knee','ankle'],['hip_extension','knee_extension','ankle_dorsiflexion'],
            ['gluteus_maximus','rectus_femoris','vastus_lateralis','vastus_medialis','vastus_intermedius'],[],['gluteus_medius'],
            ['侧面约90°：头、杠铃、髋、膝和脚完整入镜','斜前方约45°：补充膝脚方向与左右差异'],
            ['安全架与保护杠高度先调整','站距、足尖方向和深度按个体可控范围调整'],['下降包含屈髋、屈膝与踝背屈；起身包含伸髋、伸膝。']),
        ('deadlift','传统杠铃硬拉',['hip','knee'],['hip_extension','knee_extension'],['gluteus_maximus','vastus_lateralis','vastus_medialis','vastus_intermedius'],
            ['biceps_femoris_long','semitendinosus','semimembranosus'],['latissimus'],
            ['侧面约90°：全身、脚与杠铃完整入镜','斜前方约45°：补充握距和左右轨迹'],
            ['先核对杠铃总重与可控重量','杠铃靠近身体；地面起拉与站立结束要在画面内'],['从地面起拉时髋膝共同伸展；不能套用罗马尼亚硬拉的起始位置。']),
        ('romanian_deadlift','杠铃罗马尼亚硬拉',['hip','knee'],['hip_extension','hip_flexion'],['gluteus_maximus','biceps_femoris_long','semitendinosus','semimembranosus'],[],['latissimus'],
            ['侧面约90°：全身与杠铃入镜'],['从站立持杠开始，膝保持适度弯曲','按可控髋铰链幅度下降，不要求每次触地'],['主要通过髋屈伸完成；不能当成传统地面硬拉。']),
    ]
    for eid,title,joints,actions,primary,assist,stable,views,setup,execution in guides:
        item('guide_'+eid,'exercise_guide',title+'知识卡',title+'的变式、关节动作、训练部位与录像边界。',
            dict(exercise_id=eid,variant=title,joint_ids=joints,action_ids=actions,primary_muscle_ids=primary,
                assisting_muscle_ids=assist,stabilizer_muscle_ids=stable,
                principle_ids=['individualization','progression_policy','risk_policy','rom_policy','vision_policy'],
                load_basis='杠铃及两侧杠片总重 kg',camera_views=views,setup=setup,execution=execution,
                observable=['机位适合时可描述关节位置变化与杠铃轨迹','遮挡或画面不足时不作判断'],
                not_observable=['不能由录像确定肌肉激活比例、内部关节力或损伤诊断']),
            [('lianban-policy','backend/exercise_content.py：'+eid)],exercise_ids=[eid],aliases=[eid,title,title.replace('杠铃','')],
            limitations=['肌肉角色为训练说明，不是个体肌电或受力测量；动作细节尚未经过专业验证。'])
    from .knowledge_anatomy import install_anatomy
    install_anatomy(sources, nodes)
    # Independent extension point for source-linked nutrition / periodization rules.
    try:
        from .knowledge_rules import install_principles
    except ModuleNotFoundError as exc:
        if exc.name not in ('services.knowledge_rules', 'backend.services.knowledge_rules'):
            raise
    else:
        install_principles(sources, nodes)
    edge_names={'joint_ids':'crosses','action_ids':'produces','joint_id':'occurs_at','opposite_id':'opposite',
        'primary_muscle_ids':'primary','assisting_muscle_ids':'assists','stabilizer_muscle_ids':'stabilizes','principle_ids':'uses_principle', 'landmark_ids':'references_landmark'}
    edges=[]
    for node in nodes:
        for key,relation in edge_names.items():
            if node['kind']=='joint' and key=='action_ids':
                continue
            value=node['facts'].get(key,[])
            edges.extend(dict(source=node['id'],target=target,relation='uses_joint' if node['kind']=='exercise_guide' and key=='joint_ids' else relation) for target in ([value] if isinstance(value,str) else value))
    return Bundle.model_validate(dict(version=VERSION,name='练伴基础知识：三大项、解剖与饮食',sources=sources,items=nodes,relations=edges)).model_dump()
