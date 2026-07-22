import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { Check, Copy } from 'lucide-react'
import 'highlight.js/styles/github.css'

/**
 * Render de markdown para las respuestas del asistente.
 * react-markdown + remark-gfm + rehype-highlight, repintado con los tokens
 * Mist/Forest de Tequendama (nada del dark-azul de Paloma).
 */

function CodeBlock({
  children,
  className,
}: {
  children?: ReactNode
  className?: string
}) {
  const preRef = useRef<HTMLPreElement>(null)
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    const text = preRef.current?.innerText ?? ''
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard no disponible: degrada en silencio */
    }
  }

  return (
    <div className="group relative my-3 overflow-hidden rounded-xl border border-outline-variant/50 bg-surface-container-low">
      <button
        type="button"
        onClick={handleCopy}
        className="absolute right-2 top-2 z-10 inline-flex items-center gap-1 rounded-md border border-outline-variant/50 bg-surface-container-lowest/90 px-2 py-1 text-label-sm text-on-surface-variant opacity-0 shadow-sm backdrop-blur transition-opacity hover:text-primary focus:opacity-100 group-hover:opacity-100"
        aria-label="Copiar código"
      >
        {copied ? (
          <>
            <Check size={13} className="text-primary" />
            Copiado
          </>
        ) : (
          <>
            <Copy size={13} />
            Copiar
          </>
        )}
      </button>
      <pre
        ref={preRef}
        className={`overflow-x-auto p-4 text-[13px] leading-relaxed ${className ?? ''}`}
      >
        {children}
      </pre>
    </div>
  )
}

const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-2 mt-4 text-headline-md font-bold text-on-surface first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-[19px] font-bold leading-7 text-on-surface first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-3 text-label-md font-bold uppercase tracking-wide text-primary first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="mb-3 text-body-md leading-relaxed text-on-surface last:mb-0">
      {children}
    </p>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-semibold text-primary underline decoration-primary/40 underline-offset-2 transition-colors hover:decoration-primary"
    >
      {children}
    </a>
  ),
  ul: ({ children }) => (
    <ul className="mb-3 ml-1 list-disc space-y-1 pl-4 text-body-md text-on-surface marker:text-primary/60 last:mb-0">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-3 ml-1 list-decimal space-y-1 pl-4 text-body-md text-on-surface marker:font-bold marker:text-primary/70 last:mb-0">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => (
    <strong className="font-bold text-on-surface">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  hr: () => <hr className="my-4 border-outline-variant/60" />,
  blockquote: ({ children }) => (
    <blockquote className="my-3 rounded-r-xl border-l-4 border-amber-cta bg-amber-cta/10 py-2 pl-4 pr-3 text-body-md italic text-on-surface-variant">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-xl border border-outline-variant/50">
      <table className="w-full border-collapse text-left text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-surface-container-high text-label-sm uppercase text-on-surface-variant">
      {children}
    </thead>
  ),
  th: ({ children }) => (
    <th className="border-b border-outline-variant/50 px-3 py-2 font-bold">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-outline-variant/30 px-3 py-2 align-top text-on-surface">
      {children}
    </td>
  ),
  pre: ({ children, className }) => (
    <CodeBlock className={className}>{children}</CodeBlock>
  ),
  code: ({ children, className }) => {
    const isBlock = /language-/.test(className ?? '')
    if (isBlock) {
      return <code className={className}>{children}</code>
    }
    return (
      <code className="rounded-md border border-outline-variant/40 bg-surface-container px-1.5 py-0.5 font-mono text-[0.85em] text-primary">
        {children}
      </code>
    )
  },
}

export function MessageMarkdown({ content }: { content: string }) {
  return (
    <div className="assistant-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
