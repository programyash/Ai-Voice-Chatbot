import { chromium } from 'playwright'
import { resolve } from 'node:path'

const sample = resolve('..', 'tmp', 'live-input.wav')
const browser = await chromium.launch({
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${sample}`],
})
try {
  const context = await browser.newContext({ permissions: ['microphone'], viewport: { width: 1200, height: 900 } })
  const page = await context.newPage()
  const errors = []
  const frames = { sentAudio: 0, receivedAudio: 0, receivedErrors: 0 }
  page.on('pageerror', error => errors.push(error.message))
  page.on('websocket', socket => {
    socket.on('framesent', frame => { if (typeof frame.payload === 'string' && frame.payload.includes('"type":"audio"')) frames.sentAudio++ })
    socket.on('framereceived', frame => {
      if (typeof frame.payload === 'string' && frame.payload.includes('"type":"audio"')) frames.receivedAudio++
      if (typeof frame.payload === 'string' && frame.payload.includes('"type":"error"')) frames.receivedErrors++
    })
  })
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Start voice conversation' }).click()
  await page.locator('.message.user').first().waitFor({ timeout: 30000 }).catch(() => {})
  const transcript = (await page.locator('.message.user').first().count()) ? (await page.locator('.message.user').first().innerText()).slice(0, 240) : ''
  await page.locator('.message.assistant').first().waitFor({ timeout: 30000 }).catch(() => {})
  const response = (await page.locator('.message.assistant').first().count()) ? (await page.locator('.message.assistant').first().innerText()).slice(0, 240) : ''
  const status = await page.locator('.connection').innerText()
  const errorBanner = (await page.locator('.error-banner').count()) ? await page.locator('.error-banner').innerText() : ''
  await page.screenshot({ path: resolve('..', 'tmp', 'voice-check.png') })
  if (await page.getByRole('button', { name: 'Stop voice conversation' }).count()) await page.getByRole('button', { name: 'Stop voice conversation' }).click()
  console.log(JSON.stringify({ transcript, response, status, errorBanner, frames, errors }, null, 2))
  if (errors.length || !transcript || !response || frames.receivedAudio === 0) process.exitCode = 1
  await context.close()
} finally {
  await browser.close()
}
