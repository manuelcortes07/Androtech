# 🔗 Configurar Webhooks de Stripe para Producción

## 📌 Qué es un Webhook

Un webhook es una "campana" que Stripe toca cuando ocurre algo importante:
- ✅ Pago completado
- ❌ Pago cancelado
- ⚠️ Pago fallido
- 🔄 Reembolso procesado

Tu app recibe notificaciones en: `https://tudominio.com/stripe/webhook`

---

## 🔧 Opción A: Testing Local (Desarrollo)

### Usando Stripe CLI (Recomendado para develar)

#### 1. Instalar Stripe CLI
```powershell
# Descarga desde:
# https://github.com/stripe/stripe-cli/releases
# O con chocolatey:
choco install stripe-cli

# O con direct download para Windows
irm https://files.stripe.com/stripe-cli/v1.21.12/stripe_cli_v1_21_12_windows_x86_64.msi | out-file stripe-cli.msi
.\stripe-cli.msi
```

#### 2. Inicia sesión en Stripe mediante terminal
```powershell
stripe login
```
Te abrirá el navegador para autorizar. Confirma.

#### 3. Forwarding de Webhooks (en NUEVA terminal/pestañ)
```powershell
# En una segunda terminal, ejecuta:
stripe listen --forward-to localhost:5000/stripe/webhook

# Esto mostrará:
# > Ready! Your webhook signing secret is: whsec_...
```

**Copia ese `whsec_...` y configúralo:**

```powershell
# En tu sesión principal (donde está Flask):
$env:STRIPE_WEBHOOK_SECRET = "whsec_test_..."
```

#### 4. Ahora tu app recibe webhooks locales
```
Flask escucha en:  http://localhost:5000/stripe/webhook
Stripe CLI forwarda desde: checkout.session.completed, etc.
```

---

## 🚀 Opción B: Producción (Servidor Real)

### Si deployas a Heroku, AWS, DigitalOcean, etc.

#### 1. Deploy tu app
```powershell
# Ejemplo con Heroku:
heroku create mi-androtech-app
git push heroku main
```

Tu app estará en: `https://mi-androtech-app.herokuapp.com`

#### 2. Configurar URL del Webhook en Stripe Dashboard

1. Ve a https://dashboard.stripe.com/webhooks
2. Haz clic en "Add endpoint"
3. URL: `https://mi-androtech-app.herokuapp.com/stripe/webhook`
4. Eventos a recibir:
   - ✅ `checkout.session.completed`
   - ❌ `payment_intent.payment_failed`
   - 🔄 `charge.refunded`
5. Haz clic en "Add endpoint"
6. Aparecerá tu **Webhook Signing Secret** (`whsec_live_...`)

#### 3. Configura la variable de entorno en tu servidor
```powershell
# En Heroku:
heroku config:set STRIPE_WEBHOOK_SECRET="whsec_live_..."

# En AWS/DigitalOcean:
# Establece en tu .env o en el panel de admin
export STRIPE_WEBHOOK_SECRET="whsec_live_..."
```

---

## 🔐 Seguridad del Webhook

### El endpoint `/stripe/webhook` verifica:

```python
# En app.py (ya implementado):

@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    # 1. Obtiene la firma de Stripe
    sig_header = request.headers.get('Stripe-Signature')
    payload = request.get_data()
    
    # 2. Verifica que el evento es genuino
    event = stripe.Webhook.construct_event(
        payload, 
        sig_header, 
        STRIPE_WEBHOOK_SECRET  # ← CRÍTICO: sin esto, cualquiera podría engañarte
    )
    
    # 3. Si es válido, procesa el evento
    if event['type'] == 'checkout.session.completed':
        # Marca la reparación como pagada
        ...
```

---

## 📊 Testing del Webhook

### Opción 1: Con Stripe CLI (Local)
```powershell
# Terminal 2:
stripe listen --forward-to localhost:5000/stripe/webhook

# Terminal 1 (Tu app Flask):
python app.py

# Terminal 3 (Enviar evento de prueba):
stripe trigger payment_intent.succeeded
```

### Opción 2: Simular con Python
```python
# Ejecuta:
python test_payments_webhook.py
```

### Opción 3: Pagar realmente en el sitio
1. Completa un pago con tarjeta de prueba 4242...
2. Stripe envía evento `checkout.session.completed` 
3. Tu app procesa automáticamente
4. La reparación pasa a "Pagado"

---

## 🐛 Debugging del Webhook

### Ver logs en Stripe Dashboard
```
https://dashboard.stripe.com/webhooks → [Endpoint] → Logs
```

Ahí verás:
- ✅ Eventos enviados exitosamente
- ❌ Eventos fallidos (con motivo)
- ⏱️ Tiempo de respuesta

### Ver logs de tu servidor
```powershell
# Los logs JSON se imprimirán en la consola:
{"timestamp": "...", "event": "webhook_charge_succeeded", ...}
```

---

## ⚡ Resumen: Pasos Finales Para Producción

1. **Crea una tarjeta bancaria asociada a tu cuenta Stripe** (para modo LIVE)
   - Ve a https://dashboard.stripe.com/account/billing/overview
   - Añade tu tarjeta

2. **Cambia a modo LIVE**
   - En Dashboard: esquina superior derecha, apaga "Test Mode"
   - Tus claves pasarán a `sk_live_...` y `pk_live_...`

3. **Reemplaza las claves en tu `.env` de producción**
   ```
   STRIPE_SECRET_KEY = sk_live_...
   STRIPE_PUBLISHABLE_KEY = pk_live_...
   STRIPE_WEBHOOK_SECRET = whsec_live_...
   ```

4. **Deploy a tu servidor de producción**

5. **Haz ALG UN PAGO REAL** para verificar que funciona

6. **Monitorea logs** por si algo falla

---

## 📋 Checklist de Producción

- [ ] Cuenta Stripe activa y verificada
- [ ] Claves LIVE obtenidas
- [ ] App deployada en servidor público
- [ ] Webhook endpoint configurado en Stripe Dashboard
- [ ] `whsec_live_...` configurado en el servidor
- [ ] HTTPS activo (requerido por Stripe)
- [ ] Primer pago real completado
- [ ] Email de confirmación recibido
- [ ] Dashboard muestra transacción
- [ ] Logs muestran `webhook_charge_succeeded`

---

**¡Ahora tu sistema de pagos está listo para producción!** 🎉
