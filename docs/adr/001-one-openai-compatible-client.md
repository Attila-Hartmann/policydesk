# ADR-001: Egyetlen OpenAI-kompatibilis kliens felhős és lokális modellekhez

Állapot: elfogadva

## Háttér

A feladatkiírás fizetős felhős módot és ingyenes lokális módot ír elő, amelyeket kizárólag konfigurációval lehet váltani, a szolgáltató-specifikus részleteket pedig egy helyen kell tartani. A felhőhöz az OpenAI és az Azure OpenAI a jelölt; a lokálishoz az Ollama.

Mindhárom ugyanazt az OpenAI-kompatibilis HTTP API-t szolgálja ki chat completion és embedding hívásokhoz: az OpenAI natívan, az Azure OpenAI a v1 végpontján keresztül (`https://<resource>.openai.azure.com/openai/v1/`, 2025 augusztusa óta GA), az Ollama pedig a `/v1` alatt.

## Döntés

Minden módhoz a hivatalos `openai` Python SDK-t (async kliens) használjuk. A módot környezeti változók halmaza jelöli: `BASE_URL`, `API_KEY`, `CHAT_MODEL`, `EMBEDDING_MODEL`, valamint opcionális kérési paraméterek (`REASONING_EFFORT`). A `providers.py` az egyetlen modul, amely importálja az `openai`-t; ez építi fel a klienseket, és fordítja le az SDK kivételeit saját (domain) hibatípusokká.

Az alkalmazás két kis protokolltól függ, a `ChatModel`-től és az `Embedder`-től. Mindkettő második megvalósítása a tesztekben használt hamis (fake) modell.

## Alternatívák

- **LangChain chat model osztályok** (`ChatOpenAI`, `ChatOllama`, `AzureChatOpenAI`): szolgáltatónként egy osztály azt jelenti, hogy a szolgáltató választása kódba kerül, több függőség, és ugyanazok a HTTP hívások a háttérben. Elvetve.
- **Szolgáltatónként egy adapter-osztály egy interfész mögött**: ugyanannak a protokollnak három implementációja, amelyek csak a base URL-ben térnek el. Elvetve mint olyan absztrakció, amely mögött nincs valódi különbség.
- **Ollama natív API** (`/api/chat`): hozzáférést ad a `think` és `keep_alive` paraméterekhez, de a lokális módot külön kódrészletté teszi. Egy nem-gondolkodó modellel erre nincs szükség.

## Következmények

- A módváltás soha nem érinti a kódot; ugyanaz az image fut minden módban.
- Egy OpenAI-kompatibilis API-val nem rendelkező szolgáltatóhoz (például a Bedrock Converse API-ja) egy második `ChatModel` implementáció kellene. A protokoll az a csatlakozási pont, ahol ez beköthető; most nincs megépítve.
- A szolgáltatói sajátosságok konfigurációban vannak, nem kódban: a `REASONING_EFFORT=none` értéket csak akkor küldjük el, ha be van állítva, mert az Ollamának nincs rá szüksége.
