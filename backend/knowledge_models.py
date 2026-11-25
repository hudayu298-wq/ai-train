"""Bounded, source-linked foundation knowledge. No free-form executable rules."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Kind = Literal['muscle', 'joint', 'joint_action', 'bone_landmark', 'exercise_guide', 'training_principle', 'nutrition_principle', 'measurement_principle']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False, strict=True)


class Source(Strict):
    id: str = Field(pattern=r'^[a-z0-9_-]{2,80}$')
    title: str = Field(min_length=3, max_length=300)
    url: str = Field(pattern=r'^https://[^\s]+$', max_length=1000)
    edition: str = Field(min_length=1, max_length=100)
    section: str = Field(min_length=1, max_length=300)
    accessed_on: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
    content_use: Literal['paraphrased_facts', 'product_policy'] = 'paraphrased_facts'
    licensing_note: str = Field(min_length=5, max_length=500)
    publisher: str = Field(default='', max_length=150)
    published_on: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    evidence_type: Literal['textbook', 'guideline', 'position_stand', 'original_study', 'product_policy', 'unspecified'] = 'unspecified'


class Reference(Strict):
    source_id: str = Field(max_length=80)
    locator: str = Field(min_length=1, max_length=300)


FIELDS = {
    'muscle': {'origin', 'insertion', 'joint_ids', 'action_ids', 'attachment_scope', 'parts', 'not_crossing', 'landmark_ids'},
    'bone_landmark': {'bone', 'region', 'location', 'clinical_boundary'},
    'joint': {'joint_type', 'region', 'action_ids', 'rom_reference', 'use_as_video_threshold'},
    'joint_action': {'joint_id', 'plane', 'definition', 'opposite_id'},
    'exercise_guide': {'exercise_id', 'variant', 'joint_ids', 'action_ids', 'primary_muscle_ids', 'assisting_muscle_ids',
        'stabilizer_muscle_ids', 'principle_ids', 'load_basis', 'camera_views', 'observable', 'not_observable', 'setup', 'execution', 'phase_notes', 'landmark_ids'},
    'training_principle': {'principle', 'recommendations', 'governing_service', 'rule_ids', 'numeric_guidance', 'evidence_scope'},
    'nutrition_principle': {'principle', 'recommendations', 'governing_service', 'rule_ids', 'numeric_guidance', 'evidence_scope'},
    'measurement_principle': {'principle', 'recommendations', 'governing_service', 'rule_ids', 'numeric_guidance', 'evidence_scope'},
}
REQUIRED = {
    'bone_landmark': {'bone', 'region', 'location', 'clinical_boundary'},
    'muscle': {'origin', 'insertion', 'joint_ids', 'action_ids', 'attachment_scope'},
    'joint': {'joint_type', 'action_ids', 'rom_reference', 'use_as_video_threshold'},
    'joint_action': {'joint_id', 'plane', 'definition'},
    'exercise_guide': {'exercise_id', 'variant', 'joint_ids', 'primary_muscle_ids', 'action_ids', 'principle_ids', 'not_observable'},
}
RELATION_KEYS = {'joint_ids': {'joint'}, 'joint_id': {'joint'}, 'action_ids': {'joint_action'}, 'opposite_id': {'joint_action'},
    'primary_muscle_ids': {'muscle'}, 'assisting_muscle_ids': {'muscle'}, 'stabilizer_muscle_ids': {'muscle'},
    'principle_ids': {'training_principle', 'measurement_principle', 'nutrition_principle'}, 'landmark_ids': {'bone_landmark'}}


class Item(Strict):
    id: str = Field(pattern=r'^[a-z0-9_-]{2,80}$')
    kind: Kind
    title: str = Field(min_length=2, max_length=150)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=5, max_length=1500)
    facts: dict[str, str | bool | list[str]]
    population: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(min_length=1, max_length=10)
    references: list[Reference] = Field(min_length=1, max_length=6)
    exercise_ids: list[str] = Field(default_factory=list, max_length=20)
    evidence_status: Literal['source_checked', 'admin_reviewed', 'product_default', 'not_graded'] = 'not_graded'

    @model_validator(mode='after')
    def validate_facts(self):
        required = REQUIRED.get(self.kind, {'principle', 'recommendations', 'governing_service'})
        if set(self.facts) - FIELDS[self.kind] or required - self.facts.keys():
            raise ValueError('知识字段与类型不一致')
        list_keys={'origin','insertion','parts','not_crossing','camera_views','observable','not_observable','setup','execution','recommendations','phase_notes','numeric_guidance'}
        for key,value in self.facts.items():
            expected=bool if key=='use_as_video_threshold' else list if key.endswith('_ids') or key in list_keys else str
            if not isinstance(value,expected):
                raise ValueError('结构化事实字段类型错误')
        for value in [*self.aliases, *self.population, *self.limitations, *self.exercise_ids, *self.facts.values()]:
            if isinstance(value, str) and (not value or len(value) > 1500):
                raise ValueError('知识文本为空或过长')
            if isinstance(value, list) and (len(value) > 30 or any(not s.strip() or len(s) > 1000 for s in value)):
                raise ValueError('知识列表异常')
        for key in ('origin', 'insertion', 'joint_ids', 'action_ids', 'primary_muscle_ids', 'principle_ids', 'recommendations'):
            if key in self.facts and not isinstance(self.facts[key], list):
                raise ValueError('关联和结构化事实必须是列表')
        if self.kind == 'muscle' and (not self.facts['origin'] or not self.facts['insertion']):
            raise ValueError('肌肉起止点不能留空')
        if self.kind == 'joint' and self.facts['use_as_video_threshold'] is not False:
            raise ValueError('关节参考数据不能直接作为视频合格阈值')
        return self


class Relation(Strict):
    source: str = Field(max_length=80)
    target: str = Field(max_length=80)
    relation: Literal['crosses', 'uses_joint', 'produces', 'occurs_at', 'opposite', 'primary', 'assists', 'stabilizes', 'uses_principle', 'references_landmark']


class Bundle(Strict):
    version: str = Field(pattern=r'^[a-zA-Z0-9._-]{3,80}$')
    name: str = Field(min_length=3, max_length=150)
    sources: list[Source] = Field(min_length=1, max_length=60)
    items: list[Item] = Field(min_length=1, max_length=300)
    relations: list[Relation] = Field(default_factory=list, max_length=3000)

    @model_validator(mode='after')
    def validate_graph(self):
        nodes = {i.id: i for i in self.items}
        sources = {s.id for s in self.sources}
        if len(nodes) != len(self.items) or len(sources) != len(self.sources):
            raise ValueError('知识ID或来源ID重复')
        expected = set()
        relations = set()
        edge_types = {'joint_ids': 'crosses', 'action_ids': 'produces', 'joint_id': 'occurs_at', 'opposite_id': 'opposite',
            'primary_muscle_ids': 'primary', 'assisting_muscle_ids': 'assists', 'stabilizer_muscle_ids': 'stabilizes', 'principle_ids': 'uses_principle', 'landmark_ids': 'references_landmark'}
        for item in self.items:
            if any(r.source_id not in sources for r in item.references):
                raise ValueError('知识引用了未声明来源')
            for key, kinds in RELATION_KEYS.items():
                value = item.facts.get(key, [])
                for target in ([value] if isinstance(value, str) else value):
                    if target not in nodes or nodes[target].kind not in kinds:
                        raise ValueError('知识关联缺失或指向错误类型')
                    if item.kind == 'joint' and key == 'action_ids' and nodes[target].facts['joint_id'] != item.id:
                        raise ValueError('关节动作与关节不一致')
                    if not (item.kind == 'joint' and key == 'action_ids'):
                        expected.add((item.id, target, 'uses_joint' if item.kind=='exercise_guide' and key=='joint_ids' else edge_types[key]))
        for edge in self.relations:
            key = (edge.source, edge.target, edge.relation)
            if edge.source not in nodes or edge.target not in nodes or key in relations:
                raise ValueError('知识关系指向不存在节点或重复')
            relations.add(key)
        if relations != expected:
            raise ValueError('关系图必须与结构化事实一致，不能添加隐含关系')
        return self
