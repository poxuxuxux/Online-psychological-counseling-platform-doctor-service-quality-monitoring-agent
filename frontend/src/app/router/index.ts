import { createRouter, createWebHistory } from 'vue-router'
import { service } from '../../api/service'
import ConsoleLayout from '../layouts/ConsoleLayout.vue'
import LoginPage from '../../modules/auth/pages/LoginPage.vue'
import OverviewPage from '../../modules/overview/pages/OverviewPage.vue'
import EvaluationRunsPage from '../../modules/evaluation-runs/pages/EvaluationRunsPage.vue'
import RunDetailPage from '../../modules/evaluation-runs/pages/RunDetailPage.vue'
import RiskCenterPage from '../../modules/risk-center/pages/RiskCenterPage.vue'
import ReviewWorkbenchPage from '../../modules/review-workbench/pages/ReviewWorkbenchPage.vue'
import QualityMonitoringPage from '../../modules/quality-monitoring/pages/QualityMonitoringPage.vue'
import RubricPage from '../../modules/rubric-admin/pages/RubricPage.vue'
import IntegrationsPage from '../../modules/integrations/pages/IntegrationsPage.vue'
import AuditLogPage from '../../modules/audit-log/pages/AuditLogPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginPage, meta: { public: true } },
    {
      path: '/',
      component: ConsoleLayout,
      children: [
        { path: '', redirect: '/overview' },
        { path: 'overview', name: 'overview', component: OverviewPage, meta: { title: '工作台总览', eyebrow: '工作台' } },
        { path: 'evaluations', name: 'evaluations', component: EvaluationRunsPage, meta: { title: '评价任务', eyebrow: '任务管理' } },
        { path: 'evaluations/:id', name: 'run-detail', component: RunDetailPage, meta: { title: '任务详情', eyebrow: '任务管理' } },
        { path: 'risk-center', name: 'risk-center', component: RiskCenterPage, meta: { title: '风险中心', eyebrow: '待核实线索' } },
        { path: 'review/:id', name: 'review', component: ReviewWorkbenchPage, meta: { title: '人工复核', eyebrow: '复核工作台' } },
        { path: 'quality', name: 'quality', component: QualityMonitoringPage, meta: { title: '服务质量监测', eyebrow: '分析概览' } },
        { path: 'rubric', name: 'rubric', component: RubricPage, meta: { title: '质检指标', eyebrow: '规则与版本' } },
        { path: 'integrations', name: 'integrations', component: IntegrationsPage, meta: { title: '数据接入', eyebrow: '数据管理' } },
        { path: 'audit', name: 'audit', component: AuditLogPage, meta: { title: '审计日志', eyebrow: '操作留痕' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/overview' },
  ],
})

router.beforeEach((to) => {
  if (!to.meta.public && !service.isAuthenticated()) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.name === 'login' && service.isAuthenticated()) return { name: 'overview' }
})
