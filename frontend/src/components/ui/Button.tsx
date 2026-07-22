import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'cta' | 'ghost' | 'danger'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  children: ReactNode
}

const variantClass: Record<Variant, string> = {
  primary:
    'bg-primary text-on-primary hover:opacity-90 shadow-sm',
  cta: 'bg-amber-cta text-primary font-bold shadow-md shadow-amber-cta/20 hover:scale-[1.02] active:scale-95',
  ghost:
    'bg-transparent border-2 border-primary text-primary hover:bg-primary/5',
  danger: 'bg-error text-on-error hover:bg-error/90 shadow-lg',
}

export function Button({
  variant = 'primary',
  className = '',
  children,
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-label-md transition-all disabled:opacity-50 ${variantClass[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
