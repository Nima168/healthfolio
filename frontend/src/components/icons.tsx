import { useId } from 'react'

/** Trash-can icon (inline SVG, no icon library needed). */
export function TrashIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M3 6h18" />
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M19 6l-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  )
}

const SECTION_PATHS: Record<string, string[]> = {
  '/': ['M3 3h7v9H3z', 'M14 3h7v5h-7z', 'M14 12h7v9h-7z', 'M3 16h7v5H3z'],
  '/timeline': ['M12 7v5l3 2', 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z'],
  '/documents': ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M14 3v5h5', 'M9 13h6M9 17h4'],
  '/medications': ['M10.5 20.5 3.5 13.5a5 5 0 0 1 7-7l7 7a5 5 0 0 1-7 7z', 'M8.5 8.5l7 7'],
  '/follow-ups': ['M4 6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z', 'M16 2v4M8 2v4M4 10h16', 'M9 15l2 2 4-4'],
  '/summaries': ['M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z', 'M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z'],
  '/alerts': ['M18 16H6l1.4-1.6A2 2 0 0 0 8 13V10a4 4 0 0 1 8 0v3a2 2 0 0 0 .6 1.4z', 'M10 19a2 2 0 0 0 4 0'],
  '/profile': ['M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M4 21a8 8 0 0 1 16 0'],
  '/settings': ['M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6z', 'M9.5 12l1.8 1.8L15 10'],
  '/status': ['M3 12h4l3-8 4 16 3-8h4'],
}

/** A small line icon for each section of the app (decorative; the label names the section). */
export function SectionIcon({ path }: { path: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {(SECTION_PATHS[path] ?? SECTION_PATHS['/']).map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}

/** The Healthfolio mark: a folder of records with a heartbeat line, on a blue-to-teal tile. */
export function BrandMark({ size = 34 }: { size?: number }) {
  const id = useId()
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b82f6" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#${id})`} />
      <path d="M8.5 13.5a2 2 0 0 1 2-2h6.2l2.6 3h10.2a2 2 0 0 1 2 2V27a2 2 0 0 1-2 2H10.5a2 2 0 0 1-2-2z" fill="#ffffff" />
      <path
        d="M11.5 22h4.2l1.9-3.6 2.8 6.6 2-3.9h6.1"
        fill="none"
        stroke="#2563eb"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
