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
  { to: '/', label: 'Inicio', icon: 'home', end: true },
  { to: '/asistente', label: 'Asistente IA', icon: 'smart_toy', end: false },
  { to: '/llamada', label: 'Llamada IA', icon: 'support_agent', end: false },
  { to: '/vendedor', label: 'Vendedor', icon: 'badge', end: false },
  { to: '/gerente', label: 'Gerente', icon: 'monitoring', end: false },
]

const mobileLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-xl px-4 py-3 text-label-md transition-colors ${
    isActive
      ? 'bg-primary text-on-primary font-bold'
      : 'text-on-surface hover:bg-surface-variant'
  }`

export function TopNav({ variant = 'marketing' }: TopNavProps) {
  const [open, setOpen] = useState(false)
  const { user, signOut } = useAuth()

  return (
    <nav className="glass-header sticky top-0 z-50 w-full border-b border-outline-variant/40">
      <div className="mx-auto flex w-full max-w-container-max items-center justify-between gap-3 px-margin-mobile py-3 md:px-margin-desktop">
        <Link
          to="/"
          className="group flex shrink-0 items-center gap-2.5"
          onClick={() => setOpen(false)}
        >
          <img
            src="/assets/logo.svg"
            alt="Tequendama"
            className="h-10 w-auto transition-transform duration-300 group-hover:scale-105 md:h-11"
          />
          {/* El wordmark solo aparece cuando sobra espacio (evita solaparse con el menú) */}
          <span className="hidden flex-col whitespace-nowrap leading-none sm:max-md:flex lg:flex">
            <span className="font-display text-[24px] font-semibold tracking-tight text-primary md:text-[26px]">
              Tequendama
            </span>
            <span className="mt-1 text-[9px] font-semibold uppercase tracking-[0.28em] text-secondary">
              Insurance AI
            </span>
          </span>
        </Link>

        {/* Navegación por símbolos: el ítem activo (o en hover) expande su etiqueta */}
        <div className="hidden items-center gap-1 rounded-full border border-outline-variant/50 bg-surface-container-lowest/70 p-1.5 shadow-sm backdrop-blur-md md:flex">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              title={link.label}
              aria-label={link.label}
              className={({ isActive }) =>
                `group flex items-center rounded-full px-3.5 py-2 transition-colors duration-300 ${
                  isActive
                    ? 'bg-primary text-on-primary shadow-md shadow-primary/25'
                    : 'text-on-surface-variant hover:bg-surface-variant hover:text-primary'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon name={link.icon} filled={isActive} className="text-[22px]" />
                  <span
                    className={`overflow-hidden whitespace-nowrap text-label-md transition-all duration-300 ${
                      isActive
                        ? 'ml-2 max-w-32 opacity-100'
                        : 'ml-0 max-w-0 opacity-0 group-hover:ml-2 group-hover:max-w-32 group-hover:opacity-100'
                    }`}
                  >
                    {link.label}
                  </span>
                </>
              )}
            </NavLink>
          ))}
        </div>

        <div className="flex shrink-0 items-center gap-2">
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
              <button
                type="button"
                className="relative flex size-10 items-center justify-center rounded-full border border-outline-variant/60 bg-surface-container-lowest/70 text-primary transition-colors hover:bg-surface-variant"
                aria-label="Notificaciones"
                title="Notificaciones"
              >
                <Icon name="notifications" className="text-[22px]" />
                <span
                  className="absolute right-2 top-2 size-2 rounded-full bg-amber-cta ring-2 ring-white"
                  aria-hidden
                />
              </button>
              {user && (
                <div className="hidden items-center gap-2 lg:flex">
                  <div className="flex items-center gap-2.5 rounded-full border border-outline-variant/50 bg-surface-container-lowest/70 py-1 pl-1 pr-4">
                    <span className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-primary-container to-primary text-label-md font-bold text-on-primary">
                      {(user.name || user.email).charAt(0).toUpperCase()}
                    </span>
                    <span className="flex flex-col leading-tight">
                      <span className="max-w-36 truncate text-label-md text-on-surface">
                        {user.name || user.email}
                      </span>
                      <span className="text-label-sm uppercase text-on-surface-variant">
                        {user.role}
                      </span>
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={signOut}
                    className="flex size-10 items-center justify-center rounded-full border border-outline-variant/60 text-on-surface-variant transition-colors hover:border-error/40 hover:bg-error-container/60 hover:text-error"
                    aria-label="Cerrar sesión"
                    title="Cerrar sesión"
                  >
                    <Icon name="logout" className="text-[20px]" />
                  </button>
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
                <Icon name={link.icon} className="text-[22px]" />
                {link.label}
              </NavLink>
            ))}
            {variant === 'app' && user && (
              <button
                type="button"
                className="mt-2 flex items-center gap-3 rounded-xl border-t border-outline-variant/40 px-4 py-3 text-left text-label-md text-on-surface hover:bg-surface-variant"
                onClick={() => {
                  setOpen(false)
                  signOut()
                }}
              >
                <Icon name="logout" className="text-[22px]" />
                Salir ({user.name || user.email})
              </button>
            )}
          </div>
        </div>
      )}
    </nav>
  )
}
