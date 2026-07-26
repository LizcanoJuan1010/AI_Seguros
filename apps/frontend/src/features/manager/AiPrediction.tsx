/**
 * Análisis predictivo del día: ya NO es texto quemado. El botón consulta al
 * agente IA real (rol gerente, con acceso a `obtener_insights`/`listar_leads`)
 * y este produce el pronóstico y las recomendaciones sobre datos reales del
 * negocio. Se muestra en el modal de chat, donde el gerente puede además
 * repreguntar.
 */
import { useState } from 'react'
import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import { AiChatModal } from './AiChatModal'
import { useTenant } from '../../tenant/TenantContext'

const PROMPT =
  'Actúa como analista de negocio de la aseguradora. Con los datos REALES del ' +
  'negocio (usa obtener_insights y listar_leads), genera el análisis predictivo ' +
  'de HOY: 1) estimación de cierres/ingresos esperados para el cierre del día y en ' +
  'qué te basas; 2) los 2-3 focos de riesgo u oportunidad más importantes ahora; ' +
  '3) una recomendación de optimización concreta y accionable para el equipo ' +
  '(a quién mover, a qué leads priorizar). Sé específico y usa cifras reales.'

export function AiPrediction() {
  const { team } = useTenant()
  const [open, setOpen] = useState(false)

  return (
    <section className="relative overflow-hidden rounded-lg border border-primary/10 bg-surface-container-low p-6">
      <div className="absolute top-0 right-0 p-4 opacity-5">
        <Icon name="batch_prediction" className="text-[100px]" />
      </div>
      <div className="relative z-10 flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Icon name="auto_awesome" className="text-primary" />
            <h4 className="text-base font-bold text-primary">
              Análisis Predictivo con IA
            </h4>
          </div>
          <p className="max-w-2xl text-sm text-on-surface-variant">
            La IA analiza el flujo de leads, el desempeño de los agentes y el
            funnel del equipo{' '}
            <span className="font-bold text-primary">
              {team?.name ?? 'de todos los equipos'}
            </span>{' '}
            para estimar cierres del día y recomendar cómo optimizar. Genera el
            análisis con datos reales, no plantillas.
          </p>
        </div>
        <Button
          className="shrink-0 rounded-md px-6 py-2.5 shadow-lg shadow-primary/20"
          onClick={() => setOpen(true)}
        >
          <Icon name="insights" className="text-[18px]" />
          Generar análisis IA
        </Button>
      </div>

      <AiChatModal
        open={open}
        onClose={() => setOpen(false)}
        title="Análisis predictivo del día"
        subtitle="Generado por la IA con datos reales del negocio"
        initialPrompt={PROMPT}
      />
    </section>
  )
}
