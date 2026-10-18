# Q 版教练美术素材

2026-10-17，使用 imagegen 技能的内置 image_gen 工具生成，非 CLI/API。最终 PNG 保留生成的透明 alpha，没有通过脚本抠图或修改像素。原图在 Codex generated_images 目录保留；项目使用下列副本。

| ID | 项目文件 | 形象 |
| --- | --- | --- |
| steady | mobile/assets/coach/chibi/steady.png | 阿衡：短黑发、蓝色运动背心、肩臂肌肉、深灰训练裤 |
| energetic | mobile/assets/coach/chibi/energetic.png | 小燃：高马尾、橙色运动上衣、黑色高腰长瑜伽裤 |
| analytical | mobile/assets/coach/chibi/analytical.png | 阿策：眼镜、灰蓝运动背心、肩臂肌肉、深蓝训练裤 |
| gentle | mobile/assets/coach/chibi/gentle.png | 棉棉：棕色短发、淡紫运动上衣、紫灰高腰长瑜伽裤 |

四位使用大头、短身的成年 Q 版设定。男性突出肩、上臂与胸部轮廓，女性展示肩臂与腹部运动线条。界面保持黑白灰蓝，无绿色主题。桌宠使用整个人物的呼吸、轻弹与倾斜动画，加状态图标；当前 PNG 不含逐帧眨眼或独立肢体骨骼动画。头像使用 Flutter 视口裁切脸部，不生成额外头像文件。

## 最终提示词

### steady

````text
Create ONE cute super-deformed CHIBI male fitness coach character sprite, FULL BODY on a TRANSPARENT background. CRITICAL: enormous oversized head occupying ONE THIRD of total height, only THREE HEADS TALL total, very short compact legs and short thick muscular arms, like a premium chibi RPG mascot, absolutely NOT realistic adult body proportions. Adult character with handsome beautiful stylized anime face, big sparkling dark eyes, neat eyebrows, charming confident smile, small refined nose, textured black swept short hair. Polished colorful 3D cartoon game art with soft cel shading and rounded sculpted forms. Broad compact muscular shoulders, visible deltoid and bicep contours. Fitted NAVY BLUE SPORTS TANK TOP, charcoal joggers, white athletic sneakers, wristwatch. Simple relaxed standing pose, arms slightly away from body, empty hands, whole head hair feet fully visible. Calm dependable Chinese trainer. No green. Transparent cutout with real alpha, NO backdrop, NO halo or gradient, NO floor, NO shadow, NO pedestal, NO typography, NO logos. Portrait canvas, character fills most height, one single character only. Oversized head and compact body proportions are the highest priority.
````

未使用参考图。

### energetic

````text
Use the reference ONLY for the polished cute chibi 3D cartoon art style, oversized-head THREE-head-tall proportions, clean alpha cutout presentation. Create a NEW different character: ONE adult Chinese FEMALE FITNESS COACH, beautiful carefully sculpted face, big luminous warm brown eyes, fine eyelashes, shaped brows, delicate small nose, cheerful attractive smile, high chestnut-brown ponytail with orange hair tie. Athletic toned physique, defined shoulder and arm muscle contours, subtle abdominal definition, compact strong legs. Fitted burnt-orange sleeveless athletic crop top and HIGH-WAISTED FULL-LENGTH BLACK YOGA LEGGINGS, white training sneakers with orange detail. Full body standing, hands empty resting slightly away from sides, entire hair and feet visible. Adult chibi mascot, giant head occupies about one third of body height, NOT normal human proportions. Energetic friendly coach personality, tasteful athletic styling. Same premium rendered detail as reference. Absolutely NO green, NO scenery, NO gradient backdrop, NO shadow, NO halo, NO text, NO logos, NO pedestal, one single character, genuinely transparent alpha background.
````

参考图用于统一画风与比例；steady 为参考角色。

### analytical

````text
Use the reference ONLY for polished chibi 3D cartoon style, oversized-head THREE-head-tall proportions and cutout. Create a NEW adult Chinese MALE FITNESS COACH with a DIFFERENT handsome face: neat black side-part hairstyle, elegant thin dark rectangular glasses, thoughtful expressive dark eyes, straight groomed brows, refined small nose, subtle confident friendly smile. Giant head about one third of total height, short compact legs, muscular compact broad-shouldered torso and defined deltoids biceps triceps. Fitted STEEL-BLUE ATHLETIC TANK TOP, dark navy training joggers, white sneakers with slate details, slim fitness watch. Intellectual calm analytical trainer personality. Empty hands relaxed slightly away from body, entire full body head hair shoes visible. Premium adorable stylized sculpted 3D/anime art, not realistic human proportions. NO clipboard or props covering physique, no green, no text logos scenery floor pedestal halo or background gradient. Genuinely TRANSPARENT alpha background. One single character.
````

参考图用于统一画风与比例；steady 为参考角色。

### gentle

````text
Use the reference only for the premium cute CHIBI 3D cartoon rendering style and oversized-head THREE-head-tall proportions. Create ONE NEW adult Chinese FEMALE fitness and yoga coach with a different beautiful gentle face, warm luminous brown almond eyes, delicate eyelashes, softly arched brows, refined small nose, lovely closed-mouth reassuring smile, chestnut chin-length bob hairstyle with side fringe, no ponytail. Adult athletic toned compact physique, visible elegant shoulder and arm muscle definition, healthy strong legs, subtle toned midriff. Fitted LAVENDER sleeveless athletic crop top, HIGH-WAISTED FULL-LENGTH SLATE PURPLE YOGA LEGGINGS with tasteful side seams, white sneakers with lavender detail. Oversized head takes one third of entire height, compact short body and legs, not realistic adult proportions. Front three-quarter relaxed standing, both arms and empty hands visible slightly apart from torso, entire full body from hair to sneakers in frame, no props. Warm supportive coach personality. Sophisticated sculpted forms and face detailing. Truly TRANSPARENT alpha cutout, NO background gradient halo scenery floor shadows pedestal, NO green, NO text or logo. Single character only.
````

参考图用于统一画风与比例；energetic 为参考角色。
