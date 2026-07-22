import { Icon } from '../../components/ui/Icon'
import type { TranscriptLine } from '../../data/mock/types'

type Props = {
  lines: TranscriptLine[]
}

export function TranscriptPanel({ lines }: Props) {
  return (
    <div className="scroll-hide flex max-h-[300px] flex-grow flex-col gap-stack-md overflow-y-auto p-2">
      {lines.map((line) =>
        line.role === 'ai' ? (
          <div key={line.id} className="flex items-start gap-4">
            <div className="flex size-8 flex-shrink-0 items-center justify-center rounded-full bg-primary text-white">
              <Icon name="psychology" className="text-[18px]" />
            </div>
            <div className="max-w-[85%] rounded-2xl rounded-tl-none border border-outline-variant/30 bg-white p-4 shadow-sm">
              <p className="text-body-md text-on-surface">{line.text}</p>
            </div>
          </div>
        ) : (
          <div key={line.id} className="flex items-start justify-end gap-4">
            <div className="max-w-[85%] rounded-2xl rounded-tr-none bg-primary-container p-4 text-white shadow-md">
              <p className="text-body-md italic">&ldquo;{line.text}&rdquo;</p>
            </div>
            <div className="flex size-8 flex-shrink-0 items-center justify-center rounded-full bg-surface-variant text-on-surface">
              <Icon name="person" className="text-[18px]" />
            </div>
          </div>
        ),
      )}
    </div>
  )
}
