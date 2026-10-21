// 环节：前端 API 接入层；用途：封装医生画像与监测预警接口调用。
import { request } from '../client/http'
import { DoctorProfileSchema, MonitoringListSchema } from '../contracts/monitoring'

export const monitoringApi = {
  doctors: (days = 180) => request(`/api/v1/monitoring/doctors?days=${days}`, MonitoringListSchema),
  profile: (doctorId: string, days = 180) =>
    request(
      `/api/v1/monitoring/doctors/${encodeURIComponent(doctorId)}?days=${days}`,
      DoctorProfileSchema,
    ),
}
