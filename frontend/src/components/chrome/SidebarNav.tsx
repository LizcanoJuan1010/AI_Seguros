import { NavLink } from 'react-router-dom'
import { Icon } from '../ui/Icon'

type SidebarNavProps = {
  role: 'agent' | 'manager'
}

const agentLinks = [
  { to: '/vendedor', label: 'Leads', icon: 'inbox', end: true },
  { to: '/llamada', label: 'Llamada IA', icon: 'call' },
  { to: '/gerente', label: 'Vista gerente', icon: 'monitoring' },
  { to: '/', label: 'Portal', icon: 'home' },
]

const managerLinks = [
  { to: '/gerente', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/vendedor', label: 'Agentes / Leads', icon: 'groups' },
  { to: '/llamada', label: 'Llamada IA', icon: 'campaign' },
  { to: '/', label: 'Portal', icon: 'home' },
]

export function SidebarNav({ role }: SidebarNavProps) {
  const links = role === 'agent' ? agentLinks : managerLinks
  const title = role === 'agent' ? 'Panel del vendedor' : 'Dashboard Tequendama'
  const subtitle = role === 'agent' ? 'Agente Senior' : 'Manager Pro'

  return (
    <aside className="flex h-full w-64 flex-col border-r border-outline-variant bg-surface-container-lowest">
      <div className="border-b border-outline-variant p-4">
        <p className="text-base font-bold text-primary">{title}</p>
        <p className="text-sm text-outline">{subtitle}</p>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3">
        {links.map((link) => (
          <NavLink
            key={link.to + link.label}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? 'bg-primary text-on-primary'
                  : 'text-on-surface-variant hover:bg-surface-variant'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon name={link.icon} filled={isActive} />
                <span>{link.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
      {role === 'agent' ? (
        <div className="border-t border-outline-variant bg-surface-container-low p-4">
          <div className="mb-3 flex items-center gap-3">
            <img
              src="/assets/avatars/agent.png"
              alt="Andrés Mendoza"
              className="size-10 rounded-full border-2 border-primary-container object-cover"
            />
            <div>
              <p className="text-sm font-bold leading-none">Andrés Mendoza</p>
              <p className="text-xs text-outline">Agente Senior</p>
            </div>
          </div>
        </div>
      ) : null}
    </aside>
  )
}
