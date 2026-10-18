"""Rebuild the curated seed from the official USDA SR Legacy CSV download.
Usage: python scripts/build_food_seed.py path/to/extracted/csv-directory
Download: https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
folder = Path(sys.argv[1]) if len(sys.argv) > 1 else next((ROOT / '.tools/downloads/usda-sr-legacy').glob('*/food.csv')).parent
mapping = [
    (168877, '长粒白米（生，强化）', '谷物薯类', 'raw'),
    (168878, '长粒白米饭（熟，强化）', '谷物薯类', 'cooked'),
    (168875, '中粒糙米饭（熟）', '谷物薯类', 'cooked'),
    (169703, '长粒糙米（生）', '谷物薯类', 'raw'),
    (169705, '燕麦（干）', '谷物薯类', 'raw'),
    (172688, '全麦面包（商品通用）', '谷物薯类', 'prepared'),
    (168926, '鸡蛋面（熟，无添加盐）', '谷物薯类', 'cooked'),
    (168484, '红薯（水煮，去皮）', '谷物薯类', 'cooked'),
    (170440, '土豆（水煮，去皮，无盐）', '谷物薯类', 'cooked'),
    (169999, '甜玉米（水煮，无盐）', '谷物薯类', 'cooked'),
    (171477, '鸡胸肉（去皮，烤熟）', '肉蛋鱼', 'cooked'),
    (171478, '鸡胸肉（去皮，炖熟）', '肉蛋鱼', 'cooked'),
    (173424, '鸡蛋（水煮，可食部分）', '肉蛋鱼', 'cooked'),
    (171998, '野生大西洋三文鱼（熟，干热）', '肉蛋鱼', 'cooked'),
    (173686, '野生大西洋三文鱼（生）', '肉蛋鱼', 'raw'),
    (171793, '牛肉饼（90%瘦肉，煎熟）', '肉蛋鱼', 'cooked'),
    (167818, '猪里脊部肉（生，含可分离脂肪）', '肉蛋鱼', 'raw'),
    (172217, '全脂牛奶（3.25%脂肪）', '乳制品', 'prepared'),
    (171284, '原味全脂酸奶', '乳制品', 'prepared'),
    (170886, '原味低脂酸奶', '乳制品', 'prepared'),
    (172448, '硬豆腐（硫酸钙与氯化镁凝固）', '豆类豆制品', 'prepared'),
    (172449, '嫩豆腐（硫酸钙与氯化镁凝固）', '豆类豆制品', 'prepared'),
    (172421, '扁豆（水煮，无盐）', '豆类豆制品', 'cooked'),
    (173740, '芸豆（水煮，无盐）', '豆类豆制品', 'cooked'),
    (170379, '西兰花（生）', '蔬菜', 'raw'),
    (169967, '西兰花（水煮，无盐）', '蔬菜', 'cooked'),
    (168462, '菠菜（生）', '蔬菜', 'raw'),
    (170393, '胡萝卜（生）', '蔬菜', 'raw'),
    (170457, '番茄（生）', '蔬菜', 'raw'),
    (168409, '黄瓜（生，带皮）', '蔬菜', 'raw'),
    (173944, '香蕉（生，可食部分）', '水果', 'raw'),
    (167793, '富士苹果（生，带皮）', '水果', 'raw'),
    (169097, '橙子（生，可食部分）', '水果', 'raw'),
    (167762, '草莓（生）', '水果', 'raw'),
    (171711, '蓝莓（生）', '水果', 'raw'),
    (171705, '牛油果（生，可食部分）', '水果', 'raw'),
    (172430, '花生（生）', '坚果种子', 'raw'),
    (170187, '核桃仁', '坚果种子', 'prepared'),
    (170554, '奇亚籽（干）', '坚果种子', 'prepared'),
    (171413, '橄榄油', '油脂', 'prepared'),
]
foods = {r['fdc_id']: r for r in csv.DictReader((folder / 'food.csv').open(encoding='utf-8'))}
nutrients = {str(key): {} for key, *_ in mapping}
columns = {'1008': 'kcal', '1003': 'protein', '1004': 'fat', '1005': 'carbs'}
with (folder / 'food_nutrient.csv').open(encoding='utf-8') as stream:
    for row in csv.DictReader(stream):
        if row['fdc_id'] in nutrients and row['nutrient_id'] in columns and row['amount']:
            nutrients[row['fdc_id']][columns[row['nutrient_id']]] = float(row['amount'])
result = []
for key, name, category, state in mapping:
    key = str(key)
    assert len(nutrients[key]) == 4, f'Missing nutrients for {key}'
    result.append({'id': f'usda_{key}', 'name': name, 'category': category, 'state': state,
        'aliases': [foods[key]['description']], **nutrients[key], 'basis_g': 100,
        'original_name': foods[key]['description'], 'source_kind': 'usda_sr_legacy',
        'source_id': key, 'source_label': f'USDA FoodData Central · SR Legacy 2018 · FDC {key}',
        'source_url': f'https://fdc.nal.usda.gov/food-details/{key}/nutrients',
        'review_status': 'source_imported',
        'notes': '每100克可食部分；美国通用食材参考。中文名称为项目翻译，实际品牌、产地和烹调会有差异。'})
# Preserve existing IDs and their development values so old records and clients remain compatible.
for key, name, category, values in [
    ('rice', '熟米饭（原开发示例）', '谷物薯类', (116, 2.6, 0.3, 25.9)),
    ('chicken', '熟鸡胸肉（原开发示例）', '肉蛋鱼', (165, 31, 3.6, 0)),
    ('egg', '水煮鸡蛋（原开发示例）', '肉蛋鱼', (155, 12.6, 10.6, 1.1)),
    ('broccoli', '熟西兰花（原开发示例）', '蔬菜', (35, 2.4, 0.4, 7.2)),
]:
    result.insert(0, {'id': key, 'name': name, 'category': category, 'state': 'cooked',
        'aliases': [], **dict(zip(('kcal', 'protein', 'fat', 'carbs'), values)), 'basis_g': 100,
        'source_kind': 'legacy_example', 'source_label': '原MVP开发示例，来源未核验',
        'review_status': 'unverified', 'notes': '保留旧ID兼容历史记录，可选用有来源的新条目。'})
(ROOT / 'backend/data/foods.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
metadata = {'dataset': 'USDA FoodData Central SR Legacy CSV 2018-04',
    'url': 'https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip',
    'files_sha256': {f: hashlib.sha256((folder / f).read_bytes()).hexdigest() for f in ('food.csv', 'food_nutrient.csv')},
    'curated_count': len(mapping), 'legacy_count': 4, 'basis': 'per 100 g edible portion'}
(ROOT / 'backend/data/food_sources.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
print(f'Built {len(result)} food entries ({len(mapping)} USDA + 4 legacy)')
