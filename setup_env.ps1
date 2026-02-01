# ============================================================================
# Script de Setup para AndroTech (Windows PowerShell)
# Automatiza la configuración del entorno local
# ============================================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   AndroTech - Setup de Entorno Local" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Crear virtual environment
Write-Host "[1/5] Creando entorno virtual Python..." -ForegroundColor Yellow
if (Test-Path ".\.venv") {
    Write-Host "  ✓ El entorno virtual ya existe." -ForegroundColor Green
} else {
    python -m venv .venv
    Write-Host "  ✓ Entorno virtual creado en .\.venv" -ForegroundColor Green
}

# 2. Activar virtual environment
Write-Host "[2/5] Activando entorno virtual..." -ForegroundColor Yellow
& ".\.venv\Scripts\Activate.ps1"
Write-Host "  ✓ Entorno virtual activado" -ForegroundColor Green

# 3. Instalar dependencias
Write-Host "[3/5] Instalando dependencias (requirements.txt)..." -ForegroundColor Yellow
pip install -q -r requirements.txt
Write-Host "  ✓ Dependencias instaladas" -ForegroundColor Green

# 4. Crear base de datos
Write-Host "[4/5] Creando base de datos..." -ForegroundColor Yellow
if (Test-Path ".\database\andro_tech.db") {
    Write-Host "  ? Base de datos ya existe. ¿Recrear? (s/n): " -ForegroundColor Cyan -NoNewline
    $recreate = Read-Host
    if ($recreate -eq "s") {
        Remove-Item ".\database\andro_tech.db" -Force
        python create_db.py
        Write-Host "  ✓ Base de datos recreada" -ForegroundColor Green
    } else {
        Write-Host "  ✓ Base de datos existente mantenida" -ForegroundColor Green
    }
} else {
    python create_db.py
    Write-Host "  ✓ Base de datos creada" -ForegroundColor Green
}

# 5. Configurar variables de entorno
Write-Host "[5/5] Configurando variables de entorno..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Las siguientes variables de entorno son necesarias para Stripe:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. STRIPE_SECRET_KEY      - Clave secreta de prueba (sk_test_...)"
Write-Host "  2. STRIPE_PUBLISHABLE_KEY - Clave pública de prueba (pk_test_...)"
Write-Host "  3. STRIPE_WEBHOOK_SECRET  - Secret de webhook (whsec_...)"
Write-Host ""
Write-Host "¿Configuro las claves de Stripe ahora? (s/n): " -ForegroundColor Yellow -NoNewline
$configure = Read-Host

if ($configure -eq "s") {
    Write-Host ""
    Write-Host "Pega tu STRIPE_SECRET_KEY (sk_test_...): " -ForegroundColor Cyan -NoNewline
    $secret = Read-Host -AsSecureString
    $secretPlain = [System.Net.NetworkCredential]::new('', $secret).Password
    [Environment]::SetEnvironmentVariable('STRIPE_SECRET_KEY', $secretPlain, 'Process')
    Write-Host "  ✓ Configurado: STRIPE_SECRET_KEY" -ForegroundColor Green

    Write-Host "Pega tu STRIPE_PUBLISHABLE_KEY (pk_test_...): " -ForegroundColor Cyan -NoNewline
    $public = Read-Host
    [Environment]::SetEnvironmentVariable('STRIPE_PUBLISHABLE_KEY', $public, 'Process')
    Write-Host "  ✓ Configurado: STRIPE_PUBLISHABLE_KEY" -ForegroundColor Green

    Write-Host "Pega tu STRIPE_WEBHOOK_SECRET (whsec_...): " -ForegroundColor Cyan -NoNewline
    $webhook = Read-Host -AsSecureString
    $webhookPlain = [System.Net.NetworkCredential]::new('', $webhook).Password
    [Environment]::SetEnvironmentVariable('STRIPE_WEBHOOK_SECRET', $webhookPlain, 'Process')
    Write-Host "  ✓ Configurado: STRIPE_WEBHOOK_SECRET" -ForegroundColor Green
} else {
    Write-Host "  ℹ️  Puedes configurar las claves más tarde con: setx VARIABLE_NAME valor" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   ✓ Setup completado correctamente" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Próximos pasos:" -ForegroundColor Yellow
Write-Host "  1. Ejecuta la app: python app.py" -ForegroundColor Yellow
Write-Host "  2. Abre en navegador: http://127.0.0.1:5000" -ForegroundColor Yellow
Write-Host "  3. Para webhooks locales: stripe listen --forward-to localhost:5000/stripe/webhook" -ForegroundColor Yellow
Write-Host ""
Write-Host "Usuario de prueba:" -ForegroundColor Yellow
Write-Host "  - Usuario: Manuel" -ForegroundColor Yellow
Write-Host "  - Contraseña: (verificar en el script setup_test_data.py)" -ForegroundColor Yellow
Write-Host ""
