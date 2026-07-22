import { HeroStub } from '../features/landing/HeroStub'
import { TrustStrip } from '../features/landing/TrustStrip'
import { ProductCards } from '../features/landing/ProductCards'
import { InsightSection } from '../features/landing/InsightSection'

export function LandingPage() {
  return (
    <>
      <main className="pt-24">
        <div className="relative">
          <HeroStub />
          <div className="pointer-events-none absolute inset-x-0 bottom-0">
            <div className="pointer-events-auto">
              <TrustStrip />
            </div>
          </div>
        </div>
        <ProductCards />
        <InsightSection />
      </main>
      <footer className="mt-24 w-full border-t border-outline-variant/20 bg-surface-variant py-stack-lg">
        <div className="mx-auto grid w-full max-w-container-max grid-cols-1 gap-gutter px-margin-mobile md:grid-cols-2 md:px-margin-desktop">
          <div className="space-y-stack-md">
            <span className="text-display-lg-mobile font-bold text-primary">
              Tequendama
            </span>
            <p className="max-w-sm text-body-md text-on-surface-variant">
              Protección inteligente inspirada en la fuerza de la naturaleza.
              Soluciones de seguros con propósito para el mundo moderno.
            </p>
            <p className="text-label-sm text-on-surface-variant">
              © 2024 Tequendama by Salto Angel. Todos los derechos reservados.
            </p>
          </div>
          <div className="flex flex-col gap-12 pt-8 md:flex-row md:justify-end md:pt-0">
            <div className="flex flex-col gap-3">
              <span className="text-label-md font-bold text-primary">
                Compañía
              </span>
              <a className="text-label-sm text-on-surface-variant hover:text-primary" href="#seguridad">
                Seguridad
              </a>
              <a className="text-label-sm text-on-surface-variant hover:text-primary" href="#privacidad">
                Privacidad
              </a>
              <a className="text-label-sm text-on-surface-variant hover:text-primary" href="#terminos">
                Términos
              </a>
            </div>
            <div className="flex flex-col gap-3">
              <span className="text-label-md font-bold text-primary">
                Contacto
              </span>
              <a className="text-label-sm text-on-surface-variant hover:text-primary" href="#soporte">
                Soporte 24/7
              </a>
              <span className="text-label-sm text-on-surface-variant">
                Bogotá, Colombia
              </span>
              <a
                className="text-label-sm text-on-surface-variant hover:text-primary"
                href="mailto:hola@tequendama.ai"
              >
                hola@tequendama.ai
              </a>
            </div>
          </div>
        </div>
      </footer>
    </>
  )
}
