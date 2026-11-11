# Requirements traceability matrix

Every requirement in the assignment brief (Hungarian), numbered. Each row has a short quote from the brief, an English paraphrase, how it is verified, and where it is satisfied. Status: ⬜ planned · ✅ done with evidence.

Section numbers (§) follow the brief.

## General

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R1 | „működőképes, jól strukturált és reprodukálható backendalkalmazás … Pythonban” | A working, well-structured, reproducible Python backend | CI green; clean-room run of the README | | ⬜ |
| R2 | „egyszerű RAG … AI-komponenst” | Contains a simple RAG component | README *Architecture* | | ⬜ |
| R3 | „kisebb, végig működő és átgondolt megoldást” | Small, end-to-end, well-reasoned; not feature-rich | README *Capabilities and non-goals*; over-engineering review | | ⬜ |

## §1 Problem and data source

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R4 | „valós felhasználói problémát … dokumentumalapú kérdés-válasz” | Pick a real user problem that document Q&A helps with | README *Problem* | | ⬜ |
| R5 | „mutasd be a célfelhasználót, az igényt és azt, hogyan segít” | Describe target user, need, how the app helps | README *Problem* | | ⬜ |
| R6 | „kis méretű, szabadon választott szöveges dokumentumkészletet” | Small, freely chosen text corpus | `data/` contents | | ⬜ |
| R7 | „megosztható mintaadatokat vagy reprodukálható adat-előkészítést” | Shareable sample data so it runs without own documents | Data committed; clean-room run | | ⬜ |
| R8 | „Bizalmas adatot ne használj” | No confidential data | Synthetic, fictional data; README note | | ⬜ |

## §2 Application behaviour

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R9 | „HTTP API-val elérhető backendalkalmazást” | HTTP API backend (framework free) | API tests; curl smoke | | ⬜ |
| R10 | „Frontendet nem szükséges készíteni” | No frontend needed (and none built) | README *Non-goals* | | ⬜ |
| R11 | „kérdés-válasz végpont … releváns dokumentumrészleteket keres, majd … választ generál” | Q&A endpoint: takes a question, retrieves relevant chunks, generates an answer from them | API test: success path; local + cloud smoke | | ⬜ |
| R12 | „azonosítható, mely dokumentumokat vagy részleteket használta fel” | Response identifies the documents/chunks used | API test asserts `sources`; smoke | | ⬜ |
| R13 | „betöltése és indexelése külön paranccsal vagy induláskori folyamattal” | Loading and indexing by a separate command or at startup; no upload API needed | Ingest command; README *Data prep* | | ⬜ |
| R14 | „alapvető bemenetellenőrzés” | Basic input validation | API tests: invalid input | | ⬜ |
| R15 | „következetes hibaválasz” | Consistent error response format | API tests assert one error schema for every failure | | ⬜ |
| R16 | „naplózás” | Logging | Log test / request-id correlation; README *Logging* | | ⬜ |
| R17 | „Kezeld értelmezhetően az üres vagy hibás kérést” | Handle empty or malformed requests meaningfully | API tests: empty, whitespace, too long, malformed JSON | | ⬜ |
| R18 | „a hiányzó releváns találatot” | Handle no relevant hits meaningfully | API test: no-hit path, model not called | | ⬜ |
| R19 | „a modellhívás hibáját vagy időtúllépését” | Handle model error and timeout meaningfully | API tests: provider error, timeout; smoke with tiny timeout | | ⬜ |
| R20 | „egyszerű állapotellenőrző végpont” | Simple health endpoint | API test: health | | ⬜ |
| R21 | „néhány dokumentált mintakérés … curl … automatikus dokumentációjában” | A few documented sample requests (curl and/or OpenAPI docs) | README *API*; OpenAPI examples; smoke runs every curl | | ⬜ |
| R22 | „Jelezd egyértelműen, milyen képességeket és korlátokat vállal” | State capabilities and limits clearly (history, users, auth optional) | README *Capabilities and non-goals*, *Limitations* | | ⬜ |

## §3 RAG flow and architecture

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R23 | „dokumentumok előkészítését, a releváns részletek visszakeresését és a kontextus alapján történő válaszgenerálást” | RAG covers document prep, retrieval, context-grounded generation | Unit tests: chunking, retrieval; API success test | | ⬜ |
| R24 | „darabolás, embedding és tároló … röviden indokold” | Justify chunking, embedding and store choices | README *Design decisions*; ADRs | | ⬜ |
| R25 | „egyszerű LangGraph-gráffal” | Question processing is a simple LangGraph graph (retrieve → generate, optional error/prep step) | Unit test: graph routing; README graph diagram | | ⬜ |
| R26 | „Különítsd el az API-réteget, az alkalmazáslogikát, a RAG-folyamatot, a modell- és tárolóintegrációkat, valamint a konfigurációt” | Separate API, application logic, RAG flow, model/store integrations, configuration | Project layout; README *Project layout* | | ⬜ |
| R27 | „külső szolgáltatások legyenek cserélhetők és tesztelhetők” | External services swappable and testable | `FakeChat`/`FakeEmbedder` used by every API test; `test_providers` (client built from config) | | ⬜ |
| R28 | „szolgáltatóspecifikus részletek ne szóródjanak szét” | Provider-specific details in one place | Single providers module; review | | ⬜ |
| R29 | „Mutasd be a fő komponenseket, az adatáramlást és a fontosabb tervezési kompromisszumokat” | Show components, data flow, main trade-offs | README diagrams; ADRs | | ⬜ |

## §4 Models and free local alternative

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R30 | „elsődleges megoldás használhat fizetős vagy felhős LLM … modellválasztást röviden indokold” | Primary mode may use a paid/cloud LLM; justify the model | README *Model configuration*; cloud smoke | | ⬜ |
| R31 | „ingyenes, lokális futtatási lehetőséget … teljes RAG-folyamat működjön fizetős API-kulcs nélkül, beleértve az embeddinget” | Free local mode (e.g. Ollama); whole pipeline incl. embeddings without a paid key | Compose smoke in local mode with no key; Ollama integration test | | ⬜ |
| R32 | „váltás konfigurációval … alkalmazáslogika módosítása nélkül” | Mode switch by configuration only | Unit test: provider from config; both smokes from the same image | | ⬜ |
| R33 | „Dokumentáld a lokális modell beszerzését, indítását, a konfigurációt, a várható memória- és hardverigényt, valamint a korlátokat” | Document local model download, start, config, memory/hardware needs, limits | README *Local mode* with measured numbers | | ⬜ |
| R34 | „A kezdeti csomag- és modellletöltéshez internet szükséges lehet” | Internet may be needed for first download (state it) | README *Local mode* | | ⬜ |
| R35 | „Mock vagy dummy modell … nem helyettesíti a működő lokális alternatívát” | Mocks for tests only; local mode must really work | Ollama integration test; local compose smoke | | ⬜ |

## §5 Concurrent users and scalability (documentation)

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R36 | „konkrétan, a saját megoldásodra vonatkoztatva” | Explain multi-user readiness concretely for this solution | README *Concurrency and scalability* | | ⬜ |
| R37 | „Kérések elkülönítése” | Request isolation: no shared mutable state, no data mix-up | README section; per-request state in graph (code) | | ⬜ |
| R38 | „Párhuzamos végrehajtás” | Parallel execution: blocking spots; async vs worker vs background task | README section | | ⬜ |
| R39 | „Erőforráskorlátok” | Resource limits: model-call concurrency, API limits, timeout, transient errors, overload | README section; timeout/error tests | | ⬜ |
| R40 | „Több alkalmazáspéldány” | Multiple instances: what stays stateless, what moves to shared durable storage | README section | | ⬜ |
| R41 | „Szűk keresztmetszetek … metrikákat … milyen sorrendben” | Bottleneck, metrics to watch, order of improvements | README section | | ⬜ |
| R42 | „Különítsd el, mit valósítottál meg, és mi lenne egy következő fejlesztési lépés” | Separate implemented vs next step | README section labels each point [implemented]/[next step] | | ⬜ |
| R43 | „Egy rövid párhuzamosítási vagy terhelési próba opcionális” | Load/concurrency probe is optional, does not replace reasoning | Decided: no separate load test; `test_concurrent_requests_do_not_mix` and `test_overloaded_when_no_slot` cover isolation and the 503 path | | ⬜ |

## §6 Testing and reproducibility

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R44 | „sikeres kérdésfeldolgozás, hibás bemenet, üres találati lista és modellhívási hiba vagy timeout” | Automated tests: success, invalid input, empty hits, model error/timeout | `test_ask_returns_answer_with_sources`, `test_invalid_input`, `test_no_relevant_context_does_not_call_model`, `test_model_timeout_returns_504`, `test_model_errors` | | ⬜ |
| R45 | „Az alaptesztek fizetős szolgáltatás nélkül is fussanak” | Core tests run without paid services (mocked model/retriever) | CI runs with no network/keys | | ⬜ |
| R46 | „integrációs próbák legyenek külön indíthatók” | Integration tests against real services start separately | pytest marker, skipped by default; separate command | | ⬜ |
| R47 | „Dockerfile kötelező” | Dockerfile is mandatory | `docker build` in CI | | ⬜ |
| R48 | „adj docker-compose.yml-t vagy ugyanilyen egyértelmű indítási leírást” | docker-compose.yml if several services | `docker-compose.yml`; local-mode compose smoke | | ⬜ |
| R49 | „rögzített függőségeket vagy lockfájlt” | Pinned dependencies or lockfile | `uv.lock`; `uv sync --frozen` in CI and Dockerfile | | ⬜ |
| R50 | „titkok nélküli konfigurációs mintát” | Config sample without secrets | `.env.example`; `.env` gitignored | | ⬜ |
| R51 | „lokális modell külön folyamatban vagy konténerben … alkalmazásból való elérését dokumentáld” | Local model may run separately; document how the app reaches it | README *Local mode* | | ⬜ |
| R52 | „Nem szükséges 10–20 kérdéses RAG-értékelő készlet … modellek összehasonlítása” | No eval set, quality metrics or model comparison required (not built) | README *Non-goals / next steps* | | ⬜ |

## §7 Deliverables and README contents

| ID | Brief (HU, short quote) | Requirement | Verification | Evidence | Status |
|---|---|---|---|---|---|
| R53 | „teljes projekt forráskódja egy nyilvános Git repoban, a tesztekkel és … konfigurációs mintákkal” | Full source in a public Git repo with tests and config samples | Public GitHub URL | | ⬜ |
| R54 | „Dockerfile, és szükség esetén docker-compose.yml” | Dockerfile and compose file delivered | See R47, R48 | | ⬜ |
| R55 | „Mintaadatok … valamint néhány kipróbálható API-kérés” | Sample data and a few runnable API requests | See R7, R21 | | ⬜ |
| R56 | README: „választott probléma és a megvalósított funkciók” | README: problem and implemented features | README §1 | | ⬜ |
| R57 | README: „projekt felépítését, a rendszerarchitektúrát és a fő tervezési döntéseket” | README: structure, architecture, main decisions | README §3 | | ⬜ |
| R58 | README: „telepítés, adat-előkészítés, indítás és tesztfuttatás pontos lépéseit” | README: exact install, data prep, start, test steps | README §4; clean-room run | | ⬜ |
| R59 | README: „elsődleges modellkonfiguráció és az ingyenes lokális alternatíva teljes futtatási leírását” | README: primary model config and full local run guide | README §5 | | ⬜ |
| R60 | README: „konkurens felhasználók kiszolgálására és a skálázásra vonatkozó megfontolásokat” | README: concurrency and scaling considerations | README §7 (see R36–R42) | | ⬜ |
| R61 | README: „ismert korlátokat, egyszerűsítéseket és a következő fejlesztési lépéseket” | README: known limits, simplifications, next steps | README §8 | | ⬜ |
