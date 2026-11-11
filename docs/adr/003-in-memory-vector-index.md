# ADR-003: Pontos, memóriabeli vektoros visszakeresés JSON indexfájl felett

Állapot: elfogadva

## Háttér

57 chunk, 1 024 dimenzióval (helyi, `bge-m3`) vagy 3 072-vel (felhő, `text-embedding-3-large`). Az index csak akkor változik, amikor a dokumentumok vagy az embedding modell változik; a konténer indításakor csak akkor épül újra, ha az ujjlenyomata eltér, és egy Docker-kötetben él, így az újra létrehozott konténerek újrahasználják. A referencia beállításban egyetlen API-példány fut.

## Döntés

Az ingest a `var/index.json` fájlt írja: metaadatokat (embedding modell, dimenziók, ujjlenyomat, built_at), chunkokat és float32 vektorokat. Az API indításkor egyszer betölti egy normalizált NumPy mátrixba, és minden lekérdezést egyetlen mátrix-vektor szorzattal válaszol meg (pontos koszinusz hasonlóság), majd rendez, alkalmazza a küszöböt és kiveszi a top k elemet.

A fájl atomikusan íródik (ideiglenes fájl és átnevezés), így egy futó olvasó soha nem lát félig megírt indexet.

## Alternatívák

- **Chroma / FAISS / LanceDB**: közelítő vagy beágyazott vektortárak. 57 vektornál a pontos keresés már szubmilliszekundumos, így a függőségi súlyt és az átláthatatlan lemezes formátumokat bármilyen előny nélkül hoznák.
- **pgvector vagy Azure AI Search**: a helyes választás, ha több író folyamat, sok példány, memóriába nem férő korpusz, metaadat-szűrés vagy hibrid keresés van. Hozzáadnak egy üzemeltetendő szolgáltatást és migrációs terhet. Ez a dokumentált következő lépés, nem a kiindulópont.

## Következmények

- Több példány mindegyike a saját, csak olvasható másolatát tartja: rendben van, amíg az index kicsi és egy deploy vagy egy ingest job építi újra, viszont helytelen, amint a dokumentumok futásidőben változnak.
- A memória chunks × dimenziók × 4 bájt (float32): 57 × 3 072 körülbelül 0,7 MB. 100k chunk és 3 072 dimenzió esetén példányonként ~1,2 GB lenne, a JSON fájl pedig több GB szöveg lenne, lassan betölthető, jóval azelőtt, hogy a keresési idő számítana. Ez a váltás pontja (először bináris formátumra, majd egy valódi vektortárra).
- A JSON bármilyen szerkesztővel vizsgálható, ami segít a hibakeresésben és a review-ban.
