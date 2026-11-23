<script setup lang="ts">
import { computed, ref } from 'vue'
import { z } from 'zod'
import { request } from '../../api/client/http'
import { SessionSchema, type Session } from '../../api/contracts/evaluation'

defineProps<{ disabled?: boolean }>()
const emit = defineEmits<{ imported: [session: Session] }>()
const file = ref<File | null>(null)
const busy = ref(false), error = ref(''), confirmed = ref(false)
const result = ref<{ text: string; duration_seconds: number; model: string; source_modality: 'audio' | 'video' } | null>(null)
const turns = ref<{ id: string; role: 'unknown' | 'doctor' | 'patient'; content: string }[]>([])
const canImport = computed(() => confirmed.value && turns.value.length > 0
  && turns.value.every(turn => turn.role !== 'unknown' && turn.content.trim()))
const transcriptSchema = z.object({
  text: z.string(), duration_seconds: z.number(), model: z.string(),
  source_modality: z.enum(['audio', 'video']),
})
function selectFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] || null
  result.value = null
  turns.value = []
  error.value = ''
  confirmed.value = false
}
async function transcribe() {
  if (!file.value || busy.value) return
  error.value = ''
  if (file.value.size > 64 * 1024 * 1024) {
    error.value = '单个文件最多64 MiB，请拆分后上传。'
    return
  }
  busy.value = true
  result.value = null
  turns.value = []
  confirmed.value = false
  try {
    const suffix = file.value.name.slice(file.value.name.lastIndexOf('.')).toLowerCase()
    result.value = await request('/api/v1/media/transcribe?format=' + encodeURIComponent(suffix), transcriptSchema, {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: file.value,
    }, 240_000)
    turns.value = [{ id: crypto.randomUUID(), role: 'unknown', content: result.value.text }]
  } catch (exc) { error.value = (exc as Error).message }
  finally { busy.value = false }
}
function addTurn() {
  confirmed.value = false
  turns.value.push({ id: crypto.randomUUID(), role: 'unknown', content: '' })
}
function splitLines() {
  turns.value = turns.value.flatMap(turn => turn.content.split(/\n+/).filter(text => text.trim()).map(content => ({
    id: crypto.randomUUID(), role: turn.role, content: content.trim(),
  })))
  confirmed.value = false
}
function importTranscript() {
  if (!canImport.value || !result.value) return
  const session = SessionSchema.parse({
    session_id: 'media-' + crypto.randomUUID(), source_id: 'user-confirmed-asr',
    history_complete: false, observation_complete: false, consultation_round: 'unknown',
    service_context: {
      transcript_source: result.value.source_modality, transcription_model: result.value.model,
      transcript_verified_by_user: true, speaker_roles_verified_by_user: true,
      media_duration_seconds: result.value.duration_seconds, timestamps_available: false,
      visual_analysis: false,
    },
    messages: turns.value.map((turn, index) => ({
      message_id: 'media-m' + index, sequence: index, role: turn.role,
      content: turn.content.trim(), modality: 'text', message_kind: 'dialogue', timestamp: null,
    })),
  })
  emit('imported', session)
  confirmed.value = false
  error.value = '转写会话已导入列表，可查看内容后点击评价。'
}
</script>

<template>
  <details class="media-import">
    <summary>导入语音 / 视频讲话（Qwen3-ASR）</summary>
    <p>单个文件最多5分钟、64 MiB。视频仅转写音轨讲话。点击“开始转写”会将音轨发送至阿里云百炼并产生调用费用。</p>
    <div class="media-actions">
      <input aria-label="选择语音或视频文件" type="file"
        accept=".wav,.mp3,.m4a,.mp4,.mov,.mkv,.webm,.ogg,.opus,.flac,.aac,.avi"
        :disabled="disabled || busy" @change="selectFile" />
      <button class="button secondary" type="button" :disabled="!file || busy || disabled" @click="transcribe">
        {{ busy ? '转写中，请等待…' : '开始转写' }}
      </button>
    </div>
    <p v-if="error" role="status">{{ error }}</p>
    <template v-if="result">
      <p>音轨 {{ Math.round(result.duration_seconds) }} 秒。请核对转写文字，并按讲话顺序拆分医生 / 患者话轮。本接口不自动标注角色或逐句时间。</p>
      <div v-for="(turn, index) in turns" :key="turn.id" class="media-turn">
        <label>第 {{ index + 1 }} 段角色
          <select v-model="turn.role" :disabled="disabled" @change="confirmed = false">
            <option value="unknown">请选择角色</option><option value="doctor">医生</option><option value="patient">患者</option>
          </select>
        </label>
        <textarea v-model="turn.content" :aria-label="'第' + (index + 1) + '段转写文字'" :disabled="disabled"
          rows="4" @input="confirmed = false"></textarea>
        <button type="button" class="text-button" :disabled="disabled" @click="turns.splice(index, 1); confirmed = false">删除这段</button>
      </div>
      <div class="media-actions">
        <button class="button secondary" type="button" :disabled="disabled" @click="addTurn">新增一段</button>
        <button class="button secondary" type="button" :disabled="disabled" @click="splitLines">按换行拆成多段</button>
      </div>
      <label class="media-confirm"><input v-model="confirmed" type="checkbox" :disabled="disabled" />我已核对文字和每段角色，确认可用于本次评价</label>
      <button class="button primary" type="button" :disabled="!canImport || disabled" @click="importTranscript">确认并导入会话</button>
    </template>
  </details>
</template>

<style scoped>
.media-import { padding: 16px 20px; border: 1px solid #d5e3d7; border-radius: 12px; background: #fbfcf8; margin: 16px 0; color: #365844; }
.media-import summary { font-weight: 600; cursor: pointer; }
.media-import p { font-size: 13px; line-height: 1.8; margin: 12px 0; }
.media-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 12px 0; }
.media-turn { margin: 16px 0; padding: 12px; border: 1px solid #dfe8dd; border-radius: 8px; }
.media-turn label { display: flex; gap: 10px; align-items: center; font-size: 13px; }
.media-turn select { padding: 5px; border: 1px solid #cbdcd0; border-radius: 5px; }
.media-turn textarea { display: block; width: 100%; box-sizing: border-box; margin: 10px 0; padding: 10px; border: 1px solid #cbdcd0; border-radius: 6px; font: inherit; font-size: 13px; line-height: 1.7; }
.media-confirm { display: flex; align-items: center; gap: 8px; margin: 14px 0; font-size: 13px; }
</style>
