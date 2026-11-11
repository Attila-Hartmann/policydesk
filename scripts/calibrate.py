"""Relevance-threshold calibration (docs/adr/004-relevance-threshold.md).

Embeds 12 in-domain English, 12 in-domain Hungarian and 12 off-domain questions with the configured embedding model,
and prints each question's top-1 score and chunk plus the min/max per group. Pick MIN_RELEVANCE_SCORE between the
lowest in-domain score and the highest off-domain score. Needs a built index (`python -m policydesk ingest`).

    uv run python scripts/calibrate.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policydesk.config import load_settings
from policydesk.providers import OpenAICompatibleEmbedder, make_client
from policydesk.store import VectorIndex

GROUPS = {
    "in-domain EN": [
        "How much is the daily meal allowance in Vienna?",
        "Can I fly business class to New York?",
        "How many days of annual leave do I get?",
        "What is the hotel limit in London?",
        "How long do I have to submit my expenses?",
        "How many days can I work from abroad?",
        "What is the gift limit from clients?",
        "Who do I report a data breach to and how fast?",
        "What should I do if my laptop is stolen?",
        "How much is the home office allowance?",
        "Does the firm pay for my Azure certification exam?",
        "How long is the probation period?",
    ],
    "in-domain HU": [
        "Mennyi a napi ellátmány Bécsben?",
        "Repülhetek business osztályon New Yorkba?",
        "Hány nap szabadság jár egy évben?",
        "Mennyi a szállás felső határa Londonban?",
        "Meddig kell leadnom a költségelszámolást?",
        "Hány napot dolgozhatok külföldről?",
        "Mekkora értékű ajándékot fogadhatok el ügyféltől?",
        "Kinek és milyen gyorsan kell jelentenem egy adatvédelmi incidenst?",
        "Mit tegyek, ha ellopták a laptopomat?",
        "Mennyi az otthoni munkavégzési támogatás?",
        "Kifizeti a cég az Azure vizsgámat?",
        "Milyen hosszú a próbaidő?",
    ],
    "off-domain": [
        "Who won the football World Cup in 2022?",
        "What is the capital of Australia?",
        "How do I bake sourdough bread?",
        "What is the weather tomorrow in Budapest?",
        "Explain quantum entanglement.",
        "Write a poem about cats.",
        "Mi Magyarország fővárosa?",
        "Hogyan kell rántott húst készíteni?",
        "What is the stock price of Microsoft?",
        "Recommend a good movie for tonight.",
        "Ki nyerte a 2022-es foci-vb-t?",
        "How do I change a car tyre?",
    ],
}


async def main() -> None:
    settings = load_settings()
    index = VectorIndex.load(settings.index_path, settings.embedding_model)
    client = make_client(settings)
    try:
        questions = [q for group in GROUPS.values() for q in group]
        vectors = await OpenAICompatibleEmbedder(client, settings.embedding_model).embed(questions)
    finally:
        await client.close()
    print(f"embedding model: {settings.embedding_model}")
    by_question = dict(zip(questions, vectors, strict=True))
    for name, group in GROUPS.items():
        scores = []
        for question in group:
            top = index.search(by_question[question], top_k=1, min_score=-1.0)[0]
            scores.append(top.score)
            print(f"{name:13} {top.score:.3f}  {top.chunk.id:30} {question}")
        print(f"{name:13} min={min(scores):.3f} max={max(scores):.3f}\n")


if __name__ == "__main__":
    asyncio.run(main())
