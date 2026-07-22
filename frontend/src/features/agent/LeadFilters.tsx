import { Chip } from '../../components/ui/Chip'

type Tab = 'todos' | 'seguimiento' | 'cerrados'

type Props = {
  active: Tab
  onChange: (tab: Tab) => void
}

const tabs: { id: Tab; label: string }[] = [
  { id: 'todos', label: 'Todos' },
  { id: 'seguimiento', label: 'En Seguimiento' },
  { id: 'cerrados', label: 'Cerrados' },
]

export function LeadFilters({ active, onChange }: Props) {
  return (
    <div className="flex gap-4 border-b border-outline-variant bg-surface-container-low px-8 py-4">
      <div className="flex rounded-lg bg-surface-variant p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`rounded-md px-4 py-1.5 text-sm transition-all ${
              active === tab.id
                ? 'bg-surface-container-lowest font-bold text-primary shadow-sm'
                : 'font-medium text-on-surface-variant hover:text-on-surface'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="h-8 w-px self-center bg-outline-variant" />
      <Chip tone="neutral" className="cursor-default rounded-md border border-outline-variant bg-transparent">
        Filtrar por Intención
      </Chip>
      <Chip tone="neutral" className="cursor-default rounded-md border border-outline-variant bg-transparent">
        Tipo de Seguro
      </Chip>
    </div>
  )
}
