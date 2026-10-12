<script setup lang="ts">
import { ArrowRight, Database, FileSpreadsheet, LockKeyhole, PlugZap } from 'lucide-vue-next'
import { dataMode } from '../../../api/service'
</script>

<template>
  <div class="page-stack"><div class="page-heading"><span class="eyebrow">DATA INTEGRATION</span><h1>数据接入</h1><p>管理授权咨询数据的导入与规范化，确保每份报告只评价一次咨询轮次。</p></div><div class="integration-grid"><section class="panel integration-card"><span class="integration-card__icon"><FileSpreadsheet :size="25" /></span><h2>咨询记录导入</h2><p>计划接入项目数据适配器：先校验来源、切分订单或咨询轮次，再进行脱敏和预检。</p><div class="integration-card__state"><span class="status-badge status-badge--amber"><span class="status-dot" />后端接口待接入</span></div><button class="button button--secondary" disabled>导入文件 · 即将开放</button></section><section class="panel integration-card"><span class="integration-card__icon integration-card__icon--green"><Database :size="25" /></span><h2>合成演示样例</h2><p>当前前端内置合成对话，仅用于展示任务、证据定位与人工复核交互。</p><div class="integration-card__state"><span class="status-badge status-badge--green"><span class="status-dot" />{{ dataMode === 'demo' ? '演示模式可用' : '仅开发演示可用' }}</span></div><RouterLink to="/evaluations" class="button button--secondary">查看演示任务<ArrowRight :size="16" /></RouterLink></section></div><div class="panel integration-safety"><div><PlugZap :size="21" /><h2>数据接入边界</h2></div><ul><li>原始聊天线程需按订单或咨询轮次切分，不将跨期记录合并为一次评价。</li><li>复诊历史必须经过可信匿名身份关联和平台授权；历史片段只作背景。</li><li>真实对话应先完成脱敏，敏感原文和密钥不进入前端配置或浏览器日志。</li></ul><span><LockKeyhole :size="16" />真实数据导入由后端授权、校验与审计控制</span></div></div>
</template>
