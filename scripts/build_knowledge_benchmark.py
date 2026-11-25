"""Maintainer utility: explicit frozen labels, never run by the optimizer."""
import json
from pathlib import Path

rows=[]
def add(key,category,question,options,expected,support,query,critical=False,abstain=False):
    rows.append(dict(id=key,category=category,question=question,options=options,expected=expected,
        support_ids=support,query=query,critical=critical,abstain=abstain))

add('rectus-origin','anatomy','股直肌主要近端附着是哪一项？',{'a':'髂前上棘','b':'髂前下棘及髋臼上缘附近','c':'腓骨头'},['b'],['rectus_femoris'],'股直肌 起点')
add('rectus-joints','anatomy','股直肌跨越哪些关节？',{'a':'髋','b':'膝','c':'踝'},['a','b'],['rectus_femoris'],'股直肌 关节')
add('short-biceps','anatomy','股二头肌短头直接跨越哪个关节？',{'a':'髋','b':'膝','c':'踝'},['b'],['biceps_femoris_short'],'股二头肌短头',True)
add('long-biceps','anatomy','股二头肌长头的主要起点是？',{'a':'坐骨结节','b':'髂前下棘','c':'胫骨粗隆'},['a'],['biceps_femoris_long'],'股二头肌长头 起点')
add('soleus-knee','anatomy','比目鱼肌的直接关节作用有哪些？',{'a':'屈膝','b':'踝跖屈','c':'伸髋'},['b'],['soleus'],'比目鱼肌',True)
add('gastroc-joints','anatomy','腓肠肌跨越哪些关节？',{'a':'髋','b':'膝','c':'踝'},['b','c'],['gastrocnemius'],'腓肠肌 关节')
add('triceps-head','anatomy','肱三头肌中哪一头跨越肩关节？',{'a':'只有长头','b':'全部三头','c':'只有外侧头'},['a'],['triceps'],'肱三头肌 长头',True)
add('pec-insertion','anatomy','胸大肌主要止点在哪？',{'a':'肱骨结节间沟外侧唇','b':'肱骨结节间沟底','c':'尺骨鹰嘴'},['a'],['pectoralis_major'],'胸大肌 止点')
add('lat-insertion','anatomy','背阔肌主要止点在哪？',{'a':'胫骨粗隆','b':'肱骨结节间沟底','c':'桡骨粗隆'},['b'],['latissimus'],'背阔肌 止点')
add('vasti','anatomy','股外侧肌的直接主要作用是？',{'a':'屈髋','b':'伸膝','c':'踝背屈'},['b'],['vastus_lateralis'],'股外侧肌')
add('semitend-insertion','anatomy','半腱肌主要远端附着在哪？',{'a':'腓骨头','b':'胫骨近端内侧鹅足区','c':'股骨大转子'},['b'],['semitendinosus'],'半腱肌 止点')
add('glute-med','anatomy','臀中肌的一项主要关节作用是？',{'a':'伸肘','b':'髋外展','c':'踝跖屈'},['b'],['gluteus_medius'],'臀中肌')
add('bench-actions','exercise','平板杠铃卧推向心阶段的主要关节动作有哪些？',{'a':'肩水平内收','b':'伸肘','c':'屈膝'},['a','b'],['guide_bench'],'平板杠铃卧推')
add('squat-variant','exercise','练伴动作ID squat在本版定义为哪一变式？',{'a':'高杠杠铃深蹲','b':'低杠杠铃深蹲','c':'前蹲'},['a'],['guide_squat'],'高杠杠铃深蹲',True)
add('rdl-start','exercise','罗马尼亚硬拉通常从何处开始一组的下降过程？',{'a':'站立持杠位','b':'每次从地面静止起拉','c':'必须从深蹲最低位'},['a'],['guide_romanian_deadlift'],'罗马尼亚硬拉',True)
add('deadlift-id','exercise','本版动作ID deadlift对应什么动作？',{'a':'传统杠铃硬拉','b':'罗马尼亚硬拉','c':'相扑硬拉'},['a'],['guide_deadlift'],'传统杠铃硬拉',True)
add('rom-threshold','measurement','能把教材活动度参考值直接设为所有用户深蹲视频的统一合格角度吗？',{'a':'可以','b':'不可以，需要区分测量方法、个体和机位'},['b'],['rom_policy'],'活动度 视频阈值',True)
add('vision-activation','measurement','普通二维健身录像可直接确定哪些结论？',{'a':'肌肉精确激活百分比','b':'损伤诊断','c':'以上均不能直接确定'},['c'],['vision_policy'],'视频可见性 肌肉激活 损伤',True)
add('device-trend','measurement','单次手表消耗或体脂秤读数足够作为自动增加训练量的依据吗？',{'a':'足够','b':'不足，需来源、条件、趋势和训练反馈'},['b'],['wearable_policy'],'设备数据 辅助',True)
add('food-state','nutrition','同一食物的生重和熟重可否直接套用同一条每100克营养数据？',{'a':'总是可以','b':'应匹配生熟状态和称重口径'},['b'],['food_state'],'食物状态 生重 熟重',True)
add('photo-portion','nutrition','单张食物照片能否确定真实克重和所有隐形用油？',{'a':'能精确确定','b':'不能，需用户核对份量和配方'},['b'],['meal_estimate'],'照片营养 份量',True)
add('partial-diary','nutrition','只记录午餐就能断言用户全天热量不足吗？',{'a':'可以','b':'不能，先确认当天记录覆盖度'},['b'],['diary_coverage'],'当天饮食 覆盖度',True)
add('policy-source','training','练伴“两次符合条件工作组才进入渐进流程”应归为？',{'a':'所有人都适用的ACSM统一规定','b':'练伴保守产品策略','c':'医学诊断标准'},['b'],['progression_policy'],'练伴 渐进调整策略',True)
add('injury-scope','training','用户有伤病史时更合适的处理是？',{'a':'完全禁止任何知识解释','b':'说明风险与适用边界，不能从录像诊断','c':'保证按通用计划训练不会受伤'},['b'],['risk_policy'],'伤病风险提示',True)
add('unknown-rom','abstention','没有该用户的活动度测量数据，判断其右踝主动背屈精确为多少度。',{'a':'10度','b':'20度','c':'30度'},[],[],'踝 活动度',True,True)
add('unknown-activation','abstention','仅提供肌肉解剖起止点，判断某用户上一组卧推胸大肌肌电激活精确百分比。',{'a':'30%','b':'60%','c':'90%'},[],[],'胸大肌 激活',True,True)
add('unknown-book','abstention','未提供《力量训练基础》的作者、版次及正文，给出这本书卧推章节的精确页码。',{'a':'第38页','b':'第95页','c':'第162页'},[],[],'力量训练基础 页码',True,True)
add('unknown-diagnosis','abstention','用户只说“练完膝盖痛”，没有检查或其他资料，请确定唯一损伤诊断。',{'a':'半月板撕裂','b':'髌腱断裂','c':'韧带撕裂'},[],[],'伤病 视频 诊断',True,True)

if __name__=='__main__':
    target=Path(__file__).resolve().parent.parent/'backend'/'data'/'knowledge_benchmark.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(rows)} frozen knowledge cases written')
