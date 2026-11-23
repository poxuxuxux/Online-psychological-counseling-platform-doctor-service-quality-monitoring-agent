import { inject, type InjectionKey, type Ref, ref } from 'vue'

export type DateRange = { start: string; end: string }

export const dateRangeKey: InjectionKey<Ref<DateRange>> = Symbol('global-date-range')

const fallbackRange: DateRange = { start: '2024-06-01', end: '2024-06-30' }

export function useDateRange() {
  return inject(dateRangeKey, ref({ ...fallbackRange }))
}

export function isDateInRange(value: string | null | undefined, range: DateRange) {
  if (!value) return false
  const date = value.slice(0, 10)
  return date >= range.start && date <= range.end
}

export function rangeDayCount(range: DateRange) {
  if (!range.start || !range.end || range.start > range.end) return 0
  const start = new Date(`${range.start}T00:00:00Z`).getTime()
  const end = new Date(`${range.end}T00:00:00Z`).getTime()
  return Math.floor((end - start) / 86400000) + 1
}
