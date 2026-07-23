import { useEffect, useRef, useState } from 'react'

/**
 * Librería WebGL (three.js) servida por CDN y cargada bajo demanda; no se
 * bundlea. Versión pineada para evitar cambios sorpresa.
 */
const LIQUID_LIB_URL =
  'https://cdn.jsdelivr.net/npm/threejs-components@0.0.22/build/backgrounds/liquid1.min.js'

type LiquidEffectAnimationProps = {
  /** Imagen que el shader líquido ondula (misma-origen recomendada). */
  imageUrl?: string
  className?: string
}

/**
 * Fondo "líquido" interactivo (componente adaptado de 21st.dev): renderiza
 * una imagen con ondulaciones de agua vía three.js. Aparece con fade-in
 * cuando el shader está listo; si el CDN o WebGL fallan, no muestra nada y
 * la capa inferior (video/poster) sigue visible. Con reduced-motion no se
 * inicializa.
 */
export function LiquidEffectAnimation({
  imageUrl = '/assets/bg-mist.jpg',
  className = '',
}: LiquidEffectAnimationProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    let cancelled = false
    // Sin tipos publicados: la forma del objeto viene de la doc del CDN.
    let app: { dispose?: () => void } | null = null

    ;(async () => {
      try {
        const mod = await import(/* @vite-ignore */ LIQUID_LIB_URL)
        if (cancelled) return
        const liquidApp = mod.default(canvas)
        app = liquidApp
        liquidApp.loadImage(imageUrl)
        liquidApp.liquidPlane.material.metalness = 0.75
        liquidApp.liquidPlane.material.roughness = 0.25
        liquidApp.liquidPlane.uniforms.displacementScale.value = 5
        // La capa vive detrás del contenido (sin hover directo), así que la
        // "lluvia" mantiene el agua en movimiento por sí sola.
        liquidApp.setRain(true)
        setReady(true)
      } catch {
        // CDN o WebGL no disponibles: se conserva el fondo por defecto.
      }
    })()

    return () => {
      cancelled = true
      app?.dispose?.()
    }
  }, [imageUrl])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={`h-full w-full transition-opacity duration-1000 ${
        ready ? 'opacity-100' : 'opacity-0'
      } ${className}`}
    />
  )
}
