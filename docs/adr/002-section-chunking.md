# ADR-002: Szekcióalapú Markdown-darabolás determinisztikus ID-kkal

Állapot: elfogadva

## Háttér

A korpusz 9 rövid szabályzat Markdownban, mindegyik fejlécekkel tagolt szekciók halmaza (szekciónként egy szabály vagy téma). A válaszok általában egy szekcióban találhatók; néhány kérdés két dokumentumot is átfog.

## Döntés

- Az első `#` fejléc a dokumentum címe. Minden további fejléc szekciót nyit, amelyet a fejlécútvonala nevez meg (a `##` alatti `###` esetén `Parent â€ş Child`). Az első szekció előtti szöveg egy „Overview” chunkká válik. A kódblokkokon belüli fejlécek szövegnek számítanak.
- Szekciónként egy chunk. A chunk szövege a `<document title> â€ş <section path>` előtaggal kezdődik, így minden chunk magával hordozza a kontextusát mind a beágyazáshoz, mind a modellhez.
- Az 1 200 karakternél hosszabb szekciótörzseket bekezdéshatárokon daraboljuk legfeljebb 1 200 karakteres darabokra (a címelőtag ezen felül jön). Egyetlen hosszabb bekezdés egyben marad. Átfedés nincs: a határok szemantikusak, így az átfedés többnyire csak ismételné a szöveget.
- A chunk ID-k `<file-stem>:<NN>` formájúak dokumentumsorrendben. A fájlokat rendezett sorrendben, normalizált soremelésekkel olvassuk, így ugyanazokból a fájlokból mindig ugyanazok a chunkok és ID-k keletkeznek.
- Az index ujjlenyomata a chunk szövegek, a daraboló paraméterei és a beágyazási modell SHA-256 hash-e. Az ingest kihagyja a munkát, ha az ujjlenyomat változatlan.

## Alternatívák

- **Rögzített méretű ablakok átfedéssel** (pl. 500 token / 50 átfedés): formátumfüggetlen, de szabályokat vág félbe mondatokon belül, és tokenizer függőséget igényel. Hosszú, strukturálatlan szövegekhez jobb, de ez a korpusz nem ilyen.
- **LangChain `MarkdownHeaderTextSplitter`**: ugyanaz az ötlet, extra függőség, kevesebb kontroll az ID-k felett. A saját darabolónk ~50 sor és unit-tesztekkel fedett, beleértve a határeseteket (késői cím, egymásba ágyazott fejlécek, kódblokkok, `#`-re végződő fejlécek).
- **Teljes dokumentumok chunkként**: a dokumentumok rövidek, de a teljes dokumentumos vektorok elmossák a különálló szabályokat és kontextustokeneket pazarolnak.

## Következmények

- A visszakeresés minősége attól függ, hogy a dokumentumoknak értelmes fejléceik legyenek. Ez a szabályzatokra igaz, és a README is ezt mondja.
- A tartalom alapú ID-k (hashek) túlélnék a szekciók átrendezését; a pozicionális ID-k olvashatóbbak a válaszokban. Ezen a méreten az olvashatóság nyer.
