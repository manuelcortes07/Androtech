# 🚀 QUICK START - AndroTech

Instrucciones de inicio rápido para ejecutar la aplicación (Windows PowerShell).

## ⚡ Opción Rápida (Automática - 1 minuto)

```powershell
cd C:\Users\manue\OneDrive\Escritorio\AndroTech
.\setup_env.ps1
python app.py
```

Abre navegador: `http://127.0.0.1:5000`

## 🔧 Opción Manual

```powershell
# 1. Crear y activar entorno
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Base de datos (si no existe)
python create_db.py

# 4. Ejecutar app
python app.py
```

## 🔑 Configurar Stripe (Necesario para pagos)

```powershell
# Opción A: Temporal (solo sesión actual)
$env:STRIPE_SECRET_KEY = "sk_test_..."
$env:STRIPE_PUBLISHABLE_KEY = "pk_test_..."
$env:STRIPE_WEBHOOK_SECRET = "whsec_..."

# Opción B: Permanente (Windows)
setx STRIPE_SECRET_KEY "sk_test_..."
setx STRIPE_PUBLISHABLE_KEY "pk_test_..."
setx STRIPE_WEBHOOK_SECRET "whsec_..."
# Abre nueva terminal
```

## 👤 Acceder a la App

| Página | URL | Tipo |
|--------|-----|------|
| **Inicio** | `http://127.0.0.1:5000/` | Público |
| **Login** | `http://127.0.0.1:5000/login` | Admin |
| **Dashboard** | `http://127.0.0.1:5000/dashboard` | Admin (login requerido) |
| **Consulta Pública** | `http://127.0.0.1:5000/consulta` | Público (para clientes) |
| **Reparaciones** | `http://127.0.0.1:5000/reparaciones` | Admin |

### Credenciales de Prueba

- Usuario: `Manuel`
- Contraseña: (Ver en `setup_test_data.py` o usar `admin`/`admin123`)

## 🧪 Probar Pago Público E2E

```powershell
# Terminal 1: Ejecutar app
python app.py

# Terminal 2: Escuchar webhooks de Stripe
stripe listen --forward-to localhost:5000/stripe/webhook

# Terminal 3: Navegar a consulta
# http://127.0.0.1:5000/consulta
# → Número reparación: 1
# → Email: (del cliente en BD)
# → Pagar
# → Tarjeta Stripe: 4242 4242 4242 4242 (cualquier fecha futura, CVC: 123)
```

## 📂 Archivos Importantes

- **app.py** - Aplicación Flask (rutas, lógica de pagos)
- **create_db.py** - Crear/resetear BD
- **requirements.txt** - Dependencias Python
- **README.md** - Documentación completa
- **setup_env.ps1** - Setup automático
- **.env.example** - Template de variables

## ❌ Si algo falla

```powershell
# 1. Verifica que el venv está activado
.\.venv\Scripts\Activate.ps1

# 2. Reinstala dependencias
pip install --upgrade -r requirements.txt

# 3. Resetea BD
Remove-Item database\andro_tech.db -Force
python create_db.py

# 4. Verifica Flask carga
python -c "from app import app; print('OK')"

# 5. Ver logs de Flask
python app.py  # Los logs aparecen en consola
```

## 📖 Próximos Pasos

1. **Leer** [README.md](README.md) - Documentación completa
2. **Revisar** [RESUMEN_IMPLEMENTACION.md](RESUMEN_IMPLEMENTACION.md) - Checklist de features
3. **Exportar** [GITHUB_EXPORT_GUIDE.md](GITHUB_EXPORT_GUIDE.md) - Mover a GitHub

---

**¿Listo para vamos?** 🎯
