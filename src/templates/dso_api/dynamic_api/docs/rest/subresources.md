# Subresources

De REST API kan resources die onder andere resources vallen op geneste URLs
teruggeven.

Een (theoretisch) voorbeeld van een url hiervoor is bijvoorbeeld:
`https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/100002342243.1/wijken`

Dit geeft alle wijken terug die in het stadsdeel liggen met die `id`.

Dit kan meerdere niveaus diep zijn, zoals bijvoorbeeld:
`https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/100002342243.1/wijken/2000000034534.1/buurten`

<aside class="note">
    <h4 class="title">Noot</h4>
    Dit dient door de eigenaar van de dataset aangegeven te worden
    in het schema.
</aside>
