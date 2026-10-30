// 环节：前端应用入口层；用途：启动并组合 Vue 工作台界面。
import { createApp } from 'vue'
import App from './App.vue'
import './styles/global.css'
import './styles/theme.css'
import './styles/reference.css'
import './styles/consultations.css'

createApp(App).mount('#app')
