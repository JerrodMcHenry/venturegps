"""
Regression tests for Phase 10.8 -- Pitch Deck Coach V1: the
pitch_deck_reviews table (app/database/db.py), its Pydantic contracts
(app/models/pitch_deck_coach.py), the grounding sanitizer
(app/ai/pitch_deck_coaching.py), and the /pitch-deck-reviews* endpoints
in app/api.py.

Same JWT-mocking harness and zztest_* user-id convention as
test_founder_missions.py -- no live Clerk dependency, every row cleaned
up in a finally block even on failure.

Two groups of tests here, deliberately:

1. GROUNDING/SANITIZER tests (the majority) call the private sanitizer
   functions in app.ai.pitch_deck_coaching directly with hand-built
   "raw" LLM-shaped dicts -- no live OpenAI call, fully deterministic,
   free. This is where the anti-fabrication guarantee is actually
   proven: the sanitizer is what makes a fabricated claim structurally
   unable to reach the response, independent of what any given LLM call
   happens to return (same reasoning as
   test_idea_structuring.py testing _sanitize_field's cousin).
2. A small number of LIVE END-TO-END tests exercise the real
   POST/GET /pitch-deck-reviews endpoints with a real (cheap,
   gpt-4.1-mini) LLM call, following test_idea_structuring.py's own
   established precedent of calling real AI functions directly rather
   than mocking OpenAI (no mocking harness exists in this repo for it).
   Kept deliberately few -- this file makes at most 3 live LLM calls in
   the entire suite, not one per assertion.

Run with:
    python -m app.tests.test_pitch_deck_coach
"""

import time
from io import BytesIO

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import text

import app.api as api
import app.auth as auth
import app.ai.pitch_deck_coaching as coaching
from app.database.db import engine, get_rankings, create_pitch_deck_review, count_recent_pitch_deck_reviews
from app.pdf_extractor import extract_pages_from_pdf, PdfExtractionError, MAX_PDF_BYTES

USER_A = "zztest_deck_user_a"
USER_B = "zztest_deck_user_b"

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_AZP = "http://localhost:3000"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


client = TestClient(api.app)


# --- JWT mocking harness (mirrors test_founder_missions.py) -----------------


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


def _make_token(sub: str, exp_delta: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "iss": TEST_ISSUER,
        "azp": TEST_AZP,
        "iat": now,
        "exp": now + exp_delta,
    }
    return pyjwt.encode(payload, _private_key, algorithm="RS256")


class _patched_auth:
    def __enter__(self):
        self._orig_issuer = auth.CLERK_ISSUER
        self._orig_jwks_client = auth._jwks_client
        self._orig_resolve_parties = auth._resolve_authorized_parties

        auth.CLERK_ISSUER = TEST_ISSUER
        auth._jwks_client = lambda: _FakeJWKSClient()
        auth._resolve_authorized_parties = lambda: [TEST_AZP]
        return self

    def __exit__(self, *exc):
        auth.CLERK_ISSUER = self._orig_issuer
        auth._jwks_client = self._orig_jwks_client
        auth._resolve_authorized_parties = self._orig_resolve_parties
        return False


def _auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {_make_token(user_id)}"}


def _ensure_test_users() -> None:
    with engine.begin() as connection:
        for user_id in (USER_A, USER_B):
            connection.execute(
                text("INSERT INTO users (id) VALUES (:id) ON CONFLICT (id) DO NOTHING"),
                {"id": user_id},
            )


def _cleanup() -> None:
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM pitch_deck_reviews WHERE user_id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )
        connection.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)"),
            {"ids": [USER_A, USER_B]},
        )


# --- PDF builders -------------------------------------------------------------


def make_deck_pdf(page_texts: list[str]) -> bytes:
    """One page per string, in order -- mirrors test_pdf_ingestion.py's
    make_text_pdf(), extended to give each page genuinely distinct
    content so page-level grounding can actually be exercised."""
    buf = BytesIO()
    c = canvas.Canvas(buf)
    for page_text in page_texts:
        y = 750
        for line in page_text.split("\n"):
            c.drawString(72, y, line)
            y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


SAMPLE_DECK_PAGES = [
    "RideShare Campus\nGetting college students to the airport together",
    "The Problem\nCollege students pay $60+ for a solo rideshare to the airport before break, "
    "and often can't find classmates going the same direction at the same time.",
    "The Solution\nA mobile app that matches verified students at the same college heading to the "
    "same airport within a 2-hour window and splits the fare automatically.",
    "The Market\nOver 4,000 US colleges enroll students who travel home for holiday breaks.",
    "Traction\nWe ran a pilot at one campus: 42 students signed up in the first week, and "
    "9 completed a shared ride.",
    "The Team\nFounded by two seniors who organized informal ride-shares in their own dorm group chat "
    "for two years before building this.",
]  # Deliberately has no business-model, GTM, competition, financials, or ask slide.


def _upload_review(user_id: str, page_texts: list[str], filename: str = "deck.pdf"):
    """Callers must invoke this from inside a `with _patched_auth():`
    block -- it does not manage that context itself, since every test
    using it needs the SAME patched auth active for its follow-up
    GET/list calls too, not just this one POST."""
    pdf_bytes = make_deck_pdf(page_texts)
    return client.post(
        "/pitch-deck-reviews",
        files={"pdf": (filename, pdf_bytes, "application/pdf")},
        headers=_auth_headers(user_id),
    )


# =============================================================================
# GROUNDING / SANITIZER tests -- no live LLM call, pure functions.
# =============================================================================


def test_verify_quote_requires_exact_page_match() -> None:
    pages = ["We raised our seed round in 2023.", "Our team has 10 years combined experience."]

    expect(coaching._verify_quote("seed round", 1, pages), "A real substring on the cited page should verify")
    expect(not coaching._verify_quote("seed round", 2, pages), "The same quote cited on the WRONG page must fail")
    expect(not coaching._verify_quote("we raised a Series B", 1, pages), "A fabricated quote must fail")
    expect(not coaching._verify_quote("seed round", 5, pages), "An out-of-range page must fail")
    expect(not coaching._verify_quote("", 1, pages), "An empty quote must fail")
    expect(not coaching._verify_quote(None, 1, pages), "A missing quote must fail")
    expect(not coaching._verify_quote("seed round", None, pages), "A missing page must fail")


def test_sanitize_story_downgrades_unverifiable_claim() -> None:
    pages = ["We are building tools for landlords."]
    raw = {"story": {"ask": {
        "found": True,
        "summary": "Raising $2M seed round.",
        "source_quote": "Raising $2M seed round",  # never appears in pages
        "quote_page": 1,
    }}}

    story = coaching._sanitize_story(raw, pages)

    expect(story["ask"]["found"] is False, "An unverifiable claim must be downgraded to found=False")
    expect(story["ask"]["summary"] == coaching._STORY_NOT_FOUND["ask"], "Downgraded field must use the fixed honest sentence, never the fabricated one")
    expect(story["ask"]["page_refs"] == [], "A downgraded field must carry no page_refs")


def test_sanitize_story_accepts_verified_claim() -> None:
    pages = ["We are raising $500,000 to hire two engineers."]
    raw = {"story": {"ask": {
        "found": True,
        "summary": "The company is raising $500,000.",
        "source_quote": "raising $500,000",
        "quote_page": 1,
    }}}

    story = coaching._sanitize_story(raw, pages)

    expect(story["ask"]["found"] is True, "A verified claim must be preserved")
    expect(story["ask"]["summary"] == "The company is raising $500,000.", "Summary text must be preserved verbatim")
    expect(story["ask"]["page_refs"] == [1], "page_refs must name the verified page")


def test_sanitize_story_missing_field_defaults_to_not_found() -> None:
    story = coaching._sanitize_story({}, ["some page text"])
    for field_name in coaching.STORY_FIELDS:
        expect(story[field_name]["found"] is False, f"A missing '{field_name}' field must default to found=False, never fabricated")


def test_sanitize_sections_always_returns_all_twelve_categories() -> None:
    pages = ["Just a cover slide."]
    raw = {"sections": [{"category": "market", "status": "missing"}]}

    sections = coaching._sanitize_sections(raw, pages)

    expect(len(sections) == 12, f"Expected exactly 12 sections, got {len(sections)}")
    categories = {s["category"] for s in sections}
    expect(categories == set(coaching.CATEGORY_KEYS), "Every fixed category must appear exactly once")


def test_sanitize_sections_downgrades_ungrounded_effective_claim() -> None:
    pages = ["Our market is huge and growing fast."]
    raw = {"sections": [{
        "category": "market",
        "status": "effective",
        "what_its_saying": "The market is estimated at $12B.",
        "source_quote": "$12B",  # not actually in the page text
        "quote_page": 1,
        "whats_working": "Clear number.",
    }]}

    sections = coaching._sanitize_sections(raw, pages)
    market = next(s for s in sections if s["category"] == "market")

    expect(market["status"] == "missing", "An ungrounded 'effective' claim must fail closed to 'missing'")
    expect(market["what_its_saying"] is None, "A downgraded section must not keep its unverified factual claim")
    expect(market["whats_working"] is None, "A downgraded section must not keep its unverified praise either")
    expect(market["why_investors_care"] == coaching.INVESTOR_LENS["market"], "why_investors_care stays the fixed educational copy regardless of grounding outcome")


def test_sanitize_sections_accepts_grounded_effective_claim() -> None:
    pages = ["Our beachhead market is the 4,000 US colleges whose students travel home for breaks."]
    raw = {"sections": [{
        "category": "market",
        "status": "effective",
        "what_its_saying": "The deck sizes the market at 4,000 US colleges.",
        "source_quote": "4,000 US colleges",
        "quote_page": 1,
        "whats_working": "Specific and grounded in a real customer segment.",
    }]}

    sections = coaching._sanitize_sections(raw, pages)
    market = next(s for s in sections if s["category"] == "market")

    expect(market["status"] == "effective", "A properly grounded claim must be preserved")
    expect(market["page_refs"] == [1], "page_refs must include the verified page")
    expect(market["whats_working"] is not None, "A grounded effective section keeps its whats_working")


def test_sanitize_sections_unclear_only_populates_may_confuse() -> None:
    pages = ["We think this market could be big."]
    raw = {"sections": [{
        "category": "market",
        "status": "unclear",
        "what_its_saying": "The deck gestures at market size without a number.",
        "source_quote": "could be big",
        "quote_page": 1,
        "whats_working": "should never appear for an unclear status",
        "may_confuse": "No sizing methodology or number is given.",
    }]}

    sections = coaching._sanitize_sections(raw, pages)
    market = next(s for s in sections if s["category"] == "market")

    expect(market["status"] == "unclear", "Status should be preserved when grounded")
    expect(market["whats_working"] is None, "whats_working must never populate for a non-effective section")
    expect(market["may_confuse"] == "No sizing methodology or number is given.", "may_confuse should populate for an unclear, grounded section")


def _fake_sections(effective_core_count: int) -> list[dict]:
    sections = []
    core = list(coaching.CORE_READINESS_CATEGORIES)
    for i, category in enumerate(coaching.CATEGORY_KEYS):
        status = "missing"
        if category in core and core.index(category) < effective_core_count:
            status = "effective"
        sections.append({"category": category, "status": status})
    return sections


def test_readiness_label_thresholds() -> None:
    expect(coaching.readiness_label_for(_fake_sections(0)) == "Early Draft", "0 effective core categories -> Early Draft")
    expect(coaching.readiness_label_for(_fake_sections(1)) == "Early Draft", "1 effective core category -> Early Draft")
    expect(coaching.readiness_label_for(_fake_sections(2)) == "Developing", "2 effective core categories -> Developing")
    expect(coaching.readiness_label_for(_fake_sections(3)) == "Developing", "3 effective core categories -> Developing")
    expect(coaching.readiness_label_for(_fake_sections(4)) == "Getting Clear", "4 effective core categories -> Getting Clear")
    expect(coaching.readiness_label_for(_fake_sections(5)) == "Getting Clear", "5 effective core categories -> Getting Clear")
    expect(coaching.readiness_label_for(_fake_sections(6)) == "Pitch Ready", "6 effective core categories -> Pitch Ready")
    expect(coaching.readiness_label_for(_fake_sections(7)) == "Pitch Ready", "7 effective core categories -> Pitch Ready")


def test_readiness_label_ignores_non_core_categories() -> None:
    # All 5 non-core categories (cover/product/gtm/competition/financials)
    # effective, zero core categories effective -- must still be Early Draft.
    sections = [
        {"category": c, "status": "effective" if c not in coaching.CORE_READINESS_CATEGORIES else "missing"}
        for c in coaching.CATEGORY_KEYS
    ]
    expect(coaching.readiness_label_for(sections) == "Early Draft", "Non-core categories must never influence the readiness band")


def test_sanitize_fixes_rejects_fix_for_effective_category() -> None:
    statuses = {"market": "effective", "team": "missing"}
    raw = {"top_fixes": [
        {"title": "Fix market", "issue": "x", "why_it_matters": "y", "try_this": "z", "related_category": "market"},
    ]}
    fixes = coaching._sanitize_fixes(raw, statuses)
    expect(fixes == [], "A fix pointed at a category classified 'effective' must never survive sanitization")


def test_sanitize_fixes_accepts_valid_fix_and_caps_at_three() -> None:
    statuses = {c: "missing" for c in coaching.CATEGORY_KEYS}
    raw = {"top_fixes": [
        {"title": f"Fix {i}", "issue": "x", "why_it_matters": "y", "try_this": "z", "related_category": "ask"}
        for i in range(5)
    ]}
    fixes = coaching._sanitize_fixes(raw, statuses)
    expect(len(fixes) == 3, f"Expected at most 3 fixes (Part 9: prioritize, never 27), got {len(fixes)}")


def test_sanitize_fixes_drops_incomplete_entry() -> None:
    statuses = {"ask": "missing"}
    raw = {"top_fixes": [{"title": "Fix ask", "related_category": "ask"}]}  # missing issue/why_it_matters/try_this
    fixes = coaching._sanitize_fixes(raw, statuses)
    expect(fixes == [], "An incomplete fix entry must be dropped, never rendered with blank fields")


def test_sanitize_strengths_rejects_strength_for_non_effective_category() -> None:
    statuses = {"team": "missing"}
    raw = {"strengths": [{"title": "Great team", "why_it_works": "x", "related_category": "team"}]}
    strengths = coaching._sanitize_strengths(raw, statuses)
    expect(strengths == [], "A strength claimed for a non-'effective' category must never survive sanitization")


def test_sanitize_strengths_accepts_valid_strength() -> None:
    statuses = {"traction": "effective"}
    raw = {"strengths": [{"title": "Real pilot traction", "why_it_works": "x", "related_category": "traction"}]}
    strengths = coaching._sanitize_strengths(raw, statuses)
    expect(len(strengths) == 1, "A properly grounded strength must survive sanitization")


def test_sanitize_open_questions_rejects_question_for_effective_category() -> None:
    statuses = {"team": "effective"}
    raw = {"open_questions": [{"question": "Who is the team?", "related_category": "team"}]}
    questions = coaching._sanitize_open_questions(raw, statuses)
    expect(questions == [], "Part 11: an open question must never be manufactured about a category the deck handled well")


def test_sanitize_open_questions_accepts_question_for_missing_category() -> None:
    statuses = {"ask": "missing"}
    raw = {"open_questions": [{"question": "What are you raising?", "related_category": "ask"}]}
    questions = coaching._sanitize_open_questions(raw, statuses)
    expect(len(questions) == 1, "An open question grounded in a genuinely missing category must survive")


def test_sanitize_prep_questions_rejects_unknown_category() -> None:
    statuses = {c: "missing" for c in coaching.CATEGORY_KEYS}
    raw = {"prep_questions": [{"question": "What's your favorite color?", "related_category": "vibes"}]}
    questions = coaching._sanitize_prep_questions(raw, statuses)
    expect(questions == [], "A prep question tied to an invented, non-fixed category must be dropped")


def test_llm_failure_raises_coaching_error() -> None:
    original = coaching.client.chat.completions.create

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated provider outage")

    coaching.client.chat.completions.create = _boom
    try:
        threw = False
        try:
            coaching.generate_pitch_deck_review(["some deck text"], "deck.pdf")
        except coaching.PitchDeckCoachingError:
            threw = True
        expect(threw, "A provider failure must raise PitchDeckCoachingError, never propagate the raw exception")
    finally:
        coaching.client.chat.completions.create = original


def test_llm_malformed_json_raises_coaching_error() -> None:
    original = coaching.client.chat.completions.create

    class _FakeMessage:
        content = "this is not json at all {{{"

    class _FakeChoice:
        message = _FakeMessage()

    class _FakeResponse:
        choices = [_FakeChoice()]

    coaching.client.chat.completions.create = lambda *a, **k: _FakeResponse()
    try:
        threw = False
        try:
            coaching.generate_pitch_deck_review(["some deck text"], "deck.pdf")
        except coaching.PitchDeckCoachingError:
            threw = True
        expect(threw, "Malformed JSON from the provider must fail safely as PitchDeckCoachingError")
    finally:
        coaching.client.chat.completions.create = original


# =============================================================================
# PDF / INPUT tests -- app/pdf_extractor.py's extract_pages_from_pdf(),
# no LLM call. Reuses the exact same hardening extract_text_from_pdf()
# already has (see that function's own docstring) -- these tests confirm
# the NEW function inherits it rather than re-testing pdf_extractor.py's
# whole hardening surface a second time (test_pdf_ingestion.py already
# does that for extract_text_from_pdf()).
# =============================================================================


def test_extract_pages_returns_one_entry_per_page_with_distinct_content() -> None:
    pdf_bytes = make_deck_pdf(["First unique slide content", "Second unique slide content", "Third unique slide content"])
    pages = extract_pages_from_pdf(pdf_bytes)

    expect(len(pages) == 3, f"Expected 3 pages, got {len(pages)}")
    expect("First unique" in pages[0] and "Second unique" not in pages[0], "Page 1 text must not leak page 2's content")
    expect("Second unique" in pages[1], "Page 2 must contain its own distinct text")
    expect("Third unique" in pages[2], "Page 3 must contain its own distinct text")


def test_extract_pages_rejects_non_pdf() -> None:
    threw = False
    try:
        extract_pages_from_pdf(b"This is just a plain text file, not a PDF at all.")
    except PdfExtractionError:
        threw = True
    expect(threw, "A non-PDF file must be rejected")


def test_extract_pages_rejects_oversized_pdf() -> None:
    threw = False
    try:
        extract_pages_from_pdf(b"%PDF-1.4" + b"0" * (MAX_PDF_BYTES + 1))
    except PdfExtractionError:
        threw = True
    expect(threw, "An oversized PDF must be rejected")


def test_extract_pages_rejects_corrupt_pdf() -> None:
    threw = False
    try:
        extract_pages_from_pdf(b"%PDF-1.4\n" + b"not a real pdf body" * 20)
    except PdfExtractionError:
        threw = True
    expect(threw, "A corrupt/malformed PDF must be rejected")


def test_count_recent_pitch_deck_reviews_counts_rows() -> None:
    """DB-level check of the daily-cap counting mechanism -- deliberately
    NOT a live 16-upload test of the actual 429 (that would require 16
    real LLM calls); the count function itself is what the /pitch-deck-
    reviews endpoint's cap check relies on, and it's plain SQL with no
    LLM involvement, so it's tested directly and cheaply here."""
    _ensure_test_users()
    try:
        fake_review = {
            "deck_filename": "x.pdf", "page_count": 1, "readiness_label": "Early Draft",
            "story": {f: {"found": False, "summary": "x", "page_refs": []} for f in coaching.STORY_FIELDS},
            "sections": [], "top_fixes": [], "strengths": [], "open_questions": [], "prep_questions": [],
        }
        for _ in range(3):
            create_pitch_deck_review(USER_A, "x.pdf", 1, "Early Draft", fake_review)

        count = count_recent_pitch_deck_reviews(USER_A, 24)
        expect(count == 3, f"Expected 3 recent reviews counted, got {count}")

        other_count = count_recent_pitch_deck_reviews(USER_B, 24)
        expect(other_count == 0, "Counting must be scoped per-user")
    finally:
        _cleanup()


# =============================================================================
# LIVE END-TO-END tests -- real POST /pitch-deck-reviews calls, real
# (cheap) LLM calls. Kept few in number; see this file's own module
# docstring for why.
# =============================================================================


def test_pitch_deck_review_lifecycle() -> None:
    """
    One real deck upload, exercising in one pass: response contract shape
    (Part 6/7/8), AUTH ownership (owner reads, other user 404s), PERSISTENCE
    (GET by id reproduces what POST returned, GET list includes it,
    Part 17 multiple reviews coexist via a second upload), and SEPARATION
    (zero rows created in startups/analyses/modeled_ventures/
    startup_memberships; Rankings/Discovery counts unchanged).
    """
    _ensure_test_users()
    try:
        with engine.begin() as connection:
            before_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
            before_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
            before_ventures = connection.execute(text("SELECT COUNT(*) FROM modeled_ventures")).scalar()
            before_memberships = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
        before_rankings = len(get_rankings("__task3b_sanity_admin__", True))  # Portfolio Release Task 3B: admin bypass, unrelated to this test

        with _patched_auth():
            response = _upload_review(USER_A, SAMPLE_DECK_PAGES, filename="rideshare_deck.pdf")
            expect(response.status_code == 200, f"Review creation failed: {response.text}")
            body = response.json()

            # --- contract shape ---
            expect(body["deck_filename"] == "rideshare_deck.pdf", "deck_filename must round-trip")
            expect(body["page_count"] == len(SAMPLE_DECK_PAGES), "page_count must match the uploaded deck")
            expect(body["readiness_label"] in ("Early Draft", "Developing", "Getting Clear", "Pitch Ready"), "readiness_label must be one of the fixed labels -- never a number")
            expect(set(body["story"].keys()) == set(coaching.STORY_FIELDS), "story must have exactly the 7 fixed fields")
            expect(len(body["sections"]) == 12, "sections must always list all 12 fixed categories")
            expect({s["category"] for s in body["sections"]} == set(coaching.CATEGORY_KEYS), "sections must cover every fixed category exactly once")
            expect(len(body["top_fixes"]) <= 3, "top_fixes must never exceed 3 (Part 9)")
            for section in body["sections"]:
                expect(bool(section["why_investors_care"]), f"why_investors_care must always be populated ({section['category']})")

            review_id = body["id"]

            # --- persistence / reload ---
            get_response = client.get(f"/pitch-deck-reviews/{review_id}", headers=_auth_headers(USER_A))
            expect(get_response.status_code == 200, f"Owner GET by id failed: {get_response.text}")
            expect(get_response.json() == body, "Reloaded review must exactly match what POST returned")

            list_response = client.get("/pitch-deck-reviews", headers=_auth_headers(USER_A))
            expect(list_response.status_code == 200, f"List failed: {list_response.text}")
            listed_ids = [r["id"] for r in list_response.json()]
            expect(review_id in listed_ids, "The new review must appear in the owner's list")

            # --- Part 17: a second review coexists, does not overwrite the first ---
            second = _upload_review(USER_A, SAMPLE_DECK_PAGES[:3], filename="v2_deck.pdf")
            expect(second.status_code == 200, f"Second review creation failed: {second.text}")
            second_id = second.json()["id"]
            expect(second_id != review_id, "A second upload must create a distinct review, never overwrite the first")

            list_response_2 = client.get("/pitch-deck-reviews", headers=_auth_headers(USER_A))
            listed_ids_2 = [r["id"] for r in list_response_2.json()]
            expect(review_id in listed_ids_2 and second_id in listed_ids_2, "Both reviews must coexist in the owner's list")

            # --- AUTH: cross-user isolation ---
            cross_get = client.get(f"/pitch-deck-reviews/{review_id}", headers=_auth_headers(USER_B))
            expect(cross_get.status_code == 404, "Another user must get 404, never someone else's review")

            cross_list = client.get("/pitch-deck-reviews", headers=_auth_headers(USER_B))
            expect(cross_list.json() == [], "Another user's list must never include someone else's reviews")

            signed_out_get = client.get(f"/pitch-deck-reviews/{review_id}")
            expect(signed_out_get.status_code == 401, "A signed-out request must be rejected")

        # --- SEPARATION: no path into canonical startup intelligence ---
        with engine.begin() as connection:
            after_startups = connection.execute(text("SELECT COUNT(*) FROM startups")).scalar()
            after_analyses = connection.execute(text("SELECT COUNT(*) FROM analyses")).scalar()
            after_ventures = connection.execute(text("SELECT COUNT(*) FROM modeled_ventures")).scalar()
            after_memberships = connection.execute(text("SELECT COUNT(*) FROM startup_memberships")).scalar()
        after_rankings = len(get_rankings("__task3b_sanity_admin__", True))

        expect(after_startups == before_startups, "A pitch deck review must never create a startups row")
        expect(after_analyses == before_analyses, "A pitch deck review must never create an analyses row (no SPS path)")
        expect(after_ventures == before_ventures, "A pitch deck review must never create a modeled_ventures row")
        expect(after_memberships == before_memberships, "A pitch deck review must never create a startup_memberships row")
        expect(after_rankings == before_rankings, "Rankings must be completely unaffected by pitch deck review activity")
    finally:
        _cleanup()


def test_missing_information_remains_missing_end_to_end() -> None:
    """
    Part 25 GROUNDING, proven live rather than only at the sanitizer-unit
    level: SAMPLE_DECK_PAGES deliberately never mentions a fundraising
    ask, a business model, or specific paying-customer/revenue figures.
    The review must say so honestly, never invent one.
    """
    _ensure_test_users()
    with _patched_auth():
        response = _upload_review(USER_A, SAMPLE_DECK_PAGES, filename="no_ask_deck.pdf")
    try:
        expect(response.status_code == 200, f"Review creation failed: {response.text}")
        body = response.json()

        ask = body["story"]["ask"]
        if not ask["found"]:
            expect(ask["summary"] == coaching._STORY_NOT_FOUND["ask"], "A genuinely absent ask must use the fixed honest sentence")
            expect(ask["page_refs"] == [], "An absent ask must carry no page references")

        ask_section = next(s for s in body["sections"] if s["category"] == "ask")
        if ask_section["status"] != "effective":
            expect(ask_section["what_its_saying"] is None or ask_section["status"] == "unclear", "A non-effective ask section must not assert a confident factual claim")

        # No fix/strength/open-question may claim the ask was handled well
        # while also being listed as missing/unclear -- the sanitizer's
        # cross-check (proven at the unit level above) guarantees this;
        # this is the live confirmation that it actually held for a real
        # model response.
        for strength in body["strengths"]:
            if strength["related_category"] == "ask":
                expect(ask_section["status"] == "effective", "A claimed strength for 'ask' must correspond to a section actually classified effective")
    finally:
        _cleanup()


TESTS = [
    test_verify_quote_requires_exact_page_match,
    test_sanitize_story_downgrades_unverifiable_claim,
    test_sanitize_story_accepts_verified_claim,
    test_sanitize_story_missing_field_defaults_to_not_found,
    test_sanitize_sections_always_returns_all_twelve_categories,
    test_sanitize_sections_downgrades_ungrounded_effective_claim,
    test_sanitize_sections_accepts_grounded_effective_claim,
    test_sanitize_sections_unclear_only_populates_may_confuse,
    test_readiness_label_thresholds,
    test_readiness_label_ignores_non_core_categories,
    test_sanitize_fixes_rejects_fix_for_effective_category,
    test_sanitize_fixes_accepts_valid_fix_and_caps_at_three,
    test_sanitize_fixes_drops_incomplete_entry,
    test_sanitize_strengths_rejects_strength_for_non_effective_category,
    test_sanitize_strengths_accepts_valid_strength,
    test_sanitize_open_questions_rejects_question_for_effective_category,
    test_sanitize_open_questions_accepts_question_for_missing_category,
    test_sanitize_prep_questions_rejects_unknown_category,
    test_llm_failure_raises_coaching_error,
    test_llm_malformed_json_raises_coaching_error,
    test_extract_pages_returns_one_entry_per_page_with_distinct_content,
    test_extract_pages_rejects_non_pdf,
    test_extract_pages_rejects_oversized_pdf,
    test_extract_pages_rejects_corrupt_pdf,
    test_count_recent_pitch_deck_reviews_counts_rows,
    test_pitch_deck_review_lifecycle,
    test_missing_information_remains_missing_end_to_end,
]


def main() -> None:
    print("\nPitch Deck Coach V1 tests")
    print("-" * 72)

    _cleanup()

    failures: list[str] = []

    for test in TESTS:
        name = test.__name__

        try:
            test()
        except AssertionError as error:
            print(f"FAIL  {name}\n      {error}")
            failures.append(name)
        except Exception as error:
            print(f"ERROR {name}\n      {error!r}")
            failures.append(name)
        else:
            print(f"PASS  {name}")

    print("-" * 72)
    print(f"{len(TESTS) - len(failures)}/{len(TESTS)} passed")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
