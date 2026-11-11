# ADR-004: Kalibrált relevanciaküszöb; a nincs találat normális válasz, modellhívás nélkül

Állapot: elfogadva

## Háttér

Az alkalmazásnak értelmesen kell kezelnie a "nincs releváns találat" esetet. A koszinusz-hasonlósági pontszámok embedding-modellenként nem összemérhetők. A hipotézis, amelyet alább ellenőriztem: minden modellnek megvan a maga alapszintje a nem kapcsolódó szövegekre, így egyetlen fix küszöb az egyik módban biztosan rossz lenne. A kérdések lehetnek magyarok, miközben a dokumentumok angolok, és a keresztnyelvű pontszámok várhatóan alacsonyabbak, mint az egynyelvűek.

## Döntés

- A `MIN_RELEVANCE_SCORE` konfiguráció, embedding-modellenként állítjuk be az egyes `.env` mintákban.
- Az érték kalibrált: a `python -m scripts.calibrate` (egy-egy kérdésre a `python -m policydesk search "<kérdés>"`) kiírja a legjobb pontszámokat a chat-modell hívása nélkül. Minden embedding-modellnél lefuttattam domainen belüli angol, domainen belüli magyar és domainen kívüli kérdéseket. A küszöb a legalacsonyabb domainen belüli pontszám alá és a domainen kívüli klaszter fölé esik. A mérések alább találhatók.
- Ha egyetlen chunk sem éri el a küszöböt, az API `200`-at ad vissza `outcome: "no_relevant_context"` értékkel, egy fix kétnyelvű válasszal és források nélkül, és a chat-modellt nem hívjuk meg.

## Mérések

Top-1 koszinusz-pontszám kérdésenként; csoportonként 12 kérdés, 2026-11-11-én futtatva a [`scripts/calibrate.py`](../../scripts/calibrate.py) segítségével (`python -m scripts.calibrate`; ugyanaz az index és keresőkód, mint az API-ban; az embedding-modell váltása után újra kell futtatni).

| Embedding-modell | Domainen belüli angol | Domainen belüli magyar | Domainen kívüli (EN + HU) | Küszöb |
|---|---|---|---|---|
| `bge-m3` (helyi) | 0.611 â€“ 0.773 | 0.586 â€“ 0.748 | 0.297 â€“ 0.529 | **0.55** |
| `text-embedding-3-large` (felhő) | 0.458 â€“ 0.722 | 0.403 â€“ 0.685 | 0.081 â€“ 0.375 | **0.39** |
| `text-embedding-3-small` (elvetve) | 0.478 â€“ 0.717 | 0.266 â€“ 0.578 | 0.085 â€“ 0.369 | nincs lehetséges |

- A hipotézis beigazolódott: a két modell alapszintje eltér (a domainen kívüli maximumok 0.53 vs 0.38), és a keresztnyelvű pontszámok alacsonyabbak, mint az egynyelvűek.
- A `text-embedding-3-small` volt az eredeti felhős választás. A magyar pontszámai átfednek a domainen kívüli tartománnyal, és több magyar kérdésnél a legfelső találat a rossz szakasz volt, így egyetlen küszöb sem működik; helyette a `text-embedding-3-large` került be.
- A `bge-m3`-mal minden domainen belüli kérdésnél, angolul és magyarul is a helyes szakasz volt a legfelső találat.
- Mindkét határ szűk (0.529 â†’ 0.586 és 0.375 â†’ 0.403). A legmagasabb domainen kívüli pontszámok azokból a kérdésekből jöttek, amelyek Budapestet vagy Magyarországot említik, olyan szavakat, amelyek a szabályzatokban is előfordulnak.

## Alternatívák

- **Mindig hívjuk a modellt, és hagyjuk, hogy "nem tudom"-ot mondjon**: modellhívásba kerül minden témán kívüli kérdés, és egy kis helyi modellre bízza a megbízható elutasítást. A prompt továbbra is utasítja a modellt az elutasításra, második védelmi vonalként a határesetekre.
- **Top-k küszöb nélkül**: a modell mindig kap valamilyen kontextust, még a "Milyen idő van?" kérdésre is, ami magabiztos butaságot hív elő.
- **Reranker-pontszám küszöb**: jobban kalibrált lekérdezések között, de plusz modellt igényel. Következő lépés, ha a határesetek fontossá válnak.
- **404 visszaadása találat hiányában**: a kérés érvényes volt, és a szolgáltatás működött. A "semmit nem találtam" egy eredmény, és a klienseknek nem kellene hibaként kezelniük.

## Következmények

- Az embedding-modell váltása újrakalibrálást jelent; a README és a `.env` minták ezt írják a változó mellett.
- A kalibrációs halmaz kicsi (36 kérdés). Egy nagyobb, címkézett halmaz CI-ben futtatva az első következő lépés, ha a küszöb fontosabbá válik.
- A határesetek (egy releváns szó egy témán kívüli kérdésben) átjuthatnak a küszöbön. A prompt elutasítási szabálya a legtöbbjüket kezeli.
