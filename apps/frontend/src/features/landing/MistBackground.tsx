import { useEffect, useRef, useState } from 'react'
import { LiquidEffectAnimation } from '../../components/ui/LiquidEffectAnimation'

/**
 * Fondo ambiental fijo a pantalla completa detrás del contenido, en capas:
 *
 * 1. Video de bruma en loop (con poster estático mientras carga y para
 *    navegadores sin autoplay; se pausa con prefers-reduced-motion).
 * 2. En desktop, el efecto líquido WebGL (LiquidEffectAnimation) ondula el
 *    mismo fotograma de bruma por encima del video; si falla, el video
 *    queda visible.
 * 3. Overlays de legibilidad para el texto y los CTA ámbar.
 */
export function MistBackground() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [liquidEnabled, setLiquidEnabled] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => {
      if (reduced.matches) {
        video.pause()
      } else {
        // Algunos navegadores ignoran autoPlay si el tab arranca en segundo
        // plano o el atributo muted llega tarde; reintentar aquí lo cubre.
        video.play().catch(() => {})
      }
    }
    sync()
    reduced.addEventListener('change', sync)
    return () => reduced.removeEventListener('change', sync)
  }, [])

  // El shader líquido solo en pantallas grandes con motion permitido:
  // en móvil el costo de GPU no se justifica y el video basta.
  useEffect(() => {
    const mq = window.matchMedia(
      '(min-width: 1024px) and (prefers-reduced-motion: no-preference)',
    )
    const sync = () => setLiquidEnabled(mq.matches)
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      <video
        ref={videoRef}
        className="h-full w-full scale-105 object-cover"
        src="/assets/bg-mist.mp4"
        poster="/assets/bg-mist.jpg"
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        disablePictureInPicture
        tabIndex={-1}
      />
      {liquidEnabled && (
        <LiquidEffectAnimation className="absolute inset-0" />
      )}
      <div className="absolute inset-0 bg-background/60" />
      <div className="mist-overlay absolute inset-0" />
    </div>
  )
}
