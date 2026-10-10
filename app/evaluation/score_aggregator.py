"""功能：定义确定性评分汇总接口；把指标评分汇总为 6 维画像与总评分，指标体系由版本化 Skill 发布。"""

from app.domain.models import MetricScore, QualityProfile


class ScoreAggregator:
    """按 Skill 发布的权重与覆盖率门槛做加权汇总；不适用与无分数指标不进入均分。

    汇总必须可复现、可审计；总结 Agent 只消费本模块输出，不得改写分数。
    """

    def aggregate(self, metric_scores: list[MetricScore]) -> QualityProfile:
        """占位接口：接入 Skill 权重与覆盖门槛前显式报错，不生成看似真实的画像。"""
        raise NotImplementedError("Score aggregation requires weights published via skills")
