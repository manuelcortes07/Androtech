# Simple Stripe Configuration
 
Write-Host "Configurando claves de Stripe..." -ForegroundColor Cyan
Write-Host ""

# Claves de prueba (demo)
Write-Host "Opcion 1: Usar claves de DEMO (local testing)" -ForegroundColor Green
Write-Host "Opcion 2: Pegar mis claves reales de Stripe" -ForegroundColor Yellow
Write-Host ""
$choice = Read-Host "Elige 1 o 2"

if ($choice -eq "1") {
    Write-Host ""
    Write-Host "Configurando claves de DEMO para testing local..." -ForegroundColor Green
    $env:STRIPE_SECRET_KEY = "sk_test_demo_test123demo456"
    $env:STRIPE_PUBLISHABLE_KEY = "pk_test_demo_test123demo456"
    $env:STRIPE_WEBHOOK_SECRET = "whsec_demo_test123demo456"
    Write-Host "OK - Claves de demo configuradas" -ForegroundColor Green
    
} elseif ($choice -eq "2") {
    Write-Host ""
    Write-Host "Ingresa tus claves de Stripe desde https://dashboard.stripe.com/test/apikeys" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "Secret Key (sk_test_...): " -NoNewline
    $env:STRIPE_SECRET_KEY = Read-Host
    
    Write-Host "Publishable Key (pk_test_...): " -NoNewline
    $env:STRIPE_PUBLISHABLE_KEY = Read-Host
    
    Write-Host "Webhook Secret (whsec_..., opcional - pulsa Enter si no tienes): " -NoNewline
    $webhook = Read-Host
    if ($webhook) {
        $env:STRIPE_WEBHOOK_SECRET = $webhook
    }
    
    Write-Host ""
    Write-Host "OK - Claves configuradas" -ForegroundColor Green
}

Write-Host ""
Write-Host "Variables activas en esta sesion:" -ForegroundColor Cyan
Write-Host "  STRIPE_SECRET_KEY: $($env:STRIPE_SECRET_KEY.Substring(0,20))..." -ForegroundColor Yellow
Write-Host "  STRIPE_PUBLISHABLE_KEY: $($env:STRIPE_PUBLISHABLE_KEY.Substring(0,20))..." -ForegroundColor Yellow
if ($env:STRIPE_WEBHOOK_SECRET) {
    Write-Host "  STRIPE_WEBHOOK_SECRET: $($env:STRIPE_WEBHOOK_SECRET.Substring(0,20))..." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Continua con:" -ForegroundColor Green
Write-Host "  python app.py" -ForegroundColor Yellow
