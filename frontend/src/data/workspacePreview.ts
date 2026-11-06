import { dimensions, metrics as metricCatalog } from '../utils/catalog'

export type WorkspaceStatus = 'completed' | 'evaluating' | 'pending'
export type Speaker = 'patient' | 'doctor'

export type WorkspaceMessage = {
  id: string
  role: Speaker
  time: string
  content: string
  evidence?: number
}

export type WorkspaceMetric = {
  code: string
  name: string
  score: number
  rationale: string
  evidenceId: string
}

export type WorkspaceGroup = {
  id: string
  name: string
  icon: string
  metrics: WorkspaceMetric[]
}

export type WorkspaceSession = {
  id: string
  doctor: string
  patient: string
  updatedAt: string
  status: WorkspaceStatus
  score: number
  summary: string
  messages: WorkspaceMessage[]
  groups: WorkspaceGroup[]
}

type SessionSeed = Omit<WorkspaceSession, 'groups'> & { scores: number[] }

const groupIcons = ['shield', 'clock', 'message', 'heart', 'sparkle', 'alert']
const rationales = [
  '服务内容与咨询约定的目标保持一致，关键服务事项均有记录。',
  '医生及时回应了来访者的发言，并保持了稳定的互动节奏。',
  '医生围绕主要困扰收集信息，解释清楚，并回应了来访者的关键诉求。',
  '医生关注并回应了来访者的情绪，表达尊重且避免评判。',
  '医生与来访者共同梳理目标，建议结合其实际情况且便于执行。',
  '医生对风险线索作出回应，并说明了适用的后续求助或转介方式。',
]

function makeGroups(seed: SessionSeed): WorkspaceGroup[] {
  let scoreIndex = 0
  return dimensions.map((dimension, groupIndex) => ({
    id: dimension.id,
    name: `${dimension.id} ${dimension.name}`,
    icon: groupIcons[groupIndex]!,
    metrics: metricCatalog.filter((metric) => metric.id.startsWith(`${dimension.id}.`)).map((metric) => {
      const message = seed.messages[Math.min(1 + groupIndex, seed.messages.length - 1)]!
      const score = seed.scores[scoreIndex++] ?? 4
      return {
        code: metric.id,
        name: metric.name,
        score,
        rationale: rationales[groupIndex]!,
        evidenceId: message.id,
      }
    }),
  }))
}

const seeds: SessionSeed[] = [
  {
    id: 'C202406010001', doctor: '张医生', patient: '来访者 01', updatedAt: '2024-06-01 14:30', status: 'completed', score: 4.2,
    summary: '整体服务质量良好。医生在共情回应与提问引导方面表现突出，建议进一步明确风险识别与随访安排。',
    scores: [4.5, 4.2, 4.1, 4.1, 4.2, 4.2, 4.6, 4.6, 4.5, 4.5, 4.4, 4.4, 3.8, 3.9, 3.8, 3.8, 3.9, 3.9],
    messages: [
      { id: 'm1', role: 'patient', time: '2024-06-01 14:30', content: '最近一段时间我总是睡不着，脑子里会反复想很多事情。一到晚上就很焦虑，怎么办？' },
      { id: 'm2', role: 'doctor', time: '2024-06-01 14:31', content: '我理解这让你感到很困扰。能告诉我，这种情况大概持续了多久？平时还有其他不适的感觉吗？' },
      { id: 'm3', role: 'patient', time: '2024-06-01 14:33', content: '大概有两三个月了。白天还好，一到晚上就会紧张，心跳加快，脑子停不下来，有时候会想一些不好的事情。', evidence: 1 },
      { id: 'm4', role: 'doctor', time: '2024-06-01 14:35', content: '听起来你可能正经历一定程度的焦虑反应。为了更好地了解你的情况，我想再问几个问题：你平时的作息规律吗？最近有没有遇到特别的压力事件？' },
      { id: 'm5', role: 'patient', time: '2024-06-01 14:37', content: '作息有点乱，最近工作压力比较大，经常加班，感觉自己一直处于紧绷的状态。' },
      { id: 'm6', role: 'doctor', time: '2024-06-01 14:39', content: '我们可以先一起梳理压力来源，并记录一周的睡眠和情绪变化。如果不适持续加重，建议尽快到专业医疗机构进行进一步评估。' },
      { id: 'm7', role: 'doctor', time: '2024-06-01 14:40', content: '如果那些不好的想法让你感到难以保证自身安全，请立即联系身边可信任的人和当地紧急援助，不要独自承受。' },
    ],
  },
  {
    id: 'C202406010002', doctor: '李医生', patient: '来访者 02', updatedAt: '2024-06-01 11:20', status: 'evaluating', score: 4.4,
    summary: '咨询结构完整，医生能够清晰解释情绪与压力的关系。可进一步增加对个体应对资源的探索。',
    scores: [4.6, 4.4, 4.3, 4.4, 4.5, 4.2, 4.5, 4.7, 4.6, 4.4, 4.5, 4.6, 4.1, 4.2, 4.0, 4.1, 4.2, 4.3],
    messages: [
      { id: 'm1', role: 'patient', time: '2024-06-01 11:20', content: '最近工作任务特别多，我总担心自己做不好，开会前也很紧张。' },
      { id: 'm2', role: 'doctor', time: '2024-06-01 11:21', content: '持续的压力让你很难放松。最担心发生的具体结果是什么？这种情况通常一周会出现几次？' },
      { id: 'm3', role: 'patient', time: '2024-06-01 11:24', content: '我怕出错以后被否定，几乎每天上班前都会想这些。', evidence: 1 },
      { id: 'm4', role: 'doctor', time: '2024-06-01 11:26', content: '我们可以把担忧拆成可以核实的事实和尚未发生的设想，再看看哪些准备工作是你现在就能完成的。' },
      { id: 'm5', role: 'patient', time: '2024-06-01 11:28', content: '这样分开看好像轻松一点，我其实已经准备得很充分了。' },
      { id: 'm6', role: 'doctor', time: '2024-06-01 11:30', content: '是的，看见已经拥有的资源很重要。接下来一周可以记录紧张出现的场景，我们在下次咨询中一起复盘。' },
    ],
  },
  {
    id: 'C202405310089', doctor: '王医生', patient: '来访者 03', updatedAt: '2024-05-31 16:45', status: 'pending', score: 3.9,
    summary: '医生提供了基础情绪支持，后续可加强对社会支持、既往应对方式和风险信息的了解。',
    scores: [4.1, 3.8, 3.9, 3.8, 4.0, 3.7, 4.3, 4.2, 4.1, 3.9, 4.4, 4.0, 3.6, 3.8, 3.5, 3.6, 3.7, 3.9],
    messages: [
      { id: 'm1', role: 'patient', time: '2024-05-31 16:45', content: '这段时间情绪一直很低落，以前喜欢的事情现在也提不起兴趣。' },
      { id: 'm2', role: 'doctor', time: '2024-05-31 16:47', content: '这种持续低落的感觉一定很不好受。它对你的睡眠、饮食和日常工作有什么影响？' },
      { id: 'm3', role: 'patient', time: '2024-05-31 16:49', content: '吃得比较少，周末也不出门，朋友约我我都拒绝了。', evidence: 1 },
      { id: 'm4', role: 'doctor', time: '2024-05-31 16:52', content: '谢谢你愿意告诉我这些。我们可以先从一件负担很小的事情开始，同时了解你身边是否有可以支持你的人。' },
      { id: 'm5', role: 'patient', time: '2024-05-31 16:54', content: '我姐姐很关心我，但我不太想让她担心。' },
      { id: 'm6', role: 'doctor', time: '2024-05-31 16:56', content: '我们可以讨论怎样用你舒服的方式让她了解你的近况，也会一起关注这些变化是否持续加重。' },
    ],
  },
  {
    id: 'C202405310088', doctor: '陈医生', patient: '来访者 04', updatedAt: '2024-05-31 10:12', status: 'completed', score: 4.5,
    summary: '复诊目标明确，医生能够结合睡眠记录进行具体反馈，并共同确定可执行的随访计划。',
    scores: [4.7, 4.5, 4.6, 4.6, 4.5, 4.4, 4.6, 4.5, 4.7, 4.6, 4.4, 4.6, 4.3, 4.5, 4.2, 4.6, 4.4, 4.4],
    messages: [
      { id: 'm1', role: 'patient', time: '2024-05-31 10:12', content: '按照上次说的做了睡眠记录，这周有三天能比较快入睡了。' },
      { id: 'm2', role: 'doctor', time: '2024-05-31 10:13', content: '你坚持记录做得很好。我看入睡时间提前了，白天精神状态有什么变化？' },
      { id: 'm3', role: 'patient', time: '2024-05-31 10:15', content: '上午注意力好多了，但加班到很晚时还是容易反复醒来。', evidence: 1 },
      { id: 'm4', role: 'doctor', time: '2024-05-31 10:17', content: '这说明规律作息对你有帮助。我们可以针对加班日再设计一个更简短的睡前放松流程。' },
      { id: 'm5', role: 'patient', time: '2024-05-31 10:18', content: '好，我也想把午休控制在半小时以内。' },
      { id: 'm6', role: 'doctor', time: '2024-05-31 10:20', content: '可以，接下来继续记录一周。若白天功能再次明显下降，我们再及时评估并调整计划。' },
    ],
  },
  {
    id: 'C202406300076', doctor: '刘医生', patient: '来访者 05', updatedAt: '2024-05-30 15:20', status: 'pending', score: 4.1,
    summary: '医生能够接纳来访者的矛盾感受，并帮助其区分自身需求与关系期待。',
    scores: [4.2, 4.0, 4.1, 4.0, 4.1, 4.3, 4.5, 4.4, 4.2, 4.3, 4.6, 4.2, 3.9, 4.0, 3.8, 4.0, 4.1, 4.2],
    messages: [
      { id: 'm1', role: 'patient', time: '2024-05-30 15:20', content: '我和家人沟通时总是吵架，事后又觉得很内疚。' },
      { id: 'm2', role: 'doctor', time: '2024-05-30 15:22', content: '争吵后的内疚让你很矛盾。最近一次争吵是怎么开始的，当时你最希望被理解的是什么？' },
      { id: 'm3', role: 'patient', time: '2024-05-30 15:24', content: '他们替我做了决定，我觉得自己没有选择权，但又不忍心让他们难过。', evidence: 1 },
      { id: 'm4', role: 'doctor', time: '2024-05-30 15:27', content: '你既希望维护关系，也希望自己的意愿被尊重。我们可以练习怎样把这两部分同时表达清楚。' },
      { id: 'm5', role: 'patient', time: '2024-05-30 15:29', content: '我想先试着说出自己的安排，而不是马上反驳他们。' },
      { id: 'm6', role: 'doctor', time: '2024-05-30 15:31', content: '这是一个具体的开始。你可以先写下希望表达的三句话，我们下次一起看看沟通时的感受。' },
    ],
  },
  {
    id: 'C202406300075', doctor: '赵医生', patient: '来访者 06', updatedAt: '2024-05-30 09:40', status: 'completed', score: 4.3,
    summary: '医生对突发不适进行了细致询问，解释清晰，并提供了明确的就医与观察建议。',
    scores: [4.4, 4.5, 4.3, 4.1, 4.4, 4.2, 4.5, 4.6, 4.4, 4.3, 4.5, 4.4, 4.2, 4.3, 4.1, 4.4, 4.0, 4.3],
    messages: [
      { id: 'm1', role: 'patient', time: '2024-05-30 09:40', content: '昨天突然心跳很快、呼吸急促，持续了十几分钟，我很害怕。' },
      { id: 'm2', role: 'doctor', time: '2024-05-30 09:41', content: '突然经历这些确实会让人害怕。当时是否伴随胸痛、晕厥？以前做过身体检查吗？' },
      { id: 'm3', role: 'patient', time: '2024-05-30 09:43', content: '没有晕过去，休息后慢慢缓解了，最近体检也没有发现异常。', evidence: 1 },
      { id: 'm4', role: 'doctor', time: '2024-05-30 09:45', content: '建议先按医嘱排除身体原因。如果再次发作，可以记录诱因和持续时间，暂时到安全安静的地方休息。' },
      { id: 'm5', role: 'patient', time: '2024-05-30 09:46', content: '好的，那我需要马上再去医院检查吗？' },
      { id: 'm6', role: 'doctor', time: '2024-05-30 09:48', content: '如果再次出现持续胸痛、意识不清或症状明显加重，请立即就医。目前也建议尽快预约门诊做进一步评估。' },
    ],
  },
]

function cloneSession(seed: SessionSeed, index: number): WorkspaceSession {
  const cycle = Math.floor(index / seeds.length)
  const baseId = seed.id.replace(/^C\d{8}/, '')
  const copy: SessionSeed = {
    ...seed,
    id: cycle ? `C202406${String(15 + index).padStart(2, '0')}${baseId.slice(-4)}` : seed.id,
    updatedAt: cycle ? seed.updatedAt.replace('2024-05', '2024-06').replace('2024-06-01', '2024-06-12') : seed.updatedAt,
    messages: seed.messages.map((message) => ({ ...message, id: `s${index + 1}-${message.id}` })),
  }
  const { scores: _scores, ...session } = copy
  return { ...session, groups: makeGroups(copy) }
}

export function createWorkspaceSessions(): WorkspaceSession[] {
  return Array.from({ length: 12 }, (_, index) => cloneSession(seeds[index % seeds.length]!, index))
}

export const workspaceStatusText: Record<WorkspaceStatus, string> = {
  completed: '已完成',
  evaluating: '评估中',
  pending: '待评估',
}
