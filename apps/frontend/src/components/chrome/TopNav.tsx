import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Icon } from '../ui/Icon'
import { Button } from '../ui/Button'
import { TeamSwitcher } from './TeamSwitcher'
import { useAuth } from '../../contexts/AuthContext'

type TopNavProps = {
  variant?: 'marketing' | 'app'
}

const links = [
  { to: '/', label: 'Inicio', end: true },
  { to: '/asistente', label: 'Asistente IA', end: false },
  { to: '/llamada', label: 'Llamada IA', end: false },
  { to: '/vendedor', label: 'Vendedor', end: false },
  { to: '/gerente', label: 'Gerente', end: false },
]

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `text-label-md transition-colors ${
    isActive
      ? 'text-primary font-bold border-b-2 border-primary pb-1'
      : 'text-on-surface-variant hover:text-primary'
  }`

const mobileLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center rounded-lg px-4 py-3 text-label-md transition-colors ${
    isActive
      ? 'bg-primary text-on-primary font-bold'
      : 'text-on-surface hover:bg-surface-variant'
  }`

export function TopNav({ variant = 'marketing' }: TopNavProps) {
  const [open, setOpen] = useState(false)
  const { user, signOut } = useAuth()

  return (
    <nav className="glass-header sticky top-0 z-50 w-full border-b border-outline-variant/40">
      <div className="mx-auto flex w-full max-w-container-max items-center justify-between px-margin-mobile py-3 md:px-margin-desktop md:py-4">
        <Link to="/" className="flex items-center gap-3" onClick={() => setOpen(false)}>
          <img
            src="/assets/logo.svg"
            alt="Tequendama"
            className="h-10 w-auto md:h-12"
          />
          <span className="hidden text-display-lg-mobile font-extrabold text-primary sm:block">
            Tequendama
          </span>
        </Link>

        <div className="hidden items-center gap-stack-lg md:flex">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} className={linkClass} end={link.end}>
              {link.label}
            </NavLink>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {variant === 'marketing' ? (
            <Link
              to="/llamada"
              className="hidden items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-label-md font-bold text-on-primary shadow-sm transition-transform hover:scale-105 active:scale-95 sm:inline-flex"
            >
              <Icon name="support_agent" className="text-[20px]" />
              Hablar con un asesor
            </Link>
          ) : (
            <>
              <TeamSwitcher />
              <Button
                variant="ghost"
                className="size-10 rounded-full p-0"
                aria-label="Notificaciones"
              >
                <Icon name="notifications" />
              </Button>
              {user && (
                <div className="hidden items-center gap-3 md:flex">
                  <div className="flex items-center gap-2">
                    <span className="flex size-9 items-center justify-center rounded-full bg-primary text-label-md font-bold text-on-primary">
                      {(user.name || user.email).charAt(0).toUpperCase()}
                    </span>
                    <span className="flex flex-col leading-tight">
                      <span className="text-label-md text-on-surface">
                        {user.name || user.email}
                      </span>
                      <span className="text-label-sm text-on-surface-variant">
                        {user.role}
                      </span>
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    className="h-10 rounded-full px-4"
                    onClick={signOut}
                  >
                    <Icon name="logout" className="text-[20px]" />
                    Salir
                  </Button>
                </div>
              )}
            </>
          )}
          <Button
            variant="ghost"
            className="size-10 rounded-full p-0 md:hidden"
            aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
            onClick={() => setOpen((v) => !v)}
          >
            <Icon name={open ? 'close' : 'menu'} />
          </Button>
        </div>
      </div>

      {open && (
        <div className="border-t border-outline-variant/40 px-margin-mobile pb-4 pt-2 md:hidden">
          <div className="flex flex-col gap-1">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={mobileLinkClass}
                end={link.end}
                onClick={() => setOpen(false)}
              >
                {link.label}
              </NavLink>
            ))}
            {variant === 'app' && user && (
              <button
                type="button"
                className="mt-2 flex items-center gap-2 rounded-lg border-t border-outline-variant/40 px-4 py-3 text-left text-label-md text-on-surface hover:bg-surface-variant"
                onClick={() => {
                  setOpen(false)
                  signOut()
                }}
              >
                <Icon name="logout" className="text-[20px]" />
                Salir ({user.name || user.email})
              </button>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
