#!/usr/bin/env python3
"""
Viraya Interview Studio - Standalone Interview Rescoring Utility
================================================================
This script re-evaluates and updates ONLY the numerical scores of existing
interview reports in MongoDB using OpenAI, without modifying any transcripts,
rationales, quotes, summaries, strengths, or recommendations.

Usage:
    python rescore_interviews.py [--dry-run] [--input reports.txt] [--limit N]

Options:
    --dry-run     Calculate and preview new scores without writing to MongoDB.
    --input       Path to text file containing interview URLs or IDs (default: reports.txt).
    --limit       Maximum number of interviews to process (default: all).
    --delay       Delay in seconds between OpenAI API calls (default: 1.0).
    --mongo-uri   Explicit MongoDB URI (defaults to MONGO_URI in .env).
    --openai-key  Explicit OpenAI API Key (defaults to OPENAI_API_KEY in .env).
    --model       OpenAI model to use (default: gpt-4o-mini).
"""

import os
import sys
import re
import json
import time
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

import requests
from pymongo import MongoClient

# Attempt to load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def extract_interview_ids(filepath: str) -> List[str]:
    """Extract 32-character hexadecimal interview IDs from URL list or raw IDs."""
    if not os.path.exists(filepath):
        print(f"[Error] File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    ids = []
    seen = set()
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Match 32-character hex ID (e.g. /reports/<id> or bare <id>)
            match = re.search(r"([a-f0-9]{32})", line, re.IGNORECASE)
            if match:
                clean_id = match.group(1).lower()
                if clean_id not in seen:
                    seen.add(clean_id)
                    ids.append(clean_id)
    return ids


def format_transcript_text(transcript: List[Dict[str, Any]], max_chars: int = 14000) -> Tuple[str, int, int]:
    """
    Format transcript turns into readable conversation text.
    Returns (formatted_text, candidate_turns_count, candidate_words_count).
    """
    lines = []
    candidate_turns = 0
    candidate_words = 0

    for turn in transcript:
        if not isinstance(turn, dict):
            continue
        raw_role = (turn.get("role") or "").lower()
        message = (turn.get("message") or turn.get("text") or "").strip()
        if not message:
            continue

        if raw_role in ("candidate", "user"):
            speaker = "Candidate"
            candidate_turns += 1
            candidate_words += len(message.split())
        else:
            speaker = "Interviewer"

        lines.append(f"{speaker}: {message}")

    full_text = "\n".join(lines)
    if len(full_text) > max_chars:
        # Keep opening and most recent exchanges if transcript is extremely long
        half = max_chars // 2
        full_text = full_text[:half] + "\n... [transcript truncated for context length] ...\n" + full_text[-half:]

    return full_text, candidate_turns, candidate_words


def request_openai_scores(
    candidate_name: str,
    job_title: str,
    jd_text: str,
    resume_text: str,
    transcript_text: str,
    existing_rationales: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    max_retries: int = 3
) -> Dict[str, int]:
    """
    Call OpenAI API to evaluate objective competency scores (0-100) based strictly on transcript evidence.
    Uses requests directly to prevent any Windows httpx2 brotli decompressor bugs.
    """
    system_prompt = (
        "You are a rigorous, impartial technical talent evaluation director for Viraya Company. "
        "Your task is to independently calculate authentic numerical scores (0 to 100) for the candidate's "
        "interview performance based strictly on what they ACTUALLY answered in the spoken transcript."
    )

    user_prompt = f"""EVALUATION CONTEXT:
- Candidate Name: {candidate_name}
- Target Position: {job_title} at Viraya Company

TARGET JOB REQUIREMENTS (JD):
{jd_text[:3500]}

CANDIDATE RESUME SUMMARY:
{resume_text[:2500]}

SPOKEN INTERVIEW TRANSCRIPT:
{transcript_text}

EXISTING EVALUATION OBSERVATIONS & RATIONALES:
{existing_rationales[:1500]}

SCORING METHODOLOGY & CRITICAL INSTRUCTIONS:
1. Every candidate MUST be scored independently based on the substance, accuracy, and technical depth demonstrated in the transcript.
2. DO NOT return 77 or uniform scores. Differentiate authentic candidate performance across the entire 0-100 spectrum:
   * 25 - 55 (Significant Gap / Minimal): Candidate gave evasive, extremely brief, 1-word/1-line answers, or faltered on core concepts.
   * 56 - 69 (Developing / Basic): Basic conceptual familiarity, but answers lacked implementation depth or relied on broad generalities.
   * 70 - 84 (Proficient / Solid Hire): Clear, relevant answers with concrete technical examples and demonstrated hands-on experience.
   * 85 - 98 (Exceptional / Authoritative): Deep mastery, authoritative architecture breakdowns, quantified engineering impact, and proactive trade-off analysis.
3. Score each of the five standard performance dimensions independently (integers 0 to 100):
   - domain_mastery (Weight 30%): Deep technical grasp of LLMs, Python, prompt engineering, AI developer tooling, full-stack concepts.
   - problem_solving (Weight 25%): Practical reasoning through situational dilemmas, debugging, edge cases, trade-offs.
   - execution_impact (Weight 20%): Tangible hands-on contributions, specific personal project ownership rather than vague team claims.
   - communication_clarity (Weight 15%): Clarity, conciseness, structured articulation, avoidance of stalling/filler.
   - role_calibration (Weight 10%): Direct alignment with the AI developer requirements at Viraya Company.

Return ONLY a valid JSON object matching this exact schema:
{{
  "domain_mastery_score": <int 0-100>,
  "problem_solving_score": <int 0-100>,
  "execution_impact_score": <int 0-100>,
  "communication_clarity_score": <int 0-100>,
  "role_calibration_score": <int 0-100>
}}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }

    endpoint = "https://api.openai.com/v1/chat/completions"

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            if resp.ok:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return {
                    "domain_mastery": int(max(0, min(100, parsed.get("domain_mastery_score", 65)))),
                    "problem_solving": int(max(0, min(100, parsed.get("problem_solving_score", 65)))),
                    "execution_impact": int(max(0, min(100, parsed.get("execution_impact_score", 65)))),
                    "communication_clarity": int(max(0, min(100, parsed.get("communication_clarity_score", 65)))),
                    "role_calibration": int(max(0, min(100, parsed.get("role_calibration_score", 65)))),
                }
            elif resp.status_code == 429:
                wait_time = attempt * 4
                print(f"  [Rate Limit] OpenAI 429, backing off for {wait_time}s (attempt {attempt}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"OpenAI API HTTP {resp.status_code}: {resp.text[:300]}")
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            if attempt == max_retries:
                raise RuntimeError(f"Failed to obtain scores from OpenAI after {max_retries} attempts: {e}")
            time.sleep(attempt * 2)

    raise RuntimeError("OpenAI score generation failed.")


def calibrate_benchmark_level(score: int) -> str:
    """Return standard benchmark level according to calibrated rubric."""
    if score >= 90:
        return "Exceptional"
    elif score >= 75:
        return "Proficient"
    elif score >= 60:
        return "Developing"
    else:
        return "Significant Gap"


def main():
    parser = argparse.ArgumentParser(
        description="Rescore existing interviews in MongoDB without modifying any transcripts or report text."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Calculate and preview new scores without updating MongoDB."
    )
    parser.add_argument(
        "--input", default="reports.txt",
        help="Path to file containing interview URLs or IDs (default: reports.txt)."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of interviews to process (default: all)."
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Delay in seconds between OpenAI API requests (default: 1.0)."
    )
    parser.add_argument(
        "--mongo-uri", default=None,
        help="MongoDB connection URI (defaults to MONGO_URI from environment)."
    )
    parser.add_argument(
        "--openai-key", default=None,
        help="OpenAI API Key (defaults to OPENAI_API_KEY from environment)."
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini",
        help="OpenAI model to use (default: gpt-4o-mini)."
    )

    args = parser.parse_args()

    # Resolve credentials
    mongo_uri = args.mongo_uri or os.getenv("MONGO_URI")
    openai_key = args.openai_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")

    if not mongo_uri:
        print("[Error] MongoDB URI is missing. Set MONGO_URI in .env or pass --mongo-uri.", file=sys.stderr)
        sys.exit(1)

    if not openai_key:
        print("[Error] OpenAI API key is missing. Set OPENAI_API_KEY in .env or pass --openai-key.", file=sys.stderr)
        sys.exit(1)

    # Load IDs from input file
    interview_ids = extract_interview_ids(args.input)
    if not interview_ids:
        print(f"[Error] No valid interview IDs found in {args.input}.", file=sys.stderr)
        sys.exit(1)

    if args.limit:
        interview_ids = interview_ids[:args.limit]

    print("=" * 80)
    print(" VIRAYA INTERVIEW STUDIO - INTERVIEW RESCORING UTILITY")
    print("=" * 80)
    print(f" Mode:            {'DRY RUN (No changes will be saved)' if args.dry_run else 'LIVE UPDATE (Writing to MongoDB)'}")
    print(f" Input File:      {args.input} ({len(interview_ids)} interviews to process)")
    print(f" OpenAI Model:    {args.model}")
    print(f" Guardrail:       Transcripts, summaries, rationales, and text remain 100% UNTOUCHED.")
    print("=" * 80)

    # Connect to MongoDB
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
        # Verify connection
        client.admin.command("ping")
        db = client.get_default_database()
        print(f" Connected to MongoDB database: {db.name}\n")
    except Exception as e:
        print(f"[Error] Failed to connect to MongoDB: {e}", file=sys.stderr)
        sys.exit(1)

    results_summary = []
    success_count = 0
    fail_count = 0

    for idx, interview_id in enumerate(interview_ids, 1):
        print(f"[{idx}/{len(interview_ids)}] Processing Interview ID: {interview_id}...")

        # Find interview document
        doc = db.interviews.find_one({"$or": [{"_id": interview_id}, {"id": interview_id}]})
        if not doc:
            print(f"  [Skip] Interview {interview_id} not found in MongoDB.")
            fail_count += 1
            continue

        candidate_name = doc.get("candidate_name", "Unknown Candidate")
        job_title = doc.get("job_title", "AI developer")
        report = doc.get("report")

        if not report:
            print(f"  [Skip] Candidate '{candidate_name}' does not have an evaluation report yet.")
            fail_count += 1
            continue

        old_overall = report.get("overall_score")
        existing_competency_scores = report.get("competency_scores") or []

        # Extract transcript and text context
        transcript = doc.get("transcript") or []
        ts_text, cand_turns, cand_words = format_transcript_text(transcript)

        if not ts_text.strip():
            print(f"  [Warning] Candidate '{candidate_name}' has an empty transcript. Skipping.")
            fail_count += 1
            continue

        # Compile existing rationales to preserve qualitative context
        existing_rationales = []
        for c in existing_competency_scores:
            c_name = c.get("name") or c.get("id") or "Dimension"
            c_rat = c.get("rationale") or ""
            if c_rat:
                existing_rationales.append(f"{c_name}: {c_rat}")
        existing_rationales_str = "\n".join(existing_rationales)

        try:
            # 1. Obtain dynamic competency scores from OpenAI
            scores = request_openai_scores(
                candidate_name=candidate_name,
                job_title=job_title,
                jd_text=doc.get("jd_text") or "",
                resume_text=doc.get("resume_text") or "",
                transcript_text=ts_text,
                existing_rationales=existing_rationales_str,
                api_key=openai_key,
                model=args.model
            )

            # 2. Compute weighted overall score according to standard rubric weights:
            # domain_mastery (30%), problem_solving (25%), execution_impact (20%),
            # communication_clarity (15%), role_calibration (10%)
            raw_overall = round(
                scores["domain_mastery"] * 0.30 +
                scores["problem_solving"] * 0.25 +
                scores["execution_impact"] * 0.20 +
                scores["communication_clarity"] * 0.15 +
                scores["role_calibration"] * 0.10
            )

            # 3. Dynamic candidate volume & substance calibration
            if cand_turns < 2 or cand_words < 40:
                volume_scale = max(0.35, min(1.0, cand_words / 60.0))
                raw_overall = round(raw_overall * volume_scale)
                for k in scores:
                    scores[k] = round(scores[k] * volume_scale)

            new_overall = int(max(0, min(100, raw_overall)))

            # 4. Update ONLY scores and benchmark levels in existing competency items
            # (Preserving id, name, weight, rationale, supporting_quote, improvement_recommendation)
            for c in existing_competency_scores:
                cid = c.get("id")
                if cid in scores:
                    new_dim_score = scores[cid]
                    c["score"] = new_dim_score
                    c["benchmark_level"] = calibrate_benchmark_level(new_dim_score)

            # 5. Persist strictly the updated scores to MongoDB
            if not args.dry_run:
                db.interviews.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "report.overall_score": new_overall,
                            "report.competency_scores": existing_competency_scores,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )

            status_label = "PREVIEWED" if args.dry_run else "UPDATED"
            print(f"  [OK] {candidate_name}: Score {old_overall} -> {new_overall} "
                  f"(DM:{scores['domain_mastery']}, PS:{scores['problem_solving']}, "
                  f"EX:{scores['execution_impact']}, CC:{scores['communication_clarity']}, "
                  f"RC:{scores['role_calibration']}) [{status_label}]")

            results_summary.append({
                "id": interview_id,
                "name": candidate_name,
                "old_score": old_overall,
                "new_score": new_overall,
                "scores": scores,
                "status": status_label
            })
            success_count += 1

        except Exception as e:
            print(f"  [Error] Failed to rescore '{candidate_name}': {e}", file=sys.stderr)
            fail_count += 1

        if args.delay > 0 and idx < len(interview_ids):
            time.sleep(args.delay)

    # Final Summary Table
    print("\n" + "=" * 80)
    print(f" RESCORING SUMMARY ({'DRY RUN' if args.dry_run else 'COMMITTED TO MONGODB'})")
    print("=" * 80)
    print(f" {'Candidate Name':<28} | {'Old':<5} | {'New':<5} | {'Breakdown (DM/PS/EX/CC/RC)':<26} | {'Status'}")
    print("-" * 80)
    for r in results_summary:
        sc = r["scores"]
        breakdown = f"{sc['domain_mastery']}/{sc['problem_solving']}/{sc['execution_impact']}/{sc['communication_clarity']}/{sc['role_calibration']}"
        print(f" {r['name'][:28]:<28} | {str(r['old_score']):<5} | {str(r['new_score']):<5} | {breakdown:<26} | {r['status']}")

    print("=" * 80)
    print(f" Processed: {len(interview_ids)} | Success: {success_count} | Failed/Skipped: {fail_count}")
    if args.dry_run:
        print(" Dry run complete! Run without --dry-run to commit these updated scores to MongoDB.")
    else:
        print(" All scores have been updated in MongoDB. Transcripts and report rationales remain untouched.")
    print("=" * 80)


if __name__ == "__main__":
    main()
