#!/usr/bin/env python3
"""
Score note retrieval against eval/retrieval_questions.yaml.

For each question, checks where the expected note lands in the ranked results:
hit@5, hit@10, MRR (mean reciprocal rank), plus search latency. Run it before
and after any change to chunking, embeddings or ranking, so "better" is a
number instead of a feeling.

    python3 scripts/eval_retrieval.py --mode both     # legacy scan vs pgvector
    python3 scripts/eval_retrieval.py --mode vector -v

Reads SUPABASE_URL, SUPABASE_KEY and OPENAI_API_KEY from backend/.env, and the
user to search as from EVAL_USER_ID (your Supabase user UUID).
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

import yaml  # noqa: E402
from supabase import create_client  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.models.search import SearchQuery  # noqa: E402
from app.services.search_helper import extract_keywords  # noqa: E402
from app.services.search_service import SearchService, _group_chunks_by_document  # noqa: E402

logging.basicConfig(level=logging.WARNING)

QUESTIONS_FILE = BACKEND_DIR / 'eval' / 'retrieval_questions.yaml'


async def ranked_titles(service: SearchService, query: SearchQuery, mode: str):
    if mode == 'vector':
        chunks = await service._vector_search_chunks(query)
    else:
        chunks = await asyncio.to_thread(service._legacy_scan_chunks, query)
    results = _group_chunks_by_document(chunks, extract_keywords(query.query))
    return [r.title for r in sorted(results, key=lambda r: r.score, reverse=True)]


async def run(mode: str, user_id: str, questions, verbose: bool):
    settings = get_settings()
    service = SearchService(create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY))
    hits5 = hits10 = 0
    rr_total = 0.0
    latencies = []

    for q in questions:
        start = time.perf_counter()
        titles = await ranked_titles(service, SearchQuery(query=q['question'], user_id=user_id), mode)
        latencies.append(time.perf_counter() - start)

        expected = set(q['expect'])
        rank = next((i + 1 for i, t in enumerate(titles) if t in expected), None)
        hits5 += bool(rank and rank <= 5)
        hits10 += bool(rank and rank <= 10)
        rr_total += 1 / rank if rank else 0

        if verbose or not rank or rank > 5:
            print(f"  [{mode}] rank {rank or '-':>3}  {q['question']}")
            if verbose:
                print(f"         top 3: {titles[:3]}")

    n = len(questions)
    latencies.sort()
    print(
        f"{mode:>6}: hit@5 {hits5}/{n}  hit@10 {hits10}/{n}  MRR {rr_total / n:.3f}  "
        f"latency p50 {latencies[n // 2]:.2f}s  max {latencies[-1]:.2f}s"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--mode', choices=['vector', 'legacy', 'both'], default='vector')
    parser.add_argument('-v', '--verbose', action='store_true', help='print every question and its top results')
    args = parser.parse_args()

    user_id = os.environ.get('EVAL_USER_ID')
    if not user_id:
        sys.exit("Set EVAL_USER_ID to your Supabase user UUID")

    questions = yaml.safe_load(QUESTIONS_FILE.read_text())
    modes = ['legacy', 'vector'] if args.mode == 'both' else [args.mode]
    for mode in modes:
        asyncio.run(run(mode, user_id, questions, args.verbose))


if __name__ == '__main__':
    main()
