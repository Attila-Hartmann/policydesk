# Tervezési jegyzet

Ez a dokumentum rögzíti, milyen kérdésekre kellett tervezés közben választ adni, mit választottam, mi volt a fő alternatíva, és miért. Leírja azt is, mit változtatott a terven két független review, a tiszta klónból végzett próba és az implementáció. Az architektúra ábrái, a konfiguráció, az API és a tesztek leírása egy helyen, a [README](../README.md)-ben van, hogy ne legyen két, egymástól elcsúszó változat. A döntések részletes indoklása az [ADR-ekben](adr/) található, a követelmények teljesítése a [requirements.md](requirements.md)-ben.

## 1. Tervezési kérdések és válaszok

### Architektúra és cserélhetőség

1. **Hogyan különülnek el a rétegek, és hol van a szolgáltatófüggő kód?**
   API (`api.py`, `schemas.py`) → alkalmazáslogika (`service.py`) → RAG-folyamat (`graph.py`, `prompts.py`, `ingest.py`) → integrációk (`providers.py`, `store.py`); konfiguráció a `config.py`-ban. Az `openai` csomagot csak a `providers.py` importálja, ott fordítódnak le a kivételek saját hibatípusokra. A hibatípusok nem ismerik a HTTP-t; a kód → státusz leképezés egyetlen táblázat az `api.py`-ban.
2. **Milyen interfészek vannak, és mindegyiknek van-e valódi második megvalósítása?**
   Kettő: `ChatModel` és `Embedder` ([`ports.py`](../policydesk/ports.py)). Valódi megvalósításuk az OpenAI-kompatibilis kliens, a második a tesztekben használt hamis modell. A vektortárnak nincs interfésze: egy megvalósítása van, a tesztek is azt használják hamis beágyazásokkal. Szolgáltatónkénti osztály sincs, mert az OpenAI, az Azure OpenAI v1 és az Ollama ugyanazt az API-t adja ([ADR-001](adr/001-one-openai-compatible-client.md)).
3. **Hogyan vált a konfiguráció felhő és lokális között, és hogyan derül ki a hibás konfiguráció induláskor?**
   Minden beállítás környezeti változó (`.env`); két minta van (`.env.example` lokális, `.env.openai.example` felhős), ugyanaz az image fut mindkettővel. Indításkor: (1) Pydantic-validálás, a hibaüzenet a változó nevét tartalmazza, az értékét nem, mert az kulcs is lehet; a határidő és a sorvárakozás viszonyát is ellenőrzi; (2) egy embedding- és egy chat-hívás, ami a rossz kulcsot, az elírt modellnevet és a le nem töltött modellt is megfogja; (3) az index embedding-modelljének egyeznie kell a konfigurációval. Bármelyik hibánál a folyamat egy érthető naplósorral és 1-es kóddal kilép, forgalmat nem fogad.
4. **Melyik modellek, és miért?**
   Felhő: `gpt-6-luna` `reasoning_effort=none`-nal (0,10 / 0,50 USD millió tokenenként, EU-s adattárolással elérhető; a feladat a megadott szövegből válaszolni, gondolkodás nélkül gyorsabb) és `text-embedding-3-large`. A `text-embedding-3-small` volt az első választás, de a kalibrálás szerint a magyar kérdéseket nem választja el a témán kívüliektől ([ADR-004](adr/004-relevance-threshold.md)). Lokális: `qwen3:4b-instruct` (nem gondolkodó 4B-s modell, mert CPU-n a rejtett gondolkodás percekbe kerülne) és `bge-m3` (többnyelvű, nem kell előtag). A fejlesztőgépen nincs dedikált GPU (4 mag, 40 GB RAM); a mért memória, lemez és válaszidő a README 5.2-ben van.

### Adatok és visszakeresés

5. **Darabolás, és ugyanabból a dokumentumból mindig ugyanaz lesz-e?**
   Markdown-szakaszonként, a cím és a szakaszútvonal a darab elején, hosszú szakasz bekezdéshatáron vágva, átfedés nélkül. Determinisztikus: rendezett fájlsorrend, normalizált sorvégek, `fájl:NN` azonosítók; teszt ellenőrzi ([ADR-002](adr/002-section-chunking.md)).
6. **Melyik vektortár, és mi változna több példánynál?**
   Pontos koszinusz-keresés NumPy-mátrixon, JSON-fájlban tárolva: 57 darabnál mikroszekundum, nincs külön szolgáltatás. Több példánynál mindegyik ugyanazt az indexet építi vagy tölti be; ha a dokumentumok futás közben változnak, vagy a korpusz nagy, közös tár kell (pgvector, Azure AI Search) és egy indexelő job ([ADR-003](adr/003-in-memory-vector-index.md)).
7. **Mi történik, ha az embedding-modell megváltozik, de a régi index marad?**
   Az index rögzíti a modellt, a dimenziót és az ujjlenyomatot. Más modellel épült indexet az API nem tölt be (érthető hibaüzenet); a konténer indulásakor az ujjlenyomat eltérése miatt az index magától újraépül.
8. **Mikor nincs releváns találat, ha a pontszámok modellenként mások?**
   Embedding-modellenként kalibrált `MIN_RELEVANCE_SCORE`, 12 angol, 12 magyar és 12 témán kívüli kérdéssel mérve ([`scripts/calibrate.py`](../scripts/calibrate.py)); `bge-m3`: 0,55, `text-embedding-3-large`: 0,39. A rés mindkettőnél kicsi; ezt a README a korlátok között jelzi.
9. **Hiba-e a „nincs találat”, és hívjuk-e ilyenkor a modellt?**
   Nem hiba: `200`, `outcome: "no_relevant_context"`, rögzített kétnyelvű válasz, és a modellt nem hívjuk (költség, hallucináció). Teszt ellenőrzi, hogy a modell nem kap hívást.

### Folyamat és válasz

10. **Hogyan néz ki a gráf, mi közös a kérések között?**
    `retrieve → generate | no_context`, feltételes éllel. A gráf egyszer fordul le; a függőségei csak olvashatók (a szemafor párhuzamos használatra készült). Kérésadat csak a kérésenként új állapotban van. A csomópontok nem kapják el a hibákat, azok az API-hoz jutnak. Két lépéshez a LangGraph önmagában nem kellene; a kiírás kéri.
11. **Hogyan marad a válasz a kontextusnál, hogyan kötődnek hozzá a források, és mi a helyzet a prompt injectionnel?**
    A rendszerprompt szerint csak a számozott részletekből válaszolhat, ha nincs benne a válasz, mondja meg, hivatkozzon `[n]` formában, és a részletekben lévő utasításokat hagyja figyelmen kívül; a részletek elválasztva érkeznek. A `sources` minden átadott részletet tartalmaz, a `cited` a hivatkozásokból jön (`[1]`, `[1-3]`, `[1; 2]`, `[Excerpt 2]` is). Az injection elleni védelem nem garancia, de a modellnek nincsenek eszközei, így a legrosszabb eset egy rossz válasz.

### API és hibakezelés

12. **Kérés, válasz, korlátok, egységes hibaformátum?**
    `{"question": "..."}`, 3–500 karakter levágás után, extra mező tilos. Minden nem 2xx válasz `{"error": {"code", "message", "retryable", "request_id"}}`; a táblázat a README 6.3-ban.
13. **Mit lát a kliens időtúllépésnél, szolgáltatói hibánál, rate limitnél, túlterhelésnél, hiányzó indexnél, váratlan hibánál?**
    504 `model_timeout`; 502 `model_error` (`retryable` szerint átmeneti vagy elutasított); 503 `model_rate_limited` és 503 `overloaded` `Retry-After`-rel; hiányzó index esetén a szolgáltatás el sem indul; váratlan hibánál 500 általános üzenettel, a részletek csak a naplóban.
14. **Időkorlátok, újrapróbálás, konkurenciakorlát: mi készült el?**
    Mindhárom: egy határidő kérésenként a teljes folyamatra; az SDK újrapróbálása átmeneti hibákra, próbálkozásonként a határidő egyenlő részével; folyamatonkénti szemafor gyors 503-mal; és ha a kliens bontja a kapcsolatot, a munka leáll, a modellhely felszabadul ([ADR-005](adr/005-failure-policy.md)).
15. **Mit naplózunk, hogyan kapcsolódnak össze egy kérés sorai, és mit nem naplózunk?**
    JSON-sorok `request_id`-val (`contextvar`), lépésenkénti idővel, tokenszámmal, várakozási idővel. Az API-kulcsot, a kérdés és a válasz szövegét nem naplózzuk, csak a hosszukat.
16. **Mit mutat a `/health`, és hívja-e a modellt?**
    Liveness: a folyamat él, az index betöltődött, a modellek induláskor válaszoltak. Futás közben nem hívja a modellt (költség, külső függés, felesleges újraindítások szolgáltatói kiesésnél).

### Párhuzamosság és futtatás

17. **Hol blokkolódhat az eseményhurok?**
    Sehol a kérésúton: aszinkron kliens, mikroszekundumos keresés, az indexelés a forgalom előtt fut, a CPU-igényes generálás az Ollama folyamatában. Egy uvicorn worker, mert a kérések a modellre várnak, és több worker megtöbbszörözné a modellhívás-korlátot és az indexet.
18. **Hogyan fut konténerben, hogyan éri el az Ollamát, mikor fut az indexelés, hány parancs kell az első válaszig?**
    Többlépcsős Dockerfile, nem root felhasználó. Compose: `ollama` és az egyszer lefutó `ollama-pull` a `local` profilban, valamint az `api`. Az `api` induláskor indexel (ujjlenyomattal, az index kötetben marad), ellenőriz, majd kiszolgál. Az Ollama portja nincs kinyitva a gép felé. Klónozás után két parancs: `cp .env.example .env` és `docker compose up --build`.
19. **Mit futtat a CI hálózat és kulcs nélkül?**
    Lint, formázás, mypy strict, a gyors tesztcsomag lefedettséggel (küszöb 85%), Docker-build, Compose-ellenőrzés mindkét módban, és hogy elérhetetlen modellnél a konténer 1-es kóddal, `startup_failed` sorral áll le.

## 2. A terv független review-ja

A tervet egy előzményeket nem ismerő bíráló nézte át, csak a kiírás, a követelménymátrix és a terv alapján. 23 megállapításának összefoglalása:

| Téma | Eredmény |
|---|---|
| Az index kötete nem írható a nem root felhasználónak | Javítva: a `/app/var` a felhasználóé, a kötet ezt örökli |
| A felhős modell neve és ára nem ellenőrizhető | Ellenőriztem a modell OpenAI-oldalán; a link a README-ben |
| A `.env` extra kulcsai miatt összeomló beállítások; `ollama` hostnév a gépen | Javítva (`extra="ignore"`, a gépi futtatás címe dokumentálva) |
| Csendes promptlevágás az Ollamában, nem rögzített verziók | Javítva: `OLLAMA_CONTEXT_LENGTH=8192`, rögzített image |
| A lokális konkurenciakorlát nem egyezik az Ollama párhuzamosságával | Javítva: `OLLAMA_NUM_PARALLEL=1`, korlát 1 |
| Nem korlátos legrosszabb válaszidő | Javítva: egy határidő kérésenként |
| „Az indexelés bizonyítja a modellt” téves állítás | Javítva: indításkori modellellenőrzés |
| A küszöb nem számol a magyar kérdésekkel | Javítva: magyar kalibrációs kérdések, kétnyelvű válasz |
| Hiányzó skálázási tartalom (párhuzamosság, metrikák) | Javítva: README 7 |
| Külön ingest-szolgáltatás felesleges | Javítva: indexelés induláskor, ugyanabban a konténerben |
| Törékeny Compose-folyamat; a hardverigény csak a saját gépet írja le | Javítva: egészség-ellenőrzés, profilok, mért erőforrástáblázat |
| Az Azure-minta nem tesztelt konfiguráció | Elfogadva: csak README-bekezdés |
| Elutasítás `answered`-ként | Elvetve, indoklással: a kis modell helyes válasznál is kihagyhatja a hivatkozást |
| Windows-specifikus curl, sorvégek, titkok | Javítva: JSON-fájlos példák, `.gitattributes`, `SecretStr`, `.dockerignore` |

## 3. Változások az implementáció és a mérések során

| Terv | Megvalósítás | Ok |
|---|---|---|
| Az Ollama portja kinyitva, az integrációs tesztek az Ollamát hívják | A port nincs kinyitva; az integrációs tesztek a futó API-t hívják | Egy már futó natív Ollama mellett a kinyitott port ütközne; az API-n át a teljes stack tesztelődik, mindkét módban |
| Az indításkori ellenőrzés a kérési határidőt használja | Saját, 300 s-os időkorlát | A modell hidegindítása nem felhasználói kérés; a kis határidős 504-próba nem törheti el az indulást |
| `text-embedding-3-small` | `text-embedding-3-large`, küszöb 0,39 | A kalibrálás szerint a small nem választja el a magyar kérdéseket |
| Kézi kalibrálás | `scripts/calibrate.py` | Az ADR-ben szereplő számok legyenek megismételhetők |
| — | A nem JSON 200-as szolgáltatói válasz `502 model_error` | Teszt találta meg: rossz `BASE_URL`-nél 500 lett volna |
| `docker compose down` módváltáskor | `docker compose --profile local down` | A felhős füstteszt mutatta meg: üres profillal a `down` nem látja az Ollama-konténereket |

## 4. Kódreview és tiszta klónból végzett próba

**Független kódreview** (18 megállapítás, blokkoló nem volt). A fontosabbak:

| Megállapítás | Eredmény |
|---|---|
| A kapcsolatot bontó kliens a határidőig foglalja az egyetlen lokális modellhelyet | Javítva: a munka leáll, a hely felszabadul. Élőben derült ki, hogy a Starlette `BaseHTTPMiddleware` elrejti a bontást, ezért a köztes réteg sima ASGI lett |
| A próbálkozásonkénti időkorlát egyenlő volt a teljes határidővel, így beragadt hívást sosem próbált újra | Javítva: a határidő egyenlő része jut egy próbálkozásra |
| Dokumentum hozzáadása Dockerben nem működött a leírt módon; az index minden új konténerben újraépült | Javítva: a szabályzatok csak olvashatóan csatolva, az index kötetben |
| Néhány indulási hiba megkerülte a `startup_failed` utat | Javítva: `LOG_LEVEL`-validálás, üres korpusz, `OSError` |
| Hibásan újrapróbálhatónak jelölt hibák | Javítva: üres válasz, érvénytelen válasz, `insufficient_quota` |
| Darabolási határesetek | Javítva és tesztelve: késői cím, szakaszútvonal, kódblokk, `#`-re végződő cím |
| Szűk hivatkozásfelismerés | Javítva: tartományok, pontosvessző, „Excerpt n” |
| A hibatípusok ismerték a HTTP-státuszt; a szolgáltatás HTTP-DTO-t adott vissza; `Any` típusú gráf | Javítva |
| A tárolóban `ModelError` dimenzióeltérésre | Megtartva: az indításkori ellenőrzés kizárja a konfigurációs eltérést, így ez csak hibás modellválasz lehet (502) |
| Hiányzó tesztek: határidő utáni felszabadulás, kapcsolatbontás, kérésazonosítók párhuzamosan | Hozzáadva |
| Hosszú `Retry-After` a határidőn belül 504-et ad 503 helyett | Dokumentált korlát (README 8.); pontos kezelése az SDK újrapróbálásának lecserélését igényelné |
| A dokumentáció mérete és elcsúszása a kódtól | Ez a jegyzet ezért rövidebb a korábbi tervnél, és nem ismétli a README-t |

**Tiszta klónból végzett próba:** egy előzményeket nem ismerő bíráló a repót friss mappába klónozta, és csak a README-t követve indította el, kérdezett, és futtatta a teszteket Windowson (Git Bash és PowerShell). Minden lépés működött. Javított pontok: az első letöltés valós mérete (kb. 12 GB), a csendes indexelés (most kötegenként naplóz), a Docker-tesztszakasz most a lintet és a típusellenőrzést is futtatja, egy nem reprodukálható időadat törölve, futó API nélkül az integrációs tesztek hibával állnak le, és a konténeren belüli parancsok (`docker compose exec`) dokumentálva. Az első indulást friss modellkötettel külön is lemértem: a 3,7 GB-os modellek letöltésével együtt 465 s alatt lett egészséges a stack.
