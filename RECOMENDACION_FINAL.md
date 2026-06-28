# RECOMENDACIÓN FINAL — Kintsu

> Tech lead + producto. Sin marketing, sin "sí a todo". La verdad incómoda.
> Estado de partida: código sólido (243 tests + JUEZ, ruff limpio, multi-tenant
> con juez, blueprints, white-label, presupuestos+pago, superadmin, salud cerrada).

## TL;DR — el veredicto

**El proyecto NO necesita más construcción. Necesita SALIR al mundo.** Tienes un
producto técnicamente más que suficiente para un primer cliente, y llevas meses
añadiendo features mientras lo esencial para *cobrar de verdad* sigue sin hacerse:
no está desplegado, el email no funciona en producción, no hay backups, y hay
**dos bloqueadores legales/financieros reales** que nadie ha tocado. Cada feature
nueva ahora mismo es procrastinación con buena letra.

**Mi TOP recomendación única:** despliega en Render+Postgres y **usa Kintsu tú
mismo como primer taller (dogfood) durante 2-3 semanas** antes de venderlo a nadie.
Eso convierte la teoría en realidad y te dirá, en una semana, qué importa de
verdad — que no es nada de lo que está en el backlog de features.

---

## 1. ¿Está listo para usarse y cobrar?

**Para usarse (técnicamente): sí. Para cobrar a un tercero: no todavía.** Faltan
cosas que no son features, son requisitos de operar un SaaS con dinero y datos
ajenos:

- **No está desplegado.** Un SaaS sin URL pública no tiene clientes. (Render+
  Postgres preparado, pero el cutover real nunca se ha ejecutado.)
- **Email no funciona en prod.** Notificaciones, aprobación de presupuesto, reset
  de contraseña y verificación dependen de SMTP que el hosting bloquea → media
  funcionalidad muerta hasta que metas un proveedor por API (Resend/SES/Postmark).
- **Sin backups automáticos.** Datos de terceros sin copia de seguridad = ruleta
  rusa. Inaceptable antes del primer cliente.
- **Stripe en modo TEST.** No se ha cobrado un euro real nunca.
- **🔴 Dos bloqueadores legales/financieros sin resolver** (ver pregunta 4): a
  quién llega el dinero de las reparaciones, y Verifactu/facturación.

Resumen: **listo para un PILOTO/dogfood contigo**, no para facturar a un taller
ajeno. Y está perfectamente bien — es lo normal. Lo malo sería seguir construyendo.

## 2. Si solo pudieras hacer UNA cosa

**Desplegar en producción (Render+Postgres) y dogfood con tu propio taller.**

Por qué esta y no otra:
- Es la única acción que **convierte el proyecto en un producto**. Todo lo demás
  (más features, más pulido) es valor potencial; esto es valor real.
- **Te obliga a cerrar lo que importa**: en cuanto intentes usarlo en serio,
  descubrirás en horas que el email no sale, que necesitas backups, que el flujo
  de pago va a la cuenta equivocada. Esos descubrimientos valen más que 10 features.
- **Valida el trabajo ya hecho**: el cutover a Postgres ejercita por primera vez
  en real el esquema, las migraciones y el arreglo de borrados (C1) que acabas de
  hacer. Hoy todo eso es teoría no probada en prod.
- Es de **esfuerzo acotado**: el `render.yaml`, el `APP_ENV=production`, las
  cookies Secure y la SECRET_KEY ya están listos. Es conectar, no construir.

Si lo quieres aún más atómico: **conecta el repo en Render y haz que arranque
contra Postgres.** Ese primer `git push → deploy verde` es el hito que llevas
meses posponiendo.

## 3. Las features que NO hemos hecho — ¿alguna AHORA?

**Ninguna. Todas son prematuras hasta tener talleres pagando.** Tajante:

| Feature | Veredicto | Por qué |
|---|---|---|
| **IA** | ❌ No | Coste por uso, riesgo de responsabilidad, cero demanda probada. Un taller paga por plazos y confianza, no por IA. La última de la lista. |
| **Reserva online** | ❌ No | Ya tienes `solicitudes_reparacion` (el cliente contacta) a coste casi cero. La reserva con franjas es otra apuesta de producto sin demanda validada. |
| **Analítica avanzada** | ❌ No | El dashboard ya da KPIs. "Más gráficos" no se paga. Si acaso, informes concretos (cierre de caja, IVA trimestral) — pero a petición de un cliente real. |
| **SMS/WhatsApp** | ❌ Ahora no | Coste externo por mensaje que el plan plano (24,99€) no absorbe. Primero email funcionando + packaging. Mientras, ya tienes el enlace `wa.me` gratis. |
| **App móvil** | ❌ No | El sitio es responsive/PWA. Una app nativa es 10× el coste para 0× la necesidad actual. |
| **Multi-idioma** | ❌ No | Vendes a talleres en España. i18n es trabajo enorme sin un solo cliente que lo pida. |

La pregunta correcta no es "¿qué feature construyo?", es "¿por qué aún no tengo un
taller usándolo?". El backlog de features es una forma cómoda de no enfrentarte a
deploy, gestoría y ventas.

## 4. Riesgos / deuda que quizá NO estás viendo

> Esto es lo importante del documento.

- **🔴 ¿A quién llega el dinero de las reparaciones?** El pago de reparación usa
  `stripe.api_key` global = **la cuenta Stripe de la PLATAFORMA**, no la del
  taller. Es decir: hoy, el dinero que paga el cliente final de un taller **caería
  en TU cuenta**, no en la del taller. Para un SaaS multi-taller esto es casi
  seguro **incorrecto y un problema legal** (estarías manejando/reteniendo dinero
  ajeno → regulación de pagos). Lo correcto es **Stripe Connect** (cada taller
  conecta su cuenta y cobra directo). Es un cambio de arquitectura de pagos, no
  trivial, y es **bloqueante para vender a varios talleres**. Probablemente el
  mayor punto ciego del proyecto.
- **🔴 Verifactu / facturación legal (España).** Si los talleres emiten facturas
  a sus clientes vía Kintsu (el PDF "factura" existe), entras en el Reglamento
  Verifactu / Ley Antifraude (software de facturación verificable, plazos 2025-26).
  Puede bloquear la venta a negocios que cumplen. Háblalo con la gestoría **antes**
  de prometer facturación legal; puede condicionar el modelo de datos.
- **🟠 RGPD — derecho de supresión chocando con tu propia decisión C1.** Acabas de
  decidir (bien, por integridad) **impedir borrar un cliente con reparaciones**.
  Pero eso significa que **no tienes camino para atender un "bórrame mis datos"**
  (derecho de supresión RGPD) de un cliente con reparaciones. Eres el *encargado
  del tratamiento*: necesitas DPA con cada taller y una vía de anonimizar/borrar.
  La decisión técnica correcta abrió un hueco de cumplimiento que hay que cerrar
  (p. ej. anonimizar el cliente en vez de borrarlo).
- **🟠 El cutover a Postgres no se ha probado en real.** La rama Postgres de las
  migraciones (incl. `asegurar_fks_cascade`) solo corre en el CI; nunca contra una
  BD Postgres de verdad con datos. El primer deploy es también el primer test real.
- **🟠 Email = punto único de fallo de media app.** Ya señalado, pero conviene
  repetirlo: sin email transaccional en prod, presupuestos y notificaciones (parte
  del valor diferencial) no llegan.
- **🟡 Operación a ciegas.** Sentry está como costura apagada; no hay alertas ni
  monitorización. Con un cliente real, un 500 a las 22:00 no te enteras.
- **🟡 Onboarding vacío.** Un taller nuevo entra a una app vacía. El primer día
  define la conversión trial→pago; hoy no hay guía ni datos de ejemplo.

## 5. Veredicto: ¿más construcción o salir al mundo?

**Salir al mundo. Sin dudarlo.** El código está sobradamente por encima de lo que
necesita un primer cliente; el cuello de botella es 100% operativo y de negocio
(deploy, dinero, legal), no técnico. Seguir construyendo features es el camino
cómodo y el equivocado: añadirías superficie que mantener sobre algo que aún no
ha tocado a un usuario real.

El orden que yo seguiría:
1. **Deploy + dogfood contigo** (Render+Postgres, email API, backups, Stripe live).
2. **Resolver los dos bloqueadores antes de cobrar a terceros**: Stripe Connect
   (dinero al taller correcto) + Verifactu con la gestoría.
3. **Conseguir 1 taller piloto real** (idealmente alguien que conozcas) y
   escuchar qué le falta. Eso —no este documento— es tu siguiente backlog.
4. Recién entonces, features, guiadas por lo que pida ese taller que paga.

Lo más valiente que puedes hacer ahora no es escribir más código: es desplegarlo
y dejar que alguien lo use.
