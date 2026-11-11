# ADR-004: A calibrated relevance threshold; no hits is a normal answer without a model call

Status: accepted

## Context

The app must handle "no relevant hits" sensibly. Cosine-similarity scores are not comparable across embedding models. Hypothesis, checked below: each model has its own baseline for unrelated text, so a single hard-coded threshold would be wrong for one of the two modes. Questions can be Hungarian while the documents are English, and cross-lingual scores are expected to run lower than same-language ones.

## Decision

- `MIN_RELEVANCE_SCORE` is configuration, set per embedding model in each `.env` sample.
- The value is calibrated: `python -m policydesk search "<question>"` prints the top scores without calling the chat model. For each embedding model I ran in-domain English, in-domain Hungarian and off-domain questions. The threshold goes below the lowest in-domain score and above the off-domain cluster. Measurements are below.
- If no chunk reaches the threshold, the API returns `200` with `outcome: "no_relevant_context"`, a fixed bilingual answer and no sources, and the chat model is not called.

## Measurements

Top-1 cosine score per question; 12 questions per group, run on 2026-11-11 with [`scripts/calibrate.py`](../../scripts/calibrate.py) (same index and search code as the API; rerun it after changing the embedding model).

| Embedding model | In-domain English | In-domain Hungarian | Off-domain (EN + HU) | Threshold |
|---|---|---|---|---|
| `bge-m3` (local) | 0.611 – 0.773 | 0.586 – 0.748 | 0.297 – 0.529 | **0.55** |
| `text-embedding-3-large` (cloud) | 0.458 – 0.722 | 0.403 – 0.685 | 0.081 – 0.375 | **0.39** |
| `text-embedding-3-small` (rejected) | 0.478 – 0.717 | 0.266 – 0.578 | 0.085 – 0.369 | none possible |

- The hypothesis held: the two models' baselines differ (off-domain maxima 0.53 vs 0.38), and cross-lingual scores run lower than same-language ones.
- `text-embedding-3-small` was the original cloud choice. Its Hungarian scores overlap the off-domain range, and for several Hungarian questions the top hit was the wrong section, so no threshold works; it was replaced by `text-embedding-3-large`.
- With `bge-m3` every in-domain question, English and Hungarian, had the correct section as its top hit.
- Both margins are thin (0.529 → 0.586 and 0.375 → 0.403). The highest off-domain scores came from questions that mention Budapest or Hungary, words that also occur in the policies.

## Alternatives

- **Always call the model and let it say "I don't know"**: costs a model call per off-topic question and relies on a small local model to refuse reliably. The prompt still tells the model to refuse, as a second line of defence for borderline hits.
- **Top-k without a threshold**: the model always gets some context, even for "What's the weather?", which invites confident nonsense.
- **Reranker score threshold**: better calibrated across queries, but adds a model. Next step if borderline questions turn out to matter.
- **Return 404 for no hits**: the request was valid and the service worked. "Nothing found" is a result, and clients shouldn't treat it as an error.

## Consequences

- Changing the embedding model means recalibrating; the README and `.env` samples say so next to the variable.
- The calibration set is small (36 questions). A larger labelled set, run in CI, is the first next step if the threshold starts to matter more.
- Borderline questions (a relevant word in an off-topic question) can pass the threshold. The prompt's refusal rule handles most of these.
