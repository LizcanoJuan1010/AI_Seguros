import { Icon } from '../../components/ui/Icon'

const items = [
  { icon: 'verified', label: 'Respaldado por Salto Angel' },
  { icon: 'speed', label: 'Respuesta inmediata < 30s' },
  { icon: 'shield_lock', label: 'Seguridad nivel bancario AES-256' },
  { icon: 'credit_score', label: 'Pagos seguros con Polar' },
]

export function TrustStrip() {
  return (
    <div className="border-y border-outline-variant/30 bg-surface/40 backdrop-blur-sm">
      <div className="mx-auto grid w-full max-w-container-max grid-cols-1 gap-4 px-margin-mobile py-6 sm:grid-cols-2 md:py-8 lg:grid-cols-4 md:px-margin-desktop">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-center gap-3 opacity-80"
          >
            <Icon name={item.icon} className="shrink-0 text-primary" />
            <span className="text-label-md">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
