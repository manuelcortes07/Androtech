# REBRANDING → "Kintsu" + branding por taller

> Rama `saas-migration`. El producto (la plataforma SaaS) pasa a llamarse
> **Kintsu** (antes "AndroTech"). Este documento es el registro del trabajo:
> inventario inicial clasificado (Bloque 1), qué cambió por plano (Bloque 2/3),
> campos nuevos en `Taller` + migración, y la verificación final (Bloque 4).

---

## Los dos planos (decisión de diseño)

El rebranding NO es un buscar-y-reemplazar. Hay **dos identidades distintas** que
nunca deben mezclarse:

- **(a) PLATAFORMA = "Kintsu".** Es el SaaS en sí: lo que ven los **dueños/
  técnicos del taller** cuando entran a gestionar. Superficies: el **panel**
  (sidebar/topbar), las páginas de **cuenta** (login, signup, reset, perfil),
  **suscripción**, la **PWA**, los **emails de cuenta** (reset/verificación), el
  README. → todo esto dice **Kintsu**.

- **(b) TALLER = datos del taller (dinámicos, de BD).** Es lo que ven los
  **clientes finales** del taller y lo que firma legalmente el taller.
  Superficies: el **escaparate público** (landing, consulta, mis-reparaciones,
  sobre-nosotros), los **PDF** (presupuesto/factura/ticket/historial), los
  **CSV** de export y los **emails al cliente** (pago, estado, nueva reparación,
  bienvenida). → todo esto sale del **Taller activo** (nombre, dirección,
  teléfono, email, NIF, logo), **nunca** hardcodeado y **nunca** "Kintsu".

> ⚠️ **Matiz de producto importante.** El enunciado del Bloque 2 incluía "textos
> de la landing" dentro de la marca plataforma. Pero la landing actual
> (`index.html`) **no** es una página de marketing de Kintsu: es el **escaparate
> de un taller** ("Reparamos tus dispositivos", WhatsApp a un número concreto,
> "Huelva"). Un cliente de "Reparaciones Pérez" **no** debe ver "Kintsu" ahí.
> Por eso la landing/escaparate se trata como **plano (b) taller-dinámico**, no
> como Kintsu. La marca Kintsu solo aparece, si acaso, como un discreto
> *"Hecho con Kintsu"* al pie. Si en realidad querías una landing de marketing
> de Kintsu separada, dímelo y la separo (sería una página nueva, no esta).

---

## Bloque 1 — Inventario clasificado

Leyenda: **[plataforma]** marca del SaaS → Kintsu · **[taller-hardcode]** dato de
taller incrustado → debe salir de BD · **[seed]** datos del taller demo ·
**[test]** texto fijado en tests · **[doc/comentario]** documentación o
comentarios · **[interno]** identificador técnico no visible como marca
(se justifica dejarlo).

### Plantillas — chrome y títulos

| Fichero / línea | Texto | Clase |
|---|---|---|
| `base.html` :6,50,117,168,170 | `<title>AndroTech ·`, sidebar/topbar/footer `AndroTech`, `© AndroTech` | **[plataforma]** (panel) |
| `base.html` :169 | `Huelva · … · +34 633 234 395` (pie) | **[taller-hardcode]** |
| `base_public.html` :6,47,82,85 | título, nav brand, footer brand, `© AndroTech` | **[taller-hardcode]** (escaparate → nombre del taller) |
| `base_public.html` :84 | `Huelva · … · +34 633 234 395` | **[taller-hardcode]** |
| `login.html` :6,40,87 | título, wordmark, "Sistema de gestión AndroTech" | **[plataforma]** |
| `signup.html` :6,31 | título, wordmark | **[plataforma]** |
| `reset_solicitar.html` :6 · `reset_confirmar.html` :6 | título | **[plataforma]** |
| `suscripcion_bloqueado.html` :6 · `suscripcion.html` :45 | título, "Plan AndroTech" | **[plataforma]** |
| ~25 plantillas del panel | `{% block title %}… - AndroTech{% endblock %}` | **[plataforma]** |
| `index.html` :2,13,19,80 | "en Huelva", "Servicio técnico · Huelva", `wa.me/34633234395` | **[taller-hardcode]** |
| `consulta.html` :133 | "AndroTech nunca almacena tu tarjeta" | **[taller-hardcode]** (es el taller quien cobra) |
| `mis_reparaciones.html` :10,357 | "…tus reparaciones en AndroTech" | **[taller-hardcode]** |
| `sobre_nosotros.html` :10,26,36,… | historia "AndroTech nació en 2018…", "Huelva" | **[taller-hardcode]** (copy de escaparate) |
| `admin_solicitudes.html` :123 | texto WhatsApp "…en AndroTech." | **[taller-hardcode]** |
| `clientes.html` :81 | "Panel administrativo — AndroTech" | **[plataforma]** |
| `admin_test_email.html` :100 | nombre sugerido "AndroTech" para App Password | **[doc/comentario]** (instrucción Gmail) |

### Emails

| Fichero | Texto | Clase |
|---|---|---|
| `emails/bienvenida_cliente.html`, `nueva_reparacion.html`, `payment_confirmation.html`, `repair_status_update.html` | logo/título/footer "AndroTech", "Huelva, España" | **[taller-hardcode]** (taller → su cliente) |
| `emails/reset_password.html`, `verificar_email.html` | (de cuenta) | **[plataforma]** |
| `utils/email_service.py` :126,150,172,194,211,227,240,253 | asuntos "… - AndroTech" | mixto: pago/estado/nueva/bienvenida **[taller-hardcode]**; reset/verify/test **[plataforma]** |

### Documentos generados (PDF / CSV)

| Fichero / línea | Texto | Clase |
|---|---|---|
| `utils/pdf_generator.py` :32-40 (`COMPANY`), 75,248,255,321-322 | nombre/dirección/tel/email/footer "AndroTech / Huelva / +34… / email personal" | **[taller-hardcode]** ← **hallazgo nº1** |
| `app.py` :1957,2036 | PDF historial cliente: título "AndroTech", pie "AndroTech, Huelva \| +34…" | **[taller-hardcode]** |
| `app.py` :3229,3289 | ticket recogida: título "AndroTech", pie "AndroTech, Huelva — +34…" | **[taller-hardcode]** |
| `app.py` :2141-2142,2236 (`_csv_empresa_header`, pie) | "ANDROTECH — Taller…", "Huelva … Tel … email" | **[taller-hardcode]** |
| `app.py` :638,645,2243,2326,4312 | nombres de fichero de descarga "AndroTech_*", "Seed demo - AndroTech" | **[plataforma]**/cosmético (nombre de archivo) |
| `app.py` :1199 | flash "¡Bienvenido a AndroTech! Tu prueba…" | **[plataforma]** |
| `app.py` :2036/2236 etc. "Fin del informe \| AndroTech" | pie de CSV | **[taller-hardcode]** |

### Seed / demo

| Fichero / línea | Texto | Clase |
|---|---|---|
| `migrations.py` :50-56 (`_TALLER_1`) | taller 1: nombre "AndroTech", dir "Huelva, España", email/tel reales | **[seed]** (demo) — pasa a genérico |
| `app.py` :4110-4114 | clientes demo con direcciones "…, Huelva" | **[seed]** |

### Tests

| Fichero | Texto | Clase |
|---|---|---|
| `tests/test_smoke.py`, `test_aislamiento.py`, `conftest.py`, `test_seguridad_auditoria.py` | slug `"androtech"`, `taller_slug`, "Huelva" en datos demo | **[test]**/**[interno]** (slug) |
| `tests/test_pagination.py` :111 | comentario "banner ANDROTECH…" | **[test]** (se actualiza si cambia el banner) |
| `tests/test_pdf.py` :22 | dirección cliente "…, Huelva" | **[test]** (dato de cliente, neutro) |

### Identificadores internos (NO son marca visible — se dejan, justificado)

| Fichero | Identificador | Por qué se deja |
|---|---|---|
| `app.py`, `audit/historial/tenancy/notifications.py` | `logging.getLogger("androtech")`, `logs/androtech.log` | nombre interno de logger/fichero; no es UI |
| `tokens.py` :22-23 | salts `androtech-password-reset` / `-email-verify` | **cambiarlos invalida** todos los tokens vivos (resets/verificaciones en curso) |
| `tenancy.py` :43 | `DEFAULT_TALLER_SLUG = "androtech"` + slug del taller 1 | el slug sale en URLs `/t/androtech/…` y lo fijan tests/QR ya impresos; cambiarlo rompe enlaces y la suite. Es una **clave de tenant**, no la marca del producto |
| `render.yaml`, `.github/workflows/ci.yml`, `.env.example`, `DEPLOY.md` | `androtech-saas`, db `androtech`, `noreply@androtech…` | nombres de servicio/infra; despliegue PAUSADO; se pueden migrar cuando se cree el servicio Kintsu real |
| `static/css/androtech.css` (nombre de fichero), `static/sw.js` `CACHE_NAME='androtech-v1'` | nombre de fichero CSS / cache key | renombrar el fichero obliga a tocar ~40 `url_for(...'androtech.css')`; es ruido sin valor de marca (el usuario no lo ve). El **nombre visible** de la PWA (`manifest.json`) sí pasa a Kintsu |

### TFG — NO se toca

`docs/memoria/**`, `docs/defensa/**`, `INVENTARIO.md`, `INFORME_SAAS.md`,
`AndroTech_Presentacion_Final.html`, etc.: son la **memoria del TFG**. Mantienen
"AndroTech / DoJaMac / Huelva" como corresponde al proyecto académico histórico.

---

## Bloque 2 — Cambios de plataforma → Kintsu

_(se rellena al ejecutar)_

## Bloque 3 — Branding por taller

_(se rellena al ejecutar)_

## Bloque 4 — Seed/demo, tests y verificación

_(se rellena al ejecutar)_
