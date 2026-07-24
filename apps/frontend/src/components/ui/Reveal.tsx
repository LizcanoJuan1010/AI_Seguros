import { useEffect, useRef, type ReactNode } from 'react'

type RevealProps = {
  children: ReactNode
  /** Retardo escalonado en ms (var CSS --reveal-delay). */
  delay?: number
  className?: string
}

/**
 * Aparición al hacer scroll: el contenido entra con fade + desplazamiento
 * cuando el bloque se hace visible (IntersectionObserver, una sola vez).
 * Estilos en index.css (.reveal / .is-visible); respeta reduced-motion.
 */
export function Reveal({ children, delay = 0, className = '' }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (typeof IntersectionObserver === 'undefined') {
      node.classList.add('is-visible')
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={`reveal ${className}`}
      style={delay ? ({ '--reveal-delay': `${delay}ms` } as React.CSSProperties) : undefined}
    >
      {children}
    </div>
  )
}
