/**
 * Descarga un archivo same-origin (p. ej. /api/documents/...) sin abrir
 * pestaña nueva: ancla temporal con atributo `download`. El backend además
 * responde Content-Disposition: attachment, así el navegador guarda el PDF.
 */
export function downloadFile(url: string, filename?: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename ?? url.split('/').pop() ?? 'documento.pdf'
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}
