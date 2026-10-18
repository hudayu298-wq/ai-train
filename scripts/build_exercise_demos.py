"""Render original 2D joint diagrams into animated GIFs. These are not validated form templates."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CONTENT = json.loads((ROOT/'backend/data/exercise_content.json').read_text(encoding='utf-8'))
ITEMS = json.loads((ROOT/'backend/data/exercises.json').read_text(encoding='utf-8'))
OUT = ROOT/'backend/assets/exercise-demos'
OUT.mkdir(parents=True, exist_ok=True)
FONT = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 22)
SMALL = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)
BODY, TARGET, WEIGHT = '#235449', '#d86a3b', '#406b9a'

def arm_point(anchor, angle, length):
    return anchor[0]+math.cos(angle)*length, anchor[1]+math.sin(angle)*length

def pose(key, mode, u):
    p = {'h':(350,107),'s':(350,150),'hip':(350,232),'e':(365,205),'w':(365,255),
         'k':(355,290),'a':(350,350),'k2':(330,290),'a2':(325,350)}
    if mode == 'squat' and key != 'leg_press':
        p['k']=arm_point((350,350),-math.pi/2+u*.62,60)
        p['hip']=arm_point(p['k'],-math.pi/2-u*1.63,60)
        lean={'front_squat':.3,'goblet_squat':.4,'low_bar_squat':.8}.get(key,.55)*u
        p['s']=arm_point(p['hip'],-math.pi/2+lean,82)
        p['h']=arm_point(p['s'],-math.pi/2+lean,42)
        p['k2']=(p['k'][0]-23,p['k'][1]);p['a2']=(325,350)
        p['e']=(p['s'][0]+25,p['s'][1]+25)
        p['w']=(p['s'][0]-12,p['s'][1]-5)
        if key=='low_bar_squat': p['w']=(p['s'][0]-20,p['s'][1]+12)
        if key in ('front_squat','goblet_squat'): p['w']=(p['s'][0]+35,p['s'][1]+6)
        if key=='bodyweight_squat': p['w']=(p['s'][0]+75,p['s'][1]+12)
    elif mode == 'hinge':
        v=1-u if key=='deadlift' else u
        p['hip']=(350-48*v,232+15*v)
        p['k']=(355+20*v,290+12*v if key=='deadlift' else 290)
        p['s']=arm_point(p['hip'],-math.pi/2+v*1.08,82)
        p['h']=arm_point(p['s'],-math.pi/2+v*1.08,40)
        p['e']=(p['s'][0]+5,p['s'][1]+46);p['w']=(p['s'][0]+5,p['s'][1]+98)
    elif mode=='horizontal_push' and key!='pushup':
        incline=key.startswith('incline')
        p.update(h=(225,190 if incline else 250),s=(280,210 if incline else 250),hip=(435,260),k=(475,305),a=(510,350),k2=(452,310),a2=(482,350))
        p['e']=(345-62*u,(270 if incline else 310)-125*u)
        p['w']=(342-60*u,(205 if incline else 244)-130*u)
        if key=='chest_press_machine':
            p.update(h=(260,127),s=(275,170),hip=(280,270),k=(375,275),a=(390,350),k2=(345,275),a2=(360,350))
            p['e']=(300+60*u,230-45*u);p['w']=(325+110*u,182)
    elif key=='pushup':
        p.update(s=(240,220+62*u),h=(196,215+62*u),hip=(390,260+35*u),k=(460,293+15*u),a=(550,330),k2=(465,300),a2=(550,338))
        p['e']=(240-38*u,276+23*u);p['w']=(240,330)
    elif mode=='vertical_push':
        p['e']=(405-45*u,178-76*u);p['w']=(413-54*u,140-57*u)
        if key=='seated_dumbbell_press': p.update(hip=(350,255),k=(430,262),a=(443,350),k2=(400,262),a2=(416,350))
    elif mode=='horizontal_pull':
        if key in ('seated_cable_row','chest_supported_row'):
            p.update(s=(290,174),h=(288,131),hip=(285,260),k=(380,280),a=(432,350),k2=(357,288),a2=(407,350))
            p['e']=(365-43*u,200+22*u);p['w']=(432-112*u,215+10*u)
        else:
            p.update(hip=(295,260),s=(367,205),h=(400,178))
            p['e']=(373-40*u,257-25*u);p['w']=(378-55*u,317-57*u)
    elif mode=='vertical_pull':
        if key=='pullup':
            p.update(s=(350,215-55*u),h=(350,175-55*u),hip=(350,300-55*u),k=(370,330-55*u),a=(392,350-55*u),k2=(344,335-55*u),a2=(362,353-55*u))
            p['e']=(405,170-30*u);p['w']=(405,100)
        else:
            p.update(s=(350,185),h=(350,145),hip=(350,270),k=(430,280),a=(448,350),k2=(405,283),a2=(422,350))
            p['e']=(410,140+75*u);p['w']=(419,91+87*u)
    elif mode in ('shoulder_adduction','shoulder_abduction','face_pull'):
        p.update(s=(350,150),h=(350,108),hip=(350,232),k=(325,290),a=(320,350),k2=(375,290),a2=(380,350))
        p['front']=True
        if mode=='shoulder_abduction':
            p['e']=(322-50*u,205-49*u);p['w']=(318-92*u,252-98*u)
        elif mode=='shoulder_adduction':
            p['e']=(285+42*u,175+18*u);p['w']=(235+107*u,182+32*u)
        else:
            p['e']=(280-10*u,210-37*u);p['w']=(334-46*u,225-83*u)
    elif mode in ('elbow_flexion','elbow_extension'):
        angle=(math.pi/2-u*2.65) if mode=='elbow_flexion' else (-.55+u*2.12)
        p['w']=arm_point(p['e'],angle,52)
    elif key=='leg_press':
        p.update(h=(195,148),s=(230,186),hip=(285,255),k=(348-25*u,224+37*u),a=(430-55*u,174+40*u),e=(240,233),w=(270,269),k2=(338-25*u,231+37*u),a2=(420-55*u,181+40*u))
    elif mode in ('knee_extension','knee_flexion'):
        p.update(h=(280,110),s=(290,152),hip=(300,250),k=(390,260),e=(290,205),w=(320,252))
        angle=(math.pi/2-u*1.38) if mode=='knee_extension' else (.2+u*1.82)
        p['a']=arm_point(p['k'],angle,70);p['k2']=(373,267);p['a2']=(p['a'][0]-17,p['a'][1]+7)
    elif mode=='hip_extension':
        ground=key=='glute_bridge';sy=309 if ground else 224
        p.update(h=(200,sy-15),s=(240,sy),hip=(350,sy+28-62*u),k=(430,270),a=(464,350),k2=(410,279),a2=(445,350),e=(255,sy+12),w=(310,sy+8-25*u))
    elif mode=='split_squat':
        p.update(h=(350,108+48*u),s=(350,150+48*u),hip=(350,232+48*u),k=(411,285+15*u),a=(442,350),k2=(299,294+38*u),a2=(265,350),e=(370,206+48*u),w=(375,263+48*u))
    elif mode=='ankle_extension':
        for name in p: p[name]=(p[name][0],p[name][1]-12*u)
    elif mode in ('anti_extension','anti_lateral'):
        p.update(s=(240,250),h=(198,229),hip=(390,315-48*u),k=(474,318-20*u),a=(560,335),e=(238,316),w=(177,316),k2=(478,326-20*u),a2=(560,342))
        if mode=='anti_lateral': p['w']=(244,316);p['e']=(239,283)
    return p

def render(item, i, n=36):
    key=item['id'];ref=CONTENT[key];mode=ref['demo']['motion_profile']
    u=(1-math.cos(2*math.pi*i/n))/2
    if mode.startswith('anti_'): u=min(1,u*4)
    p=pose(key,mode,u)
    im=Image.new('RGB',(720,420),'#f4f6ef');d=ImageDraw.Draw(im)
    d.text((24,16),item['name'],font=FONT,fill=BODY)
    d.text((24,48),ref['movement_pattern']+' · '+('建立 / 保持' if mode.startswith('anti_') else '动作周期示意'),font=SMALL,fill='#5f6f65')
    d.line((100,354,620,354),fill='#bcc5b9',width=3)
    # Supports are deliberately simple; no equipment model or measured joint angles are claimed.
    if 'bench' in key:
        a=(200,278) if not key.startswith('incline') else (230,211);b=(453,285)
        d.line((*a,*b),fill='#adb8ac',width=12);d.line((280,280,280,354),fill='#adb8ac',width=8);d.line((440,280,440,354),fill='#adb8ac',width=8)
    if key in ('chest_press_machine','seated_cable_row','lat_pulldown','seated_dumbbell_press','leg_extension','leg_curl','leg_press'):
        d.line((250,277,365,277),fill='#adb8ac',width=10);d.line((278,277,278,354),fill='#adb8ac',width=7)
    if key=='barbell_hip_thrust': d.line((185,244,270,244),fill='#adb8ac',width=12)
    if key=='pullup': d.line((282,99,444,99),fill=WEIGHT,width=8)
    segments=[('s','hip'),('hip','k2'),('k2','a2'),('hip','k'),('k','a'),('s','e'),('e','w')]
    if p.get('front'):
        right_e=(700-p['e'][0],p['e'][1]);right_w=(700-p['w'][0],p['w'][1])
        d.line((378,150,*right_e,*right_w),fill=BODY,width=7)
        d.line((322,150,378,150),fill=BODY,width=8)
        d.line((322,150,*p['e'],*p['w']),fill=BODY,width=7)
        segments=segments[:-2]
    for a,b in segments:
        d.line((*p[a],*p[b]),fill=BODY if not a.endswith('2') and not b.endswith('2') else '#90a49b',width=7)
    d.line((*p['s'],*p['h']),fill=BODY,width=7)
    hx,hy=p['h'];d.ellipse((hx-15,hy-18,hx+15,hy+12),outline=BODY,width=6)
    for name in ('a','a2'):
        x,y=p[name];d.line((x-7,y,x+20,y),fill=BODY,width=6)
    target=['s','e'] if mode in ('horizontal_push','vertical_push','horizontal_pull','vertical_pull','face_pull') else ['e'] if mode.startswith('elbow_') else ['k'] if mode.startswith('knee_') else ['a'] if mode=='ankle_extension' else ['s'] if mode.startswith('shoulder_') else ['hip','k'] if mode in ('squat','split_squat') else ['hip']
    for name in target:
        x,y=p[name];d.ellipse((x-6,y-6,x+6,y+6),fill=TARGET)
    if item['type']=='weighted':
        x,y=p['w']
        if key=='barbell_hip_thrust': x,y=p['hip']
        if key in ('leg_press','leg_extension','leg_curl','standing_calf_raise'):
            x,y=p['a'] if mode.startswith('knee') or key=='leg_press' else p['s']
        if '杠铃' in item['equipment']:
            d.ellipse((x-15,y-15,x+15,y+15),outline=WEIGHT,width=7);d.line((x-26,y,x+26,y),fill=WEIGHT,width=5)
        else:
            d.line((x-16,y,x+16,y),fill=WEIGHT,width=6);d.rectangle((x-21,y-9,x-14,y+9),fill=WEIGHT);d.rectangle((x+14,y-9,x+21,y+9),fill=WEIGHT)
            if p.get('front'):
                rx=700-x
                d.line((rx-16,y,rx+16,y),fill=WEIGHT,width=6);d.rectangle((rx-21,y-9,rx-14,y+9),fill=WEIGHT);d.rectangle((rx+14,y-9,rx+21,y+9),fill=WEIGHT)
        if '绳索' in item['equipment'] or '下拉' in item['equipment']:
            d.line((x,y,590,110),fill='#9baec5',width=2);d.line((590,100,590,350),fill='#adb8ac',width=6)
    d.text((24,369),'橙色：主要动作关节 · 二维原创示意，不用于测量或合格判定',font=SMALL,fill='#6c6259')
    d.text((24,392),'非真人示范；细节请结合动作要点与实际器械。',font=SMALL,fill='#6c6259')
    return im

for item in ITEMS:
    frames=[render(item,i) for i in range(36)]
    frames[0].save(OUT/f"{item['id']}.png")
    frames[0].save(OUT/f"{item['id']}.gif",save_all=True,append_images=frames[1:],duration=90,loop=0,optimize=True,disposal=2)
# Contact sheet for visual inspection, using three states for five representative exercises.
sheet=Image.new('RGB',(720*3,420*5),'white')
for row,key in enumerate(('bench','squat','deadlift','dumbbell_lateral_raise','leg_curl')):
    item=next(e for e in ITEMS if e['id']==key)
    for col,i in enumerate((0,9,18)): sheet.paste(render(item,i),(col*720,row*420))
sheet.save(ROOT/'.tools/downloads/exercise-demos-contact.png')
print(f'Rendered {len(ITEMS)} GIFs and posters in {OUT}')
