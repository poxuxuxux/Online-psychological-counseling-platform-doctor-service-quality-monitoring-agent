// 环节：前端 API 接入层；用途：封装 HTTP 通信及后端业务接口调用。
import type { z } from 'zod'

let privateAccessToken = ''
export function setPrivateAccessToken(value: string) {
  privateAccessToken = value.trim()
}
export function hasPrivateAccessToken() {
  return Boolean(privateAccessToken)
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
  timeout = 30000,
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(privateAccessToken && path.startsWith('/api/')
          ? { Authorization: `Bearer ${privateAccessToken}` } : {}),
        ...options.headers,
      },
      cache: 'no-store',
    })
    if (!response.ok) {
      // Do not surface validation bodies containing submitted consultation content.
      const messages: Record<number, string> = {
        400: '服务拒绝了当前请求，请确认使用合成演示数据。',
        401: '私有数据访问令牌无效，请在服务连接中重新设置。',
        403: '没有访问权限。',
        404: '该功能尚未在当前服务部署。',
        422: '数据格式与后端约定不一致，请检查消息编号和字段。',
        429: '请求过于频繁，请稍后再试。',
      }
      throw new ApiError(
        messages[response.status] || `服务暂时不可用（${response.status}），请稍后重试。`,
        response.status,
      )
    }
    let payload: unknown
    try {
      payload = await response.json()
    } catch {
      throw new ApiError('服务返回了无法识别的内容，请检查接口地址。')
    }
    const result = schema.safeParse(payload)
    if (!result.success) throw new ApiError('服务返回的数据格式不兼容，请让后端同学核对接口契约。')
    return result.data
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted)
      throw new ApiError('请求已超时。评估可能仍在服务端执行，请先查看最近记录，再决定是否重试。')
    throw new ApiError('无法连接服务，请检查网络或后端是否启动。')
  } finally {
    clearTimeout(timer)
  }
}
