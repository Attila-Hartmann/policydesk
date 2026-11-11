# Követelmények nyomon követése

A feladatkiírás minden követelménye számozva (R1–R61), rövid idézettel, és azzal, hogy hol és mivel teljesül. A § jelek a kiírás fejezeteit jelölik. Állapot: ✅ teljesítve, bizonyítékkal · ⏳ a beadásig teljesül (nyilvános repó, CI).

A hivatkozott tesztek a [`tests/`](../tests/) mappában vannak; a „README” hivatkozások a [README.md](../README.md) fejezeteire mutatnak.

## Általános

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R1 | „működőképes, jól strukturált és reprodukálható backendalkalmazás … Pythonban” | Python 3.12, rétegzett csomag (README 3.1); `uv.lock`; Docker; CI; tiszta klónból, csak a README alapján végzett próba ([plan.md](plan.md) 4.) | ✅ |
| R2 | „egyszerű RAG … AI-komponenst” | Indexelés → visszakeresés → generálás (README 3.2–3.4) | ✅ |
| R3 | „kisebb, végig működő és átgondolt megoldást” | 6 futásidejű függőség, 15 modul; szándékosan kihagyott funkciók listája (README 1, 8); túltervezési review ([plan.md](plan.md) 10–11.) | ✅ |

## §1 Probléma és adatforrás

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R4 | „valós felhasználói problémát … dokumentumalapú kérdés-válasz” | Belső szabályzatok egy tanácsadó cégnél (README 1) | ✅ |
| R5 | „mutasd be a célfelhasználót, az igényt és azt, hogyan segít” | README 1: célfelhasználó, igény, hogyan segít | ✅ |
| R6 | „kis méretű, szabadon választott szöveges dokumentumkészletet” | 9 Markdown-szabályzat, kb. 15 KB ([`data/policies/`](../data/policies/)) | ✅ |
| R7 | „megosztható mintaadatokat vagy reprodukálható adat-előkészítést” | A mintaadat a repóban van, az index induláskor épül (README 4.2) | ✅ |
| R8 | „Bizalmas adatot ne használj” | Kitalált cég, `.example` domain ([`data/README.md`](../data/README.md)) | ✅ |

## §2 Elvárt alkalmazásműködés

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R9 | „HTTP API-val elérhető backendalkalmazást” | FastAPI ([`api.py`](../policydesk/api.py)); API-tesztek; élő próba mindkét módban | ✅ |
| R10 | „Frontendet nem szükséges készíteni” | Nincs frontend, a nem-célok között szerepel (README 1) | ✅ |
| R11 | „kérdés-válasz végpont … releváns dokumentumrészleteket keres, majd … választ generál” | `POST /ask`; `test_ask_returns_answer_with_sources`; integrációs tesztek lokális és felhős módban | ✅ |
| R12 | „azonosítható, mely dokumentumokat vagy részleteket használta fel” | `sources` (dokumentum, szakasz, pontszám, `cited`); `test_ask_returns_answer_with_sources`, `test_cited_numbers` | ✅ |
| R13 | „betöltése és indexelése külön paranccsal vagy induláskori folyamattal” | Induláskor (`serve`, az index kötetben marad) és külön paranccsal (`ingest`); `test_ingest_skips_when_fingerprint_unchanged_and_rebuilds_when_it_changes`, `test_ingest_builds_the_index` | ✅ |
| R14 | „alapvető bemenetellenőrzés” | Pydantic-séma: 3–500 karakter, extra mező tiltva; `test_invalid_input` | ✅ |
| R15 | „következetes hibaválasz” | Egy hibaformátum minden hibára (README 6.3); `assert_error` minden hibatesztben | ✅ |
| R16 | „naplózás” | JSON-naplók kérésazonosítóval (README 6.4); `test_request_id_propagates_to_header_body_and_logs`, `test_logs_do_not_contain_question_or_answer` | ✅ |
| R17 | „Kezeld értelmezhetően az üres vagy hibás kérést” | 422 `invalid_request` mezőnkénti okkal; `test_invalid_input`, `test_malformed_json`; `examples/ask-empty.json` élőben | ✅ |
| R18 | „a hiányzó releváns találatot” | `200` `no_relevant_context`, modellhívás nélkül; `test_no_relevant_context_does_not_call_model`; integrációs teszt | ✅ |
| R19 | „a modellhívás hibáját vagy időtúllépését” | 504/503/502 a hibaformátumban; `test_model_timeout_returns_504`, `test_model_errors`, `test_sdk_errors_become_domain_errors`; élő 504 mindkét módban, élő 503 lokálisan (README 6.3) | ✅ |
| R20 | „egyszerű állapotellenőrző végpont” | `GET /health`; `test_health_reports_models_and_index_without_model_calls`; Docker HEALTHCHECK | ✅ |
| R21 | „néhány dokumentált mintakérés … curl … automatikus dokumentációjában” | [`examples/`](../examples/) + curl-parancsok és valódi válaszok (README 6.1); OpenAPI példákkal a `/docs` címen | ✅ |
| R22 | „Jelezd egyértelműen, milyen képességeket és korlátokat vállal” | README 1 (képességek, nem-célok), README 8 (korlátok) | ✅ |

## §3 RAG-folyamat és architektúra

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R23 | „dokumentumok előkészítését, a releváns részletek visszakeresését és a kontextus alapján történő válaszgenerálást” | [`ingest.py`](../policydesk/ingest.py), [`store.py`](../policydesk/store.py), [`graph.py`](../policydesk/graph.py); `test_ingest.py`, `test_store.py`, `test_graph.py` | ✅ |
| R24 | „darabolás, embedding és tároló … röviden indokold” | README 3.6, 5; [ADR-002](adr/002-section-chunking.md), [ADR-003](adr/003-in-memory-vector-index.md), [ADR-004](adr/004-relevance-threshold.md) | ✅ |
| R25 | „egyszerű LangGraph-gráffal” | `retrieve → generate | no_context` (README 3.3); `test_routes_to_generate_…`, `test_routes_to_no_context_…` | ✅ |
| R26 | „Különítsd el az API-réteget, az alkalmazáslogikát, a RAG-folyamatot, a modell- és tárolóintegrációkat, valamint a konfigurációt” | Rétegtáblázat (README 3.1), modulonként egy réteg | ✅ |
| R27 | „külső szolgáltatások legyenek cserélhetők és tesztelhetők” | `ChatModel`/`Embedder` interfész valódi és hamis megvalósítással; minden API-teszt hamis modellel fut; `test_providers.py` | ✅ |
| R28 | „szolgáltatóspecifikus részletek ne szóródjanak szét” | Az `openai` csomagot csak a [`providers.py`](../policydesk/providers.py) importálja ([ADR-001](adr/001-one-openai-compatible-client.md)) | ✅ |
| R29 | „Mutasd be a fő komponenseket, az adatáramlást és a fontosabb tervezési kompromisszumokat” | Mermaid-ábrák és döntési táblázat (README 3); ADR-ek | ✅ |

## §4 Modellhasználat és ingyenes lokális alternatíva

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R30 | „elsődleges megoldás használhat fizetős vagy felhős LLM … modellválasztást röviden indokold” | OpenAI `gpt-6-luna` + `text-embedding-3-large`, indoklással és mért költséggel (README 5.1); felhős integrációs tesztek: 6/6 | ✅ |
| R31 | „ingyenes, lokális futtatási lehetőséget … teljes RAG-folyamat működjön fizetős API-kulcs nélkül, beleértve az embeddinget” | Ollama a Compose-ban, `qwen3:4b-instruct` + `bge-m3`, kulcs nélkül; lokális integrációs tesztek: 6/6 | ✅ |
| R32 | „váltás konfigurációval … alkalmazáslogika módosítása nélkül” | Két `.env`-minta, ugyanaz az image (README 2, 5); `test_env_samples_are_valid` | ✅ |
| R33 | „Dokumentáld a lokális modell beszerzését, indítását, a konfigurációt, a várható memória- és hardverigényt, valamint a korlátokat” | README 5.2: beszerzés, indítás, beállítások, mért lemez/memória/idő, ajánlott minimum, korlátok | ✅ |
| R34 | „A kezdeti csomag- és modellletöltéshez internet szükséges lehet” | README 2 és 5.2 (első letöltés, utána offline is indul) | ✅ |
| R35 | „Mock vagy dummy modell … nem helyettesíti a működő lokális alternatívát” | Hamis modellek csak a gyors tesztekben; a lokális mód valódi modellekkel ellenőrizve (integrációs tesztek, tiszta klónból végzett próba) | ✅ |

## §5 Konkurens felhasználók és skálázás

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R36 | „konkrétan, a saját megoldásodra vonatkoztatva” | README 7, a kód konkrét elemeire hivatkozva | ✅ |
| R37 | „Kérések elkülönítése” | README 7; `test_concurrent_requests_do_not_mix` | ✅ |
| R38 | „Párhuzamos végrehajtás” | README 7 (aszinkron hívások, egy worker indoklással, háttérfeladat és feladat-API mint következő lépés) | ✅ |
| R39 | „Erőforráskorlátok” | README 7; [ADR-005](adr/005-failure-policy.md); `test_overloaded_when_no_slot`, `test_timeout_releases_the_model_slot`, `test_client_disconnect_cancels_the_work_and_frees_the_slot`, `test_model_timeout_returns_504` | ✅ |
| R40 | „Több alkalmazáspéldány” | README 7 (állapotmentes API, determinisztikus index; közös vektortár mint következő lépés) | ✅ |
| R41 | „Szűk keresztmetszetek … metrikákat … milyen sorrendben” | README 7 (fő korlát, metrikák listája, fejlesztési sorrend) | ✅ |
| R42 | „Különítsd el, mit valósítottál meg, és mi lenne egy következő fejlesztési lépés” | README 7: minden pont [megvalósítva] vagy [következő lépés] címkével | ✅ |
| R43 | „Egy rövid párhuzamosítási vagy terhelési próba opcionális” | Nincs külön terheléses teszt; a párhuzamossági teszt és az élő 503-próba mutatja a viselkedést (README 6.3, 7) | ✅ |

## §6 Tesztelés és reprodukálhatóság

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R44 | „sikeres kérdésfeldolgozás, hibás bemenet, üres találati lista és modellhívási hiba vagy timeout” | README 4.4 táblázata: `test_ask_returns_answer_with_sources`, `test_invalid_input`, `test_no_relevant_context_does_not_call_model`, `test_model_timeout_returns_504`, `test_model_errors` | ✅ |
| R45 | „Az alaptesztek fizetős szolgáltatás nélkül is fussanak” | 99 gyors teszt hamis modellekkel, hálózat nélkül; CI kulcs nélkül fut | ✅ |
| R46 | „integrációs próbák legyenek külön indíthatók” | `integration` marker, alapból kihagyva; `uv run pytest -m integration` (README 4.4) | ✅ |
| R47 | „Dockerfile kötelező” | [`Dockerfile`](../Dockerfile) (build, teszt, futtató szakasz); CI-ben buildelve | ✅ |
| R48 | „adj docker-compose.yml-t vagy ugyanilyen egyértelmű indítási leírást” | [`docker-compose.yml`](../docker-compose.yml); CI-ben mindkét módra ellenőrizve | ✅ |
| R49 | „rögzített függőségeket vagy lockfájlt” | `uv.lock`; `uv sync --frozen` a Dockerfile-ban és a CI-ben; rögzített image-verziók | ✅ |
| R50 | „titkok nélküli konfigurációs mintát” | `.env.example`, `.env.openai.example` kulcs nélkül; `test_env_samples_are_valid` ellenőrzi; `.env*` a `.gitignore`-ban és a `.dockerignore`-ban | ✅ |
| R51 | „lokális modell külön folyamatban vagy konténerben … alkalmazásból való elérését dokumentáld” | README 5.2 „Hogyan éri el az alkalmazás” | ✅ |
| R52 | „Nem szükséges 10–20 kérdéses RAG-értékelő készlet … modellek összehasonlítása” | Nem készült; a küszöb kalibrálása 36 kérdéssel csak a „nincs találat” döntéshez kellett (ADR-004); kiértékelő készlet a következő lépések között (README 8) | ✅ |

## §7 Leadandók és a README tartalma

| ID | Kiírás (idézet) | Hol teljesül, mi bizonyítja | Állapot |
|---|---|---|---|
| R53 | „teljes projekt forráskódja egy nyilvános Git repoban, a tesztekkel és … konfigurációs mintákkal” | Nyilvános GitHub-repó, zöld CI | ⏳ |
| R54 | „Dockerfile, és szükség esetén docker-compose.yml” | Lásd R47, R48 | ✅ |
| R55 | „Mintaadatok … valamint néhány kipróbálható API-kérés” | Lásd R7, R21 | ✅ |
| R56 | README: „választott probléma és a megvalósított funkciók” | README 1 | ✅ |
| R57 | README: „projekt felépítését, a rendszerarchitektúrát és a fő tervezési döntéseket” | README 3 | ✅ |
| R58 | README: „telepítés, adat-előkészítés, indítás és tesztfuttatás pontos lépéseit” | README 2, 4; tiszta klónból végzett próbán ellenőrizve | ✅ |
| R59 | README: „elsődleges modellkonfiguráció és az ingyenes lokális alternatíva teljes futtatási leírását” | README 5 | ✅ |
| R60 | README: „konkurens felhasználók kiszolgálására és a skálázásra vonatkozó megfontolásokat” | README 7 | ✅ |
| R61 | README: „ismert korlátokat, egyszerűsítéseket és a következő fejlesztési lépéseket” | README 8 | ✅ |
