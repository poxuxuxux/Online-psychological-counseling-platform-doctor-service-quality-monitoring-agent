import { z } from 'zod'
import { request } from './client/http'
import { ReportSchema, type Session, type Report } from './contracts/evaluation'

const key = 'xin-heng-upload-jobs-v1'
const Entry = z.object({ job_id: z.string(), token: z.string(), fingerprint: z.string() })
const Status = z.object({
  job_id: z.string(), status: z.enum(['running', 'completed', 'interrupted']),
  stage: z.string(), model_calls: z.number(), elapsed_seconds: z.number(),
  report: ReportSchema.nullable(), error: z.string().nullable(),
  rejection_count: z.number().optional(),
})
export function savedGuestJobs() {
  try { return z.array(Entry).parse(JSON.parse(localStorage.getItem(key) || '[]')) }
  catch { return [] }
}
async function follow(entry: z.infer<typeof Entry>, update: (text: string) => void): Promise<Report> {
  for (;;) {
    let state: z.infer<typeof Status>
    try {
      state = await request(`/api/v1/guest/jobs/${entry.job_id}`, Status,
        { headers: { 'X-Guest-Token': entry.token } })
    } catch {
      throw new Error('任务进度查询暂时失败，任务编号已保存在本浏览器。请用“找回上传评价”查询，勿重复提交。')
    }
    update(`任务 ${entry.job_id.slice(0, 8)} · 阶段 ${state.stage} · ${state.model_calls} 次调用 · ${state.rejection_count || 0} 次校验拒收 · 已运行 ${Math.round(state.elapsed_seconds)} 秒`)
    if (state.report) return state.report
    if (state.status === 'interrupted')
      throw new Error('后台任务已中断，检查点已保存。请点击“继续中断任务”；恢复会继续调用模型并计费用。')
    await new Promise(resolve => setTimeout(resolve, 3000))
  }
}
export async function evaluateUploaded(session: Session, update: (text: string) => void, forceNew = false) {
  // Store only a local fingerprint and capability, never uploaded dialogue in browser storage.
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(session)))
  const fingerprint = Array.from(new Uint8Array(bytes), x => x.toString(16).padStart(2, '0')).join('')
  const entries = savedGuestJobs()
  const existing = entries.find(e => e.fingerprint === fingerprint)
  if (existing && !forceNew) return follow(existing, update)
  if (existing && forceNew) {
    const prior = await request(`/api/v1/guest/jobs/${existing.job_id}`, Status,
      { headers: { 'X-Guest-Token': existing.token } })
    if (prior.status === 'running')
      throw new Error('已有同一数据的任务正在运行，请先找回该任务，不能重复新建。')
  }
  update('正在新建后台评价任务…')
  const ready = await request('/ready', z.object({
    capabilities: z.object({ guest_jobs: z.boolean() }).optional(),
  }))
  if (!ready.capabilities?.guest_jobs)
    throw new Error('当前连接的是旧版后端，不支持后台上传任务。请停止旧服务，用本项目 scripts/run_backend.ps1 重启；此次未提交评价。')
  localStorage.setItem(key, JSON.stringify(entries)) // Check storage before starting a billed task.
  const created = await request('/api/v1/guest/jobs', z.object({ job_id: z.string(), token: z.string() }), {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(session),
  })
  const entry = { ...created, fingerprint }
  localStorage.setItem(key, JSON.stringify([entry, ...entries].slice(0, 20)))
  return follow(entry, update)
}
export async function recoverUpload(update: (text: string) => void, resume = false) {
  const entry = savedGuestJobs()[0]
  if (!entry) throw new Error('本浏览器尚未保存后台任务编号；旧版同步上传无法找回。')
  if (resume) await request(`/api/v1/guest/jobs/${entry.job_id}/resume`, z.object({ job_id: z.string() }), {
    method: 'POST', headers: { 'X-Guest-Token': entry.token },
  })
  return follow(entry, update)
}
