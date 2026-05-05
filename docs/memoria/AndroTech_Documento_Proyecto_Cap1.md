# DOCUMENTO DEL PROYECTO — ANDROTECH

---

## PORTADA

**DPTO. INFORMÁTICA — I.E.S. LA MARISMA**  
**MÓDULO PROYECTO INTERMODULAR**  
**C.F.G.M. SISTEMAS MICROINFORMÁTICOS Y REDES**

---

# ANDROTECH  
## Sistema Web de Gestión Integral para Taller Técnico de Reparaciones

---

**Autor:** Manuel Cortés Contreras  
**Fecha:** Abril 2026  
**Tutor:** Juan Alonso Limón Limón  

---

---

## HOJA RESUMEN — PROYECTO

**Título del proyecto:** AndroTech — Sistema Web de Gestión Integral para Taller Técnico de Reparaciones

**Autor:** Manuel Cortés Contreras  
**Fecha:** Abril 2026  
**Tutor:** Juan Alonso Limón Limón  
**Titulación:** C.F.G.M. Sistemas Microinformáticos y Redes

**Palabras clave:**

- Castellano: gestión de reparaciones, aplicación web, Flask, Python, SQLite, taller técnico, digitalización, Stripe, facturación
- English: repair management, web application, Flask, Python, SQLite, technical workshop, digitalization, Stripe, invoicing

---

**Resumen del proyecto (Español)**

AndroTech es una aplicación web desarrollada con Python y Flask para la gestión integral de un taller técnico de reparación de dispositivos móviles y ordenadores. El sistema digitaliza todos los procesos del taller, sustituyendo el uso de papel y hojas de cálculo por una plataforma centralizada accesible desde cualquier navegador.

El proyecto incluye gestión completa de clientes y reparaciones con historial de estados, panel de administración con indicadores clave de rendimiento y gráficos interactivos, portal público para que los clientes consulten sus reparaciones sin necesidad de cuenta, sistema de pagos online integrado con Stripe, generación automática de facturas y presupuestos en PDF, comunicación automática por email en cada etapa del proceso, y un sistema de seguridad con protección CSRF, roles y permisos granulares, rate limiting y auditoría completa de eventos.

El proyecto ha sido desarrollado de forma individual durante seis meses, partiendo desde cero en programación web, y supera ampliamente los objetivos definidos en el anteproyecto inicial.

---

**Abstract (English)**

AndroTech is a web application developed with Python and Flask for the comprehensive management of a technical repair workshop for mobile devices and computers. The system digitizes all workshop processes, replacing paper and spreadsheets with a centralized platform accessible from any browser.

The project includes complete client and repair management with status history, an admin dashboard with key performance indicators and interactive charts, a public portal for clients to check their repairs without an account, an online payment system integrated with Stripe, automatic PDF invoice and quote generation, automatic email communication at each process stage, and a security system with CSRF protection, granular roles and permissions, rate limiting, and complete event auditing.

The project was developed individually over six months, starting from scratch in web programming, and significantly exceeds the objectives defined in the initial project proposal.

---

---

# ÍNDICE

1. Introducción
   - 1.1 Introducción a la memoria
   - 1.2 Descripción
   - 1.3 Objetivos generales
   - 1.4 Beneficios
   - 1.5 Motivaciones personales
   - 1.6 Estructura de la memoria

2. Estudio de viabilidad
   - 2.1 Introducción
   - 2.2 Estudio de la situación actual
   - 2.3 Requisitos del sistema
   - 2.4 Alternativas y selección de la solución
   - 2.5 Planificación del proyecto
   - 2.6 Evaluación de riesgos
   - 2.7 Presupuesto
   - 2.8 Conclusiones

3. Análisis
   - 3.1 Introducción
   - 3.2 Requisitos funcionales de usuarios
   - 3.3 Requisitos no funcionales
   - 3.4 Diagramas de casos de uso
   - 3.5 Diagrama lógico de datos
   - 3.6 Menús de navegación
   - 3.7 Conclusión del análisis

4. Diseño
   - 4.1 Introducción
   - 4.2 Selección del entorno de desarrollo
   - 4.3 Selección de base de datos
   - 4.4 Configuración de la plataforma
   - 4.5 Estructura de la base de datos
   - 4.6 Arquitectura de la aplicación

5. Implementación
   - 5.1 Introducción
   - 5.2 Codificación de las capas principales
   - 5.3 Integración de herramientas de apoyo

6. Pruebas
   - 6.1 Introducción
   - 6.2 Pruebas realizadas
   - 6.3 Resultados obtenidos
   - 6.4 Conclusiones

7. Conclusiones
   - 7.1 Conclusiones finales
   - 7.2 Desviaciones temporales
   - 7.3 Posibles ampliaciones
   - 7.4 Valoración personal

8. Bibliografía

9. Glosario

10. Anexos

---

---

# 1. INTRODUCCIÓN

## 1.1 Introducción a la memoria

El presente documento recoge la memoria del Proyecto Intermodular desarrollado en el segundo curso del Ciclo Formativo de Grado Medio de Sistemas Microinformáticos y Redes, impartido en el I.E.S. La Marisma de Huelva durante el curso 2025/2026.

El proyecto consiste en el desarrollo de una aplicación web completa denominada AndroTech, cuyo objetivo es digitalizar la gestión de un taller técnico de reparación de dispositivos móviles y ordenadores. La aplicación ha sido diseñada e implementada tomando como referencia el taller real DoJaMac Informática – Andropple, ubicado en Huelva, que hasta el momento gestionaba su actividad de forma manual mediante papel y hojas de cálculo.

A lo largo de esta memoria se describe de forma detallada el proceso seguido desde el análisis inicial de la situación hasta la implementación final del sistema, incluyendo las decisiones técnicas tomadas, las herramientas utilizadas, las pruebas realizadas y las conclusiones obtenidas.

## 1.2 Descripción

AndroTech es una aplicación web desarrollada con Python y el framework Flask, que proporciona una plataforma centralizada para la gestión integral de un taller técnico. El sistema cubre todo el ciclo de vida de una reparación: desde que el cliente la solicita hasta que la recoge y realiza el pago.

Las funcionalidades principales del sistema son las siguientes. En primer lugar, gestiona el ciclo completo de reparaciones, permitiendo registrar, actualizar y hacer seguimiento de cada reparación con un sistema de estados controlados: Pendiente, En Proceso, Terminado y Entregado. En segundo lugar, dispone de un panel de administración con indicadores clave de rendimiento en tiempo real, gráficos interactivos y alertas inteligentes. En tercer lugar, ofrece un portal público donde cualquier cliente puede consultar el estado de su reparación introduciendo únicamente su número de reparación y su dirección de correo electrónico, sin necesidad de registrarse. En cuarto lugar, integra un sistema de pagos online mediante Stripe que permite al cliente abonar el importe de la reparación de forma segura desde cualquier dispositivo. En quinto lugar, genera automáticamente facturas y presupuestos en formato PDF con diseño profesional. Finalmente, envía notificaciones automáticas por correo electrónico al cliente en cada cambio relevante de su reparación.

La aplicación ha sido desarrollada con especial atención a la seguridad, implementando protección contra ataques CSRF, sistema de roles y permisos granulares, limitación de intentos de acceso, cabeceras HTTP de seguridad y registro de auditoría de todos los eventos críticos del sistema.

## 1.3 Objetivos generales

El objetivo principal del proyecto es proporcionar al taller DoJaMac Informática – Andropple una herramienta digital que sustituya sus procesos manuales actuales, mejorando la organización, la eficiencia y la comunicación con los clientes.

Los objetivos específicos del proyecto son los siguientes. El primero es centralizar toda la información de clientes y reparaciones en una base de datos única y accesible. El segundo es eliminar el uso de papel y hojas de cálculo, reduciendo el riesgo de pérdida de datos y errores. El tercero es proporcionar al equipo técnico una interfaz clara e intuitiva para gestionar el trabajo diario. El cuarto es ofrecer a los clientes un servicio de consulta online disponible en todo momento. El quinto es integrar un sistema de cobro online que elimine la dependencia del pago en efectivo. El sexto es automatizar la comunicación con el cliente mediante notificaciones por correo electrónico. El séptimo es garantizar la seguridad del sistema y la privacidad de los datos de los clientes.

## 1.4 Beneficios

La implantación de AndroTech aporta beneficios tanto al taller como a sus clientes.

Desde el punto de vista del taller, los beneficios son los siguientes. Se reduce considerablemente el tiempo dedicado a la gestión administrativa, ya que la búsqueda, el registro y la actualización de reparaciones se realiza en segundos en lugar de minutos. Se elimina el riesgo de pérdida de información al contar con una base de datos centralizada en lugar de documentos físicos dispersos. El panel de administración con indicadores clave permite tomar decisiones basadas en datos reales, como identificar los dispositivos que más se reparan o los meses con mayor facturación. La generación automática de facturas y presupuestos en PDF ahorra tiempo y garantiza un formato profesional y uniforme. El sistema de alertas inteligentes avisa automáticamente de reparaciones atrasadas, pendientes de pago o sin presupuesto asignado, reduciendo los olvidos y mejorando la organización.

Desde el punto de vista del cliente, los beneficios son los siguientes. El cliente puede consultar el estado de su reparación en cualquier momento y desde cualquier dispositivo, sin necesidad de llamar al taller. Recibe notificaciones automáticas por correo electrónico cuando su reparación cambia de estado o cuando se confirma el pago. Puede abonar el importe de la reparación de forma segura y cómoda mediante pago online con tarjeta.

## 1.5 Motivaciones personales

La elección de este proyecto responde a varias razones de carácter personal y profesional.

En primer lugar, el proyecto surge de una necesidad real. El taller DoJaMac Informática – Andropple existe físicamente en Huelva y, en el momento de plantear el anteproyecto, gestionaba su actividad de forma completamente manual. Esto convierte el proyecto en algo con aplicación práctica real y no en un ejercicio académico sin destinatario.

En segundo lugar, el desarrollo de una aplicación web completa permite integrar y aplicar de forma práctica los conocimientos adquiridos a lo largo del ciclo formativo en diferentes módulos, incluyendo sistemas operativos, redes, seguridad informática, aplicaciones web y programación.

En tercer lugar, el proyecto supone un reto personal significativo. Al comenzar el desarrollo en octubre de 2025, los conocimientos de programación web eran básicos y no se había desarrollado nunca una aplicación completa. La complejidad progresiva del proyecto, desde el CRUD inicial hasta la integración de pagos con Stripe o el sistema de auditoría, ha permitido un aprendizaje constante y profundo durante los seis meses de desarrollo.

Por último, desarrollar un sistema real que podría ser utilizado por una empresa local representa una motivación adicional que va más allá de la obtención de la calificación académica.

## 1.6 Estructura de la memoria

La presente memoria está organizada en diez capítulos que siguen el proceso de desarrollo del proyecto de forma lógica y cronológica.

El capítulo 1 es la introducción, que presenta el proyecto, sus objetivos, los beneficios esperados y las motivaciones del autor. El capítulo 2 corresponde al estudio de viabilidad, donde se analiza la situación actual del taller, se definen los requisitos del sistema, se evalúan las alternativas tecnológicas, se planifica el proyecto y se estima el presupuesto. El capítulo 3 recoge el análisis del sistema, incluyendo los requisitos funcionales y no funcionales, los diagramas de casos de uso y el modelo de datos. El capítulo 4 describe el diseño de la solución, con las decisiones técnicas tomadas sobre el entorno de desarrollo, la base de datos y la arquitectura de la aplicación. El capítulo 5 detalla la implementación, describiendo las capas principales del sistema y las herramientas de apoyo integradas. El capítulo 6 presenta las pruebas realizadas y los resultados obtenidos. El capítulo 7 recoge las conclusiones finales, las desviaciones respecto a la planificación inicial y las posibles ampliaciones futuras del sistema. Los capítulos 8, 9 y 10 contienen la bibliografía, el glosario de términos técnicos y los anexos respectivamente.
