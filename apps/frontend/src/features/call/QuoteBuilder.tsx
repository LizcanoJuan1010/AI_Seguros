import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'
import type { Quote } from '../../data/mock/types'

type Props = {
  quote: Quote
}

export function QuoteBuilder({ quote }: Props) {
  return (
    <aside className="z-10 lg:col-span-5">
      <div className="sticky top-28 overflow-hidden rounded-3xl border border-primary/5 bg-white p-stack-lg shadow-lg">
        <div className="absolute top-0 right-0 p-4">
          <Icon name="description" className="text-6xl text-primary/20" />
        </div>
        <h3 className="mb-6 flex items-center gap-2 text-headline-md text-forest-deep">
          Tu Póliza Personalizada
          <Icon name="auto_awesome" className="text-primary" />
        </h3>
        <div className="mb-8 space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-outline-variant/20 bg-surface-container-low p-4">
            <div>
              <p className="text-label-sm uppercase text-on-surface-variant">
                Vehículo Protegido
              </p>
              <p className="text-body-md font-bold text-on-surface">
                {quote.vehicle}
              </p>
            </div>
            <Icon name="directions_car" className="text-primary" />
          </div>
          <div className="space-y-3">
            <p className="text-label-md font-bold text-on-surface">
              Coberturas activadas:
            </p>
            <ul className="space-y-2">
              {quote.coverages.map((item, index) => (
                <li
                  key={item}
                  className={`flex items-center gap-3 text-on-surface-variant ${
                    index === quote.coverages.length - 1 ? 'animate-pulse' : ''
                  }`}
                >
                  <Icon
                    name={
                      index === quote.coverages.length - 1
                        ? 'add_circle'
                        : 'check_circle'
                    }
                    className={`text-[20px] ${
                      index === quote.coverages.length - 1
                        ? 'text-amber-cta'
                        : 'text-primary'
                    }`}
                  />
                  <span
                    className={`text-body-md ${
                      index === quote.coverages.length - 1
                        ? 'font-bold text-forest-deep'
                        : ''
                    }`}
                  >
                    {item}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="border-t border-outline-variant/30 pt-6">
          <div className="mb-2 flex items-end justify-between">
            <p className="text-label-md text-on-surface-variant">
              Mensualidad estimada
            </p>
            <p className="rounded bg-primary/10 px-2 text-label-sm font-bold text-primary">
              {quote.savingsLabel}
            </p>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-display-lg-mobile text-forest-deep">
              {quote.monthly}
            </span>
            <span className="text-label-md text-on-surface-variant">
              COP / mes
            </span>
          </div>
        </div>
        <Button variant="cta" className="mt-8 w-full rounded-md py-4">
          <Icon name="bolt" filled />
          Comprar ahora con un clic
        </Button>
        <p className="mt-4 text-center text-label-sm text-on-surface-variant">
          Transacción segura protegida por Salto Angel
        </p>
      </div>
    </aside>
  )
}
