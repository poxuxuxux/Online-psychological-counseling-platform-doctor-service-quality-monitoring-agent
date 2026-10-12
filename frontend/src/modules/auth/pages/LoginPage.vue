<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, LockKeyhole, ShieldCheck, Sparkles } from 'lucide-vue-next'
import { dataMode, service } from '../../../api/service'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function enter() {
  busy.value = true
  error.value = ''
  try {
    await service.signIn(username.value, password.value)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/overview'
    await router.replace(next)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-screen">
    <section class="login-intro">
      <div class="login-intro__brand"><span><ShieldCheck :size="25" /></span>澄心质检</div>
      <div class="login-intro__content">
        <span class="login-intro__eyebrow"><Sparkles :size="15" />线上心理咨询服务质量监测</span>
        <h1>让每一项评价<br />都有据可循。</h1>
        <p>从咨询过程到证据核验，再到人工复核，让平台看见服务质量，也看清每个结论的依据。</p>
        <div class="login-intro__steps"><span>01 过程评价</span><i /><span>02 证据追溯</span><i /><span>03 人工把关</span></div>
      </div>
      <div class="login-intro__foot">服务质量监测 · 单平台工作空间</div>
    </section>

    <section class="login-panel">
      <div class="login-panel__inner">
        <div class="login-panel__icon"><LockKeyhole :size="23" /></div>
        <div class="eyebrow">平台操作员入口</div>
        <h2>欢迎进入工作台</h2>
        <p class="muted">查看评价任务、核对咨询证据并处理待复核案件。</p>

        <form v-if="dataMode === 'api'" class="login-form" @submit.prevent="enter">
          <label>操作员账号<input v-model="username" autocomplete="username" required placeholder="请输入账号" /></label>
          <label>密码<input v-model="password" type="password" autocomplete="current-password" required placeholder="请输入密码" /></label>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button class="button button--primary button--wide" :disabled="busy" type="submit">{{ busy ? '正在验证…' : '登录工作台' }}<ArrowRight :size="17" /></button>
        </form>
        <div v-else class="login-form">
          <div class="notice notice--blue"><strong>合成数据演示</strong><span>此模式不连接真实患者数据，也不执行模型评价。所有案例和结果仅用于前端联调。</span></div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button class="button button--primary button--wide" :disabled="busy" @click="enter">进入演示工作台<ArrowRight :size="17" /></button>
        </div>
        <div class="login-panel__security"><ShieldCheck :size="16" />真实业务模式下，登录与数据访问均由后端校验。</div>
      </div>
    </section>
  </div>
</template>
