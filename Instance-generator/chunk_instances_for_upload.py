#!/usr/bin/env python3
"""Convert the generated TSV into six randomized, importer-ready CSV batches."""

import argparse
import csv
import random
import re
from pathlib import Path


SOURCE = Path(__file__).with_name("vietnamese_instances_600.tsv")
DEFAULT_OUTPUT_DIR = Path(__file__).with_name("upload_batches")
BATCH_COUNT = 6
BATCH_SIZE = 100
CSV_HEADERS = [
    "occupation",
    "occupation_en",
    "participant_role",
    "participant_role_en",
    "term_set",
    "narrator_position",
    "distractor_level",
    "intro_vi",
    "intro_en",
    "distractor_1_vi",
    "distractor_1_en",
    "distractor_2_vi",
    "distractor_2_en",
    "distractor_3_vi",
    "distractor_3_en",
    "distractor_4_vi",
    "distractor_4_en",
    "distractor_5_vi",
    "distractor_5_en",
    "target_vi",
    "target_en",
    "correct_answer",
]


def split_sentences(text, uid, field_name):
    sentences = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)
    if len(sentences) != 2:
        raise ValueError(f"{field_name} for source UID {uid} must contain context and target sentences")
    return sentences


def to_import_row(source_row):
    context, _ = split_sentences(source_row["sentence"], source_row["uid"], "sentence")
    _, target = split_sentences(source_row["human_sentence"], source_row["uid"], "human_sentence")
    row = {header: "" for header in CSV_HEADERS}
    row.update(
        {
            "occupation": source_row["occupation"],
            "occupation_en": "N/A",
            "participant_role": source_row["participant"],
            "participant_role_en": "N/A",
            "term_set": source_row["pronoun"],
            "narrator_position": "unspecified",
            "distractor_level": 0,
            "intro_vi": context,
            "intro_en": "N/A",
            "target_vi": target,
            "target_en": "N/A",
            "correct_answer": source_row["pronoun"],
        }
    )
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261008, help="Randomization seed (default: 20261008)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    with SOURCE.open(encoding="utf-8", newline="") as source:
        source_rows = list(csv.DictReader(source, delimiter="\t"))
    expected = BATCH_COUNT * BATCH_SIZE
    if len(source_rows) != expected:
        raise SystemExit(f"Expected {expected} source rows in {SOURCE}, found {len(source_rows)}")

    import_rows = [to_import_row(row) for row in source_rows]
    instance_keys = [
        (
            row["occupation"],
            row["participant_role"],
            row["term_set"],
            row["narrator_position"],
            row["distractor_level"],
            row["intro_vi"],
            row["target_vi"],
        )
        for row in import_rows
    ]
    duplicate_keys = len(instance_keys) - len(set(instance_keys))

    random.Random(args.seed).shuffle(import_rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for batch_index in range(BATCH_COUNT):
        start = batch_index * BATCH_SIZE
        batch = import_rows[start : start + BATCH_SIZE]
        output_path = args.output_dir / f"instances_{batch_index + 1:02d}.csv"
        with output_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(batch)
        print(f"{output_path}: {len(batch)} instances")

    print(f"Created {BATCH_COUNT} randomized CSV batches ({expected} rows total), seed={args.seed}.")
    if duplicate_keys:
        print(
            f"Warning: {duplicate_keys} rows are exact duplicates under the importer's full instance key. "
            "The importer may skip them as duplicates."
        )


if __name__ == "__main__":
    main()
