# 2. ESTUDIO DE VIABILIDAD

## 2.1 Introducción

### 2.1.1 Tipología y palabras clave

El proyecto AndroTech pertenece a la tipología de creación de aplicación completa de nueva creación, dentro de la categoría de desarrollo de aplicaciones web con acceso a base de datos. Se trata de un sistema de gestión empresarial orientado a la digitalización de procesos en una pequeña empresa del sector de servicios tecnológicos.

Palabras clave: aplicación web, Flask, Python, SQLite, gestión de reparaciones, taller técnico, digitalización, Stripe, facturación digital, seguridad web.

### 2.1.2 Descripción

AndroTech es una aplicación web que digitaliza la gestión integral del taller técnico DoJaMac Informática – Andropple, ubicado en Huelva. El sistema cubre la gestión de clientes, reparaciones, facturación, pagos online, comunicación automática con el cliente y seguridad del sistema.

### 2.1.3 Objetivos del proyecto

El objetivo principal es sustituir el sistema de gestión manual del taller, basado en papel y hojas de cálculo, por una plataforma web centralizada que mejore la eficiencia operativa, reduzca errores y mejore la experiencia del cliente.

### 2.1.4 Clasificación de los objetivos

Los objetivos del proyecto se clasifican en dos categorías. Los objetivos obligatorios son aquellos que deben estar presentes en la versión final del sistema: gestión completa de clientes y reparaciones, sistema de estados con historial, panel de administración, consulta pública sin login, generación de PDF y seguridad básica. Los objetivos deseables son mejoras que aportan valor adicional pero no son imprescindibles: integración de pagos con Stripe, emails automáticos, sistema de roles granular, inventario de piezas, calendario, firma digital y PWA.

### 2.1.5 Definiciones, acrónimos y abreviaciones

- **CRUD:** Create, Read, Update, Delete. Operaciones básicas sobre datos.
- **API:** Application Programming Interface. Interfaz de programación de aplicaciones.
- **CSRF:** Cross-Site Request Forgery. Tipo de ataque web que ejecuta acciones no autorizadas.
- **PDF:** Portable Document Format. Formato de documento portable.
- **KPI:** Key Performance Indicator. Indicador clave de rendimiento.
- **PWA:** Progressive Web App. Aplicación web progresiva instalable en dispositivos.
- **SMTP:** Simple Mail Transfer Protocol. Protocolo de envío de correo electrónico.
- **ORM:** Object-Relational Mapping. Técnica de mapeo entre objetos y base de datos.
- **VPS:** Virtual Private Server. Servidor privado virtual.
- **IVA:** Impuesto sobre el Valor Añadido.

### 2.1.6 Partes interesadas

Las partes interesadas en el proyecto son las siguientes. El taller DoJaMac Informática – Andropple es el cliente final del sistema, que se beneficia directamente de la digitalización de sus procesos. Los técnicos del taller son los usuarios principales del panel de administración. Los clientes del taller son los usuarios del portal público de consulta de reparaciones. El tutor del módulo, Juan Alonso Limón Limón, supervisa el desarrollo académico del proyecto.

### 2.1.7 Referencias

- Documentación oficial de Flask: https://flask.palletsprojects.com
- Documentación oficial de Stripe: https://stripe.com/docs
- Bootstrap 5: https://getbootstrap.com
- ReportLab: https://www.reportlab.com/docs/reportlab-userguide.pdf
- Flask-Mail: https://flask-mail.readthedocs.io
- Flask-Limiter: https://flask-limiter.readthedocs.io

### 2.1.8 Documentación del proyecto

La documentación del proyecto incluye el presente documento de memoria, el README del repositorio GitHub, el archivo EMAIL_SETUP.md con instrucciones de configuración del sistema de correo, el archivo WEBHOOK_SETUP.md con instrucciones de configuración de Stripe, y el historial de commits del repositorio como evidencia del desarrollo progresivo del sistema.

---

## 2.2 Estudio de la situación actual

### 2.2.1 Contexto

DoJaMac Informática – Andropple es un taller técnico de reparación de dispositivos móviles y ordenadores ubicado en el Paseo de la Independencia, 19, Local Derecha, 21002 Huelva. El taller cuenta con dos técnicos y atiende a clientes particulares y pequeñas empresas de la ciudad y provincia.

Antes del desarrollo de AndroTech, el taller gestionaba toda su actividad de forma manual, sin ningún sistema informático especializado. Los datos de los clientes se anotaban en papel o en hojas de cálculo de Microsoft Excel sin estructura definida, las reparaciones se registraban en documentos físicos, y el seguimiento del estado de cada reparación dependía de la memoria del técnico o de notas manuscritas.

### 2.2.2 Lógica del sistema

El proceso actual de gestión de una reparación en el taller sigue los siguientes pasos. Cuando el cliente entrega el dispositivo, el técnico anota a mano los datos del cliente y la descripción del problema. El técnico asigna un número de reparación manual y guarda el papel junto al dispositivo. A medida que avanza la reparación, el técnico actualiza mentalmente o en papel el estado. Cuando la reparación termina, el técnico llama al cliente para avisarle. El cliente acude al taller, se comprueba manualmente el importe y se cobra en efectivo o mediante TPV físico. La factura se genera manualmente en Excel o en papel.

### 2.2.3 Descripción física

El entorno físico del taller consta de un ordenador de sobremesa con Windows para la gestión administrativa, un punto de venta físico con TPV para cobros con tarjeta, archivadores físicos con las fichas de reparaciones anteriores y una hoja de cálculo Excel sin estructura uniforme para el registro de clientes.

### 2.2.4 Diagnóstico del sistema actual

El sistema actual presenta los siguientes problemas identificados. La información no está centralizada, lo que dificulta la búsqueda y el seguimiento de reparaciones históricas. El riesgo de pérdida de datos es elevado al depender de documentos físicos y archivos locales sin copia de seguridad automatizada. El proceso de registro es lento, ya que no existe ninguna relación automática entre clientes y reparaciones. No hay un sistema que muestre el estado de cada reparación de forma visual e inmediata. Los clientes deben llamar o acudir físicamente para conocer el estado de su reparación. El control de inventario de piezas es inexistente, lo que genera problemas de stock. No hay posibilidad de cobro online, lo que limita la comodidad del cliente. La generación de facturas es manual y no tiene un formato profesional uniforme.

### 2.2.5 Normativa y legislación

El sistema AndroTech gestiona datos de carácter personal de los clientes del taller, por lo que su uso en producción debe cumplir con el **Reglamento General de Protección de Datos (RGPD)**, Reglamento UE 2016/679, y la **Ley Orgánica 3/2018 de Protección de Datos Personales y garantía de los derechos digitales (LOPDGDD)**.

En el ámbito del comercio electrónico y los pagos, el sistema integra Stripe como pasarela de pago, que cumple con la normativa **PCI DSS** (Payment Card Industry Data Security Standard) para el tratamiento seguro de datos de tarjetas bancarias.

Adicionalmente, la facturación electrónica generada por el sistema debe cumplir con los requisitos del **Real Decreto 1619/2012** sobre obligaciones de facturación en España, incluyendo la indicación del IVA aplicable.

---

## 2.3 Requisitos del sistema

### 2.3.1 Requisitos

Los requisitos funcionales del sistema son los siguientes. El sistema debe permitir registrar, consultar, modificar y eliminar clientes y reparaciones. Debe gestionar el estado de cada reparación mediante un flujo controlado de transiciones. Debe mantener un historial completo de todos los cambios de estado. Debe generar facturas y presupuestos en formato PDF con datos del taller, del cliente y del IVA. Debe permitir el cobro online de reparaciones mediante tarjeta bancaria. Debe enviar notificaciones automáticas por correo electrónico al cliente. Debe ofrecer un portal público de consulta sin necesidad de registro. Debe proporcionar un panel de administración con indicadores de rendimiento en tiempo real. Debe controlar el acceso mediante usuarios con diferentes roles y permisos.

### 2.3.2 Restricciones del sistema

Las restricciones técnicas del sistema son las siguientes. La aplicación debe funcionar en cualquier navegador moderno sin necesidad de instalación de software adicional en el cliente. El tiempo de respuesta de las páginas no debe superar los 3 segundos en condiciones normales de uso. La base de datos debe garantizar la integridad referencial entre clientes y reparaciones. Las claves de API de Stripe y las credenciales SMTP nunca deben almacenarse en el código fuente, sino en variables de entorno. El sistema debe funcionar correctamente en entorno local durante el desarrollo y ser desplegable en un servidor de producción.

### 2.3.3 Catalogación y priorización de los requisitos

Los requisitos se clasifican en tres prioridades. Los requisitos de prioridad alta, que son imprescindibles, son el CRUD de clientes y reparaciones, el sistema de estados, la autenticación con roles, la consulta pública y la generación de PDF. Los requisitos de prioridad media, importantes pero no bloqueantes, son la integración de Stripe, los emails automáticos, el dashboard con gráficos y el sistema de auditoría. Los requisitos de prioridad baja, que aportan valor añadido, son el calendario, el inventario de piezas, la firma digital, las fotos de reparación y la PWA.

---

## 2.4 Alternativas y selección de la solución

### 2.4.1 Alternativa 1: Django + PostgreSQL

Django es el framework web de Python más utilizado en proyectos de producción. Incluye un ORM propio, panel de administración automático y un ecosistema maduro de librerías. PostgreSQL es un sistema de base de datos relacional robusto y escalable.

Las ventajas de esta alternativa son la robustez para proyectos de gran escala, el panel de administración automático generado por Django, la madurez del ecosistema y la escalabilidad de PostgreSQL. Los inconvenientes son la curva de aprendizaje elevada para un desarrollador principiante, la mayor complejidad de configuración inicial, la menor flexibilidad para proyectos con estructura personalizada y el sobredimensionamiento para las necesidades del proyecto.

### 2.4.2 Alternativa 2: Flask + SQLite (solución elegida)

Flask es un microframework de Python ligero y flexible que proporciona las herramientas mínimas necesarias para construir una aplicación web, dejando libertad total al desarrollador para elegir el resto de componentes. SQLite es un sistema de base de datos sin servidor que almacena toda la información en un único fichero.

Las ventajas de esta alternativa son la simplicidad y la baja curva de aprendizaje, la flexibilidad total para construir la arquitectura deseada, el rendimiento suficiente para las necesidades de un taller pequeño, la facilidad de despliegue al no requerir un servidor de base de datos separado, y la adecuación al nivel técnico del proyecto. Los inconvenientes son la menor escalabilidad respecto a PostgreSQL y la limitación de SQLite para accesos concurrentes muy elevados.

### 2.4.3 Alternativa 3: Solución SaaS existente (Repairshopr, RepairDesk)

Existen soluciones comerciales específicas para talleres de reparación, como Repairshopr o RepairDesk, que ofrecen funcionalidades similares a las del proyecto.

Las ventajas son la inmediatez de uso sin desarrollo, el soporte técnico incluido y la estabilidad garantizada. Los inconvenientes son el coste mensual elevado (entre 50 y 150 euros al mes), la imposibilidad de personalizar el sistema, la dependencia de un servicio externo y la inviabilidad como proyecto académico de desarrollo.

### 2.4.4 Conclusiones

Se selecciona la Alternativa 2, Flask con SQLite, por ser la más adecuada al nivel técnico del proyecto, al tamaño del negocio y a los objetivos académicos del módulo. Flask permite aprender y aplicar los conceptos de desarrollo web desde sus fundamentos, construyendo cada componente con comprensión real de su funcionamiento, lo que resulta más valioso desde el punto de vista formativo que utilizar un framework que automatice los procesos.

---

## 2.5 Planificación del proyecto

### 2.5.1 Recursos del proyecto

Los recursos humanos del proyecto consisten en un único desarrollador, Manuel Cortés Contreras, que ha asumido todos los roles del proyecto: análisis, diseño, desarrollo, pruebas y documentación.

Los recursos materiales utilizados son los siguientes. Para hardware: un ordenador personal de sobremesa con Windows 11 Pro utilizado durante la fase de desarrollo en el instituto hasta el 3 de febrero de 2026, y un ordenador portátil personal con Windows 11 Pro utilizado desde esa fecha hasta la finalización del proyecto. Para software: Python 3.12, Visual Studio Code, Git y GitHub para el control de versiones, y un navegador web moderno para las pruebas.

### 2.5.2 Tareas del proyecto

Las tareas principales del proyecto son las siguientes. La tarea 1 es el análisis y diseño inicial, que incluye el estudio de la situación del taller, la definición de requisitos y el diseño de la base de datos. La tarea 2 es la configuración del entorno, que incluye la instalación de Python, Flask y las dependencias iniciales, y la creación del repositorio en GitHub. La tarea 3 es el desarrollo del núcleo del sistema, que incluye la implementación del CRUD de clientes y reparaciones, el sistema de autenticación y el sistema de estados. La tarea 4 es el desarrollo del panel de administración, que incluye el dashboard con KPIs, los gráficos con Chart.js y las alertas inteligentes. La tarea 5 es la integración de funcionalidades avanzadas, que incluye Stripe, Flask-Mail, ReportLab, firma digital y fotos. La tarea 6 es el desarrollo del portal público, que incluye la consulta sin login, el formulario de solicitud y el rediseño visual. La tarea 7 es la implementación de seguridad, que incluye CSRF, rate limiting, headers HTTP y auditoría. La tarea 8 es las pruebas y corrección de errores. La tarea 9 es la documentación final y la preparación de la exposición.

### 2.5.3 Planificación temporal

La planificación temporal del proyecto es la siguiente, distribuida en seis meses:

| Período | Tarea | Descripción |
|---------|-------|-------------|
| Octubre 2025 | Análisis y configuración | Anteproyecto, diseño inicial de la BD, configuración del entorno de desarrollo |
| Noviembre 2025 | Núcleo del sistema | CRUD de clientes y reparaciones, autenticación básica, sistema de estados e historial |
| Diciembre 2025 | Panel de administración | Dashboard con KPIs, filtros avanzados, exportación CSV, sistema de auditoría |
| Enero 2026 | Funcionalidades avanzadas | Integración Stripe, emails Flask-Mail, generación PDF con ReportLab, roles y permisos |
| Febrero 2026 | Portal público y seguridad | Consulta pública, formulario de solicitud, CSRF, rate limiting, headers HTTP |
| Marzo – Abril 2026 | Mejoras y documentación | Rediseño visual, calendario, inventario, firma digital, fotos, PWA, documentación |

---

## 2.6 Evaluación de riesgos

### 2.6.1 Lista de riesgos

Los riesgos identificados para el proyecto son los siguientes. El riesgo 1 es la pérdida del código fuente por fallo del equipo. El riesgo 2 es la exposición accidental de claves de API en el repositorio público. El riesgo 3 es el fallo en la integración de la pasarela de pago Stripe. El riesgo 4 es la falta de tiempo para completar todas las funcionalidades planificadas. El riesgo 5 es el fallo en el envío de correos electrónicos en producción. El riesgo 6 es la corrupción de la base de datos SQLite.

### 2.6.2 Catalogación de riesgos

| Riesgo | Probabilidad | Impacto | Nivel |
|--------|-------------|---------|-------|
| Pérdida del código fuente | Baja | Alto | Medio |
| Exposición de claves API | Media | Alto | Alto |
| Fallo integración Stripe | Media | Alto | Alto |
| Falta de tiempo | Media | Medio | Medio |
| Fallo envío emails | Baja | Bajo | Bajo |
| Corrupción base de datos | Baja | Alto | Medio |

### 2.6.3 Plan de contingencia

Para cada riesgo identificado se ha definido un plan de contingencia. Ante la pérdida del código fuente, el repositorio GitHub actúa como copia de seguridad remota con historial completo de commits. Ante la exposición de claves API, todas las credenciales se almacenan en el fichero `.env` que está incluido en `.gitignore` y nunca se sube al repositorio. Este riesgo se materializó parcialmente durante el desarrollo al incluir accidentalmente una clave de Stripe en un script, siendo detectado y bloqueado por el sistema de protección de secretos de GitHub. Ante el fallo en la integración de Stripe, la aplicación incluye validaciones que permiten marcar manualmente un pago como realizado. Ante la falta de tiempo, los requisitos están priorizados de forma que las funcionalidades esenciales se desarrollaron primero. Ante el fallo en el envío de emails, la aplicación no interrumpe su funcionamiento si el servicio SMTP no está configurado. Ante la corrupción de la base de datos, el esquema completo está documentado en `create_db.py` y permite reconstruir la estructura en cualquier momento.

---

## 2.7 Presupuesto

### 2.7.1 Estimación de coste material

| Recurso | Coste |
|---------|-------|
| Ordenador personal (amortización 3 años) | 0 € (equipo propio) |
| Licencia Windows 11 Pro | 0 € (licencia educativa) |
| Visual Studio Code | 0 € (software libre) |
| Python, Flask y librerías | 0 € (software libre) |
| Git y GitHub | 0 € (gratuito) |
| Stripe (cuenta de pruebas) | 0 € (gratuito en desarrollo) |
| Dominio web (estimado para producción) | 12 € / año |
| Hosting Railway.app (estimado para producción) | 0 – 20 € / mes |
| **Total desarrollo** | **0 €** |
| **Total producción (estimado anual)** | **12 – 252 €** |

### 2.7.2 Estimación de coste personal

| Rol | Horas estimadas | Coste hora (junior) | Total |
|-----|----------------|---------------------|-------|
| Analista / Diseñador | 20 h | 20 € / h | 400 € |
| Desarrollador backend | 80 h | 20 € / h | 1.600 € |
| Desarrollador frontend | 30 h | 20 € / h | 600 € |
| Tester | 15 h | 15 € / h | 225 € |
| Documentación | 15 h | 15 € / h | 225 € |
| **Total** | **160 h** | | **3.050 €** |

En este proyecto, todos los roles han sido desempeñados por una única persona, por lo que el coste personal real es de 0 euros al tratarse de un proyecto académico sin remuneración.

### 2.7.3 Resumen y análisis coste-beneficio

El coste total de desarrollo del proyecto es de 0 euros, al haberse utilizado exclusivamente herramientas de software libre y equipos propios. En un escenario de desarrollo profesional con un desarrollador junior a 20 euros la hora, el coste estimado ascendería a 3.050 euros.

El beneficio para el taller es significativo. La eliminación del trabajo manual de gestión supone un ahorro estimado de 30 a 60 minutos diarios en tareas administrativas. La integración del cobro online reduce la dependencia del efectivo y mejora la experiencia del cliente. La consulta online del estado de reparación reduce las llamadas entrantes al taller, liberando tiempo para el trabajo técnico.

---

## 2.8 Conclusiones

### 2.8.1 Beneficios

El desarrollo de AndroTech aporta beneficios concretos y cuantificables al taller. La centralización de datos elimina la dispersión de información y reduce el tiempo de búsqueda de reparaciones históricas. La automatización de la comunicación con el cliente mediante emails reduce el volumen de llamadas. La integración de cobro online amplía las posibilidades de pago y mejora la comodidad del cliente. El panel de administración con indicadores de rendimiento proporciona visibilidad sobre la actividad del taller que antes no existía.

Desde el punto de vista académico, el proyecto demuestra la aplicación práctica de los contenidos del ciclo formativo en un entorno real, incluyendo desarrollo de software, gestión de bases de datos, seguridad informática, servicios en red y administración de sistemas.

### 2.8.2 Inconvenientes

El principal inconveniente del sistema es la dependencia de una base de datos SQLite, que no es adecuada para entornos con acceso concurrente de muchos usuarios simultáneos. Para el tamaño actual del taller, con dos técnicos usando el sistema, esta limitación no supone un problema práctico. Sin embargo, una hipotética expansión del negocio requeriría migrar a un sistema de base de datos más robusto como PostgreSQL.

El segundo inconveniente es la necesidad de configurar las variables de entorno correctamente antes del despliegue, especialmente las credenciales de Stripe y SMTP, lo que requiere un conocimiento técnico mínimo por parte del administrador del sistema.
