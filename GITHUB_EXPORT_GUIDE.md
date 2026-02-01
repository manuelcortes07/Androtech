# 📤 Guía: Exportar a GitHub

Instrucciones paso-a-paso para mover tu proyecto AndroTech a GitHub.

## 🔑 Requisitos Previos

1. **Cuenta GitHub** - [github.com](https://github.com)
2. **Git instalado** - Descarga desde [git-scm.com](https://git-scm.com)
3. **Credenciales GitHub** - Usuario y token personal

## 📋 Paso 1: Crear Personal Access Token (PAT)

1. Ve a [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click "Generate new token"
3. Dale nombre: `AndroTech-Deploy`
4. Selecciona permisos:
   - `repo` (acceso completo a repositorios)
   - `workflow` (para acciones CI/CD futuras)
5. Copy el token (lo usarás solo una vez)

## 🆕 Paso 2: Crear Repositorio en GitHub

1. Ve a [github.com/new](https://github.com/new)
2. Rellena:
   - **Repository name**: `androtech` o `AndroTech-Repair`
   - **Description**: "Aplicación Flask para gestión de reparaciones con pagos públicos"
   - **Visibility**: Private (recomendado para datos sensibles)
   - **NO** inicializar con README, .gitignore, o License (ya los tienes)
3. Click "Create repository"
4. GitHub te dará URLs para conectar tu repo local

## 🔗 Paso 3: Conectar Repositorio Local a GitHub

Desde PowerShell en la carpeta AndroTech:

```powershell
# Verificar que ya tienes un repo git local
git status

# Ver el remote actual (debe estar vacío o apuntar al local)
git remote -v

# Añadir GitHub como remote
git remote add origin https://github.com/TU_USUARIO/androtech.git

# Verificar que se agregó
git remote -v
```

Debería mostrar:
```
origin  https://github.com/TU_USUARIO/androtech.git (fetch)
origin  https://github.com/TU_USUARIO/androtech.git (push)
```

## ⬆️ Paso 4: Subir Código a GitHub

```powershell
# Ver el estado actual
git status

# Asegúrate de que los cambios están commiteados
git log --oneline -5

# Subir main branch
git push -u origin main
```

Cuando te pida credenciales:
- **Username**: tu usuario de GitHub
- **Password**: el Personal Access Token que copiaste (¡no tu contraseña!)

## ✅ Paso 5: Verificar en GitHub

1. Abre [github.com/TU_USUARIO/androtech](https://github.com/tu_usuario/androtech)
2. Verifica que ves:
   - ✅ Todos tus archivos subidos
   - ✅ Commits en el timeline
   - ✅ README.md visible
   - ✅ Archivos ocultos (.env.example, .gitignore)

## 🔐 Paso 6: Configurar Secretos (Para Deployments Futuros)

Si planeás deployar con GitHub Actions:

1. Ve a repo → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Añade cada variable:

| Name | Value |
|------|-------|
| `STRIPE_SECRET_KEY` | Tu `sk_test_...` |
| `STRIPE_PUBLISHABLE_KEY` | Tu `pk_test_...` |
| `STRIPE_WEBHOOK_SECRET` | Tu `whsec_...` |
| `FLASK_SECRET_KEY` | Una clave aleatoria segura |

**Nota**: Estos secretos NO se muestran en público, solo los usa GitHub en deployments.

## 📥 Paso 7: Clonar en Otra Máquina (Para Colaboradores)

En una máquina nueva:

```powershell
# Clonar el repositorio
git clone https://github.com/TU_USUARIO/androtech.git

# Entrar a carpeta
cd androtech

# Ejecutar setup (si existe setup_env.ps1)
.\setup_env.ps1

# O manual:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python create_db.py
python app.py
```

## 🚨 Checklist Pre-Upload

Antes de subir, verifica que NO incluyes:

- [ ] ❌ `.env` (archivo real con claves) - Usa `.env.example` solo
- [ ] ❌ `database/andro_tech.db` con datos reales
- [ ] ❌ `__pycache__/` o `*.pyc`
- [ ] ❌ `.venv/` carpeta completa
- [ ] ❌ Claves privadas

Verifica que **SÍ** incluyes:

- [ ] ✅ `.env.example` (template vacío)
- [ ] ✅ `.gitignore` (para excluir archivos grandes)
- [ ] ✅ `requirements.txt` (con stripe incluido)
- [ ] ✅ `README.md` (documentación)
- [ ] ✅ `setup_env.ps1` (para setup automatizado)
- [ ] ✅ Todos los scripts y templates

## 📄 Archivo .gitignore Recomendado

Si no tienes `.gitignore`, crear uno con:

```plaintext
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
.venv/
venv/
ENV/
env/

# Database
*.db
*.sqlite
*.sqlite3

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment variables (NO subir archivos .env reales)
.env
.env.local
.env.*.local

# OS
.DS_Store
Thumbs.db

# Logs
*.log
logs/

# Temporales
tmp/
temp/
*.tmp
```

## 🔄 Flujo de Trabajo Futuro

Una vez en GitHub:

```powershell
# Cambiar código localmente
# Hacer testing

# Cuando todo funciona:
git add .
git commit -m "Descripción clara del cambio"
git push origin main

# Si trabajas en rama de desarrollo:
git checkout -b feature/nueva-funcionalidad
# ... cambios ...
git push origin feature/nueva-funcionalidad
# Luego abrir Pull Request en GitHub
```

## 🎯 Próximas Mejoras en GitHub

1. **Crear rama `develop`**
   ```powershell
   git checkout -b develop
   git push -u origin develop
   ```

2. **Configurar rama default en Settings → Branches → Default branch**
   - Cambiar a `develop` (si trabajas con gitflow)

3. **Crear Issues para tareas** (Audit Log, Charts, etc.)

4. **Configurar GitHub Actions** para CI/CD (testing automático)

## 🆘 Troubleshooting

### Error: "fatal: 'origin' does not appear to be a 'git' repository"

```powershell
# Reinicializar git
git init
git remote add origin https://github.com/TU_USUARIO/androtech.git
git branch -M main
git push -u origin main
```

### Error: "fatal: The remote end hung up unexpectedly"

```powershell
# Aumentar buffer
git config --global http.postBuffer 524288000
git push origin main
```

### Error: "Permission denied (publickey)"

Este es error SSH. Usa HTTPS en lugar de SSH:

```powershell
git remote set-url origin https://github.com/TU_USUARIO/androtech.git
```

### Error: "fatal: refusing to merge unrelated histories"

```powershell
git pull origin main --allow-unrelated-histories
```

---

## 📝 Resumen Rápido

```powershell
# 1. Crear repo en github.com

# 2. Conectar local
git remote add origin https://github.com/TU_USUARIO/androtech.git

# 3. Subir código
git push -u origin main

# 4. ¡Listo! Compartir URL con equipo
```

---

**¿Preguntas?** Consulta la [documentación oficial de GitHub](https://docs.github.com/en/get-started/quickstart/hello-world)
