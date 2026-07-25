import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { Icon } from '../ui/Icon'
import { TeamSwitcher } from './TeamSwitcher'
import { useAuth } from '../../contexts/AuthContext'

type TopNavProps = {
  variant?: 'marketing' | 'app'
}

/**
 * Marketing: anclas a secciones de la landing (solo se monta en "/", así que
 * los href de hash navegan sin recargar). App: rutas protegidas con icono.
 */
const marketingLinks = [
  { href: '#planes', label: 'Planes', icon: 'verified_user' },
  { href: '#como-funciona', label: 'Cómo funciona', icon: 'route' },
  { href: '#opiniones', label: 'Opiniones', icon: 'reviews' },
  { href: '#faq', label: 'Preguntas', icon: 'help' },
]

const appLinks = [
  { to: '/', label: 'Inicio', icon: 'home', end: true },
  { to: '/asistente', label: 'Asistente IA', icon: 'smart_toy', end: false },
  { to: '/llamada', label: 'Llamada IA', icon: 'support_agent', end: false },
  { to: '/vendedor', label: 'Vendedor', icon: 'badge', end: false },
  { to: '/gerente', label: 'Gerente', icon: 'monitoring', end: false },
  { to: '/campanas', label: 'Campañas', icon: 'campaign', end: false },
]

const appLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-full px-4 py-2 text-label-md transition-colors duration-200 ${
    isActive
      ? 'bg-primary text-on-primary shadow-md shadow-primary/25'
      : 'text-on-surface-variant hover:bg-primary/10 hover:text-primary'
  }`

const sheetLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-xl px-4 py-3.5 text-body-md font-semibold transition-colors ${
    isActive
      ? 'bg-primary text-on-primary'
      : 'text-on-surface hover:bg-surface-variant'
  }`

export function TopNav({ variant = 'marketing' }: TopNavProps) {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const { user, signOut } = useAuth()
  const location = useLocation()

  // El header de marketing arranca transparente sobre el hero y gana fondo
  // glass al hacer scroll. En la app el scroll ocurre en un contenedor
  // interno (no window), así que siempre va con fondo.
  useEffect(() => {
    if (variant !== 'marketing') return
    const onScroll = () => setScrolled(window.scrollY > 16)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [variant])

  useEffect(() => {
    setOpen(false)
  }, [location.pathname, location.hash])

  useEffect(() => {
    if (!open) return
    document.body.style.overflow = 'hidden'
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const solid = variant === 'app' || scrolled || open

  return (
    <header
      className={`sticky top-0 z-50 w-full transition-[background-color,box-shadow,border-color] duration-300 ${
        solid
          ? 'glass-header border-b border-outline-variant/40 shadow-sm'
          : 'border-b border-transparent'
      }`}
    >
      <div className="mx-auto grid h-16 w-full max-w-container-max grid-cols-[auto_1fr_auto] items-center gap-3 px-margin-mobile md:h-20 md:px-margin-desktop">
        {/* Marca */}
        <Link
          to="/"
          className="group flex min-w-0 shrink-0 items-center gap-2.5"
          onClick={() => setOpen(false)}
        >
          <img
            src="/assets/logo.svg"
            alt="Tequendama"
            className="h-9 w-auto transition-transform duration-300 group-hover:scale-105 md:h-10"
          />
          <span
            className={`flex-col whitespace-nowrap leading-none ${
              variant === 'app' ? 'hidden xl:flex' : 'hidden sm:flex'
            }`}
          >
            <span className="font-display text-[21px] font-semibold tracking-tight text-primary md:text-[24px]">
              Tequendama
            </span>
            <span className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.28em] text-secondary">
              Insurance AI
            </span>
          </span>
        </Link>

        {/* Navegación central (desktop) */}
        {variant === 'marketing' ? (
          <nav
            aria-label="Secciones"
            className="hidden items-center justify-center gap-1 lg:flex"
          >
            {marketingLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="rounded-full px-4 py-2 text-label-md text-on-surface-variant transition-colors duration-200 hover:bg-primary/10 hover:text-primary"
              >
                {link.label}
              </a>
            ))}
          </nav>
        ) : (
          <nav
            aria-label="Aplicación"
            className="hidden items-center justify-center gap-1 lg:flex"
          >
            {appLinks.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={appLinkClass}
              >
                {({ isActive }) => (
                  <>
                    <Icon name={link.icon} filled={isActive} className="text-[20px]" />
                    <span className="whitespace-nowrap">{link.label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        )}

        {/* Acciones */}
        <div className="flex min-w-0 items-center justify-end gap-2">
          {variant === 'marketing' ? (
            <>
              <Link
                to={user ? '/asistente' : '/login'}
                className="hidden rounded-full px-4 py-2 text-label-md text-primary transition-colors hover:bg-primary/10 md:inline-flex"
              >
                {user ? 'Mi panel' : 'Ingresar'}
              </Link>
              <Link
                to="/llamada"
                className="hidden items-center gap-2 rounded-full bg-amber-cta px-5 py-2.5 text-label-md font-bold text-primary shadow-md shadow-amber-cta/25 transition-all hover:scale-105 hover:shadow-lg hover:shadow-amber-cta/30 active:scale-95 sm:inline-flex"
              >
                <Icon name="support_agent" className="text-[20px]" />
                <span className="whitespace-nowrap">Hablar con un asesor</span>
              </Link>
            </>
          ) : (
            <>
              <TeamSwitcher />
              <button
                type="button"
                className="relative hidden size-10 items-center justify-center rounded-full border border-outline-variant/60 bg-surface-container-lowest/70 text-primary transition-colors hover:bg-surface-variant sm:flex"
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
                <div className="hidden items-center gap-2 xl:flex">
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
          <button
            type="button"
            className="flex size-10 items-center justify-center rounded-full border border-outline-variant/50 bg-surface-container-lowest/70 text-primary transition-colors hover:bg-surface-variant lg:hidden"
            aria-label={open ? 'Cerrar menú' : 'Abrir menú'}
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen((v) => !v)}
          >
            <Icon name={open ? 'close' : 'menu'} className="text-[22px]" />
          </button>
        </div>
      </div>

      {/* Menú móvil / tablet */}
      {open && (
        <>
          <div
            className="fixed inset-0 top-16 z-40 bg-forest-deep/25 backdrop-blur-sm md:top-20 lg:hidden"
            aria-hidden
            onClick={() => setOpen(false)}
          />
          <div
            id="mobile-nav"
            className="nav-sheet absolute inset-x-0 top-full z-50 max-h-[calc(100svh-4rem)] overflow-y-auto border-b border-outline-variant/40 bg-surface/95 shadow-xl backdrop-blur-xl lg:hidden"
          >
            <div className="mx-auto flex w-full max-w-container-max flex-col gap-1 px-margin-mobile py-4 md:px-margin-desktop">
              {variant === 'marketing' ? (
                <>
                  {marketingLinks.map((link) => (
                    <a
                      key={link.href}
                      href={link.href}
                      className="flex items-center gap-3 rounded-xl px-4 py-3.5 text-body-md font-semibold text-on-surface transition-colors hover:bg-surface-variant"
                      onClick={() => setOpen(false)}
                    >
                      <Icon name={link.icon} className="text-[22px] text-primary" />
                      {link.label}
                    </a>
                  ))}
                  <div className="mt-3 flex flex-col gap-2 border-t border-outline-variant/40 pt-4">
                    <Link
                      to="/llamada"
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-amber-cta px-5 py-3.5 text-body-md font-bold text-primary shadow-md shadow-amber-cta/25"
                      onClick={() => setOpen(false)}
                    >
                      <Icon name="support_agent" className="text-[22px]" />
                      Hablar con un asesor
                    </Link>
                    <Link
                      to={user ? '/asistente' : '/login'}
                      className="inline-flex items-center justify-center gap-2 rounded-xl border-2 border-primary px-5 py-3 text-body-md font-bold text-primary transition-colors hover:bg-primary/5"
                      onClick={() => setOpen(false)}
                    >
                      {user ? 'Ir a mi panel' : 'Ingresar'}
                    </Link>
                  </div>
                </>
              ) : (
                <>
                  {appLinks.map((link) => (
                    <NavLink
                      key={link.to}
                      to={link.to}
                      className={sheetLinkClass}
                      end={link.end}
                      onClick={() => setOpen(false)}
                    >
                      <Icon name={link.icon} className="text-[22px]" />
                      {link.label}
                    </NavLink>
                  ))}
                  {user && (
                    <button
                      type="button"
                      className="mt-2 flex items-center gap-3 rounded-xl border-t border-outline-variant/40 px-4 py-3.5 text-left text-body-md font-semibold text-on-surface hover:bg-surface-variant"
                      onClick={() => {
                        setOpen(false)
                        signOut()
                      }}
                    >
                      <Icon name="logout" className="text-[22px]" />
                      Salir ({user.name || user.email})
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </header>
  )
}
