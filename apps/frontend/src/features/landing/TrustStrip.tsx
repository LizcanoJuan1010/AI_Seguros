import { Icon } from '../../components/ui/Icon'

const items = [
  { icon: 'verified', label: 'Respaldado por Salto Angel' },
  { icon: 'speed', label: 'Respuesta inmediata < 30s' },
  { icon: 'shield_lock', label: 'Seguridad nivel bancario AES-256' },
]

export function TrustStrip() {
  return (
    <div className="mx-auto hidden w-full max-w-container-max items-center justify-between border-t border-outline-variant/30 px-margin-desktop pb-12 pt-10 md:flex">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-3 opacity-70">
          <Icon name={item.icon} className="text-primary" />
          <span className="text-label-md">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
