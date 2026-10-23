'use client'

import { useEffect, type RefObject } from 'react'

/** Keep page/scroll clearance equal to the rendered bar, including safe area and large text. */
export function useNavigationClearance(
  navigation: RefObject<HTMLElement>,
  publicPage: boolean,
) {
  useEffect(() => {
    const root = document.documentElement
    const bar = navigation.current
    const update = () => {
      const height =
        bar && !publicPage ? Math.ceil(bar.getBoundingClientRect().height) : 0
      root.style.setProperty('--bm-nav-occupied', `${height}px`)
    }
    update()
    const observer =
      typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(update)
    if (bar) observer?.observe(bar)
    window.addEventListener('resize', update)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', update)
      root.style.removeProperty('--bm-nav-occupied')
    }
  }, [navigation, publicPage])
}
