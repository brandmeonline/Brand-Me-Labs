/**
 * Wait until a page has settled before a capture. Full-page screenshots measure the document first and paint a
 * moment later; a client notice that grows in between (a resource leaving "Loading…" for its unavailable state
 * after hydration) left `consumer-1440x900-light.png` cut at 1803 of 1864 rows on runs 41098774318 and
 * 41503830686, whichever PR was under test. `networkidle` does not cover this: the fetches fail at once and
 * hydration can finish after the quiet window on a slow runner (reproduced locally with the CPU throttled 8x).
 *
 * Settled means: fonts loaded, the experience-preferences provider has hydrated (both apps mark
 * `data-bm-preferences-ready`), no resource notice is still loading (`data-bm-resource="loading"`, or a
 * status whose text starts with "Loading"), every image is decoded, and the document height has not changed
 * for three consecutive animation frames.
 */
export async function settled(page) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForFunction(
    () => document.documentElement.dataset.bmPreferencesReady === 'true',
  )
  await page.waitForFunction(
    () =>
      !document.querySelector('[data-bm-resource="loading"]') &&
      ![...document.querySelectorAll('[role="status"]')].some((element) =>
        /^\s*Loading/.test(element.textContent || ''),
      ),
  )
  await page.waitForFunction(() =>
    [...document.images].every((image) => image.complete),
  )
  await page.waitForFunction(
    () =>
      new Promise((resolve) => {
        let last = -1
        let unchanged = 0
        const tick = () => {
          const height = document.documentElement.scrollHeight
          unchanged = height === last ? unchanged + 1 : 0
          last = height
          if (unchanged >= 3) resolve(true)
          else requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      }),
  )
}
