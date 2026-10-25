import { useId } from 'react'

// Original 2D garment study for the shell. Not retailer media, a 3D asset or fit evidence.
export function LookIllustration({
  variant = 'everyday',
}: {
  variant?: 'everyday' | 'evening'
}) {
  const uid = useId().replace(/:/g, '')
  const jacket = variant === 'evening' ? '#45433f' : '#b6b09b'
  return (
    <svg
      className="bm-look-illustration"
      viewBox="0 0 640 520"
      role="img"
      aria-labelledby={`${uid}-title ${uid}-desc`}
    >
      <title id={`${uid}-title`}>An original study in everyday dressing</title>
      <desc id={`${uid}-desc`}>
        A softly tailored sage jacket, ivory knit, charcoal trousers and brown
        loafers, arranged as an illustrated flat lay. Fictional garments; no
        body or fit simulation.
      </desc>
      <defs>
        <linearGradient id={`${uid}-fabric`} x1="0" x2="1" y2="1">
          <stop stopColor={jacket} />
          <stop
            offset="1"
            stopColor={variant === 'evening' ? '#292c29' : '#8e9583'}
          />
        </linearGradient>
        <linearGradient id={`${uid}-trouser`} x1="0" x2="1">
          <stop stopColor="#414a42" />
          <stop offset=".5" stopColor="#586052" />
          <stop offset="1" stopColor="#363e38" />
        </linearGradient>
        <filter
          id={`${uid}-shadow`}
          x="-30%"
          y="-30%"
          width="160%"
          height="170%"
        >
          <feDropShadow
            dx="5"
            dy="11"
            stdDeviation="9"
            floodColor="#202720"
            floodOpacity=".16"
          />
        </filter>
      </defs>
      <g opacity=".2" stroke="#77776c" fill="none">
        <path d="M42 456H598M42 64H598" />
        <path d="M42 52v24m556-24v24M42 444v24m556-24v24" />
      </g>
      <g
        transform="translate(328 168) rotate(8)"
        filter={`url(#${uid}-shadow)`}
      >
        <path
          d="M28 5h151l-10 72-5 238-64 3-6-191-19 191-60-4L26 74Z"
          fill={`url(#${uid}-trouser)`}
          stroke="#333c34"
          strokeWidth="1.5"
        />
        <path
          d="M29 22h148M97 24l-3 72M42 30L30 76m132-46 8 43M64 79l-13 213m71-213 10 213"
          fill="none"
          stroke="#9caa91"
          strokeOpacity=".34"
        />
        <path d="M80 7v15m45-15v15" stroke="#2c352e" strokeWidth="4" />
        <circle cx="103" cy="13" r="3" fill="#acaa98" />
      </g>
      <g
        transform="translate(46 38) rotate(-8 160 180)"
        filter={`url(#${uid}-shadow)`}
      >
        <path
          d="m106 55 43-13h27l43 14 35 225-151 5Z"
          fill="#eeebe0"
          stroke="#d4cfc0"
        />
        <path
          d="M141 45q21 33 45 0M141 50q21 38 45 0"
          fill="none"
          stroke="#c8c0ae"
          strokeWidth="3"
        />
        <g stroke="#d9d3c4" strokeWidth="1">
          <path d="M131 94v156m13-158v160m13-154v152m13-151v149m13-153v155m13-165v166m13-174v171" />
        </g>
        <path
          d="m106 57-44 19-36 131 33 13 37-89-6 186 70 0 7-139 7 139 72-2-11-184 37 87 34-15-45-129-49-19-28 100-10 30-13-47Z"
          fill={`url(#${uid}-fabric)`}
          stroke="#777f6e"
          strokeWidth="1.5"
        />
        <path
          d="m116 44-22 68 43 32-14 24 36 72 3-66Zm69 1 39 65-45 34 12 24-29 72 8-77Z"
          fill={jacket}
          stroke="#818a77"
          strokeWidth="1.5"
        />
        <path
          d="m101 247 43-3-2 42-39 1Zm89-4 38 0-1 42-36 0ZM61 198l-29-7m242 0 23-7M99 129l5 98m121-99-3 93"
          fill="none"
          stroke="#6e7868"
          strokeWidth="1.5"
        />
        <g fill="#5b6656">
          <circle cx="171" cy="209" r="3" />
          <circle cx="170" cy="247" r="3" />
          <circle cx="169" cy="284" r="3" />
        </g>
        <path d="m99 310 47-1m38 0h54" stroke="#ced1bd" strokeWidth="1" />
      </g>
      <g
        transform="translate(151 391) rotate(-17)"
        filter={`url(#${uid}-shadow)`}
      >
        <path
          d="M8 32Q0-4 24-9h80q23 8 11 36l-8 8H20Z"
          fill="#574b3b"
          stroke="#392f26"
          strokeWidth="2"
        />
        <path
          d="M13 30q51 10 95-2"
          fill="none"
          stroke="#282a24"
          strokeWidth="8"
        />
        <path d="M20 9q28-13 50-5l6 24-48-1Z" fill="#7e7058" stroke="#b29c78" />
        <path d="m72 5 15-5 11 23-22 5" fill="#473e32" />
        <g transform="translate(31 57)">
          <path
            d="M8 32Q0-4 24-9h80q23 8 11 36l-8 8H20Z"
            fill="#574b3b"
            stroke="#392f26"
            strokeWidth="2"
          />
          <path
            d="M13 30q51 10 95-2"
            fill="none"
            stroke="#282a24"
            strokeWidth="8"
          />
          <path
            d="M20 9q28-13 50-5l6 24-48-1Z"
            fill="#7e7058"
            stroke="#b29c78"
          />
          <path d="m72 5 15-5 11 23-22 5" fill="#473e32" />
        </g>
      </g>
      <g transform="translate(454 90) rotate(12)">
        <path
          d="M0 5q32-22 55 0m-23 7 13 1"
          stroke="#564e3e"
          strokeWidth="4"
          fill="none"
        />
        <rect
          x="0"
          y="2"
          width="26"
          height="19"
          rx="7"
          fill="#5e6456"
          stroke="#82775f"
          strokeWidth="3"
        />
        <rect
          x="38"
          y="2"
          width="26"
          height="19"
          rx="7"
          fill="#5e6456"
          stroke="#82775f"
          strokeWidth="3"
        />
      </g>
    </svg>
  )
}
