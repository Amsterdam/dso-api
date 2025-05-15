# Sorteren van resultaten

Gebruik de parameter `?_sort={veld1},{veld2},{...}` om resultaten te
ordenen. Bijvoorbeeld:

``` bash
curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=naam'
```

Sorteren om meerdere velden is ook mogelijk met
`?_sort={veld1},{veld2}`:

``` bash
curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=ingangCyclus,naam'
```

Gebruik het `-`-teken om omgekeerd te sorteren
`?_sort=-{veld1},-{veld2}`:

``` bash
curl 'https://api.data.amsterdam.nl/v1/gebieden/stadsdelen/?_sort=-ingangCyclus,naam'
```

<aside class="note">
<h4 class="title">Note</h4>

In plaats van `_sort` wordt ook `sorteer` ondersteund, maar `_sort`
heeft de voorkeur.
</aside>
