import Link from 'next/link'
export function Wordmark({ href = '/' }: { href?: string }) {
  return (
    <Link href={href} className="bm-wordmark" aria-label="Brand.Me home">
      Brand<span>.</span>Me<span className="bm-wordmark-period">®</span>
    </Link>
  )
}
