Remotes (proxies)
=================

Sommige datasets in DSO-API zijn in feite verbindingen met andere services.
Meer bepaald zijn dit:

* [brp]({{uri}}brp), een verbinding met de Basisregistratie Personen, bijgehouden door
  Team Basis- en Kernregistraties, Gemeente Amsterdam;
* [haalcentraal/bag]({{uri}}haalcentraal/bag), de [Landelijke Voorziening Basisregistratie
  Adressen en Gebouwen van Haal Centraal](https://lvbag.github.io/BAG-API/)
* [haalcentraal/brk]({{uri}}haalcentraal/brk), de [Basisregistratie Kadaster van Haal Centraal](
  https://vng-realisatie.github.io/Haal-Centraal-BRK-bevragen).

De endpoints voor deze datasets accepteren andere parameters
en leveren andere formats op dan de overige datasets.

Bevraging van Haal Centraal BRK vereist een token (zie [Autorisatie](authorization.html))
met scopes BRK/RO, BRK/RS en BRK/RSN.
