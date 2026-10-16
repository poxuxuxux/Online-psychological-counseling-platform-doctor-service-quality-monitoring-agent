// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../src/api/endpoints/evaluations'
import { useConsole } from '../../src/composables/useConsole'
import { ConsultationDetailSchema } from '../../src/api/contracts/consultations'
import { previewSession, previewReport } from '../../src/data/preview'
vi.mock('../../src/api/endpoints/evaluations', () => ({
  api: {
    demo: vi.fn(),
    consultation: vi.fn(),
    consultations: vi.fn(),
    evaluate: vi.fn(),
    health: vi.fn(),
    ready: vi.fn(),
    recent: vi.fn(),
  },
}))
beforeEach(() => vi.resetAllMocks())
const detail = (index: number) => {
  const session = previewSession(index)
  return { session, report: previewReport(session) }
}
describe('consultation detail ownership', () => {
  it('keeps the explicit built-in demo usable when the configured database is empty', async () => {
    vi.mocked(api.consultations).mockResolvedValue({
      database_configured: true,
      total: 0,
      items: [],
    })
    vi.mocked(api.demo).mockResolvedValue(previewSession())
    const state = useConsole()
    await state.loadSession()
    expect(state.listSource.value).toBe('demo')
    expect(state.session.value?.messages).toHaveLength(6)
    expect(state.report.value).toBeNull()
    expect(api.consultation).not.toHaveBeenCalled()
  })
  it('drops an outstanding service detail after switching to offline mode', async () => {
    const second = detail(1)
    let finish!: (value: typeof second) => void
    vi.mocked(api.consultation).mockReturnValue(new Promise((resolve) => (finish = resolve)))
    const state = useConsole()
    const pending = state.selectConsultation(second.session.session_id)
    await state.setMode('preview')
    finish(second)
    await pending
    expect(state.session.value?.session_id).toBe('preview-synthetic-001')
    expect(state.report.value?.session_id).toBe('preview-synthetic-001')
    expect(state.listSource.value).toBe('preview')
  })
  it('reads a saved report without submitting another evaluation', async () => {
    const result = detail(1)
    vi.mocked(api.consultations).mockResolvedValue({
      database_configured: true,
      total: 1,
      items: [
        {
          session_id: result.session.session_id,
          consultation_round: 'initial',
          message_count: 6,
          updated_at: '',
          evaluation_status: 'completed',
        },
      ],
    })
    vi.mocked(api.consultation).mockResolvedValue(result)
    const state = useConsole()
    await state.loadSession()
    expect(state.listSource.value).toBe('database')
    expect(state.report.value?.session_id).toBe(result.session.session_id)
    expect(api.evaluate).not.toHaveBeenCalled()
  })
  it('rejects late responses after a different ID has been selected', async () => {
    const second = detail(1),
      third = detail(2)
    let finishSecond!: (value: typeof second) => void
    vi.mocked(api.consultation).mockImplementation((id) =>
      id === second.session.session_id
        ? new Promise((resolve) => (finishSecond = resolve))
        : Promise.resolve(third),
    )
    const state = useConsole()
    const pending = state.selectConsultation(second.session.session_id)
    expect(state.report.value).toBeNull()
    await state.selectConsultation(third.session.session_id)
    finishSecond(second)
    await pending
    expect(state.session.value?.session_id).toBe(third.session.session_id)
    expect(state.report.value?.evaluation_id).toBe(third.report.evaluation_id)
  })
  it('never pairs one consultation with another report', async () => {
    const bad = { session: previewSession(1), report: previewReport() }
    expect(ConsultationDetailSchema.safeParse(bad).success).toBe(false)
    vi.mocked(api.consultation).mockResolvedValue(bad)
    const state = useConsole()
    await state.selectConsultation(bad.session.session_id)
    expect(state.errors.value.session).toContain('不一致')
    expect(state.session.value).toBeNull()
    expect(state.report.value).toBeNull()
  })
  it('keeps a consultation without a report unscored', async () => {
    vi.mocked(api.consultation).mockResolvedValue({ session: previewSession(2), report: null })
    const state = useConsole()
    await state.selectConsultation('preview-synthetic-003')
    expect(state.session.value?.messages).toHaveLength(6)
    expect(state.report.value).toBeNull()
    expect(state.rows.value).toHaveLength(0)
  })
  it('does not fall back to demo data when the database list fails', async () => {
    vi.mocked(api.consultations).mockRejectedValue(new Error('database unavailable'))
    const state = useConsole()
    await state.refreshConsultations()
    expect(state.listSource.value).toBe('unavailable')
    expect(state.listError.value).toBe('database unavailable')
    expect(api.demo).not.toHaveBeenCalled()
  })
})
