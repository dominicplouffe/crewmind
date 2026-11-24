"""The memory eval suite (MEM-8): Nightsquad measures its own recall.

A scripted project history is stored in the real engine (Mem0, the local embedding model,
and the store for the database under test). Each question is worded differently from the
fact that answers it. The score is how often that fact is among the top results. A score
below the recorded baseline fails the build. Pinned memory has its own, exact check
(`test_INV_25_...`), which must always be 100%.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsquad.domain.memory.engine import Mem0Engine, shipped_model_directory

SCOPE = "project:eval"
TOP = 3

HISTORY = [
    "The launch event is booked for 4 May at the Palais des Congres in Montreal.",
    "The venue holds 300 people; fire rules cap standing guests at 350.",
    "The chairman wants every summary as a table, not as paragraphs.",
    "Never quote prices with taxes included; show taxes on a separate line.",
    "The caterer is Maison Verte and needs final numbers ten days ahead.",
    "The printing supplier ships from Lisbon every Monday and takes six working days.",
    "Our annual revenue target is four million euros.",
    "The marketing budget for the launch is capped at 80,000 euros.",
    "Sophie Tremblay signs all contracts above 10,000 euros.",
    "The website is built with Astro and deployed on Cloudflare Pages.",
    "Customer interviews showed most buyers are clinics with fewer than ten staff.",
    "The first pricing experiment failed: a free tier attracted students, not clinics.",
    "Support tickets are answered within one working day, in French and English.",
    "The data protection review found no personal data leaves Canada.",
    "The mobile app is postponed until after the autumn release.",
    "Invoices are sent on the first of each month through Stripe.",
    "The logo must always sit on a white background with clear space around it.",
    "The competitor Clinova raised its prices by 15% in March.",
    "Weekly status reports are due on Fridays before noon.",
    "The pilot with Clinique du Parc ended with a signed two-year contract.",
    "Backups run nightly and are kept for ninety days.",
    "The onboarding flow lost 40% of users at the email verification step.",
    "The team agreed to stop using the old CRM at the end of June.",
    "Translations into Spanish are planned for next year, not this one.",
]

QUESTIONS = [
    ("When and where does the launch take place?", 0),
    ("How many guests fit in the room?", 1),
    ("In what format does the chairman like summaries?", 2),
    ("Should taxes be part of the quoted price?", 3),
    ("Who provides the food and what is their deadline?", 4),
    ("How long does printed material take to arrive?", 5),
    ("What sales goal do we have for the year?", 6),
    ("How much may we spend on promoting the launch?", 7),
    ("Who has to approve a large contract?", 8),
    ("What technology runs the site?", 9),
    ("What kind of customer buys from us?", 10),
    ("What did we learn from offering a free plan?", 11),
    ("How fast do we reply to customers who need help?", 12),
    ("Does any private information get stored abroad?", 13),
    ("Is the phone application still planned for this release?", 14),
    ("How and when do we bill customers?", 15),
    ("What are the rules for showing the brand mark?", 16),
    ("What did the rival company do with its pricing?", 17),
    ("When must the weekly update be handed in?", 18),
    ("How did the trial with the clinic end?", 19),
    ("For how long are copies of the data retained?", 20),
    ("Where do new users drop out when signing up?", 21),
    ("When do we retire the previous customer database tool?", 22),
    ("Are we offering the product in Spanish this year?", 23),
]

# Measured on 21 Nov 2026: 24 of 24 with embedded Qdrant, 23 of 24 with pgvector. The
# baselines sit one question below, because ONNX results can differ slightly by processor.
BASELINE_SQLITE = 23
BASELINE_POSTGRES = 22


async def test_MEM_8_recall_accuracy_meets_the_recorded_baseline(
    tmp_path: Path, migrated_url: str, request: pytest.FixtureRequest
) -> None:
    """MEM-8, MEM-2, MEM-5: the fact that answers each question is among the top results at
    least as often as the recorded baseline, on the store for this database. A regression
    fails the build."""
    if not any(shipped_model_directory().glob("models--*")):
        pytest.skip(
            "the embedding model is not on disk: run "
            "`uv run python -m nightsquad.domain.memory.fetch_model` first"
        )
    engine = Mem0Engine(tmp_path / "data", migrated_url)
    ids = [await engine.add(SCOPE, fact, {"source": "eval"}) for fact in HISTORY]
    try:
        hits = 0
        missed: list[str] = []
        for question, answer in QUESTIONS:
            found = await engine.search([SCOPE], question, TOP)
            if ids[answer] in [row.id for row in found]:
                hits += 1
            else:
                missed.append(question)
    finally:
        await engine.forget_scope(SCOPE)
    sqlite = request.config.getoption("--db") == "sqlite"
    baseline = BASELINE_SQLITE if sqlite else BASELINE_POSTGRES
    print(f"recall@{TOP}: {hits}/{len(QUESTIONS)}; missed: {missed}")
    assert hits >= baseline, f"recall@{TOP} fell to {hits}/{len(QUESTIONS)}; missed: {missed}"
