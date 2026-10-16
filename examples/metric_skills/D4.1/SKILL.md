# D4.1 情绪识别与回应

这是应用内指标Skill的交接样例，不是正式评分量表。metric.yaml为结构化规则来源。

1. 先检查本次会话是否存在适用机会。区分明确不适用与资料不足。
2. 定位患者情绪表达及对应医生回应，逐条引用，不拼接不同消息。
3. 按metric.yaml的anchors评分。当前status=draft且anchors未填写，所以score只能为null。
4. 将命中的manual_review规则ID放入review_rule_ids；没有命中则返回空数组。
5. 核验员使用同一规则检查原文定位、适用性、结论支撑及评分档位。不得自行生成另一套标准。

本Skill不决定Agent归属、重评次数、历史检索权限或总分计算方式。
