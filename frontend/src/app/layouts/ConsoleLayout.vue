<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  Activity, ArrowUpRight, BookOpenText, ChevronDown, ClipboardList, Database,
  FileClock, LayoutDashboard, LogOut, Menu, PanelLeftClose, SearchCheck,
  ShieldAlert, ShieldCheck, X,
} from 'lucide-vue-next'
import { dataMode, service } from '../../api/service'

const route = useRoute()
const router = useRouter()
const mobileOpen = ref(false)
const signingOut = ref(false)
const navigation = [
  { label: '工作台总览', to: '/overview', icon: LayoutDashboard },
  { label: '评价任务', to: '/evaluations', icon: ClipboardList },
  { label: '服务质量监测', to: '/quality', icon: Activity },
  { label: '风险中心', to: '/risk-center', icon: ShieldAlert },
  { label: '质检指标', to: '/rubric', icon: BookOpenText },
  { label: '数据接入', to: '/integrations', icon: Database },
  { label: '审计日志', to: '/audit', icon: FileClock },
]
const title = computed(() => String(route.meta.title || '工作台'))
const eyebrow = computed(() => String(route.meta.eyebrow || '服务质量监测'))
const today = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())

async function signOut() {
  signingOut.value = true
  try {
    await service.signOut()
    await router.replace('/login')
  } catch {
    signingOut.value = false
  }
}
</script>

<template>
  <div class="shell">
    <button v-if="mobileOpen" class="mobile-scrim" aria-label="关闭导航" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ 'sidebar--open': mobileOpen }">
      <div class="brand">
        <span class="brand__mark"><ShieldCheck :size="24" :stroke-width="2.2" /></span>
        <span><strong>澄心质检</strong><small>服务质量监测平台</small></span>
        <button class="icon-button sidebar__close" aria-label="关闭导航" @click="mobileOpen = false"><X :size="18" /></button>
      </div>

      <div class="workspace-card">
        <div class="workspace-card__avatar">心</div>
        <div><strong>平台质检工作空间</strong><span>单操作员工作台</span></div>
        <ChevronDown :size="15" aria-hidden="true" />
      </div>

      <div class="nav-label">工作区域</div>
      <nav aria-label="主导航" class="nav-list">
        <RouterLink v-for="item in navigation" :key="item.to" :to="item.to" class="nav-link" :class="{ 'nav-link--active': route.path === item.to || (item.to === '/evaluations' && route.path.startsWith('/evaluations')) || (item.to === '/risk-center' && route.path.startsWith('/review/')) }" @click="mobileOpen = false">
          <component :is="item.icon" :size="18" :stroke-width="1.8" />
          <span>{{ item.label }}</span>
          <ArrowUpRight v-if="route.path === item.to" :size="14" class="nav-link__arrow" />
        </RouterLink>
      </nav>

      <div class="sidebar__bottom">
        <div class="sidebar-note"><SearchCheck :size="18" /><span>每项结论均应追溯到咨询证据</span></div>
        <button class="sidebar-user" :disabled="signingOut" @click="signOut">
          <span class="sidebar-user__avatar">质</span>
          <span><strong>质检操作员</strong><small>{{ dataMode === 'demo' ? '演示会话' : '平台工作空间' }}</small></span>
          <LogOut :size="17" />
        </button>
      </div>
    </aside>

    <div class="shell__main">
      <header class="topbar">
        <button class="icon-button mobile-menu" aria-label="打开导航" @click="mobileOpen = true"><Menu :size="21" /></button>
        <div class="topbar__title"><span>{{ eyebrow }}</span><b>/</b><strong>{{ title }}</strong></div>
        <div class="topbar__right">
          <span class="topbar__date">{{ today }}</span>
          <span v-if="dataMode === 'demo'" class="demo-pill"><span />合成数据演示</span>
          <span v-else class="api-pill">API 模式</span>
        </div>
      </header>
      <main id="main-content" class="main-content"><RouterView /></main>
      <footer class="main-footer"><PanelLeftClose :size="14" />仅用于平台内部质检辅助；模型结论需结合证据与人工复核。</footer>
    </div>
  </div>
</template>
