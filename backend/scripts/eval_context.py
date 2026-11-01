#!/usr/bin/env python3
"""
Score what reaches the model for each question in eval/context_questions.yaml.

Builds the real chat prompt (ChatService._build_prompt: search plan, recent
notes, notes from a period, search fragments) and checks it holds the notes
each question needs. With --answers it also asks the model and checks that
every quote in the answer appears word for word in the notes it was given,
and that every [[citation]] names a note that was in the prompt.

    python3 scripts/eval_context.py
    python3 scripts/eval_context.py --answers
    python3 scripts/eval_context.py -v     # list every question's notes

Reads SUPABASE_URL, SUPABASE_KEY and OPENAI_API_KEY from backend/.env and the
user from EVAL_USER_ID. Costs a planner call per dated or follow-up question,
plus one answer per question with --answers.
"""
import argparse
import asyncio
import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parent.parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / 'scripts'))

import yaml  # noqa: E402
from supabase import create_client  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.chat_service import ChatService  # noqa: E402
from app.services.search_service import SearchService  # noqa: E402
from app.services.settings_service import SettingsService  # noqa: E402
from backfill_missing_notes import name_key, name_keys  # noqa: E402

logging.basicConfig(level=logging.WARNING)

QUESTIONS_FILE = BACKEND_DIR / 'eval' / 'context_questions.yaml'
# The period questions' expected ranges are written against this day.
TODAY = date(2026, 11, 1)
# Quotes shorter than this are phrases, not lines from a note.
MIN_QUOTE_WORDS = 5


def _norm(text: str) -> str:
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    text = re.sub(r'\^[\w-]{6,}', '', text)  # Roam block ids
    # Compare letters and digits only: answers re-punctuate quotes (curly vs
    # straight quotes, a dropped "!!!", a trailing comma) without changing a word.
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def check_answer(answer: str, prompt: str, prompt_titles: set) -> tuple:
    """
    (quotes found in the notes, quotes checked, [[name.md]] citations not in
    the prompt, the quotes not found). A bare [[link]] is not a citation: it is
    a Roam link the answer copied from a note's own text.
    """
    notes = _norm(prompt)
    quotes = [q for q in re.findall(r'["“]([^"“”]{10,400})["”]', answer)
              if len(q.split()) >= MIN_QUOTE_WORDS]
    # A quote may drop words with an ellipsis or [brackets]; each piece must still be verbatim.
    missing = [q for q in quotes
               if not all(_norm(piece) in notes
                          for piece in re.split(r'\s*(?:\.\.\.|…|\[[^\]]*\])\s*', q) if piece.strip())]
    bad_citations = [c for c in re.findall(r'\[\[([^\]]+\.md)\]\]', answer) if name_key(c) not in prompt_titles]
    return len(quotes) - len(missing), len(quotes), bad_citations, missing


async def run(user_id: UUID, questions: list, answers: bool, verbose: bool):
    settings = get_settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    search = SearchService(supabase)
    chat = ChatService(supabase, search, None, SettingsService(supabase))

    passed = 0
    coverage = []
    quotes_ok = quotes_total = 0
    bad_citations_total = 0
    latencies = []

    for q in questions:
        start = time.perf_counter()
        prompt = await chat._build_prompt(q['question'], q.get('history') or [], user_id, today=TODAY)
        latencies.append(time.perf_counter() - start)
        in_prompt = {name_key(t) for t in prompt.recent_titles + prompt.range_titles + prompt.fragment_titles}
        plan = prompt.plan

        if q['kind'] == 'theme':
            found = [t for t in q['expect'] if name_keys(t) & in_prompt]
            ok = len(found) >= q.get('need', 1)
            detail = f"{len(found)}/{len(q['expect'])} expected notes (need {q.get('need', 1)})"
        elif q['kind'] == 'period':
            want = tuple(date.fromisoformat(str(d)) for d in q['range'])
            got = (plan.date_start, plan.date_end)
            notes, total = await search.get_notes_in_range(user_id, *want, token_budget=10**9)
            share = sum(1 for n in notes if name_key(n.title) in in_prompt) / max(total, 1)
            coverage.append(share)
            ok = got == want and share > 0
            detail = f"range {got[0]}..{got[1]} (want {want[0]}..{want[1]}), {share:.0%} of {total} notes in prompt"
        else:
            ok = plan.date_start is None
            detail = f"range {plan.date_start}..{plan.date_end}"
        passed += ok

        line = f"  {'ok  ' if ok else 'FAIL'} {q['question'][:58]:58} {detail}"
        if answers:
            response = await chat.openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "system", "content": prompt.system_content}, *(q.get('history') or []),
                          {"role": "user", "content": q['question']}],
                max_completion_tokens=4000,
            )
            answer = response.choices[0].message.content or ''
            found_quotes, n_quotes, bad, missing = check_answer(answer, prompt.system_content, in_prompt)
            quotes_ok += found_quotes
            quotes_total += n_quotes
            bad_citations_total += len(bad)
            line += f" | quotes {found_quotes}/{n_quotes} verbatim" + (f", unknown citations {bad}" if bad else "")
            if verbose:
                line += "".join(f"\n      not in notes: {m!r}" for m in missing)
        print(line)
        if verbose:
            print(f"      plan: {plan}")
            print(f"      notes from period: {prompt.range_titles[:12]}")
            print(f"      fragments: {prompt.fragment_titles[:12]}")

    n = len(questions)
    latencies.sort()
    summary = f"passed {passed}/{n}"
    if coverage:
        summary += f"  period coverage {sum(coverage) / len(coverage):.0%}"
    if answers:
        summary += f"  quotes verbatim {quotes_ok}/{quotes_total}  unknown citations {bad_citations_total}"
    summary += f"  context build p50 {latencies[n // 2]:.1f}s  max {latencies[-1]:.1f}s"
    print(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--answers', action='store_true', help='also generate answers and check their quotes')
    parser.add_argument('-v', '--verbose', action='store_true', help='print plans, notes and answers')
    args = parser.parse_args()

    user_id = os.environ.get('EVAL_USER_ID')
    if not user_id:
        sys.exit("Set EVAL_USER_ID to your Supabase user UUID")

    questions = yaml.safe_load(QUESTIONS_FILE.read_text())
    asyncio.run(run(UUID(user_id), questions, args.answers, args.verbose))


if __name__ == '__main__':
    main()
