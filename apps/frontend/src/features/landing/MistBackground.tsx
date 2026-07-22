/**
 * Fondo ambiental estático (fotograma del video de bruma + hojas verde
 * bosque). Capa fija a pantalla completa detrás del contenido; el overlay
 * Mist mantiene la legibilidad del texto y la jerarquía de los CTA ámbar.
 */
export function MistBackground() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
    >
      <img
        className="h-full w-full scale-105 object-cover"
        src="/assets/bg-mist.jpg"
        alt=""
      />
      <div className="absolute inset-0 bg-background/70" />
      <div className="mist-overlay absolute inset-0" />
    </div>
  )
}
