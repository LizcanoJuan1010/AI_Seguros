import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import type { LeaderEntry } from '../../data/mock/types'

type Props = {
  entries: LeaderEntry[]
}

const toneClass = {
  gold: 'text-amber-cta',
  silver: 'text-slate-300',
  bronze: 'text-orange-400',
} as const

const barClass = {
  gold: 'bg-amber-cta',
  silver: 'bg-slate-300',
  bronze: 'bg-orange-400',
} as const

export function Leaderboard({ entries }: Props) {
  return (
    <div className="relative overflow-hidden rounded-lg bg-forest-deep p-5 text-white shadow-lg">
      <div className="absolute -right-10 -bottom-10 rotate-12 opacity-10">
        <Icon name="emoji_events" className="text-[120px]" />
      </div>
      <h3 className="relative z-10 mb-4 flex items-center gap-2 text-sm font-bold">
        <Icon name="military_tech" className="text-amber-cta" />
        Ranking de Ventas
      </h3>
      <div className="relative z-10 flex flex-col gap-4">
        {entries.map((entry) => (
          <div key={entry.id}>
            <div className="mb-1 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold ${toneClass[entry.tone]}`}>
                  {entry.rank}
                </span>
                <p className="text-xs">{entry.name}</p>
              </div>
              <p className="text-xs font-bold">{entry.amount}</p>
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className={`h-full ${barClass[entry.tone]}`}
                style={{ width: entry.width }}
              />
            </div>
          </div>
        ))}
      </div>
      <Button
        variant="ghost"
        className="relative z-10 mt-6 w-full rounded-lg border-white/20 bg-white/5 py-2 text-[10px] font-bold tracking-wider text-white uppercase hover:bg-white/10"
      >
        Ver Ranking Completo
      </Button>
    </div>
  )
}
