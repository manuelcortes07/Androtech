# Configuracion de Email para AndroTech
# Este script configura las variables de entorno necesarias para el sistema de email

Write-Host "Configuracion de Email para AndroTech" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Solicitar configuracion SMTP
$mailServer = Read-Host "Servidor SMTP (ej: smtp.gmail.com)"
$mailPort = Read-Host "Puerto SMTP (ej: 587)"
$useTls = Read-Host "Usar TLS? (true/false) [true]"
$useSsl = Read-Host "Usar SSL? (true/false) [false]"
$mailUsername = Read-Host "Usuario/Email SMTP"
$mailPassword = Read-Host "Contrasena SMTP" -AsSecureString
$mailDefaultSender = Read-Host "Email remitente por defecto (ej: noreply@androtech.com)"

# Convertir SecureString a texto plano para las variables de entorno
$passwordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($mailPassword))

# Establecer valores por defecto
if ([string]::IsNullOrWhiteSpace($useTls)) { $useTls = "true" }
if ([string]::IsNullOrWhiteSpace($useSsl)) { $useSsl = "false" }
if ([string]::IsNullOrWhiteSpace($mailDefaultSender)) { $mailDefaultSender = "noreply@androtech.com" }

# Crear archivo .env para las variables de entorno
$envContent = @"
# Configuracion de Email - Generado por configure_email.ps1
MAIL_SERVER=$mailServer
MAIL_PORT=$mailPort
MAIL_USE_TLS=$useTls
MAIL_USE_SSL=$useSsl
MAIL_USERNAME=$mailUsername
MAIL_PASSWORD=$passwordPlain
MAIL_DEFAULT_SENDER=$mailDefaultSender
"@

# Guardar en archivo .env
$envContent | Out-File -FilePath ".env" -Encoding UTF8

Write-Host ""
Write-Host "Configuracion guardada en .env" -ForegroundColor Green
Write-Host ""
Write-Host "Para usar Gmail:" -ForegroundColor Yellow
Write-Host "   - Servidor: smtp.gmail.com" -ForegroundColor Yellow
Write-Host "   - Puerto: 587" -ForegroundColor Yellow
Write-Host "   - Activar 'Acceso de aplicaciones menos seguras' en tu cuenta Google" -ForegroundColor Yellow
Write-Host "   - O usar 'Contrasenas de aplicacion' si tienes 2FA activado" -ForegroundColor Yellow
Write-Host ""
Write-Host "Para aplicar los cambios, reinicia la aplicacion." -ForegroundColor Cyan
Write-Host ""
Write-Host "Para probar el email, ejecuta una reparacion de prueba." -ForegroundColor Cyan