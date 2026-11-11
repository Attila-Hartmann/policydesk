# ADR-005: Hibakezelés: egy hibaformátum, egy határidő, korlátozott újrapróbálások, konkurencialimit

Állapot: elfogadva

## Háttér

Minden kérés lassú és megbízhatatlan része a modelhívás: több másodperces késleltetés, szolgáltatói rate limit, átmeneti 5xx hibák. CPU-only helyi környezetben emellett kemény áteresztési korlát is van: nagyjából egyszerre egy generálás fut. A klienseknek tudniuk kell, érdemes-e újrapróbálni, és egy kérés nem lóghat tovább egy tipikus proxy timeoutnál.

## Döntés

- **Egységes hibatörzs** minden nem 2xx válaszra: `{"error": {"code", "message", "retryable", "request_id"}}`. A validációs hibákhoz `details` is kerül. Státuszkódok: 422 érvénytelen bemenet (beleértve a nem parse-olható JSON-t, a FastAPI konvenciója szerint), 504 határidő túllépve, 503 rate limit vagy túlterhelés (`Retry-After` fejléccel), 502 szolgáltatói hiba (`retryable` jelzi, hogy átmeneti volt-e vagy elutasított hívás), 500 váratlan hiba. A teljes táblázat a README-ben található.
- **Fordítás a peremeken**: a `providers.py` az SDK kivételeit domain hibákká alakítja (amelyek semmit nem tudnak a HTTP-ről); az `api.py`-ban egyetlen táblázat képezi le a kódjaikat HTTP státuszkódokra. A gráf nem kapja el őket.
- **Egy határidő kérésenként**: a `REQUEST_TIMEOUT_SECONDS` (felhőben 30 s, lokálisan 120 s) `asyncio.timeout`-tal fogja körbe a teljes gráffuttatást (embedding, sorban várakozás, generálás). A legrosszabb késleltetés a határidő, nem a hívásonkénti timeoutok és újrapróbálások összege.
- **Újrapróbálások**: az SDK beépített exponenciális backoffja jitterrel, amely tiszteletben tartja a `Retry-After` fejlécet, kizárólag kapcsolódási hibákra, timeoutokra, 408, 409, 429 és 5xx esetén. Minden kísérlet a határidő egyenlő részét kapja (felhőben: 30 s / 3 kísérlet = 10 s), így egy beragadt kísérletet újrapróbálunk ahelyett, hogy a teljes keretet felélné; amikor a határidő lejár, a futó kísérlet megszakad. Az `LLM_MAX_RETRIES` értéke felhőben 2, lokálisan 0, ahol egy timeoutolt generálás újrapróbálásra nem lesz gyorsabb, az újrapróbálás pedig megduplázza a terhelést. Az `insufficient_quota`-val érkező 429 számlázási kérdés, nem terhelés: `model_error`, nem újrapróbálható.
- **Konkurencialimit**: folyamatonként egy `asyncio.Semaphore` korlátozza a folyamatban lévő chat hívásokat (`MAX_CONCURRENT_MODEL_CALLS`: lokálisan 1, összhangban az `OLLAMA_NUM_PARALLEL=1` beállítással; felhőben 8). Az a kérés, amely `QUEUE_TIMEOUT_SECONDS`-nél (5 s, validálva, hogy rövidebb a határidőnél) tovább vár modellhelyre, gyorsan elbukik `503 overloaded` hibával és `Retry-After: 10` fejléccel, ahelyett hogy addig várakozna a sorban, amíg minden kérés túllépi a határidőt.
- **Kapcsolatbontás**: az endpoint 0,5 s-onként ellenőrzi a bontást, és megszakítja a munkát, ami felszabadítja a modellhelyet. Enélkül egy elhagyott kérés (például egy rövidebb timeoutú proxy mögött) az egyetlen lokális modellhelyet a határidőig foglalná.

## Alternatívák

- **Hibák `200`-ként, `error` mezővel**: megsérti a HTTP szemantikáját, a proxykat és a kliens újrapróbálási logikáját.
- **Saját újrapróbálási ciklus (tenacity)**: megduplikálja azt, amit az SDK már helyesen csinál.
- **Csak hívásonkénti timeoutok**: a legrosszabb eset (újrapróbálások + 1) × timeout + backoff + sorban várakozás lesz, amit könnyű elrontani, és túllépi a proxy limiteket.
- **Circuit breaker / tartalék modell**: hasznos, ha már van második szolgáltató és valódi forgalom; következő lépés.

## Következmények

- A kliensek korlátozott válaszidőt és géppel olvasható újrapróbálási útmutatást kapnak.
- Ha a szolgáltató hosszabb várakozást kér (`Retry-After`), mint amennyi a határidőből hátravan, a határidő megszakítja az SDK várakozását, és a kliens `504 model_timeout` hibát kap `503 model_rate_limited` helyett. Ennek pontos kezelése az SDK újrapróbálási ciklusának lecserélését jelentené; ekkora méretnél nem éri meg.
- A szemafor folyamatonkénti, és az API egy workerrel fut. N példány esetén a szolgáltató akár N × limit egyidejű hívást lát; a globális limithez megosztott limiter (Redis) vagy API-gateway kvóta kell. Ez a dokumentált következő lépés.
