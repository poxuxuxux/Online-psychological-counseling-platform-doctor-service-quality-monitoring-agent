export function downloadJson(value: unknown, name: string): void {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: 'application/json;charset=utf-8' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = name.replace(/[^\p{L}\p{N}._-]/gu, '_')
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
