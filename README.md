# AndroTech

Sistema Web de Gestión Integral para Taller Técnico de Reparaciones

Proyecto Intermodular del C.F.G.M. Sistemas Microinformáticos y Redes
I.E.S. La Marisma, Huelva — Curso 2025/2026

Autor: Manuel Cortés Contreras
Tutor: Juan Alonso Limón Limón

---

## Aplicación en producción

URL pública: https://androtech-production.up.railway.app
Credenciales demo: usuario `admin` / contraseña `admin123`

## Documentación

Toda la documentación está organizada en la carpeta `docs/`:

- **Memoria del proyecto** → `docs/memoria/AndroTech_Documento_Proyecto.docx`
- **Manual de usuario** → `docs/memoria/AndroTech_Manual_Usuario.md`
- **Manual de instalación** → `docs/memoria/AndroTech_Manual_Instalacion.md`
- **Presentación de defensa** → `docs/defensa/AndroTech_Presentacion_Final.html`
- **Guía técnica del código** → `docs/defensa/GUIA_CODIGO.md`
- **Configuración técnica** → `docs/tecnico/`

## Tecnologías utilizadas

Backend: Python 3.12, Flask 3.1, SQLite3, Werkzeug, Stripe API, ReportLab
Frontend: Bootstrap 5.3, Jinja2, Chart.js, FullCalendar
Infraestructura: Railway.app, GitHub, Gunicorn, PWA

## Estructura del repositorio

```
├── app.py              Aplicación Flask principal
├── db.py, auth.py...   Módulos del sistema
├── utils/              Servicios auxiliares (email, PDF, seguridad)
├── templates/          Plantillas HTML (Jinja2)
├── static/             Recursos estáticos (CSS, imágenes, PWA)
├── database/           Base de datos SQLite
├── docs/               Documentación completa del proyecto
├── scripts/            Scripts de inicialización y mantenimiento
└── requirements.txt    Dependencias Python
```

## Instalación local

Ver guía completa en `docs/tecnico/INSTALAR_EN_PORTATIL.md`

Resumen:
```bash
git clone https://github.com/manuelcortes07/Androtech.git
cd Androtech
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/create_db.py
python app.py
```

Acceso: http://127.0.0.1:5000

## Características principales

- Portal público con consulta de estado y pago online (Stripe)
- Panel administrativo con dashboard de KPIs y 4 gráficos en tiempo real
- 31 permisos granulares organizados en 5 categorías
- Generación automática de PDF con código QR y IVA al 21%
- Notificaciones por email con plantillas HTML y PDF adjuntos
- Seguridad multicapa: CSRF, PBKDF2, rate limiting, webhook validado
- Inventario de piezas, calendario, firma digital, fotos drag & drop
- PWA instalable con modo oscuro persistente
- Sistema de auditoría con registro JSON estructurado

## Licencia

Proyecto académico desarrollado para el Proyecto Intermodular del C.F.G.M. SMR.
