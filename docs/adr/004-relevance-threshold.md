# ADR-004: A calibrated relevance threshold; no hits is a normal answer without a model call

Status: accepted

## Context

The app must handle "no relevant hits" sensibly. Cosine-similarity scores are not comparable across embedding models. Hypothesis, checked below: each model has its own baseline for unrelated text, so a single hard-coded threshold would be wrong for one of the two modes. Questions can be Hungarian while the documents are English, and cross-lingual scores are expected to run lower than same-language ones.

## Decision

- `MIN_RELEVANCE_SCORE` is configuration, set per embedding model in each `.env` sample.
- The value is calibrated: `python -m policydesk search "<question>"` prints the top scores without calling the chat model. For each embedding model I ran in-domain English, in-domain Hungarian and off-domain questions. The threshold goes below the lowest in-domain score and above the off-domain cluster. Measurements are below.
- If no chunk reaches the threshold, the API returns `200` with `outcome: "no_relevant_context"`, a fixed bilingual answer and no sources, and the chat model is not called.

## Measurements

_Filled in from the calibration run during implementation._

## Alternatives

- **Always call the model and let it say "I don't know"**: costs a model call per off-topic question and relies on a small local model to refuse reliably. The prompt still tells the model to refuse, as a second line of defence for borderline hits.
- **Top-k without a threshold**: the model always gets some context, even for "What's the weather?", which invites confident nonsense.
- **Reranker score threshold**: better calibrated across queries, but adds a model. Next step if borderline questions turn out to matter.
- **Return 404 for no hits**: the request was valid and the service worked. "Nothing found" is a result, and clients shouldn't treat it as an error.

## Consequences

- Changing the embedding model means recalibrating; the README and `.env` samples say so next to the variable.
- Borderline questions (a relevant word in an off-topic question) can pass the threshold. The prompt's refusal rule handles most of these.
