import { Icon } from '../../components/ui/Icon'

type Props = {
  muted: boolean
  onMuteToggle: () => void
  onEnd: () => void
}

export function CallControls({ muted, onMuteToggle, onEnd }: Props) {
  return (
    <nav className="fixed bottom-0 z-50 w-full border-t border-outline-variant/10 bg-surface-container-high/95 backdrop-blur-xl">
      <div className="mx-auto flex max-w-container-max items-center justify-center gap-3 px-margin-mobile pt-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] md:gap-4 md:px-margin-desktop md:py-6">
        <div className="flex items-center gap-8">
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
      </div>
    </nav>
  )
}
