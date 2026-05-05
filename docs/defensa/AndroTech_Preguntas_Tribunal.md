# AndroTech — Preguntas del Tribunal y Respuestas

## BLOQUE 1 — DECISIONES TÉCNICAS

**P1. ¿Por qué elegiste Flask y no Django?**
Flask es un microframework que no impone estructura ni incluye ORM ni autenticación propios. Eso me obligó a entender qué hace cada pieza del sistema, desde la gestión de sesiones hasta el enrutamiento. Con Django muchas cosas se generan automáticamente y no entiendes lo que hay debajo. Para un proyecto de aprendizaje, Flask aporta más valor formativo. Además, el tamaño del proyecto no justificaba la complejidad de Django.

**P2. ¿Por qué SQLite y no MySQL o PostgreSQL?**
SQLite no requiere instalar ni configurar un servidor separado, está incluida en Python, es más que suficiente para el volumen de datos de un taller pequeño con dos técnicos, y facilita enormemente el despliegue en Railway sin configuración adicional. La limitación principal es la concurrencia muy elevada, que no es un problema real para este caso de uso.

**P3. ¿Qué es Railway y por qué lo usaste?**
Railway es una plataforma de hosting en la nube conectada directamente a GitHub. Cada push al repositorio genera un redespliegue automático en 2-3 minutos. Elegí Railway porque tiene tier gratuito suficiente para una demo, genera URL HTTPS automáticamente, no requiere gestionar servidores ni certificados SSL, y detecta automáticamente que es una aplicación Python.

**P4. ¿Por qué no usaste un ORM como SQLAlchemy?**
Decidí usar SQL directo con sqlite3 porque quería entender exactamente qué consulta se ejecuta en cada momento. Un ORM abstrae eso y para un proyecto de aprendizaje prefería el control total. Las queries están todas parametrizadas para evitar inyección SQL, nunca con concatenación de strings.

---

## BLOQUE 2 — SEGURIDAD

**P5. ¿Qué es CSRF y cómo lo implementaste?**
CSRF es un ataque en el que un sitio malicioso engaña al navegador del usuario autenticado para que envíe peticiones no autorizadas a la aplicación. La defensa es incluir en cada formulario un valor secreto que el atacante no puede conocer. Lo implementé desde cero en utils/security.py: al iniciar sesión genero un token con secrets.token_urlsafe(16) y lo guardo en la sesión. Cada template lo incluye en un campo oculto. El decorador @csrf_protect valida que coincida antes de procesar cualquier POST.

**P6. ¿Cómo guardas las contraseñas?**
Con el algoritmo PBKDF2 + SHA-256 mediante la librería Werkzeug. PBKDF2 es un algoritmo diseñado específicamente para contraseñas: incorpora un salt aleatorio por contraseña y aplica miles de iteraciones de hash, lo que hace que los ataques de fuerza bruta sean computacionalmente inviables. Es imposible recuperar la contraseña original a partir del hash almacenado.

**P7. ¿Qué es el rate limiting y por qué lo pusiste en el login?**
El rate limiting limita el número de peticiones que un cliente puede hacer en un tiempo determinado. Lo apliqué al login para prevenir ataques de fuerza bruta: si alguien intenta adivinar contraseñas probando miles de combinaciones, el sistema le bloquea tras 5 intentos por minuto. Usé Flask-Limiter con almacenamiento en memoria.

**P8. ¿Qué headers HTTP de seguridad añadiste y para qué sirven?**
Tres headers añadidos en after_request en cada respuesta. X-Frame-Options: SAMEORIGIN evita que la aplicación sea incrustada en un iframe de otro dominio, protegiendo contra ataques de clickjacking. X-Content-Type-Options: nosniff impide que el navegador interprete archivos con un tipo MIME diferente al declarado. Referrer-Policy: strict-origin-when-cross-origin controla qué información de origen se envía con las peticiones.

**P9. ¿Cómo funciona el webhook de Stripe?**
Cuando el cliente paga, Stripe envía una petición POST a mi endpoint /stripe/webhook con los datos del pago. Antes de procesar nada, valido la firma criptográfica de esa petición usando stripe.Webhook.construct_event() con el STRIPE_WEBHOOK_SECRET. Si la firma no es válida, rechazo la petición con error 400. Esto garantiza que solo Stripe puede marcar reparaciones como pagadas, y que nadie puede falsificar un pago enviando una petición directa al endpoint.

**P10. ¿Tuviste algún problema de seguridad durante el desarrollo?**
Sí, uno real. Una clave de Stripe quedó incluida accidentalmente en un script de prueba. GitHub bloqueó el push automáticamente mediante su sistema de detección de secretos. Revoqué la clave desde el panel de Stripe inmediatamente, limpié el historial de commits y desde ese momento todas las credenciales se gestionan exclusivamente en el fichero .env, que está excluido del repositorio con .gitignore.

---

## BLOQUE 3 — BASE DE DATOS Y ARQUITECTURA

**P11. ¿Cuántas tablas tiene la base de datos y por qué tantas?**
12 tablas. Cada tabla tiene una responsabilidad clara: clientes, reparaciones, historial de cambios de estado, fotos adjuntas, notas internas, inventario de piezas, piezas usadas por reparación, solicitudes web, usuarios, roles, permisos y auditoría. Normalizar así evita duplicar datos y garantiza la integridad. Por ejemplo, el historial de estados es una tabla separada porque necesito guardar quién cambió el estado y cuándo, sin modificar el registro principal.

**P12. ¿Qué pasaría si dos técnicos editan la misma reparación a la vez?**
Es una limitación real de SQLite. En un escenario de alta concurrencia, SQLite puede dar problemas porque bloquea el fichero entero al escribir. Para el tamaño actual del taller, con dos técnicos, esto no supone un problema práctico porque las operaciones son muy rápidas. En un entorno de mayor escala, la solución sería migrar a PostgreSQL, que gestiona la concurrencia con bloqueos a nivel de fila.

**P13. ¿Cómo funciona el sistema de roles y permisos?**
Hay 31 permisos organizados en 5 categorías: clientes, reparaciones, inventario, general y administración. El rol admin tiene los 31. El rol técnico tiene 17, sin ningún permiso de administración. Cada ruta sensible tiene el decorador @permiso_requerido('nombre_permiso'). Al hacer login, los permisos del usuario se cargan en la sesión para no consultar la BD en cada petición. Para el admin hay un cortocircuito directo que devuelve True sin consultar nada.

**P14. ¿Por qué separaste el código en módulos y no lo dejaste todo en app.py?**
Por mantenibilidad y separación de responsabilidades. auth.py contiene todo lo relacionado con autenticación y permisos. audit.py gestiona el registro de eventos. historial.py controla las transiciones de estado. alerts.py calcula las alertas inteligentes. Si necesito modificar cómo funciona la auditoría, solo toco audit.py sin arriesgarme a romper las rutas de app.py.

---

## BLOQUE 4 — FUNCIONALIDADES

**P15. ¿Cómo generaste los PDF?**
Con la librería ReportLab usando el patrón Flowables: construyo una lista de elementos (párrafos, tablas, espaciadores, QR) y el motor los distribuye en páginas automáticamente. Soporte dos tipos: presupuesto (antes del pago) y factura (con pago confirmado). El documento incluye logo, datos del cliente, IVA al 21% desglosado, términos y condiciones y un código QR con la URL de consulta. El PDF se genera en un objeto BytesIO para poder enviarlo por email sin escribir a disco.

**P16. ¿Cómo funciona el sistema de emails?**
Con Flask-Mail configurado via SMTP. Tengo 5 plantillas HTML en templates/emails/ que se renderizan con Jinja2. Los emails se envían automáticamente al cambiar el estado de una reparación y al confirmar el pago. En este último caso se adjunta la factura PDF generada al vuelo. El sistema está diseñado para ser tolerante a fallos: si el SMTP no está configurado o falla, el error se registra en el log pero la ruta principal no se interrumpe.

**P17. ¿Qué es una PWA y cómo la implementaste?**
Progressive Web App es una aplicación web que usa tecnologías modernas para comportarse como una app nativa. La implementé con dos ficheros: manifest.json, que define los metadatos de instalación (nombre, colores, iconos en 8 resoluciones), y el service worker static/sw.js, que implementa la estrategia network-first con caché como respaldo. Esto permite instalar AndroTech en el móvil desde el navegador y que aparezca en la pantalla de inicio como una app normal.

**P18. ¿Cómo funciona el sistema de alertas inteligentes?**
El módulo alerts.py calcula automáticamente alertas por reparación según cuatro criterios: sin presupuesto asignado, pago pendiente, reparación atrasada más de 7 días sin actualización, y terminada pero sin entregar. Cada alerta tiene un tipo, un mensaje, un icono y un color. El dashboard agrupa las reparaciones con alertas activas para que el administrador vea de un vistazo qué requiere atención.

---

## BLOQUE 5 — PROYECTO Y PROCESO

**P19. ¿Por cuánto superaste la estimación de horas?**
La estimación inicial era 60-80 horas. La dedicación real fue de 160-180 horas, aproximadamente el doble. Tres causas: el aprendizaje desde cero de tecnologías nuevas como Stripe con webhooks, ReportLab y la PWA; la incorporación de funcionalidades no previstas que surgieron naturalmente durante el desarrollo; y el tiempo del rediseño visual completo con modo oscuro y animaciones.

**P20. ¿Qué es lo más difícil que tuviste que implementar?**
La integración con Stripe, especialmente el webhook. No basta con recibir la petición, hay que validar criptográficamente su firma para garantizar que proviene realmente de Stripe y no de alguien intentando marcar reparaciones como pagadas sin pagar. Entender cómo funciona construct_event(), qué es el STRIPE_WEBHOOK_SECRET y por qué el importe va en céntimos y no en euros me llevó varios días.

**P21. ¿Qué mejorarías del proyecto?**
Lo primero sería migrar de SQLite a PostgreSQL para mejorar la robustez y la concurrencia. Lo segundo, añadir notificaciones por WhatsApp via la API de Twilio, que tiene más tasa de lectura que el email para los clientes de un taller. Lo tercero, autenticación de dos factores con TOTP mediante pyotp para eliminar el riesgo de acceso con credenciales robadas.

**P22. ¿El sistema cumple con el RGPD?**
El sistema gestiona datos personales (nombre, teléfono, email, dirección) por lo que en producción real debe cumplir el RGPD (Reglamento UE 2016/679) y la LOPDGDD (Ley Orgánica 3/2018). Los pagos se procesan via Stripe, que cumple PCI DSS, exonerando al sistema de gestionar datos de tarjetas bancarias. Las facturas generadas incluyen el IVA al 21% conforme al Real Decreto 1619/2012 sobre obligaciones de facturación. Para una implantación real habría que añadir política de privacidad, formulario de consentimiento y mecanismo de eliminación de datos.

**P23. ¿Cómo hiciste las pruebas?**
Las pruebas fueron manuales durante todo el desarrollo, probando cada funcionalidad tras implementarla. Para Stripe usé la tarjeta de prueba 4242 4242 4242 4242. Para el webhook usé la CLI de Stripe para reenviar eventos en local. Las pruebas de seguridad incluyeron intentos de CSRF, accesos sin autenticación, transiciones de estado inválidas y rate limiting. Todas las pruebas están documentadas en el capítulo 6 de la memoria.

**P24. ¿Por qué usaste Claude como asistente?**
Claude me ayudó principalmente con documentación, planificación y resolución de errores concretos cuando estaba bloqueado. Todo el código lo analicé y entendí antes de incorporarlo al proyecto. Puedo explicar cualquier parte de la aplicación porque fui yo quien tomó todas las decisiones de diseño y quien debuggeó cuando algo no funcionaba. Claude es una herramienta, igual que Stack Overflow o la documentación oficial.

**P25. ¿Cómo funciona el control de versiones del proyecto?**
Usé Git con GitHub desde el inicio. El repositorio es público en github.com/manuelcortes07/Androtech y tiene el historial completo desde octubre de 2025. Los commits están en español con mensajes descriptivos. La rama principal es main y Railway está conectado a ella para el despliegue automático. Ante cualquier error grave podía revertir al estado anterior en segundos con git revert.

