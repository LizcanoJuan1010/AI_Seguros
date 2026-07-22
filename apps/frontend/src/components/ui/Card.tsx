import type { HTMLAttributes, ReactNode } from 'react'

type CardProps = HTMLAttributes<HTMLDivElement> & {
  children: ReactNode
  glass?: boolean
}

export function Card({
  children,
  glass = false,
  className = '',
  ...props
}: CardProps) {
  return (
    <div
      className={`rounded-lg bg-surface-container-lowest soft-forest-shadow ${glass ? 'glass-card' : ''} ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
