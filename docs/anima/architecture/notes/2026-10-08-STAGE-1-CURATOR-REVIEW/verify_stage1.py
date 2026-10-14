"""Read-only verification of the curator's frozen Stage 1 input and outputs.

Reads only visible message text from the named primary archive. Internal
reasoning, instructions and tool payloads are never exported. Writes evidence
only to this review directory; does not extend the curator's capture frontier.
"""

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[4]
REVIEW = Path(__file__).resolve().parent
PACKET = ROOT / "ANIMA/context/integrations/2026-10-08"
PRIMARY = Path(r"<codex-sessions>\2026\10\01\rollout-2026-10-01T22-14-31-01a0f85a-6e14-7e93-8bc3-83af412e7eec.jsonl")


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def relative(path):
    return path.relative_to(ROOT).as_posix()


def parse_primary(frontier_lines):
    digest = hashlib.sha256()
    messages = {}
    role_counts = Counter()
    byte_count = 0
    frontier_timestamp = None
    with PRIMARY.open("rb") as stream:
        for ordinal in range(frontier_lines):
            raw = stream.readline()
            if not raw:
                raise ValueError("Archive ends before the declared capture frontier")
            digest.update(raw)
            byte_count += len(raw)
            record = json.loads(raw)
            frontier_timestamp = record.get("timestamp")
            item = record.get("payload", {})
            if record.get("type") != "response_item" or item.get("type") != "message":
                continue
            role = item.get("role")
            if role not in ("user", "assistant") or item.get("channel") == "analysis":
                continue
            role_counts[role] += 1
            visible_text = "\n".join(
                block.get("text", "") for block in item.get("content", [])
                if block.get("type") in ("input_text", "output_text", "text")
            )
            environment_only = bool(re.fullmatch(r"\s*<environment_context>.*</environment_context>\s*", visible_text, re.S))
            messages[ordinal] = {
                "ordinal": ordinal,
                "physical_line": ordinal + 1,
                "timestamp": record.get("timestamp"),
                "message_id": item.get("id"),
                "role": role,
                "environment_only": environment_only,
                "text": visible_text,
            }
    return messages, {
        "physical_lines": frontier_lines,
        "ordinal_last": frontier_lines - 1,
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
        "last_record_timestamp": frontier_timestamp,
        "visible_message_counts_before_filtering": dict(role_counts),
        "live_archive_bytes_at_review": PRIMARY.stat().st_size,
        "records_beyond_frontier": "Not reviewed or integrated",
    }


def check_preserved(path, heading, messages):
    text = path.read_text(encoding="utf-8")
    headings = list(re.finditer(heading, text, re.M))
    rows = []
    for index, match in enumerate(headings):
        section = text[match.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        count = re.search(r"\*\*(?:Character Count|Length):\*\* (\d+)", section)
        fence = re.search(r"```(?:text|markdown)\n", section)
        message_id = re.search(r"\*\*Message ID:\*\* `([^`]+)`", section)
        ordinal = int(match.group(2))
        source = messages.get(ordinal)
        extracted = section[fence.end():fence.end() + int(count.group(1))] if fence and count else None
        expected = source["text"] if source else None
        row = {
            "ordinal": ordinal,
            "source_physical_line": ordinal + 1,
            "labelled_physical_line": int(match.group(1)),
            "message_id_matches": bool(source and message_id and message_id.group(1) == source["message_id"]),
            "timestamp_matches": bool(source and match.group(3).strip() == source["timestamp"]),
            "exact_text_matches": expected is not None and expected == extracted,
            "trim_only_matches": expected is not None and expected != extracted and expected.strip() == extracted,
            "characters": len(expected) if expected is not None else None,
            "contains_bare_triple_backtick_line": bool(expected and re.search(r"^```\s*$", expected, re.M)),
        }
        rows.append(row)
    return {
        "file": relative(path),
        "sections": len(rows),
        "exact_matches": sum(row["exact_text_matches"] for row in rows),
        "trim_only_matches": sum(row["trim_only_matches"] for row in rows),
        "mismatches": [row for row in rows if not (row["exact_text_matches"] or row["trim_only_matches"])],
        "wrong_physical_line_labels": sum(row["labelled_physical_line"] != row["source_physical_line"] for row in rows),
        "nested_fence_sections": sum(row["contains_bare_triple_backtick_line"] for row in rows),
        "rows": rows,
    }


def heading_slugs(text):
    seen = Counter()
    slugs = set()
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", match.group(1).lower()).replace(" ", "-")
        occurrence = seen[slug]
        seen[slug] += 1
        slugs.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
    return slugs


def check_links(paths):
    checked = 0
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?<!!)\[[^\]\n]+\]\(([^\)\n]+)\)", text):
            target = match.group(1).strip().strip("<>")
            if re.match(r"(?:https?://|mailto:|app://)", target):
                continue
            target_path, _, anchor = target.partition("#")
            resolved = (path.parent / unquote(target_path)).resolve() if target_path else path
            checked += 1
            issue = None
            if not resolved.exists():
                issue = "missing_local_target"
            elif anchor and resolved.is_file() and resolved.suffix.lower() == ".md":
                if unquote(anchor) not in heading_slugs(resolved.read_text(encoding="utf-8")):
                    issue = "missing_heading_anchor"
            if issue:
                problems.append({"file": relative(path), "line": text.count("\n", 0, match.start()) + 1, "target": target, "problem": issue})
    return {"files_checked": len(paths), "local_links_checked": checked, "problems": problems,
            "scope": "Authored navigation/control documents only; historical links inside verbatim text are not rewritten. Heading checks approximate GitHub Markdown, not a browser rendering test."}


def main(output):
    sources = read_rows(PACKET / "SOURCES.jsonl")
    declared = next(row for row in sources if row.get("session_id") == "01a0f85a-6e14-7e93-8bc3-83af412e7eec")
    messages, capture = parse_primary(declared["lines"])
    capture["matches_declared_sha256"] = capture["sha256"] == declared["sha256"]
    capture["matches_declared_bytes"] = capture["bytes"] == declared["bytes"]
    capture["declared_last_record_timestamp"] = declared["capture_frontier_timestamp"]
    capture["matches_declared_last_record_timestamp"] = capture["last_record_timestamp"] == declared["capture_frontier_timestamp"]

    users = check_preserved(PACKET / "preserved/USER-SUBSTANTIVE-TURNS.md", r"^## Turn: Physical Line (\d+) \| Ordinal (\d+) \| ([^\n]+)", messages)
    assistants = check_preserved(PACKET / "preserved/ASSISTANT-SUBSTANTIVE-PROPOSALS.md", r"^## Assistant Turn: Physical Line (\d+) \| Ordinal (\d+) \| ([^\n]+)", messages)
    user_ordinals = {row["ordinal"] for row in users["rows"]}
    assistant_ordinals = {row["ordinal"] for row in assistants["rows"]}
    omitted = []
    for ordinal, message in messages.items():
        if message["role"] == "assistant" and ordinal not in assistant_ordinals:
            omitted.append({key: message[key] for key in ("ordinal", "physical_line", "timestamp", "message_id")}
                          | {"characters": len(message["text"]), "disposition": "No individual disposition found in delivered coverage records"})

    substantive_users = [message for message in messages.values() if message["role"] == "user" and not message["environment_only"]]
    groups = defaultdict(list)
    for message in substantive_users:
        groups[message["text"]].append(message["ordinal"])

    corpus = []
    for path in (ROOT / "ANIMA").rglob("*.md"):
        if REVIEW not in path.parents:
            corpus.append((relative(path), path.read_text(encoding="utf-8")))
    for row in omitted:
        row["exact_full_text_present_elsewhere"] = [name for name, text in corpus if messages[row["ordinal"]]["text"] in text]
        row["disposition"] = (
            "Exact text retained elsewhere, but individual coverage mapping is absent"
            if row["exact_full_text_present_elsewhere"] else
            "No full exact-text route found; needs substantive/duplicate/omission disposition"
        )
    session_identity_checks = []
    for source in sources:
        source_path = Path(source["path"].replace("/mnt/c/", "C:/", 1))
        digest = hashlib.sha256()
        captured_bytes = 0
        last_timestamp = None
        with source_path.open("rb") as stream:
            for _ in range(source["lines"]):
                raw = stream.readline()
                if not raw:
                    raise ValueError("Session shorter than recorded frontier: " + source["session_id"])
                digest.update(raw)
                captured_bytes += len(raw)
                last_timestamp = json.loads(raw).get("timestamp")
        session_identity_checks.append({
            "session_id": source["session_id"], "physical_lines": source["lines"],
            "bytes": captured_bytes, "sha256": digest.hexdigest(),
            "matches_declared_identity": captured_bytes == source["bytes"] and digest.hexdigest() == source["sha256"],
            "last_record_timestamp": last_timestamp,
            "scope": "Byte-prefix identity check only; secondary message contents not reviewed",
        })
    omission_examples = []
    for ordinal in (1017, 1345, 4278):
        message = messages[ordinal]
        omission_examples.append({"ordinal": ordinal, "physical_line": ordinal + 1,
                                  "visible_assistant_text": message["text"],
                                  "exact_full_text_present_in_existing_anima_markdown": [name for name, text in corpus if message["text"] in text],
                                  "limitation": "Exact-text absence does not establish semantic absence; curator must supply an explicit disposition or exact-source route."})

    control_names = ["ANIMA/START-HERE.md", "ANIMA/README.md", "ANIMA/context/README.md",
                     "ANIMA/context/OPERATIVE-BRIEF.md", "ANIMA/context/INTAKE-AND-ROUTING.md",
                     "ANIMA/architecture/notes/README.md"]
    controls = [ROOT / name for name in control_names]
    controls += [PACKET / name for name in ("SYNTHESIS.md", "INDEX.md", "ARCHITECTURE-HANDOFF.md", "COVERAGE-AND-REVIEW.md", "preserved/SOURCE-MAP.md")]
    controls += sorted((ROOT / "ANIMA/context/tracks").glob("*.md"))
    documents = sorted((ROOT / "ANIMA/architecture/notes/2026-10-05-DEVELOPMENTAL-WORLDS").rglob("*"))
    document_inventory = []
    for path in documents:
        if path.is_file():
            data = path.read_bytes()
            document_inventory.append({"path": relative(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                       "note": "Identity observed by coordinator review; not evidence of curator reading or architecture acceptance"})

    structured = []
    for path in (PACKET / "SOURCES.jsonl", PACKET / "DECISIONS.jsonl",
                 ROOT / "ANIMA/context/SOURCES.jsonl", ROOT / "ANIMA/context/DECISIONS-AND-CORRECTIONS.jsonl"):
        structured.append({"path": relative(path), "parseable_rows": len(read_rows(path))})

    result = {
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Stage 1 documentary verification only. No Stage 2 execution, implementation inspection, tests, deployments or source edits.",
        "capture": capture,
        "session_identity_checks": session_identity_checks,
        "user_coverage": {"substantive_visible_turns": len(substantive_users),
                          "distinct_texts": len(groups),
                          "environment_only_records_excluded": sum(message["environment_only"] for message in messages.values()),
                          "substantive_turns_missing_from_user_file": [message["ordinal"] for message in substantive_users if message["ordinal"] not in user_ordinals],
                          "exact_duplicate_text_groups": [ordinals for ordinals in groups.values() if len(ordinals) > 1],
                          "note": "Both occurrences remain in the user file. Identical go-N strings refer to different vector rounds and cannot be treated as identical instructions."},
        "user_preservation": users,
        "assistant_preservation": assistants,
        "omitted_visible_assistant_messages": omitted,
        "assistant_messages_absent_from_main_file_summary": {
            "absent_from_main_file": len(omitted),
            "exact_text_present_elsewhere": sum(bool(row["exact_full_text_present_elsewhere"]) for row in omitted),
            "no_full_exact_text_route_found": sum(not row["exact_full_text_present_elsewhere"] for row in omitted),
            "note": "Semantic duplicates and routine acknowledgements may be legitimately omitted after explicit individual disposition; exact-string absence alone is not proof of lost meaning.",
        },
        "omitted_assistant_examples": omission_examples,
        "sources_register": {"integration_rows": len(sources),
                             "integration_document_source_rows": sum(row.get("session_id") is None for row in sources)},
        "structured_files": structured,
        "control_document_identity": [
            {"path": relative(path), "bytes": path.stat().st_size,
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in controls
        ],
        "navigation": check_links(controls),
        "developmental_packet_document_inventory": document_inventory,
        "ecosystem": {"directory_present": (ROOT / "ecosystem").exists(),
                      "provenance_files": [relative(path) for path in sorted((ROOT / "ANIMA/context/provenance/initial-ecosystem-draft-2026-10-02").rglob("*")) if path.is_file()],
                      "limitation": "Post-deletion observation cannot recheck prior hidden files, reparse points, original redirect contents, or pre-deletion dependency checks."},
        "execution_note": "An earlier interactive probe completed its comparisons but failed while printing a large Unicode user excerpt under cp1252. This reproducible script writes UTF-8 JSON and exports no large transcript excerpts. The failure changed no source or deliverable.",
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"evidence": relative(output), "capture_sha256_matches": capture["matches_declared_sha256"],
               "capture_timestamp_matches": capture["matches_declared_last_record_timestamp"],
               "users": {key: users[key] for key in ("sections", "exact_matches", "trim_only_matches", "nested_fence_sections")},
               "assistants": {key: assistants[key] for key in ("sections", "exact_matches", "trim_only_matches", "nested_fence_sections")},
               "omitted_assistant_messages": len(omitted), "navigation": result["navigation"],
               "assistant_messages_absent_from_main_file_summary": result["assistant_messages_absent_from_main_file_summary"],
               "session_identities_match": all(row["matches_declared_identity"] for row in session_identity_checks),
               "document_inventory_files": len(document_inventory)}
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REVIEW / "verification.json")
    args = parser.parse_args()
    if args.output.resolve().parent != REVIEW:
        raise SystemExit("Evidence output must remain in this review directory")
    main(args.output)
