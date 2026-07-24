import { useEffect, useRef, useState } from 'react'

type CountUpProps = {
  end: number
  /** Duración de la animación en ms. */
  duration?: number
  /** Decimales a mostrar (default 0, comportamiento entero original). */
  decimals?: number
  prefix?: string
  suffix?: string
  className?: string
}

/**
 * Contador animado: cuenta de 0 al valor final cuando el elemento entra en
 * viewport (una sola vez, ease-out). Con reduced-motion o sin
 * IntersectionObserver muestra el valor final directamente.
 */
export function CountUp({
  end,
  duration = 1600,
  decimals = 0,
  prefix = '',
  suffix = '',
  className = '',
}: CountUpProps) {
  const factor = 10 ** decimals
  const ref = useRef<HTMLSpanElement>(null)
  const [value, setValue] = useState(0)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (
      typeof IntersectionObserver === 'undefined' ||
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      setValue(end)
      return
    }
    let raf = 0
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        observer.disconnect()
        const start = performance.now()
        const tick = (now: number) => {
          const progress = Math.min((now - start) / duration, 1)
          const eased = 1 - Math.pow(1 - progress, 3)
          setValue(Math.round(end * eased * factor) / factor)
          if (progress < 1) raf = requestAnimationFrame(tick)
        }
        raf = requestAnimationFrame(tick)
      },
      { threshold: 0.4 },
    )
    observer.observe(node)
    return () => {
      observer.disconnect()
      cancelAnimationFrame(raf)
    }
  }, [end, duration, factor])

  return (
    <span ref={ref} className={className}>
      {prefix}
      {value.toLocaleString('es-CO', { maximumFractionDigits: decimals })}
      {suffix}
    </span>
  )
}
