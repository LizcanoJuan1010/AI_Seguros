import { useEffect, useRef, useState } from 'react'
import { Icon } from '../ui/Icon'
import { useTenant } from '../../tenant/TenantContext'

/**
 * Selector de tenant (equipo) del TopNav. Scopea toda la app: dashboard,
 * leads y sesión del asistente. Oculto si el backend no está disponible.
 */
export function TeamSwitcher() {
  const { teams, teamId, team, setTeamId, offline, loading } = useTenant()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  if (offline || loading || teams.length === 0) return null

  const options = [{ id: '', name: 'Todos los equipos' }, ...teams]

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full border border-outline-variant bg-surface-container-low px-3 py-2 text-label-md text-on-surface transition-colors hover:bg-surface-variant"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <Icon name="groups" className="text-[20px] text-primary" />
        <span className="hidden max-w-40 truncate sm:block">
          {team?.name ?? 'Todos los equipos'}
        </span>
        <Icon name="expand_more" className="text-[18px] text-on-surface-variant" />
      </button>

      {open && (
        <ul
          role="listbox"
          className="glass-card absolute right-0 z-50 mt-2 w-56 overflow-hidden rounded-xl py-1 shadow-lg"
        >
          {options.map((opt) => {
            const active = (teamId || '') === opt.id
            return (
              <li key={opt.id || 'all'}>
                <button
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => {
                    setTeamId(opt.id)
                    setOpen(false)
                  }}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-label-md transition-colors ${
                    active
                      ? 'bg-primary/10 font-bold text-primary'
                      : 'text-on-surface hover:bg-surface-variant'
                  }`}
                >
                  <span className="truncate">{opt.name}</span>
                  {active && <Icon name="check" className="text-[18px]" />}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
