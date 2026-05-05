# 📋 Guía Completa: Probar Flujo de Pago End-to-End

## 🌐 Ambiente de Prueba Stripe

**Status:** ✅ Activo y funcionando  
**URL:** http://127.0.0.1:5000  
**Modo:** Test (no es dinero real)

---

## 🎯 Pasos para Probar el Flujo Completo

### Paso 1: Acceder a la Aplicación
```
1. Abre tu navegador
2. Ve a: http://127.0.0.1:5000
3. Deberías ver la página de inicio de AndroTech
```

### Paso 2: Navegar a "Consulta" (Pago Público)
```
1. En el menú superior, haz clic en "Consulta"
   O usa: http://127.0.0.1:5000/consulta
2. Verás un formulario para buscar reparaciones
```

### Paso 3: Buscar una Reparación Existente
Para testing usamos la reparación que creamos en el test:
- **ID Reparación:** 9
- **Cliente:** TestPaymentUser
- **Email:** juan@example.com
- **Precio:** €50.00

```
1. En el campo "Número de Reparación", ingresa: 9
2. Haz clic en "Consultar Estado"
3. Aparecerá la información de la reparación
```

### Paso 4: Proceder al Pago
```
1. En la sección "Estado de Pago", haz clic en "Pagar"
   (Debe decir "⏳ Pendiente de pago")
2. Un formulario te pedirá:
   - Email: juan@example.com
3. Haz clic en "Proceder al Pago"
```

### Paso 5: Completar el Pago en Stripe
Te llevará a la página de checkout de Stripe (https://checkout.stripe.com)

**Usa estas tarjetas de prueba:**

| Tipo | Tarjeta | Test |
|------|---------|------|
| ✅ Pago exitoso | 4242 4242 4242 4242 | Completar sin errores |
| ❌ Pago rechazado | 4000 0000 0000 0002 | Simula rechazo |
| ⚠️ Autenticación 3D | 4000 0025 0000 3155 | Requiere verificación |

**Rellena con:**
- Fecha: Cualquier fecha futura (ej: 12/25)
- CVC: Cualquier número de 3 dígitos (ej: 123)
- Nombre: Tu nombre (ej: Juan)
- Email: igual o diferente

### Paso 6: Verificar Confirmación de Pago
Después de completar el pago en Stripe:
```
1. Serás redirigido a tu sitio (página de éxito)
2. Verás: "✅ Pago completado exitosamente"
3. La reparación mostrará entonces: "✅ Pagado"
```

### Paso 7: Verificar en la Base de Datos
Para los técnicos/admin, verifique que se guardó:
```
1. Vaya al Dashboard administrativo
2. Filtrar por "Pagado" para ver transacciones
3. Debería ver: Reparación #9 con estado "Pagado"
```

---

## 🐛 Si Algo Falla

| Error | Causa | Solución |
|-------|-------|----------|
| "Error de autenticación con Stripe" | Claves no configuradas | Ejecuta `.\run_with_stripe.ps1` |
| "Correo no coincide" | Email diferente al registrado | Usa `juan@example.com` |
| "Reparación no encontrada" | ID incorrecto | Usa ID: 9 |
| "No hay un importe válido" | Precio en 0 | Crea nueva reparación con precio |

---

## 📊 Log de Testing

### Test #1: Pago Exitoso
- ID Reparación: 9
- Monto: €50.00
- Tarjeta: 4242 4242 4242 4242
- Resultado: ✅ EXITOSO

### Test #2: Pago Rechazado
- ID Reparación: [Crea nuevo]
- Monto: €25.00
- Tarjeta: 4000 0000 0000 0002
- Resultado: [Ejecutar manual]

---

## 💡 Consejos

1. **Crea más reparaciones de prueba** para testear diferentes montos:
   ```
   ID 8: €25.00
   ID 9: €50.00
   ID 10: €75.00
   ```

2. **En Stripe Dashboard** puedes ver todas las transacciones:
   https://dashboard.stripe.com/test/payments

3. **Los webhooks** pueden tardar 1-2 segundos en procesar

4. **Si necesitas resetear**, ejecuta:
   ```powershell
   rm database/andro_tech.db
   python scripts/create_db.py
   ```

---

## ✅ Checklist de Verificación

- [ ] Servidor Flask corriendo en http://127.0.0.1:5000
- [ ] Página de inicio carga correctamente
- [ ] Menú "Consulta" accesible
- [ ] Se encuentra reparación #9
- [ ] Botón "Pagar" aparece
- [ ] Redirige a Stripe Checkout
- [ ] Pago con 4242... se completa
- [ ] Regresa a página de éxito
- [ ] Dashboard muestra pago procesado
- [ ] Base de datos registra la transacción

---

**¡Listo!** Con estos pasos habrás probado el flujo completo de pago end-to-end.
