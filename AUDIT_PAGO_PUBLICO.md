# Auditoría del Flujo de Pago Público (Stripe Checkout)

## Checklist de Implementación

### ✅ COMPLETADOS
- [x] Dependencias: `stripe` en `requirements.txt`
- [x] Variables de entorno: documentadas en README.md
- [x] `consulta.html`: formulario de pago con validación de email
- [x] Ruta `/publico/pagar/<id>`: crea sesión Checkout
- [x] Ruta `/stripe/webhook`: maneja eventos de pago
- [x] Página `/pago_exito`: redirección tras pago
- [x] `editar_reparacion.html`: UI para mostrar estado de pago
- [x] Jinja2 filter `strftime`: registrado y funcionando

---

## 🔴 PROBLEMAS ENCONTRADOS Y SOLUCIONES

### 1. **Falta de validación: reparación no existe**
**Ubicación**: `/publico/pagar/<id>` (línea ~522)
**Problema**: Si la reparación no existe, la consulta devuelve `None` pero no se captura bien.
**Solución**: Añadir validación explícita antes de usar `reparacion`.

### 2. **Estado de pago no mostrado en consulta.html**
**Ubicación**: `consulta.html` (línea ~270)
**Problema**: El formulario de pago se muestra si `reparacion.precio and reparacion.estado_pago != 'Pagado'`, pero si ya está pagado, no se muestra mensaje de confirmación.
**Solución**: Añadir bloque `elif reparacion.estado_pago == 'Pagado'` para mostrar confirmación.

### 3. **Método de pago no definido en webhook**
**Ubicación**: `app.py` línea ~553
**Problema**: El webhook establece `metodo='Tarjeta'` fijo, pero si la sesión de Checkout no completa, el valor no se actualiza.
**Solución**: Verificar que la reparación existe antes de actualizar; usar try-except más robusto.

### 4. **Email no se valida correctamente si es NULL en BD**
**Ubicación**: `/publico/pagar/<id>` línea ~527
**Problema**: `(reparacion['cliente_email'] or '').strip().lower()` puede generar AttributeError si `cliente_email` es None.
**Solución**: Usar `str()` para garantizar string o coalescer a ''.

### 5. **Falta rate-limiting en endpoints públicos**
**Ubicación**: `/publico/pagar/<id>` y `/consulta`
**Problema**: Sin límite de intentos, posibilidad de brute-force/scraping.
**Solución**: Implementar rate-limiting básico con `flask-limiter` o logs de intentos.

### 6. **No se envía email de confirmación**
**Ubicación**: Webhook (línea ~553)
**Problema**: El webhook no envía email al cliente tras pago.
**Solución**: Implementar envío de email (opcional para v1, pero recomendado documentar).

### 7. **falta validación: precio <= 0**
**Ubicación**: `/publico/pagar/<id>` línea ~525
**Problema**: Se valida `precio > 0`, pero si `precio` es None se puede colapsar.
**Solución**: Añadir validación explícita de `reparacion['precio'] is not None`.

### 8. **Sesión Checkout sin fallback si falla**
**Ubicación**: `/publico/pagar/<id>` línea ~540
**Problema**: Si `stripe.checkout.Session.create()` falla, el error se muestra pero no se registra.
**Solución**: Añadir logging y fallback más robusto.

---

## 📋 VALIDACIONES RECOMENDADAS

### En `/publico/pagar/<id>`:
1. ✅ Email proporcionado y válido (regex basic)
2. ✅ Reparación existe (ya implementado)
3. ✅ Email coincide con cliente (ya implementado)
4. ✅ Estado_pago != 'Pagado' (ya implementado)
5. ✅ Precio > 0 y existe (ya implementado)
6. ⚠️ **NUEVO**: Añadir rate-limiting por IP
7. ⚠️ **NUEVO**: Loguear intentos fallidos

### En `/stripe/webhook`:
1. ✅ Verificar firma (ya implementado)
2. ✅ Extraer reparacion_id (ya implementado)
3. ✅ Marcar como pagado (ya implementado)
4. ⚠️ **NUEVO**: Verificar que reparacion_id existe
5. ⚠️ **NUEVO**: Verificar que no está ya pagada
6. ⚠️ **NUEVO**: Loguear evento para auditoría

### En `consulta.html`:
1. ✅ Mostrar estado de pago si ya pagado (FALTA)
2. ✅ Mostrar método de pago si existe (FALTA)
3. ✅ Mostrar fecha de pago si existe (FALTA)

---

## 🔐 CONSIDERACIONES DE SEGURIDAD

✅ **Implementadas**:
- No se maneja datos de tarjeta (Stripe lo hace)
- Email + número reparación para verificación
- Webhook valida firma de Stripe
- Claves en variables de entorno

⚠️ **Falta implementar**:
- Rate-limiting por IP
- Logging de intentos fallidos
- Validación de webhook sin secret (rechazo)
- HTTPS en producción (documentado)

---

## 📝 ACCIONES A REALIZAR

1. **Corregir validaciones en `/publico/pagar/<id>`**: hacer más robusta
2. **Mejorar webhook `/stripe/webhook`**: añadir validaciones y logging
3. **Actualizar `consulta.html`**: mostrar estado de pago + método + fecha
4. **Crear `.env.example`**: con todas las variables
5. **Crear script `setup_env.ps1`**: para facilitar setup en Windows
6. **Prueba E2E**: verificar flujo completo con Stripe test keys
7. **Documentar en README**: next steps para obtener claves Stripe

