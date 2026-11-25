import 'dart:convert';

const parameterNames = {
  'default_target_rir': '默认目标余力（次）',
  'week_review_days': '训练周复核间隔（天）',
  'progression_rpe_ceiling': '进阶复核的RPE上限',
  'max_weight_increase_fraction': '单次加重比例上限',
  'max_rep_change': '单组次数调整上限',
  'rm_max_age_days': 'RM复核期限（天）',
  'reduction_rpe_floor': '减量复核的RPE起点',
  'deload_set_fraction': '减量周保留组数比例',
  'max_weight_reduction_fraction': '单次减重比例上限',
  'interruption_review_days': '断训复核间隔（天）',
  'weight': '体重',
  'height': '身高',
  'age': '年龄',
  'male': '男性',
  'female': '女性',
  'min': '下限',
  'max': '上限',
  'default': '默认值',
  'cut': '减脂',
  'gain': '增肌',
  'maintain': '维持',
  'fat_loss': '减脂',
  'muscle_gain': '增肌',
  'protein': '蛋白质',
  'carbs': '碳水',
  'fat': '脂肪',
  'window_days': '观察天数',
  'weight_days_per_week': '每周称重天数',
  'step_kcal': '建议调整步长（kcal/日）',
  'expires_hours': '建议有效时间（小时）',
  'cooldown_days': '两次调整间隔（天）',
  'max_cumulative_adjustment_kcal': '累计调整幅度上限（kcal/日）',
  'adherence_tolerance_percent': '摄入与目标允许偏差（%）',
  'fat_loss_weekly_percent': '减脂周体重变化范围（%）',
  'muscle_gain_weekly_percent': '增肌周体重变化范围（%）',
  'rapid_change_stop_percent': '快速变化停止门槛（%）',
  'female_min': '女性自动计算下界',
  'male_min': '男性自动计算下界',
};

String friendlyValue(dynamic value) {
  if (value is List) return value.map(friendlyValue).join('；');
  if (value is Map) {
    return value.entries
        .map(
          (e) => '${parameterNames[e.key] ?? e.key}：${friendlyValue(e.value)}',
        )
        .join('；');
  }
  var text = '$value';
  if (text.trimLeft().startsWith('{')) {
    final end = text.lastIndexOf('}');
    if (end >= 0) {
      try {
        final parsed = jsonDecode(text.substring(0, end + 1));
        return '${friendlyValue(parsed)}${text.substring(end + 1)}';
      } on FormatException {
        // Preserve ordinary prose if it only resembles JSON.
      }
    }
  }
  for (final e in parameterNames.entries) {
    text = text.replaceAll(RegExp('\\b${e.key}\\b'), e.value);
  }
  return text;
}
