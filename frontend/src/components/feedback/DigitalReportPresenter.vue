<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Report } from '../../api/contracts/evaluation'
import { reportNarration, speechChunks, spokenReportText } from '../../utils/reportNarration'
import stillImage from '../../assets/digital-human/xiaojian-still.png'
import waveImage from '../../assets/digital-human/xiaojian-wave.webp'

const props = defineProps<{ report?: Report | null; demoText?: string; compact?: boolean }>()
const emit = defineEmits<{ playbackChange: [playing: boolean] }>()
type Playback = 'idle' | 'speaking' | 'paused' | 'complete' | 'error'
const playback = ref<Playback>('idle')
const supported = ref(false)
const voices = ref<SpeechSynthesisVoice[]>([])
const selectedVoice = ref('')
const speechRate = ref(0.98)
const chineseVoices = computed(() => voices.value.filter(voice => /^zh/i.test(voice.lang)))
const text = computed(() => props.demoText
  ? spokenReportText('你好，我是小鉴。以下是离线合成数据的演示播报，仅用于体验功能。\n\n' + props.demoText)
  : reportNarration(props.report ?? null))
const active = computed(() => playback.value === 'speaking' || playback.value === 'paused')
const status = computed(() => ({
  idle: text.value ? '报告已就绪，点击开始播报' : '等待评价报告',
  speaking: '正在播报当前报告',
  paused: '播报已暂停',
  complete: '本次播报已结束',
  error: '语音播放未完成，请重试或阅读下方播报内容',
})[playback.value])
let engine: SpeechSynthesis | undefined
let utterance: SpeechSynthesisUtterance | null = null
let generation = 0

function stop() {
  generation++
  if (utterance) {
    utterance.onend = null
    utterance.onerror = null
    utterance = null
    engine?.cancel()
  }
  playback.value = 'idle'
}

function start() {
  if (!engine || !text.value) return
  stop()
  const current = generation
  const chunks = speechChunks(text.value)
  const voice = chineseVoices.value.find(item => (item.voiceURI || item.name) === selectedVoice.value)
    || voices.value.find(item => /^zh/i.test(item.lang) && item.localService)
    || voices.value.find(item => /^zh/i.test(item.lang))
  let index = 0
  playback.value = 'speaking'
  function next() {
    if (current !== generation) return
    if (index >= chunks.length) {
      utterance = null
      playback.value = 'complete'
      return
    }
    utterance = new SpeechSynthesisUtterance(chunks[index++]!)
    utterance.lang = voice?.lang || 'zh-CN'
    if (voice) utterance.voice = voice
    utterance.rate = Number(speechRate.value)
    utterance.onend = next
    utterance.onerror = () => {
      if (current !== generation) return
      utterance = null
      playback.value = 'error'
    }
    engine!.speak(utterance)
  }
  next()
}

function togglePause() {
  if (!engine) return
  if (playback.value === 'speaking') {
    engine.pause()
    playback.value = 'paused'
  } else if (playback.value === 'paused') {
    engine.resume()
    playback.value = 'speaking'
  }
}
function loadVoices() {
  voices.value = engine?.getVoices() || []
}
onMounted(() => {
  supported.value = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  if (!supported.value) return
  engine = window.speechSynthesis
  loadVoices()
  engine.addEventListener('voiceschanged', loadVoices)
})
watch(text, stop)
watch(playback, value => emit('playbackChange', value === 'speaking'))
onBeforeUnmount(() => {
  stop()
  engine?.removeEventListener('voiceschanged', loadVoices)
})
</script>

<template>
  <section :class="['digital-presenter', { compact }]" aria-label="小鉴报告语音播报">
    <div class="presenter-portrait" aria-hidden="true">
      <span class="portrait-ring"></span>
      <picture>
        <source media="(prefers-reduced-motion: reduce)" :srcset="stillImage" />
        <img :src="playback === 'speaking' ? waveImage : stillImage" alt="" />
      </picture>
      <span class="presenter-name">心鉴助手 · 小鉴</span>
    </div>
    <div class="presenter-body">
      <span class="presenter-eyebrow">你的报告讲解员</span>
      <h2>让小鉴为你读报告</h2>
      <p class="presenter-description">听一听本次评价的结论与改进建议，也可以展开文字边听边看。</p>
      <p v-if="demoText" class="presenter-note">离线演示 · 以下内容来自预设合成报告</p>
      <p class="presenter-status" role="status">
        <span :class="['voice-indicator', { playing: playback === 'speaking' }]"><i></i><i></i><i></i><i></i></span>
        {{ status }}
      </p>
      <div class="presenter-controls">
        <button class="presenter-play" type="button" :disabled="!text || !supported || active" @click="start">
          {{ playback === 'complete' ? '再次播报' : '播报报告' }}
        </button>
        <button type="button" :disabled="!active" @click="togglePause">{{ playback === 'paused' ? '继续播报' : '暂停播报' }}</button>
        <button type="button" :disabled="!active" @click="stop">停止播报</button>
      </div>
      <div v-if="supported" class="presenter-settings">
        <label>中文音色
          <select v-model="selectedVoice" :disabled="active">
            <option value="">自动选择</option>
            <option v-for="voice in chineseVoices" :key="voice.voiceURI || voice.name" :value="voice.voiceURI || voice.name">
              {{ voice.name }}{{ voice.localService ? '（本地）' : '（在线）' }}
            </option>
          </select>
        </label>
        <label>语速
          <select v-model.number="speechRate" :disabled="active">
            <option :value="0.85">舒缓</option>
            <option :value="0.98">自然</option>
            <option :value="1.1">稍快</option>
          </select>
        </label>
      </div>
      <p v-if="!supported" class="presenter-note">当前浏览器暂不支持语音播报，你仍可阅读下方报告文字。</p>
      <p v-else class="presenter-note">使用浏览器或系统语音，中文音色及联网需求取决于当前设备。</p>
      <details v-if="text" class="presenter-transcript">
        <summary>查看播报内容</summary>
        <p>{{ text }}</p>
      </details>
    </div>
  </section>
</template>

<style scoped>
.digital-presenter { display: grid; grid-template-columns: 200px minmax(0, 1fr); overflow: hidden; border: 1px solid #dbe7de; border-radius: 18px; background: #fbfcf8; margin-top: 24px; color: #244d3e; }
.presenter-portrait { position: relative; display: flex; align-items: flex-end; justify-content: center; min-height: 300px; overflow: hidden; background: radial-gradient(ellipse at 50% 40%, #f9f5e6, #e4eee4); }
.portrait-ring { position: absolute; width: 230px; height: 230px; top: 32px; border: 1px solid #bfd4c4; border-radius: 50%; }
.presenter-portrait picture { display: block; position: relative; height: 280px; width: 190px; }
.presenter-portrait img { height: 100%; width: 100%; object-fit: contain; object-position: bottom; }
.presenter-name { position: absolute; bottom: 12px; background: #fffffff0; border-radius: 20px; padding: 6px 14px; font-size: 12px; letter-spacing: .06em; }
.presenter-body { padding: 28px 30px; min-width: 0; }
.presenter-eyebrow { color: #688271; font-size: 12px; letter-spacing: .12em; }
.presenter-body h2 { margin: 9px 0; font-size: 23px; font-weight: 600; }
.presenter-description { color: #657569; line-height: 1.8; font-size: 14px; margin: 0; }
.presenter-status { display: flex; align-items: center; gap: 10px; font-size: 13px; margin: 18px 0; }
.voice-indicator { height: 18px; display: inline-flex; align-items: center; gap: 3px; }
.voice-indicator i { display: block; width: 3px; height: 6px; border-radius: 4px; background: #50866c; }
.playing i { animation: voice-wave .8s ease-in-out infinite alternate; }
.playing i:nth-child(2) { animation-delay: -.2s; }
.playing i:nth-child(3) { animation-delay: -.5s; }
.playing i:nth-child(4) { animation-delay: -.3s; }
.presenter-controls { display: flex; flex-wrap: wrap; gap: 9px; }
.presenter-controls button { border: 1px solid #cbdcd0; border-radius: 9px; background: white; color: #315d47; padding: 10px 15px; cursor: pointer; font: inherit; font-size: 13px; }
.presenter-controls .presenter-play { background: #285b43; color: white; border-color: #285b43; }
.presenter-controls button:disabled { opacity: .45; cursor: default; }
.presenter-controls button:focus-visible, .presenter-transcript summary:focus-visible { outline: 3px solid #8eb59d; outline-offset: 3px; }
.presenter-note { font-size: 11px; color: #78877a; line-height: 1.7; margin: 12px 0; }
.presenter-settings { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 14px; font-size: 12px; }
.presenter-settings label { display: flex; align-items: center; gap: 8px; }
.presenter-settings select { max-width: 250px; padding: 6px; border: 1px solid #cbdcd0; border-radius: 6px; background: white; color: #315d47; }
.digital-presenter.compact { display: block; border: 0; margin: 0; border-radius: 0; }
.compact .presenter-portrait { display: none; }
.compact .presenter-body { padding: 20px; }
.compact .presenter-body h2 { font-size: 20px; }
.compact .presenter-eyebrow { display: none; }
.compact .presenter-settings select { max-width: 190px; }
.presenter-transcript { margin-top: 15px; font-size: 13px; border-top: 1px solid #e0e9df; padding-top: 12px; }
.presenter-transcript summary { cursor: pointer; }
.presenter-transcript p { white-space: pre-line; color: #586b5c; line-height: 1.9; max-height: 230px; overflow: auto; margin-bottom: 0; }
@keyframes voice-wave { to { height: 17px; } }
@media (prefers-reduced-motion: reduce) { .playing i { animation: none; height: 12px; } }
@media (max-width: 650px) {
  .digital-presenter { grid-template-columns: 1fr; }
  .presenter-portrait { min-height: 210px; }
  .presenter-portrait picture { height: 220px; }
  .presenter-body { padding: 22px; }
}
</style>
