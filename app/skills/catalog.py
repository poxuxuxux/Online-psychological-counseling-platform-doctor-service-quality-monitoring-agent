"""Versioned indicator definitions; missing scoring anchors are explicit, never invented."""

import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    name: str
    owner: str
    definition: str
    scoring_status: str = "not_configured"


VERSION = "indicators-20261010-draft-v1"
CATALOG = (
    MetricDefinition(
        "D1.1",
        "实质性服务履行",
        "professional_service",
        "是否提供针对诉求的实质性答复，而非只有问候或模板回复",
    ),
    MetricDefinition(
        "D1.2",
        "服务内容一致性",
        "professional_service",
        "同次咨询的建议是否存在无合理解释的前后矛盾",
    ),
    MetricDefinition(
        "D2.1",
        "首次响应及时性",
        "process_response",
        "订单进入咨询阶段至首次实际回复的间隔；必须由时间工具计算",
    ),
    MetricDefinition(
        "D2.2",
        "交互响应及时性",
        "process_response",
        "患者需回应问题至医生回应的间隔；不得凭对话顺序猜测时长",
    ),
    MetricDefinition(
        "D3.1",
        "症状信息探询",
        "professional_service",
        "对症状表现、持续时间、严重程度或功能影响的必要追问",
    ),
    MetricDefinition(
        "D3.2", "病史与治疗信息核对", "professional_service", "涉及病史、药物或既往治疗时的必要核查"
    ),
    MetricDefinition(
        "D3.3",
        "心理社会背景探询",
        "professional_service",
        "相关情境下对压力事件、生活处境、情绪诱因的询问",
    ),
    MetricDefinition(
        "D3.4", "关键诉求回应", "professional_service", "答复是否覆盖患者明确提出的核心问题"
    ),
    MetricDefinition(
        "D3.5", "信息解释清晰性", "professional_service", "症状、治疗信息或建议是否解释清晰"
    ),
    MetricDefinition(
        "D4.1", "情绪识别与回应", "empathy_relationship", "是否识别并回应患者表达的情绪"
    ),
    MetricDefinition(
        "D4.2", "反映式理解", "empathy_relationship", "通过复述、澄清或解释体现对患者心理体验的理解"
    ),
    MetricDefinition(
        "D4.3", "尊重与非评判性", "empathy_relationship", "尊重、接纳，避免指责、贬低和否定体验"
    ),
    MetricDefinition(
        "D5.1", "咨询目标协商", "process_response", "需要制定计划时是否澄清或共同讨论目标"
    ),
    MetricDefinition(
        "D5.2", "患者意见征询", "process_response", "是否询问对方案的意见、意愿或顾虑"
    ),
    MetricDefinition(
        "D5.3", "建议个体化程度", "process_response", "建议是否结合症状、经历和具体处境"
    ),
    MetricDefinition(
        "D5.4", "建议可执行性", "process_response", "是否给出明确、具体、可理解的下一步行动"
    ),
    MetricDefinition(
        "D6.1",
        "风险信号回应",
        "empathy_relationship",
        "明确严重风险表达时是否进行必要的安全询问或风险回应；评价医生行为",
    ),
    MetricDefinition(
        "D6.2",
        "必要转介与求助提示",
        "professional_service",
        "明确涉及紧急处理或超出线上范围时是否提供求助或转介指引",
    ),
)


def snapshot(packages_dir: Path | None = None) -> dict:
    from app.skills.metric_loader import merge_metric_packages

    base = {
        "version": VERSION,
        "status": "draft",
        "score_range": [0, 5],
        "metrics": [asdict(metric) for metric in CATALOG],
    }
    directory = packages_dir or Path(
        os.getenv("METRIC_SKILLS_DIR", str(Path(__file__).parent / "metric_packages"))
    )
    return merge_metric_packages(base, directory)
