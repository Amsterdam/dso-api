# Autorisatie

Veel van de REST API endpoints zijn anoniem toegankelijk. Echter, voor
sommige endpoints is autorisatie nodig. Deze autorisatie vindt plaats
mbv. een JSON Web Token (JWT).

Per dataset is aangegeven of deze openbaar is, of dat er een of meer
zgn. autorisatiescopes van toepassing zijn.

Deze scope kan gelden voor de volledige dataset, voor een of meer
tabellen binnen de dataset of voor individuele velden van een tabel. Als
een dataset of tabel is beschermd met een scope die niet aanwezig is in
het JWT, dan geven requests op die dataset/tabel een error 403
(Forbidden). Als alleen een veld zodanig is beschermd, dan wordt het
request uitgevoerd als gewoonlijk maar verschijnt het beschermde veld
niet in het resultaat. Er verschijnt ook geen melding over velden die om
deze reden niet aanwezig zijn. Bij twijfel moet het resultaat van een
request naast het betreffende schema worden gelegd om te zien welke
velden ontbreken en waarom.

## Bestaande scopes

De scopes zijn gedefineerd op https://github.com/Amsterdam/amsterdam-schema/tree/master/scopes.
Bekende scopes zijn:

* `FP/MDW`: Deze scope heeft elke ingelogde medewerker van de gemeente Amsterdam.
* `FP/WAGENPARK`: Dit functieprofiel geeft toegang tot de dataset met info over het wagenpark.
* `FP/STURINGSMIDDELEN`: Dit functieprofiel geeft toegang tot financiele gegevens uit de administratie van de gemeente Amsterdam.
* `BRK/RO`: Deze scope geeft toegang tot kadastrale objecten.
* `BRK/RS`: Deze scope geeft de rechten van `BRK/RO` en bovendien toegang tot niet natuurlijke subjecten.
* `BRK/RSN`: Deze scope geeft de rechten van `BRK/RS` en bovendien toegang tot natuurlijke subjecten.

Toekenning van deze scopes kan worden aangevraagd bij de afdeling IV Beheer.

Om de API te testen met autorisatie kan de Swagger UI worden gebruikt.
Deze is te vinden op:

    https://api.data.amsterdam.nl/v1/<dataset-id>

Bij klikken op **Authorize** wordt het JWT token gezet voor gebruik in de
Swagger UI. Bovendien wordt het token ook gepresenteerd in het scherm,
zodat het kan worden gekopieerd om bijv. als volgt met `curl` te
gebruiken:

    curl https://api.data.amstdam.nl/v1/<dataset>/<table>/...
        --header "Authorization: Bearer ${token}"

<aside class="note">
<h4 class="title">Note</h4>

Als de "Authorize" in de Swagger UI niet werkt helpt het om dit in een
anoniem browser window te doen.
</aside>
