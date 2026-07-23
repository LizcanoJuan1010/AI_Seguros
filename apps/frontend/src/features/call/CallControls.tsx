import { Icon } from '../../components/ui/Icon'
import { Button } from '../../components/ui/Button'

type Props = {
  muted: boolean
  onMuteToggle: () => void
  onEnd: () => void
  onSend: () => void
}

export function CallControls({ muted, onMuteToggle, onEnd, onSend }: Props) {
  return (
    <nav className="fixed bottom-0 z-50 w-full border-t border-outline-variant/10 bg-surface-container-high/95 backdrop-blur-xl">
      <div className="mx-auto flex max-w-container-max flex-col items-center justify-between gap-4 px-margin-mobile py-6 md:flex-row md:px-margin-desktop">
        <div className="flex items-center gap-6">
          <button
            type="button"
            className="group flex flex-col items-center gap-1"
            onClick={onMuteToggle}
          >
            <div
              className={`flex size-12 items-center justify-center rounded-full border-2 transition-all ${
                muted
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-outline-variant text-on-surface-variant group-hover:border-primary group-hover:text-primary'
              }`}
            >
              <Icon name={muted ? 'mic_off' : 'mic'} />
            </div>
            <span className="text-label-sm text-on-surface-variant">
              {muted ? 'Activar mic' : 'Silenciar'}
            </span>
          </button>
          <button
            type="button"
            className="group flex flex-col items-center gap-1"
            onClick={onEnd}
          >
            <div className="flex size-12 items-center justify-center rounded-full bg-error text-white shadow-lg transition-all hover:bg-error/90 active:scale-90">
              <Icon name="call_end" filled />
            </div>
            <span className="text-label-sm text-on-surface-variant">
              Finalizar
            </span>
          </button>
        </div>
        <div className="flex flex-wrap justify-center gap-4">
          <Button variant="ghost" className="rounded-full px-6 py-3">
            <Icon name="person_heart" className="text-[20px]" />
            Hablar con un asesor humano
          </Button>
          <Button
            variant="primary"
            className="rounded-full bg-forest-deep px-6 py-3"
            onClick={onSend}
          >
            <Icon name="send" className="text-[20px]" />
            Enviar a mi correo
          </Button>
        </div>
      </div>
    </nav>
  )
}
