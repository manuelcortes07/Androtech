# Manual de Usuario — AndroTech

**Sistema de Gestión para Taller Técnico de Reparaciones**

**Autor:** Manuel Cortés Contreras  
**Versión:** 1.0  
**Fecha:** Abril 2026  
**Centro:** I.E.S. La Marisma, Huelva  

---

## Introducción

Este manual explica cómo usar AndroTech, la aplicación web que he desarrollado para gestionar las reparaciones del taller DoJaMac Informática – Andropple. Está pensado para que cualquier persona pueda usarlo sin necesidad de tener conocimientos técnicos avanzados.

La aplicación tiene dos partes bien diferenciadas: la parte pública, que pueden ver los clientes del taller sin necesidad de registrarse, y el panel interno, al que solo acceden los técnicos y el administrador con su usuario y contraseña.

---

## Parte 1 — Lo que puede hacer un cliente (sin cuenta)

### 1.1 Ver la página principal

Al entrar en la web, el cliente ve la página de inicio con información del taller: los servicios que se ofrecen, los precios orientativos, las valoraciones de otros clientes y un formulario rápido para consultar una reparación.

La navegación es sencilla: en la barra superior hay enlaces a Servicios, Sobre Nosotros, Consulta y un botón de Acceso Técnico para el personal del taller.

---

### 1.2 Consultar el estado de una reparación

Esta es la función más usada por los clientes. Permite saber en qué punto está su reparación sin tener que llamar al taller.

**Pasos:**

1. Hacer clic en **Consulta** en la barra de navegación, o usar el formulario que hay en la página de inicio.
2. Introducir el **número de reparación** (lo proporciona el taller cuando se deja el dispositivo).
3. Introducir el **email** con el que estás registrado en el taller.
4. Hacer clic en **Buscar**.

Si los datos son correctos, se muestra:
- El dispositivo en reparación
- El estado actual (Pendiente, En Proceso, Terminado o Entregado)
- La descripción del problema
- El precio

Si el estado es **Terminado**, también aparece el botón de pago online para abonar la reparación desde allí mismo.

> Si el sistema dice que no encuentra la reparación, comprueba que el número y el email sean exactamente los mismos que diste en el taller.

---

### 1.3 Pagar una reparación online

Cuando la reparación está lista, el cliente puede pagar directamente desde la web con tarjeta bancaria, sin necesidad de acudir físicamente al taller.

**Pasos:**

1. Entrar en la consulta de la reparación (como se explica en el punto anterior).
2. Si el estado es **Terminado**, aparece el botón **Pagar ahora**.
3. Hacer clic en el botón. El sistema redirige a la página segura de pago de Stripe.
4. Introducir los datos de la tarjeta en la pantalla de Stripe.
5. Confirmar el pago.

Tras el pago, el sistema actualiza automáticamente el estado de la reparación y el cliente recibe un email de confirmación con el detalle del pago.

> El pago se procesa de forma segura a través de Stripe, que cumple con los más altos estándares de seguridad para pagos con tarjeta. AndroTech nunca almacena los datos de la tarjeta.

---

### 1.4 Solicitar una reparación online

Si el cliente quiere solicitar una reparación sin pasar por el taller, puede rellenar el formulario de solicitud online.

**Pasos:**

1. Hacer clic en **Solicitar Reparación** (disponible en la página de inicio y en la barra de navegación).
2. Rellenar el formulario con:
   - Nombre completo
   - Teléfono de contacto
   - Email (opcional, pero necesario para recibir notificaciones)
   - Dispositivo (marca y modelo)
   - Descripción del problema
   - Nivel de urgencia (normal, urgente)
   - Fecha y horario preferido para la entrega
3. Hacer clic en **Enviar solicitud**.

La solicitud llega al panel de administración del taller, donde el técnico la revisa y la acepta o la rechaza. Si se acepta, se crea automáticamente la ficha del cliente y la reparación en el sistema.

También hay disponible un botón de **contacto por WhatsApp** por si el cliente prefiere comunicarse por ese canal.

---

---

## Parte 2 — El panel interno (para técnicos y administrador)

Para acceder al panel interno hay que hacer clic en **Acceso Técnico** en la barra de navegación e introducir el usuario y la contraseña.

> Por seguridad, el sistema bloquea el acceso durante 1 minuto si se introducen datos incorrectos más de 5 veces seguidas.

---

### 2.1 El Dashboard

Lo primero que se ve al entrar es el dashboard, que es el panel de control principal. Está pensado para tener de un vistazo todo lo que está pasando en el taller.

**Lo que muestra el dashboard:**

**Indicadores principales (KPIs):**
- Total de clientes registrados
- Reparaciones activas en este momento
- Reparaciones completadas
- Ingresos totales y del mes actual
- Tasa de cobro (porcentaje de reparaciones pagadas)

**Gráficos interactivos:**
- Ingresos por mes en los últimos 6 meses
- Reparaciones por técnico
- Distribución de estados (cuántas están pendientes, en proceso, terminadas)
- Dispositivos más reparados

**Alertas inteligentes:**
El sistema avisa automáticamente cuando hay situaciones que requieren atención:
- Reparaciones que llevan más de 7 días sin actualizarse
- Reparaciones terminadas pendientes de cobro
- Piezas de inventario por debajo del mínimo
- Solicitudes web sin gestionar

**Últimas actividades:**
- Las 5 últimas reparaciones registradas
- Los últimos eventos de auditoría del sistema

---

### 2.2 Gestión de clientes

Se accede desde el menú **Clientes**.

**Ver el listado de clientes:**
La pantalla muestra todos los clientes del taller con su nombre, teléfono, email y el número de reparaciones que tienen. Se puede buscar por nombre o email usando el buscador de la parte superior.

**Crear un cliente nuevo:**
1. Hacer clic en **Nuevo cliente**.
2. Rellenar el formulario: nombre (obligatorio), teléfono, email y dirección.
3. Hacer clic en **Guardar**.

**Ver el historial de un cliente:**
Hacer clic en el nombre del cliente para ver todas sus reparaciones, pasadas y actuales.

**Editar o eliminar un cliente:**
Disponible en los botones de acción de cada cliente en el listado. La eliminación solo está disponible para el administrador.

---

### 2.3 Gestión de reparaciones

Es la parte más usada del panel. Se accede desde el menú **Reparaciones**.

**Ver el listado de reparaciones:**
Se muestran todas las reparaciones con su estado actual, el cliente, el dispositivo, la fecha de entrada y el precio. Hay filtros para buscar por estado, cliente, fechas o precio.

**Crear una reparación nueva:**
1. Hacer clic en **Nueva reparación**.
2. Seleccionar el cliente (se puede buscar por nombre).
3. Rellenar el dispositivo y la descripción del problema.
4. Asignar el estado inicial (normalmente Pendiente).
5. Introducir el precio si ya se conoce.
6. Hacer clic en **Guardar**.

**Editar una reparación:**
Hacer clic en el icono de edición de la reparación. Desde ahí se puede actualizar cualquier dato, cambiar el estado, modificar el precio y ver el historial de cambios.

**Cambiar el estado de una reparación:**
El estado sigue un flujo controlado: Pendiente → En Proceso → Terminado → Entregado. No es posible hacer transiciones hacia atrás para evitar errores.

Cada cambio de estado queda registrado automáticamente con la fecha y el usuario que lo realizó. Si el cliente tiene email, recibe una notificación automática.

**Funciones adicionales dentro de una reparación:**

- **Notas internas:** Se pueden añadir anotaciones privadas sobre la reparación. Las notas importantes se pueden marcar con una estrella para que destaquen.
- **Fotos:** Se pueden subir fotos del dispositivo antes y después de la reparación. Las fotos se pueden arrastrar y soltar directamente sobre la zona de subida.
- **Firma digital:** El cliente puede firmar digitalmente en la pantalla del dispositivo para aceptar el presupuesto o confirmar la recogida.
- **Piezas utilizadas:** Se pueden registrar las piezas del inventario que se han usado en la reparación.

**Generar PDF de presupuesto o factura:**
Dentro de la reparación hay un botón para generar el documento en PDF. Se puede elegir entre presupuesto (cuando aún no está pagado) o factura (cuando ya está pagado). El documento se descarga directamente al ordenador.

---

### 2.4 Inventario de piezas

Se accede desde el menú **Inventario**.

El inventario permite controlar el stock de piezas y materiales del taller. Muestra el nombre de cada pieza, la categoría, la cantidad disponible, el precio de coste y el precio de venta.

Cuando la cantidad de una pieza baja del mínimo configurado, aparece una alerta en el dashboard avisando de que hay que reponer.

**Añadir una pieza nueva:**
1. Hacer clic en **Nueva pieza**.
2. Rellenar nombre, categoría, cantidad inicial, cantidad mínima y precios.
3. Hacer clic en **Guardar**.

---

### 2.5 Calendario

Se accede desde el menú **Calendario**.

El calendario muestra las citas y eventos del taller en formato mensual, semanal o diario. Se pueden crear nuevas citas haciendo clic directamente en el día y hora deseados.

---

### 2.6 Búsqueda global

El icono de búsqueda en la barra de navegación permite buscar en todo el sistema a la vez: clientes, reparaciones y usuarios. Es útil cuando se necesita encontrar algo rápidamente sin saber exactamente dónde está.

---

### 2.7 Exportar datos a CSV

Desde el listado de reparaciones y el listado de clientes hay un botón de exportar a CSV. El fichero generado se puede abrir directamente en Microsoft Excel y tiene el formato correcto para el español (separador de punto y coma y codificación UTF-8).

---

---

## Parte 3 — Funciones exclusivas del administrador

El administrador tiene acceso a todas las funciones del técnico más las que se describen a continuación, disponibles en el menú desplegable **Administración**.

---

### 3.1 Gestión de usuarios

Permite crear, editar y desactivar las cuentas de los técnicos y otros usuarios del sistema.

**Crear un usuario nuevo:**
1. Ir a **Administración → Usuarios**.
2. Hacer clic en **Nuevo usuario**.
3. Introducir el nombre de usuario, la contraseña y el rol asignado.
4. Hacer clic en **Guardar**.

Los roles disponibles son admin y técnico. Cada rol tiene permisos específicos que determinan a qué partes del sistema puede acceder el usuario.

---

### 3.2 Gestión de solicitudes web

Cuando un cliente rellena el formulario de solicitud de reparación desde la web, la solicitud aparece aquí para que el administrador la gestione.

**Para aceptar una solicitud:**
1. Ir a **Administración → Solicitudes Web**.
2. Hacer clic en **Aceptar** en la solicitud correspondiente.
3. El sistema crea automáticamente el cliente y la reparación en el sistema.

**Para rechazar una solicitud:**
Hacer clic en **Rechazar**. Se puede añadir una nota explicando el motivo.

---

### 3.3 Auditoría del sistema

El log de auditoría registra automáticamente todos los eventos importantes del sistema: inicios de sesión, cambios de estado, pagos, creaciones y eliminaciones de registros.

Se accede desde **Administración → Auditoría**. Muestra el tipo de evento, el usuario que lo realizó, la dirección IP desde la que se hizo y la fecha y hora exacta.

Esto es útil para detectar accesos no autorizados, errores en el sistema o para saber quién hizo qué y cuándo.

---

---

## Preguntas frecuentes

**No encuentro mi reparación al consultar**
Comprueba que el número de reparación y el email son exactamente los mismos que diste en el taller. El email es sensible a mayúsculas y espacios.

**El sistema me dice "Formulario inválido o expirado"**
Esto ocurre cuando la sesión ha caducado o has tardado mucho en rellenar el formulario. Recarga la página e inténtalo de nuevo.

**He pagado pero la reparación no aparece como pagada**
El sistema actualiza el estado automáticamente tras confirmar el pago con Stripe. Si tras unos minutos no se ha actualizado, contacta con el taller para que lo verifiquen manualmente.

**El sistema bloquea el acceso al panel**
Si introduces mal la contraseña más de 5 veces seguidas, el acceso queda bloqueado durante 1 minuto como medida de seguridad. Espera ese tiempo e inténtalo de nuevo con la contraseña correcta.

**No llegan los emails de notificación**
Comprueba la carpeta de spam. Si no están ahí, verifica con el taller que el email registrado en tu ficha es el correcto.

---

---

## Datos de contacto

**AndroTech – Taller de Reparación de Dispositivos**  
Huelva, España  
manuelcortescontreras11@gmail.com  
+34 633 234 395

---

*Manual de usuario — AndroTech v1.0 · Abril 2026*  
*Desarrollado por Manuel Cortés Contreras · I.E.S. La Marisma, Huelva*
