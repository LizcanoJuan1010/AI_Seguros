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
    <div className="flex flex-wrap items-center gap-3 border-b border-outline-variant bg-surface-container-low px-4 py-3 md:gap-4 md:px-8 md:py-4">
      <div className="flex rounded-lg bg-surface-variant p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`rounded-md px-3 py-2 text-sm transition-all md:px-4 md:py-1.5 ${
              active === tab.id
                ? 'bg-surface-container-lowest font-bold text-primary shadow-sm'
                : 'font-medium text-on-surface-variant hover:text-on-surface'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="hidden h-8 w-px self-center bg-outline-variant sm:block" />
      <Chip tone="neutral" className="cursor-default rounded-md border border-outline-variant bg-transparent">
        Filtrar por Intención
      </Chip>
      <Chip tone="neutral" className="cursor-default rounded-md border border-outline-variant bg-transparent">
        Tipo de Seguro
      </Chip>
    </div>
  )
}
