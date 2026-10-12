import { readFile, readdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
const frontend = fileURLToPath(new URL('..', import.meta.url))
const dist = resolve(frontend, 'dist')
// A double-clickable preview must contain its local image assets too.
const images = new Map()
const mimeTypes = {
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
}
for (const name of await readdir(resolve(dist, 'assets'))) {
  const extension = name.slice(name.lastIndexOf('.')).toLowerCase()
  if (!mimeTypes[extension]) continue
  const bytes = await readFile(resolve(dist, 'assets', name))
  images.set(`/assets/${name}`, `data:${mimeTypes[extension]};base64,${bytes.toString('base64')}`)
}
function embedImages(source) {
  for (const [url, data] of images) source = source.split(url).join(data)
  return source
}
let html = await readFile(resolve(dist, 'index.html'), 'utf8')
const scripts = [...html.matchAll(/<script[^>]*src="([^"\s]+)"[^>]*><\/script>/g)]
const styles = [...html.matchAll(/<link[^>]*href="([^"\s]+\.css)"[^>]*>/g)]
if (scripts.length !== 1) throw new Error('Unexpected build entrypoint')
for (const match of scripts) {
  const js = embedImages(await readFile(resolve(dist, '.' + match[1]), 'utf8'))
  html = html.replace(
    match[0],
    () =>
      '<script>document.addEventListener("DOMContentLoaded",function(){\n' +
      js.replace(/<\/script/gi, '<\\/script') +
      '\n});</script>',
  )
}
for (const match of styles) {
  const css = embedImages(await readFile(resolve(dist, '.' + match[1]), 'utf8'))
  html = html.replace(match[0], () => '<style>' + css + '</style>')
}
await writeFile(resolve(frontend, '../frontend-preview.html'), html)
console.log('Created self-contained offline frontend-preview.html')
