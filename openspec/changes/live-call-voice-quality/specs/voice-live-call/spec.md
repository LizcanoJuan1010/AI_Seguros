# Voice Live Call Specification

## Purpose

Comportamiento de la llamada de voz en tiempo real (`/ws/voice/live`):
contexto, turno, cierre de venta y latencia. Primer spec (sin versión previa).

## Requirements

### Requirement: Continuidad de contexto conversacional

El sistema MUST conservar en el historial al menos el mensaje `user` más
reciente en cada turno, incluso cuando turnos previos generaron muchos
mensajes de herramientas (`tool`/`assistant tool_calls`). MUST NOT enviar al
modelo un historial vacío mientras la sesión tenga un turno de usuario
previo real.

#### Scenario: Turno con muchas tool-calls no vacía el historial

- GIVEN una llamada con 3 turnos completados, el último con 6 tool-calls
- WHEN el usuario habla un cuarto turno
- THEN el historial enviado al modelo no es una lista vacía y contiene al
  menos un mensaje `user` real (no el hint de canal)

#### Scenario: Ventana llena prioriza el turno de usuario más reciente

- GIVEN que la ventana de historial tiene un límite fijo de mensajes
- WHEN ese límite se alcanza a mitad de una secuencia larga de herramientas
- THEN el sistema SHOULD priorizar mensajes `user` sobre `tool` en vez de
  devolver una lista vacía

### Requirement: Sin saludo repetido

El sistema MUST NOT repetir el saludo/presentación inicial en ningún turno
posterior al primero de una misma llamada.

#### Scenario: Segundo turno en adelante no re-saluda

- GIVEN una llamada donde el asistente ya saludó en el turno 1
- WHEN responde en el turno 2 o posterior
- THEN la respuesta no contiene una presentación/saludo inicial, y el hint
  de canal no queda mezclado con el mensaje real del usuario en el
  historial persistido

### Requirement: Cierre autónomo de venta en el canal de voz

El sistema MUST ofrecer y ejecutar el cierre autónomo de la venta (cotizar
→ datos → consentimiento → identidad → riesgo → firma → pago → emisión) en
voz, con la misma disposición a cerrar que WhatsApp. MUST NOT derivar el
cierre a otro canal por defecto cuando hay intención de compra.

#### Scenario: Cliente listo para comprar en la llamada

- GIVEN un cliente que ya eligió una opción cotizada
- WHEN dice que quiere continuar
- THEN el asistente avanza el cierre en la misma llamada, sin derivar a
  WhatsApp como única salida

### Requirement: Detección de turno semántica

El sistema SHOULD determinar el fin del turno usando comprensión semántica
del habla (no solo silencio fijo), con decisión de fin de turno en menos de
400ms desde que el usuario termina de hablar.

#### Scenario: Pausa natural a mitad de frase no corta el turno

- GIVEN una pausa breve dentro de una frase incompleta
- WHEN dura menos que el silencio configurado pero el contenido es
  claramente incompleto
- THEN el sistema no dispara el turno todavía

#### Scenario: Fin de turno se detecta rápido tras una frase completa

- GIVEN un usuario que termina una frase completa y calla
- WHEN pasa el umbral de confianza de fin de turno
- THEN el sistema dispara el turno en menos de 400ms

### Requirement: Latencia de respuesta hablada

El sistema SHOULD empezar a reproducir audio antes de que el modelo
termine de generar el texto completo del turno, y SHOULD evitar reabrir una
conexión de síntesis nueva en cada turno.

#### Scenario: Audio arranca antes de la respuesta completa

- GIVEN una respuesta de varias oraciones
- WHEN la primera oración ya está lista
- THEN el sistema reproduce esa oración sin esperar el resto

### Requirement: Interrupción del usuario (barge-in) sigue funcionando

El sistema MUST seguir permitiendo que el usuario interrumpa al asistente
mientras habla, cortando el audio en curso, bajo el nuevo mecanismo de
turno y síntesis.

#### Scenario: Usuario interrumpe mientras el asistente habla

- GIVEN que el asistente está reproduciendo audio
- WHEN el usuario empieza a hablar
- THEN el audio se corta de inmediato y el sistema queda listo para el
  nuevo turno
