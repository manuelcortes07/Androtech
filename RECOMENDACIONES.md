# RECOMENDACIONES — qué construir ahora en Kintsu

> Modo recomendación (tech lead + producto). Criterio honesto, sin marketing.
> Estado de partida: refactor B1 cerrado (entrypoint fino, 10 blueprints, 195
> tests + EL JUEZ, seguridad auditada, white-label, multi-tenant con filtro
> automático + juez, suscripciones Stripe). La casa está ordenada **a nivel de
> código**. La tesis de este documento: **lo que falta NO es código de features,
> es poder operar y vender de verdad.**

---

## TL;DR — mi TOP recomendación

**No empieces por una feature. Empieza por hacer el producto OPERABLE.**

El refactor dejó el código limpio, pero Kintsu hoy no está desplegado, no tiene
backups automáticos, el email saliente probablemente no funciona en producción,
y no hay forma de operar la plataforma (alta/soporte/suspensión) sin SQL a mano.
Con eso, ninguna feature 2026 importa: no hay clientes a los que dársela.

**Camino crítico corto (lo que yo haría, en orden):**

1. **Deploy real + backups automáticos + email transaccional en prod** (gate).
2. **Panel superadmin mínimo** (operar sin tocar la BD a mano).
3. **Notificaciones al cliente por EMAIL** (estado de la reparación) — la feature
   con mejor ratio valor/esfuerzo, y la que hace que el taller "sienta" el producto.
4. **Presupuestos con aprobación del cliente** — cierra el bucle comercial
   (presupuesto → aprobar → pagar) sobre los raíles que YA existen.

Todo lo demás (IA, SMS/WhatsApp API, reserva online, analítica avanzada) va
después, y con condiciones. Detalle abajo.

---

## 1. ¿Cierre técnico antes de features?

Respuesta corta: **el refactor B1 NO dejó deuda bloqueante.** Lo que quedó
"opcional" es cosmético.

| Pendiente técnico | ¿Necesario? | Veredicto |
|---|---|---|
| Hooks dentro de `create_app()` | No | **Nice-to-have.** Hoy los `before_request`/`context_processor`/`error_handlers` corren a nivel de módulo sobre la app-singleton, idénticos y cubiertos por la suite. Solo merece la pena si algún día necesitas instanciar apps con configs distintas (p. ej. tests paralelos). Difiérelo. |
| Tests de los blueprints nuevos | Hecho | pagos y dashboard tienen smoke GET; suscripción está cubierta por `test_suscripcion` (22). No es un hueco. |
| Helpers a medias | Ninguno | El refactor quedó cerrado: `csv_utils`, `query_helpers`, `uploads`, `email_valido` extraídos; 0 `@app.route` sueltas; 0 referencias colgantes. |
| **RLS en Postgres** (aplazado a hardening) | Sí, pero no urgente | El aislamiento de aplicación (juez) es bueno, pero un solo `text()`/`__table__` mal escrito lo salta (el propio CLAUDE lo avisa). RLS = cinturón + tirantes. Prográmalo **antes de escalar**, no antes de la 1ª feature. |

**Conclusión:** no hay un cierre técnico que bloquee empezar. Lo que bloquea es
**operativo** (sección 5). Si quieres tocar algo "de código" antes, que sea
*verificar el email saliente en prod* (sección 4), porque media hoja de ruta
depende de él.

---

## 2. Features 2026 — análisis honesto

| Feature | Valor para el taller | Esfuerzo (arq. actual) | Cimientos que YA existen | Riesgos / dependencias |
|---|---|---|---|---|
| **Notificaciones cliente (email)** | **Alto** — es lo que el cliente final más pregunta ("¿está listo?"). Reduce llamadas. | **Bajo** | `Notificador` (B6, canal email listo), `RepairHistorial` (punto de disparo = cambio de estado), emails white-label con logo | Entregabilidad email en prod (infra). Plantillas por estado. |
| **Notificaciones cliente (SMS/WhatsApp)** | Alto, pero es un *add-on* | Medio-alto | Mismo `Notificador` (`registrar_canal`), `TallerSetting` para preferencias | **Coste externo por mensaje** (Twilio/Meta). WhatsApp Business API = fricción de alta. Consentimiento RGPD. No cabe en plan plano. |
| **Presupuestos con aprobación del cliente** | **Alto** — necesidad legal/comercial; reduce disputas ("yo no acepté 120 €") | **Medio** | Portal público + `codigo_publico` (token seguro H3), `Reparacion.precio`, generador PDF de presupuesto, `RepairHistorial`, `audit_log`, `Notificador` | Peso legal de "aprobación" (mitigable: timestamp + IP/UA en `audit_log`). Decisiones de producto: ¿aprobación parcial? (v1: todo/nada). |
| **Reserva / cita online** | Medio-alto **según tipo de taller** (cita vs. walk-in) | Medio-alto | `SolicitudReparacion` (proto ya existe), FullCalendar (ya en stack, ruta `/calendario`), `Notificador` | Complejidad de producto (disponibilidad, aforo, no-shows). Muchos talleres no trabajan con cita. |
| **Analítica** | Medio — el dashboard ya da KPIs buenos | Bajo-medio | Blueprint `dashboard`, patrones de query con índices `taller_id`, Chart.js | Bajo. Vigilar coste de queries a escala. Riesgo: construir "plataforma de analítica" genérica en vez de informes concretos. |
| **IA de apoyo** | Medio, **especulativo** — el valor del taller es confianza y plazos, no IA | Medio (API fácil; lo difícil es un uso real) | Ninguno específico (sería un `ai.py` nuevo); puedes usar la Claude API | **Coste por token** (margen). **Responsabilidad** si la IA cotiza precios o promete reparaciones. Privacidad: enviar datos de cliente a un modelo (RGPD/DPA). |
| **Panel superadmin** | **Alto para TI** (operador), invisible al taller | Medio | `es_superadmin` (H1), `sin_filtro_taller()` (escape auditado), `Taller.estado`/Stripe, `audit_log`, patrón blueprint `admin` | Es el ÚNICO punto que cruza tenants → blindar + auditar. Impersonación = mina de privacidad (consentir + auditar). |

### Notas por feature (lo que no cabe en la tabla)

- **Notificaciones (email)** — empieza por aquí en cuanto el email funcione en
  prod. El disparo es un `notificador.enviar_email(...)` en el punto donde
  `historial.py` registra el cambio de estado. Vive entre `reparaciones` (dispara)
  y `TallerSetting` (preferencias/plantillas por taller). Es casi un quick win.
- **SMS/WhatsApp** — NO antes de tener email funcionando y de decidir
  *packaging* (no puedes absorber SMS ilimitado en 24,99 € plano). Mientras tanto,
  ya tienes el enlace `wa.me` en el portal público: explótalo como canal de coste
  cero antes de integrar API real.
- **Presupuestos con aprobación** — es la feature que **justifica la suscripción**
  porque conecta con el cobro que ya tienes. Flujo: el taller fija precio y envía →
  el cliente abre por su `codigo_publico` → aprueba/rechaza (acción pública firmada,
  como `/consulta`) → se audita (IP/UA ya los capturas) → notifica → habilita pago.
  Modelos: un par de estados en `Reparacion` (p. ej. `presupuesto_estado`) +
  fecha/medio de aprobación. Vive en `publico` (aprobar/rechazar) + `reparaciones`
  (emitir).
- **Reserva online** — `SolicitudReparacion` ya cubre el "el cliente contacta"
  a coste casi cero. La reserva con franjas es una apuesta de producto mayor
  (modelo de disponibilidad, confirmaciones, conflictos). **Valida demanda antes
  de construirla.** Quick win alternativo: pulir el flujo de solicitudes que ya
  existe.
- **Analítica** — no construyas un módulo genérico. Añade informes **concretos**
  que un dueño pide: **cierre de caja diario** y **resumen de IVA trimestral**
  (para la gestoría). Eso se quiere y se paga; "más gráficos" no.
- **IA** — la última, y acotada. El primer toque seguro: **redactar el mensaje de
  estado al cliente** (bajo riesgo). NUNCA precios ni diagnósticos (responsabilidad).
  Revísala cuando talleres que pagan te digan dónde pierden tiempo de verdad.
- **Superadmin** — necesario para operar a >5 talleres. Versión mínima
  read-mostly: lista cross-tenant de talleres (vía `sin_filtro_taller`), estado de
  suscripción, MRR/trials, suspender/reactivar a mano. Impersonación: déjala para
  v2 y bien auditada.

---

## 3. El orden que yo seguiría (camino crítico a "se puede vender y operar")

El encuadre honesto: tienes un producto **construido**, no **operable**. El orden
mezcla operación y la feature que cierra el bucle comercial.

```
GATE  Deploy real + backups automáticos + email transaccional en prod
  │   (sin esto, no hay clientes; media hoja de ruta depende del email)
  ▼
1.    Panel superadmin mínimo
  │   (operar altas/soporte/suspensión sin SQL a mano)
  ▼
2.    Notificaciones al cliente por EMAIL (estado de reparación)
  │   (mejor ratio valor/esfuerzo; el cliente final "siente" el producto,
  │    y eso es lo que hace que el taller siga pagando)
  ▼
3.    Presupuestos con aprobación del cliente
  │   (presupuesto → aprobar → pagar, sobre portal + cobro YA existentes;
  │    es la feature que justifica la suscripción)
  ▼
4.    Add-ons bajo demanda y con packaging:
      SMS/WhatsApp (de pago) · informes caja/IVA · reserva (si hay demanda)
      · IA acotada a texto de bajo riesgo
```

**Por qué este orden:** las features 2 y 3 son el "wow" para el cliente final y
la columna comercial; pero el GATE y el paso 1 son lo que te permite **tener**
clientes. No construyas nada de clase "paso 4" antes de poder desplegar, respaldar
y operar.

---

## 4. Quick wins (alto impacto, bajo esfuerzo) — AHORA

1. **Verificar la entregabilidad de email en Render** *(media hora)*. Railway
   bloqueaba SMTP saliente; si Render hace lo mismo, **media hoja de ruta
   (notificaciones, verificación, reset, aprobación de presupuesto) está sobre un
   canal muerto**. Compruébalo ANTES de construir sobre él; si está bloqueado,
   presupuesta un proveedor transaccional (relay HTTP) en vez de SMTP directo.
2. **"Cierre de caja diario"** *(una query + un export)*. Un dueño concilia caja
   a diario; es percepción de valor altísima por esfuerzo mínimo. Vive en
   `dashboard`.
3. **Notificación de estado por email** *(la costura ya existe)*. Engánchala al
   punto de cambio de estado en `historial.py` → `notificador`. Es a la vez quick
   win y el inicio de la feature #2.
4. **Decidir la política de verificación de email** *(decisión de producto)*. Hoy
   "nunca bloquea" (lo dice CLAUDE). Decide si a partir de cierto punto se exige.
   Cero código nuevo, evita ambigüedad.
5. **Onboarding / empty-state** *(bajo)*. Un taller nuevo entra a... vacío. Un
   checklist de puesta en marcha o un toggle de datos de ejemplo mueve la
   conversión trial→pago. Barato y se suele olvidar.
6. **NO** hagas el `create_app()` de los hooks todavía. Dilo en el roadmap como
   "diferido": no aporta valor a un cliente y toca middleware de seguridad.

---

## 5. Lo que me preocupa / lo que quizá no estás viendo

> Esto es lo importante del documento. Los huecos no están en las features, están
> en operar un SaaS con datos reales de terceros.

- **🔴 Deploy + entregabilidad de email = el elefante.** Notificaciones,
  verificación, reset de contraseña, aprobación de presupuesto y confirmaciones de
  reserva **dependen del email saliente en prod**. Railway lo bloqueaba; verifica
  Render y asume que probablemente necesitas un proveedor transaccional. Es el
  mayor riesgo individual de toda la hoja de ruta.
- **🔴 Backups automáticos.** Hoy la BD se commitea al repo (comodidad de dev) y
  no hay backups automáticos. **Antes del primer cliente que pague**, necesitas
  backups automáticos *y restauración probada*. Perder datos de un taller es
  existencial y legalmente grave (RGPD).
- **🟠 Cumplimiento fiscal (España).** "Serie fiscal/NIF depende de gestoría",
  pero si los talleres **facturan a sus clientes a través de Kintsu**, entran en
  juego numeración correlativa, IVA, conservación y, sobre todo, la **Ley
  Antifraude / Reglamento Verifactu** (software de facturación verificable). Es un
  durmiente que puede **bloquear vender a negocios que cumplen**. Háblalo con la
  gestoría YA: puede condicionar el modelo de datos de facturación.
- **🟠 RGPD operativo.** Eres el *encargado del tratamiento* de PII de los clientes
  de cada taller. Necesitas: un **DPA** con cada taller, una vía de **exportar/
  borrar** los datos de un cliente (derecho de supresión), y política de retención.
  "Bloquear nunca borra" está bien, pero las solicitudes de supresión necesitan
  camino. El `audit_log` + el white-label hacen esto real ya.
- **🟠 Packaging vs. coste externo.** Plan único 24,99 €. SMS e IA tienen coste
  por uso **ilimitado** que un plan plano no absorbe. Decide medición/add-ons
  ANTES de enviar canales que cuestan dinero por mensaje/token.
- **🟡 RLS diferida.** El juez cubre el aislamiento de aplicación, pero un raw SQL
  mal escrito lo salta. Postgres RLS antes de escalar (no antes de la 1ª feature).
- **🟡 Impersonación en superadmin.** Cuando construyas soporte, impersonar a un
  taller debe ir consentido + auditado, o es una mina de privacidad.
- **🟢 Escala técnica: no te preocupes todavía.** Single-DB/single-region aguanta
  mucho. El riesgo real de escala es **operativo** (soporte, backups, facturación),
  no técnico. No sobre-ingenierices.

---

## Cierre

El refactor B1 hizo bien su trabajo: el código está listo para crecer. Pero
"listo para construir features" no es "listo para vender". Mi recomendación
fuerte: **gasta el próximo bloque en hacer Kintsu operable (deploy + backups +
email + superadmin mínimo), y luego construye notificaciones por email y
presupuestos con aprobación** — las dos features que, sobre lo que ya tienes,
convierten Kintsu en algo que un taller paga y su cliente final nota. IA, SMS,
reserva y analítica avanzada: después, con demanda probada y packaging decidido.

Y antes de cualquier cosa: **comprueba que el email sale en producción.** Si no,
medio roadmap está construido sobre arena.
