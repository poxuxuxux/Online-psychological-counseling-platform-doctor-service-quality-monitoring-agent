<script setup lang="ts">
import { computed } from 'vue'
import type { Report, Session } from '../../api/contracts/evaluation'
import { relatedFindings, localReference, type Row } from '../../utils/trust'
import { agentName, label, metricName } from '../../utils/catalog'
import Icon from '../base/Icon.vue'
import StatusBadge from '../base/StatusBadge.vue'
const props = defineProps<{ row: Row; report: Report; session: Session | null }>()
defineEmits<{ focus: [ids: string[]] }>()
const v = computed(() => props.row.verification)
const versions = computed(() => relatedFindings(props.report, props.row.finding))
const discussions = computed(() =>
  props.report.discussions.filter((d) => versions.value.some((f) => f.finding_id === d.finding_id)),
)
const decisions = computed(() =>
  props.report.arbitration_decisions.filter((d) =>
    d.metric_ids.includes(props.row.finding.metric_id),
  ),
)
const claimResults = computed(() => new Map(v.value?.claim_results.map((c) => [c.claim_id, c])))
const checks = computed(() => [
  ['原文定位', label(v.value?.reference_status)],
  ['指标适用性', label(v.value?.applicability_status)],
  ['评分锚点', label(v.value?.rubric_status)],
  ['事实支持', label(v.value?.support_status)],
])
</script>
<template>
  <div class="finding-detail">
    <div class="detail-title">
      <div>
        <span class="metric-code">{{ row.finding.metric_id }}</span>
        <h3>{{ metricName(row.finding.metric_id) }}</h3>
      </div>
      <StatusBadge :tone="row.verdict.tone">{{ row.verdict.text }}</StatusBadge>
    </div>
    <p class="detail-meta">
      {{ agentName(row.agentId) }} · {{ row.finding.metric_version || '版本未提供' }} ·
      {{ row.finding.attempt ? '修订评价' : '初次评价' }}
    </p>
    <p class="rationale">{{ row.finding.rationale }}</p>
    <div
      v-if="row.finding.score !== null && row.finding.applicability === 'applicable'"
      class="candidate-score"
    >
      <span>{{ row.verdict.code === 'verified' ? '核验后分数' : 'Agent 初评分' }}</span
      ><strong>{{ row.finding.score.toFixed(1) }}<small> / 5</small></strong
      ><span v-if="row.verdict.code !== 'verified'">未进入确定性评分</span>
    </div>
    <section class="detail-section">
      <h4>
        原文证据 <span>{{ row.finding.evidence.length }}</span>
      </h4>
      <div v-for="(e, index) in row.finding.evidence" :key="index" class="evidence-quote">
        <blockquote>{{ e.quote || '未提供引文' }}</blockquote>
        <p>{{ e.explanation }}</p>
        <div class="evidence-actions">
          <button
            v-for="id in e.message_ids"
            :key="id"
            class="text-button"
            @click="$emit('focus', [id])"
          >
            <Icon name="link" :size="15" />{{ id }}<Icon name="chevron" :size="14" />
          </button>
        </div>
        <small :class="{ 'error-text': !localReference(e, session).valid }">{{
          localReference(e, session).reason
        }}</small>
        <small v-if="e.media_time_ranges.length"
          >媒体区间：{{
            e.media_time_ranges.map((t) => `${t.start_seconds}–${t.end_seconds} 秒`).join('；')
          }}。当前未配置受控媒体播放器。</small
        >
      </div>
      <p v-if="!row.finding.evidence.length" class="empty-note">
        {{
          row.finding.applicability === 'not_applicable'
            ? '本项标记为不适用；适用性依据仍需单独核查。'
            : '缺少本次会话证据，不能将初评分作为确定性结论。'
        }}
      </p>
    </section>
    <section class="detail-section">
      <h4>证据核验</h4>
      <p v-if="!v" class="notice">
        后端尚未返回本项的结构化核验结果。能找到原话，不代表语义和评分依据已经核验。
      </p>
      <template v-else
        ><dl class="verification-grid">
          <div v-for="[name, value] in checks" :key="name">
            <dt>{{ name }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <p v-if="v.reference_conflict" class="notice danger">
          参考材料存在冲突，保留支持与反证，等待复核。
        </p>
        <div v-for="claim in v.claims" :key="claim.claim_id" class="claim-row">
          <div>
            <StatusBadge
              :tone="
                claimResults.get(claim.claim_id)?.status === 'supported'
                  ? 'success'
                  : claimResults.get(claim.claim_id)?.status === 'contradicted'
                    ? 'danger'
                    : 'warning'
              "
              >{{ label(claimResults.get(claim.claim_id)?.status) }}</StatusBadge
            >
            <p>{{ claim.statement }}</p>
            <small
              v-if="
                claim.subject_role || claim.time_scope || claim.negated || claim.qualifiers.length
              "
            >
              {{
                claim.subject_role
                  ? `主体：${{ doctor: '医生', patient: '咨询者', system: '系统', unknown: '角色未知' }[claim.subject_role]}。`
                  : ''
              }}
              {{ claim.time_scope ? `核验范围：${claim.time_scope}。` : '' }}
              {{ claim.negated ? '否定主张，需要核查材料完整性。' : '' }}
              {{ claim.qualifiers.join('；') }}
            </small>
            <small>{{ claimResults.get(claim.claim_id)?.rationale || '核验理由尚未提供' }}</small>
          </div>
          <div class="evidence-actions">
            <button
              v-for="(e, i) in [
                ...(claimResults.get(claim.claim_id)?.supporting_evidence || []),
                ...(claimResults.get(claim.claim_id)?.contradicting_evidence || []),
              ]"
              :key="i"
              class="text-button"
              @click="$emit('focus', e.message_ids)"
            >
              查看{{
                i < (claimResults.get(claim.claim_id)?.supporting_evidence.length || 0)
                  ? '支持'
                  : '反证'
              }}原文
            </button>
          </div>
        </div>
        <p v-if="!v.claims.length" class="empty-note">尚未返回逐事实核验记录。</p>
        <ul v-if="v.issues.length" class="issue-list">
          <li v-for="issue in v.issues" :key="issue">{{ issue }}</li>
        </ul>
        <p v-if="v.revision_request" class="notice">定向修正要求：{{ v.revision_request }}</p>
        <small>核验版本：{{ v.verifier_version || '未提供' }}</small>
      </template>
    </section>
    <section class="detail-section">
      <h4>评价修正与讨论</h4>
      <div v-if="versions.length > 1" class="revision-compare">
        <article v-for="f in versions" :key="f.finding_id">
          <span>{{ f.attempt ? '修订评价' : '原始评价' }}</span
          ><strong>{{ f.score === null ? '无确定分数' : `${f.score.toFixed(1)} / 5` }}</strong>
          <p>{{ f.rationale }}</p>
        </article>
      </div>
      <ol v-if="discussions.length" class="discussion-list">
        <li v-for="(d, i) in discussions" :key="i">
          <span class="discussion-marker" aria-hidden="true"></span
          ><strong>{{ label(d.role) }}</strong>
          <p>{{ d.text }}</p>
          <button
            v-if="d.message_ids.length"
            class="text-button"
            @click="$emit('focus', d.message_ids)"
          >
            回看讨论引用
          </button>
        </li>
      </ol>
      <p v-else class="empty-note">
        当前没有返回讨论记录。只有实际发生的定向质疑与回复才会显示在这里。
      </p>
    </section>
    <section class="detail-section">
      <h4>
        分歧仲裁 <StatusBadge>{{ label(report.arbitration_status) }}</StatusBadge>
      </h4>
      <article v-for="d in decisions" :key="d.conflict_id" class="arbitration-record">
        <strong>{{ label(d.status) }} · {{ label(d.adopted) }}</strong>
        <p>{{ d.rationale }}</p>
        <small v-if="d.requires_manual_review">仍需人工复核</small>
      </article>
      <p v-if="!decisions.length" class="empty-note">
        {{
          report.arbitration_status === 'not_needed'
            ? '本次未触发仲裁。'
            : '后端未提供本项的裁决记录，不能认定分歧已经解决。'
        }}
      </p>
    </section>
    <details v-if="row.finding.knowledge_refs.length" class="detail-section">
      <summary>指标知识依据（不属于咨询行为证据）</summary>
      <article v-for="ref in row.finding.knowledge_refs" :key="ref.source_id">
        <h4>{{ ref.title }}</h4>
        <p>{{ ref.excerpt }}</p>
        <small>{{ ref.version || '版本未提供' }}</small>
      </article>
    </details>
    <details v-if="row.finding.limitations.length" class="detail-section">
      <summary>本项限制与说明</summary>
      <ul class="issue-list">
        <li v-for="item in row.finding.limitations" :key="item">{{ item }}</li>
      </ul>
    </details>
  </div>
</template>
