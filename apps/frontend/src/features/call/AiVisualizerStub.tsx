import { useEffect, useRef, useState } from 'react'

export type AiOrbState = 'listening' | 'speaking' | 'muted' | 'ended'

type Props = {
  /** Estado conversacional que anima el orbe (ondas, ojos, intensidad). */
  state?: AiOrbState
}

/**
 * Orbe de la asesora IA (estilo asistente de voz, paleta naturaleza):
 * esfera vidriosa con colores de bosque (petróleo, verde hoja, ámbar sol),
 * halo de partículas y ondas de sonido reactivas.
 *
 * Interactividad de los ojos:
 *  - siguen el cursor por toda la pantalla (y se agrandan al acercarse);
 *  - si no hay movimiento ~4s, entran en modo "mirar alrededor" (idle);
 *  - clic/tap sobre el orbe → guiño con rebote;
 *  - parpadean solos y "hablan" cuando el estado es speaking.
 * Animación en CSS (bloque "Orbe IA" de index.css); respeta reduced-motion.
 */
export function AiVisualizerStub({ state = 'listening' }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const idleRef = useRef<number | null>(null)
  const [wink, setWink] = useState(false)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    el.setAttribute('data-idle', '1')
    const clamp = (v: number) => Math.max(-1, Math.min(1, v))
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect()
      const dx = (e.clientX - (r.left + r.width / 2)) / (r.width / 2)
      const dy = (e.clientY - (r.top + r.height / 2)) / (r.height / 2)
      el.style.setProperty('--eye-x', `${(clamp(dx) * 9).toFixed(2)}%`)
      el.style.setProperty('--eye-y', `${(clamp(dy) * 7).toFixed(2)}%`)
      // Más cerca del orbe → ojos un poco más grandes (curiosidad).
      const dist = Math.min(1, Math.hypot(dx, dy) / 2.5)
      el.style.setProperty('--eye-scale', (1 + (1 - dist) * 0.18).toFixed(3))
      el.removeAttribute('data-idle')
      if (idleRef.current) window.clearTimeout(idleRef.current)
      idleRef.current = window.setTimeout(() => {
        el.style.setProperty('--eye-x', '0%')
        el.style.setProperty('--eye-y', '0%')
        el.style.setProperty('--eye-scale', '1')
        el.setAttribute('data-idle', '1')
      }, 4000)
    }
    window.addEventListener('pointermove', onMove)
    return () => {
      window.removeEventListener('pointermove', onMove)
      if (idleRef.current) window.clearTimeout(idleRef.current)
    }
  }, [])

  const doWink = () => {
    if (wink) return
    setWink(true)
    window.setTimeout(() => setWink(false), 650)
  }

  return (
    <div
      ref={wrapRef}
      onPointerDown={doWink}
      className={`ai-orb-wrap relative mb-6 cursor-pointer select-none ${wink ? 'is-wink' : ''}`}
      data-state={state}
      aria-hidden
    >
      <span className="ai-orb-ripple" />
      <span className="ai-orb-ripple r2" />
      <span className="ai-orb-ripple r3" />
      <span className="ai-orb-halo" />
      <span className="ai-orb-halo h2" />
      <div className="ai-orb">
        <span className="ai-orb-blob b1" />
        <span className="ai-orb-blob b2" />
        <span className="ai-orb-blob b3" />
        <span className="ai-orb-gloss" />
        <div className="ai-orb-eyes">
          <span />
          <span />
        </div>
      </div>
    </div>
  )
}
