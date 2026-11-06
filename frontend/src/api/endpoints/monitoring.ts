// 环节：前端 API 接入层；用途：封装医生画像与监测预警接口调用。
import { request } from '../client/http'
import { DoctorProfileSchema, MonitoringListSchema } from '../contracts/monitoring'

export const monitoringApi = {
  doctors: (startDate: string, endDate: string) =>
    request(
      `/api/v1/monitoring/doctors?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`,
      MonitoringListSchema,
    ),
  profile: (doctorId: string, startDate: string, endDate: string) =>
    request(
      `/api/v1/monitoring/doctors/${encodeURIComponent(doctorId)}?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`,
      DoctorProfileSchema,
    ),
}
