import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'
import { WhatsAppIcon } from '../../components/ui/WhatsAppIcon'
import {
  ADVISOR_WHATSAPP_DISPLAY,
  ADVISOR_WHATSAPP_URL,
} from '../../lib/contact'

const productLinks = [
  { label: 'Seguro de Vida', href: '#planes' },
  { label: 'Seguro de Auto', href: '#planes' },
  { label: 'Seguro de Salud', href: '#planes' },
  { label: 'Cómo funciona', href: '#como-funciona' },
]

const companyLinks = [
  { label: 'Opiniones', href: '#opiniones' },
  { label: 'Preguntas frecuentes', href: '#faq' },
  { label: 'Privacidad', href: '#privacidad' },
  { label: 'Términos', href: '#terminos' },
]

export function SiteFooter() {
  const year = new Date().getFullYear()

  return (
    <footer className="relative z-10 mt-24 w-full border-t border-outline-variant/20 bg-surface-variant">
      <div className="mx-auto w-full max-w-container-max px-margin-mobile py-16 md:px-margin-desktop">
        <div className="grid grid-cols-1 gap-12 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.2fr)]">
          {/* Marca */}
          <div className="space-y-stack-md sm:col-span-2 lg:col-span-1">
            <Link to="/" className="inline-flex items-center gap-2.5">
              <img src="/assets/logo.svg" alt="Tequendama" className="h-10 w-auto" />
              <span className="flex flex-col leading-none">
                <span className="font-display text-[24px] font-semibold tracking-tight text-primary">
                  Tequendama
                </span>
                <span className="mt-0.5 text-[9px] font-semibold uppercase tracking-[0.28em] text-secondary">
                  Insurance AI
                </span>
              </span>
            </Link>
            <p className="max-w-sm text-body-md text-on-surface-variant">
              Protección inteligente inspirada en la fuerza de la naturaleza.
              Soluciones de seguros con propósito para el mundo moderno.
            </p>
          </div>

          {/* Producto */}
          <nav className="flex flex-col gap-3" aria-label="Producto">
            <span className="text-label-md font-bold text-primary">Producto</span>
            {productLinks.map((link) => (
              <a
                key={link.label}
                className="inline-block py-1.5 text-label-sm text-on-surface-variant transition-colors hover:text-primary"
                href={link.href}
              >
                {link.label}
              </a>
            ))}
          </nav>

          {/* Compañía */}
          <nav className="flex flex-col gap-3" aria-label="Compañía">
            <span className="text-label-md font-bold text-primary">Compañía</span>
            {companyLinks.map((link) => (
              <a
                key={link.label}
                className="inline-block py-1.5 text-label-sm text-on-surface-variant transition-colors hover:text-primary"
                href={link.href}
              >
                {link.label}
              </a>
            ))}
          </nav>

          {/* Contacto */}
          <div className="flex flex-col gap-3">
            <span className="text-label-md font-bold text-primary">Contacto</span>
            <a
              className="flex items-center gap-2 text-label-sm text-on-surface-variant transition-colors hover:text-primary"
              href="mailto:hola@tequendama.ai"
            >
              <Icon name="mail" className="text-[18px]" />
              hola@tequendama.ai
            </a>
            <a
              className="flex items-center gap-2 text-label-sm text-on-surface-variant transition-colors hover:text-[#1faf54]"
              href={ADVISOR_WHATSAPP_URL}
              target="_blank"
              rel="noopener noreferrer"
            >
              <WhatsAppIcon className="size-[18px] text-[#25d366]" />
              WhatsApp {ADVISOR_WHATSAPP_DISPLAY}
            </a>
            <Link
              className="flex items-center gap-2 text-label-sm text-on-surface-variant transition-colors hover:text-primary"
              to="/asistente"
            >
              <Icon name="support_agent" className="text-[18px]" />
              Soporte 24/7 con IA
            </Link>
            <span className="flex items-center gap-2 text-label-sm text-on-surface-variant">
              <Icon name="location_on" className="text-[18px]" />
              Bogotá, Colombia
            </span>
            <span className="mt-2 inline-flex w-fit items-center gap-2 rounded-full border border-outline-variant/50 bg-surface-container-lowest/70 px-3 py-1.5 text-label-sm text-on-surface-variant">
              <Icon name="lock" className="text-[16px] text-primary" />
              Pagos seguros con Polar
            </span>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-4 border-t border-outline-variant/30 pt-8 sm:flex-row">
          <p className="text-label-sm text-on-surface-variant">
            © {year} Tequendama by Salto Angel. Todos los derechos reservados.
          </p>
          <p className="flex items-center gap-1.5 text-label-sm text-on-surface-variant">
            Hecho con
            <Icon name="favorite" filled className="text-[14px] text-error" />
            en Colombia
          </p>
        </div>
      </div>
    </footer>
  )
}
