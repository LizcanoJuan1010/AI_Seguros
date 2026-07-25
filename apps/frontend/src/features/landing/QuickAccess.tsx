import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'
import { useAuth } from '../../contexts/AuthContext'

type Shortcut = {
  to: string
  icon: string
  title: string
  hint: string
  tone?: 'amber'
  /** Solo tiene sentido mostrarlo con sesión iniciada (roles internos). */
  requiresAuth?: boolean
}

const shortcuts: Shortcut[] = [
  {
    to: '/asistente',
    icon: 'smart_toy',
    title: 'Asistente IA',
    hint: 'Cotiza y asegúrate por chat',
  },
  {
    to: '/llamada',
    icon: 'graphic_eq',
    title: 'Llamada IA',
    hint: 'Habla en vivo con la asesora',
    tone: 'amber',
  },
  {
    to: '/gerente?tab=clientes',
    icon: 'diversity_3',
    title: 'Clientes',
    hint: 'Cartera y expediente 360',
    requiresAuth: true,
  },
  {
    to: '/gerente',
    icon: 'monitoring',
    title: 'Gerente',
    hint: 'KPIs, alertas y reportes',
    requiresAuth: true,
  },
]

/** Accesos directos del inicio a cada área de la plataforma. */
export function QuickAccess() {
  const { user } = useAuth()
  const visible = shortcuts.filter((s) => !s.requiresAuth || user)

  return (
    <section className="px-margin-mobile pb-4 pt-10 md:px-margin-desktop">
      <div className="mx-auto max-w-container-max">
        <Reveal
          className={`grid grid-cols-1 gap-3 xs:grid-cols-2 md:gap-4 ${
            visible.length === 4 ? 'lg:grid-cols-4' : ''
          }`}
        >
          {visible.map((s) => (
            <Link
              key={s.to}
              to={s.to}
              className={`glass-card group flex items-center gap-4 rounded-2xl p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg md:p-5 ${
                s.tone === 'amber' ? 'border-2 border-amber-cta/50' : ''
              }`}
            >
              <span
                className={`flex size-12 shrink-0 items-center justify-center rounded-xl transition-transform group-hover:scale-110 ${
                  s.tone === 'amber'
                    ? 'bg-amber-cta/20 text-secondary'
                    : 'bg-primary/10 text-primary'
                }`}
              >
                <Icon name={s.icon} filled className="text-[24px]" />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-body-md font-bold text-on-surface">
                  {s.title}
                </span>
                <span className="block truncate text-label-sm text-on-surface-variant">
                  {s.hint}
                </span>
              </span>
              <Icon
                name="arrow_forward"
                className="ml-auto hidden text-[20px] text-outline transition-all group-hover:translate-x-0.5 group-hover:text-primary sm:block"
              />
            </Link>
          ))}
        </Reveal>
      </div>
    </section>
  )
}
