# Despliegue de AndroTech SaaS (Render, plan free)

Despliegue de la rama **`saas-migration`** en Render con PostgreSQL. Es un
servicio **nuevo y separado** del despliegue del TFG — no lo toca.

> Modo de pago de Stripe: **TEST**. El salto a `live` es una fase posterior.

---

## 1. Provisionar todo con el Blueprint (1 vez)

El fichero [`render.yaml`](render.yaml) declara la web + el Postgres + las
variables. Render lo lee y crea todo.

1. Entra en https://dashboard.render.com → **New +** → **Blueprint**.
2. Conecta tu cuenta de **GitHub** y elige el repo **`manuelcortes07/Androtech`**.
3. Render detecta `render.yaml` en la rama **`saas-migration`**. Si te deja
   elegir rama, selecciona `saas-migration`. Pulsa **Apply**.
4. Render crea:
   - el servicio web **androtech-saas** (gunicorn, healthcheck `/health`),
   - la base de datos **androtech-saas-db** (PostgreSQL free),
   - e inyecta `DATABASE_URL` y genera `SECRET_KEY` automáticamente.

La primera build instala `requirements.txt` y arranca gunicorn. Al primer
arranque, la app **crea el esquema completo en Postgres** desde los modelos
(14 tablas, `taller_id`, UNIQUEs, FKs, roles, taller 1).

---

## 2. Rellenar las variables SECRETAS (en el panel)

El Blueprint deja estas variables **vacías** (`sync:false`) para que las pongas
tú. Ve a: servicio **androtech-saas** → pestaña **Environment** → añade el valor
de cada una:

| Variable | Qué es | De dónde sale |
|----------|--------|---------------|
| `STRIPE_SAAS_SECRET_KEY` | Clave secreta del SaaS (test) | tu `sk_test_...` (la misma de reparaciones vale) |
| `STRIPE_SAAS_WEBHOOK_SECRET` | Firma webhook suscripción | del paso 4 (Stripe) |
| `STRIPE_SECRET_KEY` | Clave secreta reparaciones (test) | tu `sk_test_...` |
| `STRIPE_PUBLISHABLE_KEY` | Clave pública reparaciones | tu `pk_test_...` |
| `STRIPE_WEBHOOK_SECRET` | Firma webhook reparaciones | del webhook de reparaciones |
| `MAIL_USERNAME` | Email emisor | tu Gmail |
| `MAIL_PASSWORD` | App Password de Gmail (16 chars) | Google → App Passwords |
| `MAIL_DEFAULT_SENDER` | Remitente | tu Gmail |

> `STRIPE_SAAS_PRICE_ID`, `APP_ENV=production`, `SECRET_KEY` y `DATABASE_URL` ya
> los pone el Blueprint — no los toques.

Tras guardar, Render redepliega solo.

---

## 3. Comprobar que arranca

- En el panel del servicio verás la **URL pública**: `https://androtech-saas.onrender.com`
  (o con un sufijo si el nombre estaba cogido).
- `https://<tu-url>/health` debe responder `{"status":"ok"}` (200).
- `https://<tu-url>/signup` debe mostrar la página de alta.

---

## 4. Webhook de la SUSCRIPCIÓN en Stripe (test) → producción

Una vez tengas la URL pública, hay que decirle a Stripe que avise a esa URL.

En el dashboard de Stripe (modo test): **Developers → Webhooks → Add endpoint**:
- **Endpoint URL**: `https://<tu-url>/saas/webhook`
- **Eventos a escuchar**: `checkout.session.completed`,
  `customer.subscription.updated`, `customer.subscription.deleted`,
  `invoice.payment_failed`, `invoice.paid`.
- Al crearlo, Stripe muestra el **Signing secret** (`whsec_...`) → cópialo a la
  variable `STRIPE_SAAS_WEBHOOK_SECRET` en Render (paso 2).

> El `stripe listen` local era solo para desarrollo. En producción el webhook
> es este endpoint público.

---

## 5. Probar el alta de punta a punta

1. Ve a `https://<tu-url>/signup`, crea un taller.
2. Paga con tarjeta de prueba `4242 4242 4242 4242` (fecha futura, CVC 123).
3. Vuelves al panel, en prueba de 14 días. En Stripe → Webhooks verás el
   evento entregado con `200`.

---

## Notas del plan free (importante)

- **La web se duerme** tras ~15 min sin tráfico; la primera visita tarda ~30s
  en despertar. Normal en free.
- **El Postgres free se borra a los ~30 días.** Para producción real, sube el
  Postgres a un plan de pago (o migra a otro Postgres) — no pierdas datos de
  clientes reales en free.
- **Sin disco persistente** en free: las fotos/firmas subidas se pierden en cada
  redeploy. Mejora futura: almacenamiento de objetos (S3 / Cloudflare R2) — la
  app ya centraliza la ruta en `UPLOADS_DIR`.
- **SMTP saliente** suele estar bloqueado en PaaS → el email puede no enviar en
  producción (igual que en el TFG). No es un bug.

---

## Variables de entorno (referencia)

Ver [`.env.example`](.env.example) para la lista completa con descripciones. En
local se usan desde `.env`; en Render, desde el panel / Blueprint.

| Variable | Secreta | La pone |
|----------|:------:|---------|
| `APP_ENV` | no | Blueprint (`production`) |
| `SECRET_KEY` | sí | Blueprint (autogenerada) |
| `DATABASE_URL` | sí | Render (del Postgres) |
| `STRIPE_SAAS_PRICE_ID` | no | Blueprint |
| `STRIPE_SAAS_SECRET_KEY` / `STRIPE_SAAS_WEBHOOK_SECRET` | sí | tú |
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | sí | tú |
| `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_DEFAULT_SENDER` | sí | tú |
| `UPLOADS_DIR` | no | opcional (default `static/uploads`) |
| `SEED_KEY` | no | opcional (default `demo2026`) |
