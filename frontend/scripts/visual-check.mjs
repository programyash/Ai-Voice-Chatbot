import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'

const output = resolve('..', 'tmp')
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const results = []
try {
  for (const [name, width, height] of [['desktop', 1440, 1100], ['mobile', 390, 844]]) {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, isMobile: name === 'mobile', hasTouch: name === 'mobile' })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto('http://127.0.0.1:5173/', { waitUntil: 'networkidle' })
    await page.screenshot({ path: resolve(output, `${name}-playwright.png`), fullPage: true })
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }))
    await page.getByRole('button', { name: 'Project B', exact: true }).click()
    const projectSwitchWorks = await page.getByText('Everything within reach.').isVisible()
    await page.getByRole('button', { name: /Make an inquiry/i }).click()
    const inquiryWorks = await page.getByRole('dialog').isVisible()
    await page.getByRole('button', { name: 'Close inquiry' }).click()
    await page.getByRole('button', { name: 'Tell me about the villa plots' }).click()
    await page.locator('.message.assistant').waitFor()
    const textChatWorks = (await page.locator('.message.assistant').innerText()).length > 20
    results.push({ name, ...dimensions, projectSwitchWorks, inquiryWorks, textChatWorks, errors })
    await context.close()
  }
} finally {
  await browser.close()
}
console.log(JSON.stringify(results, null, 2))
if (results.some(x => x.document > x.viewport || !x.projectSwitchWorks || !x.inquiryWorks || !x.textChatWorks || x.errors.length)) process.exitCode = 1
