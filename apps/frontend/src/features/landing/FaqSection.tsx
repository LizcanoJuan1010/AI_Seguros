import { Link } from 'react-router-dom'
import { Icon } from '../../components/ui/Icon'
import { Reveal } from '../../components/ui/Reveal'

const faqs = [
  {
    q: '¿Cómo funciona el asesor de IA?',
    a: 'Hablas o chateas con nuestra IA como lo harías con un asesor humano. Entiende lenguaje natural, responde al instante y está disponible 24/7 para cotizar, resolver dudas o acompañarte en un siniestro.',
  },
  {
    q: '¿Puedo hablar con una persona si lo prefiero?',
    a: 'Claro. En cualquier momento de la conversación puedes pedir que te transfieran a un asesor certificado. La IA le entrega todo el contexto para que no tengas que repetir nada.',
  },
  {
    q: '¿Cómo pago mi póliza?',
    a: 'Los pagos se procesan de forma segura con la pasarela Polar: tarjetas de crédito y débito, con cobro en pesos colombianos. Nunca almacenamos los datos de tu tarjeta en nuestros servidores.',
  },
  {
    q: '¿Mis datos están seguros?',
    a: 'Sí. Usamos cifrado AES-256 de nivel bancario, cumplimos la ley de Habeas Data colombiana y tus datos nunca se venden ni comparten con terceros sin tu autorización.',
  },
  {
    q: '¿Qué tan rápido recibo mi póliza?',
    a: 'Minutos después de confirmar el pago recibes tu póliza en PDF en el correo, y tu cobertura queda activa desde ese momento.',
  },
  {
    q: '¿Puedo cancelar cuando quiera?',
    a: 'Sí, sin cláusulas de permanencia ni penalidades. Puedes pausar o cancelar tu plan desde el asistente en cualquier momento.',
  },
]

export function FaqSection() {
  return (
    <section id="faq" className="px-margin-mobile py-24 md:px-margin-desktop">
      <div className="mx-auto grid max-w-container-max grid-cols-1 gap-12 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-16">
        <Reveal>
          <div className="lg:sticky lg:top-28">
            <p className="mb-2 font-hand text-xl font-semibold text-secondary">
              Resolvemos tus dudas
            </p>
            <h2 className="mb-4 text-headline-lg text-primary">
              Preguntas frecuentes
            </h2>
            <p className="mb-8 text-body-md text-on-surface-variant">
              Todo lo que necesitas saber antes de dar el paso. ¿No encuentras
              tu pregunta? Nuestro asistente la responde en segundos.
            </p>
            <Link
              to="/asistente"
              className="inline-flex items-center gap-2 rounded-md border-2 border-primary px-6 py-3 text-label-md font-bold text-primary transition-colors hover:bg-primary/5"
            >
              <Icon name="smart_toy" className="text-[20px]" />
              Preguntarle al asistente
            </Link>
          </div>
        </Reveal>
        <div className="flex flex-col gap-3">
          {faqs.map((faq, i) => (
            <Reveal key={faq.q} delay={i * 70}>
              <details className="group rounded-lg border border-outline-variant/40 bg-surface-container-lowest/80 transition-shadow open:shadow-md">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-5 text-body-md font-semibold text-primary [&::-webkit-details-marker]:hidden">
                  {faq.q}
                  <Icon
                    name="expand_more"
                    className="shrink-0 text-on-surface-variant transition-transform duration-300 group-open:rotate-180"
                  />
                </summary>
                <p className="px-6 pb-6 text-body-md text-on-surface-variant">
                  {faq.a}
                </p>
              </details>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
