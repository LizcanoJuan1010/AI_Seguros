import type { HTMLAttributes, ReactNode } from 'react'

type ChipProps = HTMLAttributes<HTMLSpanElement> & {
  children: ReactNode
  tone?: 'neutral' | 'hot' | 'warm' | 'cold' | 'success' | 'amber'
}

const toneClass: Record<NonNullable<ChipProps['tone']>, string> = {
  neutral: 'bg-surface-variant text-outline',
  hot: 'bg-error-container text-on-error-container',
  warm: 'bg-secondary-fixed text-on-secondary-container',
  cold: 'bg-surface-variant text-outline',
  success: 'bg-primary-fixed text-primary',
  amber: 'bg-amber-cta/20 text-on-secondary-fixed-variant',
}

export function Chip({
  children,
  tone = 'neutral',
  className = '',
  ...props
}: ChipProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-label-sm font-bold ${toneClass[tone]} ${className}`}
      {...props}
    >
      {children}
    </span>
  )
}
