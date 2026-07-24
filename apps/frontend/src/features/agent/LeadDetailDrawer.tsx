import { useEffect } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import type { Lead } from '../../data/mock/types'

type Props = {
  lead: Lead | null
  open: boolean
  onClose: () => void
}

export function LeadDetailDrawer({ lead, open, onClose }: Props) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <aside
      className={`fixed top-0 right-0 z-30 flex h-full w-[450px] flex-col overflow-hidden border-l border-outline-variant bg-surface-container-lowest shadow-2xl transition-transform duration-300 ${
        open ? 'translate-x-0' : 'translate-x-full'
      }`}
      aria-hidden={!open}
    >
      <div className="flex items-center justify-between border-b border-outline-variant bg-white p-6">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="flex size-8 items-center justify-center rounded-full hover:bg-surface-variant"
            onClick={onClose}
            aria-label="Cerrar"
          >
            <Icon name="close" />
          </button>
          <h3 className="text-lg font-bold">Detalles del Lead</h3>
        </div>
      </div>
      {lead ? (
        <>
          <div className="flex-1 space-y-8 overflow-y-auto px-6 py-8">
            <section>
              <div className="mb-6 flex items-center gap-4">
                <div className="flex size-16 items-center justify-center rounded-2xl bg-primary text-2xl font-black text-on-primary">
                  {lead.initials}
                </div>
                <div>
                  <h4 className="text-2xl font-black text-on-surface">
                    {lead.name}
                  </h4>
                  <p className="flex items-center gap-2 text-outline">
                    <Icon name="location_on" className="text-sm" />
                    {lead.location}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg bg-surface-container-low p-4">
                  <p className="mb-1 text-xs font-bold text-outline uppercase">
                    Teléfono
                  </p>
                  <p className="text-sm font-semibold">{lead.phone}</p>
                </div>
                <div className="rounded-lg bg-surface-container-low p-4">
                  <p className="mb-1 text-xs font-bold text-outline uppercase">
                    Correo
                  </p>
                  <p className="text-sm font-semibold">{lead.email}</p>
                </div>
              </div>
            </section>
            <section className="space-y-4">
              <div className="flex items-center gap-2">
                <div className="flex size-6 items-center justify-center rounded-full bg-primary-container text-on-primary-container">
                  <Icon name="smart_toy" className="text-sm" />
                </div>
                <h5 className="font-bold text-primary">Análisis de la IA</h5>
              </div>
              <div className="space-y-3 rounded-lg border border-primary/20 bg-primary-fixed/20 p-4">
                <p className="text-sm leading-relaxed text-on-surface">
                  <span className="font-bold text-primary">
                    Siguiente Paso Sugerido:
                  </span>{' '}
                  {lead.insight}
                </p>
                <ul className="space-y-2">
                  {lead.checks.map((check) => (
                    <li key={check} className="flex items-start gap-2 text-xs">
                      <Icon name="check_circle" className="text-base text-primary" />
                      <span>{check}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
            <section className="space-y-4">
              <h5 className="border-b border-outline-variant pb-2 font-bold text-on-surface">
                Transcripción de la Llamada
              </h5>
              <div className="space-y-4 text-sm">
                {lead.transcript.map((line) => (
                  <div
                    key={line.time + line.speaker}
                    className={`flex flex-col gap-1 ${line.side === 'client' ? 'items-end' : ''}`}
                  >
                    <span className="text-[10px] font-bold tracking-tighter text-outline uppercase">
                      {line.speaker} ({line.time})
                    </span>
                    <p
                      className={
                        line.side === 'bot'
                          ? 'mr-8 rounded-2xl rounded-tl-none bg-surface-container p-3'
                          : 'ml-8 rounded-2xl rounded-tr-none bg-primary p-3 text-on-primary'
                      }
                    >
                      {line.text}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          </div>
          <div className="border-t border-outline-variant bg-white p-6">
            <Button className="w-full rounded-2xl py-4">
              <Icon name="call" />
              Iniciar Llamada Ahora
            </Button>
          </div>
        </>
      ) : null}
    </aside>
  )
}
