export type QualityReportStatus = 'completed' | 'processing'

export type QualityReport = {
  id: string
  title: string
  createdAt: string
  total: number
  high: number
  medium: number
  low: number
  status: QualityReportStatus
  qualityScore: number
  summary: string
  improvement: string
  dimensions: { name: string; score: number; change: string }[]
  findings: string[]
  recommendations: string[]
  samples: { sessionId: string; doctor: string; level: 'high' | 'medium' | 'low'; pending: number }[]
}

export const reportStatusText: Record<QualityReportStatus, string> = {
  completed: '已完成',
  processing: '处理中',
}

const sampleDimensions = [
  { name: '专业服务', score: 4.3, change: '+0.2' },
  { name: '沟通互动', score: 4.5, change: '+0.1' },
  { name: '风险管理', score: 3.9, change: '-0.1' },
]

export function createQualityReports(): QualityReport[] {
  return ([
    {
      id: 'ZJ-20240628-001',
      title: '2024年6月第四周质检',
      createdAt: '2024-06-28 14:30:22',
      total: 1852,
      high: 128,
      medium: 346,
      low: 1378,
      status: 'completed',
      qualityScore: 4.2,
      summary: '本次共检测 1,852 条会话，整体服务质量良好。高风险占比保持在 6.9%，较上次下降 0.6%，建议继续保持风险识别与复核闭环。',
      improvement: '重点关注风险管理维度的危机识别提示，持续提升随访建议完整性。',
      dimensions: sampleDimensions,
      findings: ['高风险会话主要集中在风险识别敏感性与危机干预建议。', '沟通互动整体表现稳定，情绪回应及时性得分最高。', '12 条会话缺少完整随访信息，已进入人工复核队列。'],
      recommendations: ['为高风险会话增加二次复核。', '完善随访话术模板，明确复查时间与触发条件。', '每周跟踪风险管理维度变化，低于 4.0 时触发专项培训。'],
      samples: [
        { sessionId: 'C202406010001', doctor: '张医生', level: 'high', pending: 3 },
        { sessionId: 'C202406010002', doctor: '李医生', level: 'medium', pending: 2 },
        { sessionId: 'C202405310088', doctor: '陈医生', level: 'low', pending: 0 },
      ],
    },
    {
      id: 'ZJ-20240621-001', title: '2024年6月第三周质检', createdAt: '2024-06-21 10:12:08', total: 1624, high: 142, medium: 318, low: 1164, status: 'completed', qualityScore: 4.1,
      summary: '整体服务质量保持稳定，高风险占比较上一周期略有上升。', improvement: '建议加强危机干预话术培训。', dimensions: sampleDimensions, findings: ['高风险会话数量较上周增加 14 条。'], recommendations: ['补充危机识别案例培训。'], samples: [],
    },
    {
      id: 'ZJ-20240614-001', title: '2024年6月第二周质检', createdAt: '2024-06-14 16:20:15', total: 1908, high: 156, medium: 372, low: 1380, status: 'completed', qualityScore: 4.1,
      summary: '本批次专业服务和沟通互动指标表现均衡。', improvement: '风险沟通清晰度仍有提升空间。', dimensions: sampleDimensions, findings: ['风险沟通清晰度平均分 3.8。'], recommendations: ['优化高风险提示的表达结构。'], samples: [],
    },
    {
      id: 'ZJ-20240607-001', title: '2024年6月第一周质检', createdAt: '2024-06-07 11:05:33', total: 1736, high: 168, medium: 334, low: 1234, status: 'completed', qualityScore: 4.0,
      summary: '服务质量整体良好，但风险识别敏感性需要持续关注。', improvement: '建议完善初诊会话的风险筛查流程。', dimensions: sampleDimensions, findings: ['初诊会话高风险占比 10.2%。'], recommendations: ['对初诊咨询增加风险清单提示。'], samples: [],
    },
    {
      id: 'ZJ-20240531-001', title: '2024年5月第五周质检', createdAt: '2024-05-31 15:42:11', total: 1690, high: 138, medium: 310, low: 1242, status: 'completed', qualityScore: 4.2,
      summary: '本批次低风险会话占比 73.5%，复核效率较高。', improvement: '继续保持证据回溯完整性。', dimensions: sampleDimensions, findings: ['证据引用完整率达到 96.4%。'], recommendations: ['将优秀会话纳入培训案例库。'], samples: [],
    },
    {
      id: 'ZJ-20240524-001', title: '2024年5月第四周质检', createdAt: '2024-05-24 09:28:17', total: 1502, high: 112, medium: 286, low: 1104, status: 'completed', qualityScore: 4.3,
      summary: '服务质量整体表现较好，风险管理维度波动较小。', improvement: '建议保持当前复核节奏。', dimensions: sampleDimensions, findings: ['人工复核平均处理时长缩短至 1.8 天。'], recommendations: ['保持周度质检频率。'], samples: [],
    },
    {
      id: 'ZJ-20240517-001', title: '2024年5月第三周质检', createdAt: '2024-05-17 14:16:05', total: 1618, high: 136, medium: 302, low: 1180, status: 'completed', qualityScore: 4.2,
      summary: '沟通互动维度表现突出，专业服务维度保持稳定。', improvement: '个性化方案制定可进一步细化。', dimensions: sampleDimensions, findings: ['个性化方案制定平均分 3.9。'], recommendations: ['增加方案颗粒度示例。'], samples: [],
    },
    {
      id: 'ZJ-20240510-001', title: '2024年5月第二周质检', createdAt: '2024-05-10 10:34:50', total: 1460, high: 98, medium: 268, low: 1094, status: 'completed', qualityScore: 4.4,
      summary: '本批次为近八周最佳表现，高风险占比较低。', improvement: '建议复盘本批次优秀实践。', dimensions: sampleDimensions, findings: ['低风险会话占比 74.9%。'], recommendations: ['沉淀优质服务标准。'], samples: [],
    },
    {
      id: 'ZJ-20240705-001', title: '2024年7月第一周质检', createdAt: '2024-07-05 09:00:00', total: 0, high: 0, medium: 0, low: 0, status: 'processing', qualityScore: 0,
      summary: '本批次正在整理离线演示数据，完成后将展示风险分布与复核建议。', improvement: '等待数据解析完成。', dimensions: sampleDimensions, findings: [], recommendations: [], samples: [],
    },
  ] satisfies QualityReport[]).sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}
