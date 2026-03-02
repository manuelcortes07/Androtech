# ============================================================================
# Script para configurar claves de Stripe (Windows PowerShell)
# ============================================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Configuración de Claves Stripe" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "¿Qué deseas hacer?" -ForegroundColor Yellow
Write-Host "  [1] Configurar con mis claves reales de Stripe (sk_test_...)" -ForegroundColor Green
Write-Host "  [2] Usar claves de demo para testing (para desarrollo local)" -ForegroundColor Yellow
Write-Host "  [3] Salir" -ForegroundColor Red
Write-Host ""

$choice = Read-Host "Selecciona una opcion (1/2/3)"

if ($choice -eq 1) {
    Write-Host ""
    Write-Host "Para obtener tus claves reales:" -ForegroundColor Cyan
    Write-Host "  1. Ve a https://dashboard.stripe.com/test/apikeys" -ForegroundColor Gray
    Write-Host "  2. Asegurate de tener Test Mode activado (esquina superior)" -ForegroundColor Gray
    Write-Host "  3. Copia las claves que ves ahi" -ForegroundColor Gray
    Write-Host ""

    Write-Host "Pega tu STRIPE_SECRET_KEY (sk_test_...): " -ForegroundColor Cyan -NoNewline
    $secret = Read-Host
    
    if ($secret -and $secret.StartsWith("sk_test_")) {
        Write-Host "  OK - Formato valido (sk_test_)" -ForegroundColor Green
        $env:STRIPE_SECRET_KEY = $secret
        Write-Host "  Variable configurada en esta sesion" -ForegroundColor Green
    } elseif ($secret -and $secret.StartsWith("sk_live_")) {
        Write-Host "  ADVERTENCIA: Esta es una clave LIVE (produccion)" -ForegroundColor Red
        Write-Host "     Usala solo si sabes lo que haces. Continuando..." -ForegroundColor Yellow
        $env:STRIPE_SECRET_KEY = $secret
    } else {
        Write-Host "  ERROR - Formato no reconocido. Debe empezar por sk_test_ o sk_live_" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "Pega tu STRIPE_PUBLISHABLE_KEY (pk_test_...): " -ForegroundColor Cyan -NoNewline
    $public = Read-Host
    
    if ($public -and $public.StartsWith("pk_test_")) {
        Write-Host "  OK - Formato valido (pk_test_)" -ForegroundColor Green
        $env:STRIPE_PUBLISHABLE_KEY = $public
        Write-Host "  Variable configurada en esta sesion" -ForegroundColor Green
    } elseif ($public -and $public.StartsWith("pk_live_")) {
        Write-Host "  ADVERTENCIA: Esta es una clave LIVE (produccion)" -ForegroundColor Red
        $env:STRIPE_PUBLISHABLE_KEY = $public
    } else {
        Write-Host "  ERROR - Formato no reconocido. Debe empezar por pk_test_ o pk_live_" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
    Write-Host "Deseas tambien configurar STRIPE_WEBHOOK_SECRET? (s/n): " -ForegroundColor Yellow -NoNewline
    $webhookChoice = Read-Host
    if ($webhookChoice -eq "s") {
        Write-Host ""
        Write-Host "Pega tu STRIPE_WEBHOOK_SECRET (whsec_...): " -ForegroundColor Cyan -NoNewline
        $webhook = Read-Host
        if ($webhook -and $webhook.StartsWith("whsec_")) {
            $env:STRIPE_WEBHOOK_SECRET = $webhook
            Write-Host "  Variable configurada" -ForegroundColor Green
        } else {
            Write-Host "  ADVERTENCIA - Formato no reconocido. Omitiendo." -ForegroundColor Yellow
        }
    }

} elseif ($choice -eq 2) {
    Write-Host ""
    Write-Host "OK - Configurando claves de DEMO para testing..." -ForegroundColor Green
    Write-Host ""
    
    # Claves de demo (estos son valores validos pero ficticios para testing)
    $env:STRIPE_SECRET_KEY = "sk_test_demo_1234567890abcdefghijk"
    $env:STRIPE_PUBLISHABLE_KEY = "pk_test_demo_1234567890abcdefghijk"
    $env:STRIPE_WEBHOOK_SECRET = "whsec_demo_1234567890abcdefghijk"
    
    Write-Host "  Variable STRIPE_SECRET_KEY: $($env:STRIPE_SECRET_KEY)" -ForegroundColor Yellow
    Write-Host "  Variable STRIPE_PUBLISHABLE_KEY: $($env:STRIPE_PUBLISHABLE_KEY)" -ForegroundColor Yellow
    Write-Host "  Variable STRIPE_WEBHOOK_SECRET: $($env:STRIPE_WEBHOOK_SECRET)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "NOTA: Estas claves solo funcionaran para TESTING local" -ForegroundColor Yellow
    Write-Host "   Los pagos reales requieren claves validas de Stripe" -ForegroundColor Yellow

else {
    Write-Host "Saliendo..." -ForegroundColor Red
    exit 0
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   OK - Variables configuradas" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Variables activas en esta sesion:" -ForegroundColor Cyan
if ($env:STRIPE_SECRET_KEY) {
    Write-Host "  STRIPE_SECRET_KEY: $($env:STRIPE_SECRET_KEY.Substring(0,[Math]::Min(15,$env:STRIPE_SECRET_KEY.Length)))..." -ForegroundColor Gray
} else {
    Write-Host "  STRIPE_SECRET_KEY: NO CONFIGURADA" -ForegroundColor Red
}
if ($env:STRIPE_PUBLISHABLE_KEY) {
    Write-Host "  STRIPE_PUBLISHABLE_KEY: $($env:STRIPE_PUBLISHABLE_KEY.Substring(0,[Math]::Min(15,$env:STRIPE_PUBLISHABLE_KEY.Length)))..." -ForegroundColor Gray
} else {
    Write-Host "  STRIPE_PUBLISHABLE_KEY: NO CONFIGURADA" -ForegroundColor Red
}
if ($env:STRIPE_WEBHOOK_SECRET) {
    Write-Host "  STRIPE_WEBHOOK_SECRET: $($env:STRIPE_WEBHOOK_SECRET.Substring(0,[Math]::Min(15,$env:STRIPE_WEBHOOK_SECRET.Length)))..." -ForegroundColor Gray
} else {
    Write-Host "  STRIPE_WEBHOOK_SECRET: NO CONFIGURADA" -ForegroundColor Red
}
Write-Host ""
Write-Host "Proximos pasos:" -ForegroundColor Yellow
Write-Host "  1. Ejecuta: python app.py" -ForegroundColor Yellow
Write-Host "  2. Abre: http://127.0.0.1:5000" -ForegroundColor Yellow
Write-Host "  3. Ve a Consulta y paga una reparacion" -ForegroundColor Yellow
Write-Host ""
Write-Host "Para persistir estas variables (permanentes):" -ForegroundColor Cyan
if ($env:STRIPE_SECRET_KEY) {
    Write-Host "  setx STRIPE_SECRET_KEY `"$($env:STRIPE_SECRET_KEY)`"" -ForegroundColor Gray
}
if ($env:STRIPE_PUBLISHABLE_KEY) {
    Write-Host "  setx STRIPE_PUBLISHABLE_KEY `"$($env:STRIPE_PUBLISHABLE_KEY)`"" -ForegroundColor Gray
}
if ($env:STRIPE_WEBHOOK_SECRET) {
    Write-Host "  setx STRIPE_WEBHOOK_SECRET `"$($env:STRIPE_WEBHOOK_SECRET)`"" -ForegroundColor Gray
}
Write-Host ""
