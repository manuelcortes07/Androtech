# Run Flask with Stripe keys loaded

$env:STRIPE_SECRET_KEY = "sk_test_51T6eO5BLNTOC0gyI1zBErEGuZLtMVbzlGYQYb1Wl8EarLWaQZ4TEUXsjHFzhsS2iqE5TCrAKzMamynW4wV7AkC9K00DOQHNRr1"
$env:STRIPE_PUBLISHABLE_KEY = "pk_test_51T6eO5BLNTOC0gyIcEPQMP1VcfEtDQgOM7gyK61ajih7bt8qju1SfIca21YSYyl0LSmcNJnHhbCLaoVkCdWNvigx0055K1tjfq"

Write-Host "Iniciando servidor Flask con claves de Stripe configu
radas..." -ForegroundColor Green
Write-Host ""
python app.py
