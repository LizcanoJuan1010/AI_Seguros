import { Link, NavLink } from 'react-router-dom'
import { Icon } from '../ui/Icon'
import { Button } from '../ui/Button'

type TopNavProps = {
  variant?: 'marketing' | 'app'
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-label-md transition-colors ${
    isActive
      ? 'text-primary font-bold border-b-2 border-primary pb-1'
      : 'text-on-surface-variant hover:text-primary'
  }`

export function TopNav({ variant = 'marketing' }: TopNavProps) {
  return (
    <nav
      className={`z-50 flex w-full items-center justify-between px-margin-mobile py-4 md:px-margin-desktop ${
        variant === 'marketing'
          ? 'fixed top-0 mx-auto max-w-container-max bg-surface/80 shadow-sm backdrop-blur-md'
          : 'glass-header sticky top-0 border-b border-outline-variant'
      }`}
    >
      <Link to="/" className="flex items-center gap-3">
        <img
          src="/assets/logo.png"
          alt="Tequendama"
          className="h-10 w-auto md:h-12"
        />
        <span className="hidden text-display-lg-mobile font-extrabold text-primary md:block">
          Tequendama
        </span>
      </Link>

      <div className="hidden items-center gap-stack-lg md:flex">
        <NavLink to="/" className={linkClass} end>
          Inicio
        </NavLink>
        <NavLink to="/llamada" className={linkClass}>
          Llamada IA
        </NavLink>
        <NavLink to="/vendedor" className={linkClass}>
          Vendedor
        </NavLink>
        <NavLink to="/gerente" className={linkClass}>
          Gerente
        </NavLink>
      </div>

      {variant === 'marketing' ? (
        <Button
          variant="primary"
          className="rounded-full"
          onClick={() => undefined}
        >
          <Icon name="support_agent" className="text-[20px]" />
          Hablar con un asesor
        </Button>
      ) : (
        <div className="flex items-center gap-2">
          <Button variant="ghost" className="size-10 rounded-full p-0" aria-label="Notificaciones">
            <Icon name="notifications" />
          </Button>
        </div>
      )}
    </nav>
  )
}
