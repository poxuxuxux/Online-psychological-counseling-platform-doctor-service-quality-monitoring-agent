// 环节：前端构建辅助层；用途：执行构建产物同步、预览启动或产物检查。
import { cp, readFile, readdir, writeFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve, relative } from 'node:path'
const frontend = fileURLToPath(new URL('..', import.meta.url))
const project = resolve(frontend, '..')
const source = resolve(frontend, 'dist'),
  target = resolve(project, 'app/web')
if (relative(project, target) !== 'app\\web' && relative(project, target) !== 'app/web')
  throw new Error('Unexpected target')
const html = await readFile(resolve(source, 'index.html'), 'utf8')
const assets = await readdir(resolve(source, 'assets'))
if (!assets.length || !html.includes('/assets/')) throw new Error('Build first; assets not found')
// Copy assets before switching the HTML entry point. Never delete existing teammate assets.
await mkdir(resolve(target, 'assets'), { recursive: true })
await cp(resolve(source, 'assets'), resolve(target, 'assets'), { recursive: true })
await writeFile(resolve(target, 'index.html'), html.replace(/\r\n?/g, '\n'))
console.log(`Frontend build synced to ${target}`)
