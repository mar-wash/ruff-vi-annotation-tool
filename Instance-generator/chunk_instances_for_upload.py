#!/usr/bin/env python3
"""Convert the generated TSV into randomized importer-ready CSV output."""

import argparse
import csv
import random
import re
from pathlib import Path


SOURCE = Path(__file__).with_name("sampled_for_humans_vietnamese.tsv")
DEFAULT_OUTPUT_DIR = Path(__file__).with_name("upload_batches")
DEFAULT_SINGLE_OUTPUT = Path(__file__).with_name("upload_instances_600.csv")
BATCH_COUNT = 6
BATCH_SIZE = 100
CSV_HEADERS = [
    "occupation",
    "occupation_en",
    "participant_role",
    "participant_role_en",
    "term_set",
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
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) < 2:
        raise ValueError(f"{field_name} for source UID {uid} must contain context and target sentences")
    return sentences


def to_import_row(source_row):
    source_sentences = split_sentences(source_row["sentence"], source_row["uid"], "sentence")
    human_sentences = split_sentences(source_row["human_sentence"], source_row["uid"], "human_sentence")
    if len(source_sentences) != len(human_sentences):
        raise ValueError(f"sentence and human_sentence lengths differ for source UID {source_row['uid']}")
    distractors = source_sentences[1:-1]
    row = {header: "" for header in CSV_HEADERS}
    row.update(
        {
            "occupation": source_row["occupation"],
            "occupation_en": "N/A",
            "participant_role": source_row["participant"],
            "participant_role_en": "N/A",
            "term_set": source_row["pronoun"],
            "distractor_level": len(distractors),
            "intro_vi": source_sentences[0],
            "intro_en": "N/A",
            "target_vi": human_sentences[-1],
            "target_en": "N/A",
            "correct_answer": source_row["pronoun"],
        }
    )
    for level, distractor in enumerate(distractors, start=1):
        row[f"distractor_{level}_vi"] = distractor
        row[f"distractor_{level}_en"] = "N/A"
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261008, help="Randomization seed (default: 20261008)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--single-file",
        action="store_true",
        help=f"Write all 600 instances to {DEFAULT_SINGLE_OUTPUT.name} instead of six batch files.",
    )
    parser.add_argument("--single-output", type=Path, default=DEFAULT_SINGLE_OUTPUT)
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
            row["distractor_level"],
            row["intro_vi"],
            row["target_vi"],
        )
        for row in import_rows
    ]
    duplicate_keys = len(instance_keys) - len(set(instance_keys))

    random.Random(args.seed).shuffle(import_rows)
    if args.single_file:
        args.single_output.parent.mkdir(parents=True, exist_ok=True)
        with args.single_output.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(import_rows)
        print(f"{args.single_output}: {len(import_rows)} instances")
        print(f"Created one randomized CSV ({len(import_rows)} rows total), seed={args.seed}.")
    else:
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
