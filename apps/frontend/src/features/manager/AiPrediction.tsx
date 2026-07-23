import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'

export function AiPrediction() {
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
              Análisis Predictivo de Hoy
            </h4>
          </div>
          <p className="max-w-2xl text-sm text-on-surface-variant">
            Basado en el flujo actual de leads y el desempeño histórico de los
            agentes, la IA estima un cierre de{' '}
            <span className="font-bold text-primary">$85M COP</span> para las
            18:00 hrs.{' '}
            <span className="italic">
              Recomendación: Mover 2 agentes a la campaña &ldquo;Salud
              Premium&rdquo; para maximizar cierres.
            </span>
          </p>
        </div>
        <Button className="shrink-0 rounded-md px-6 py-2.5 shadow-lg shadow-primary/20">
          Aplicar Optimización IA
        </Button>
      </div>
    </section>
  )
}
