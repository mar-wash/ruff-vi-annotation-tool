#!/usr/bin/env python3
import argparse
import csv
import random
import re
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from pronouns import mapping


NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
BASE_HEADERS = [
    "occupation",
    "participant",
    "sentence",
    "pronoun_type",
    "word",
    "pronoun",
    "uid",
    "confuse_pronoun",
]
HUMAN_HEADERS = [*BASE_HEADERS, "human_sentence"]
CONDITION_NAMES = [
    "eo_task",
    "eo_ep_task",
    "eo_ep_ip_task",
    "eo_ep_ip_ip_task",
    "eo_ep_ip_ip_ip_task",
    "eo_ep_ip_ip_ip_ip_task",
]


def collapse_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def capitalize_sentence(text):
    text = collapse_spaces(text)
    return text[:1].upper() + text[1:] if text else text


def column_index(cell_ref):
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    total = 0
    for letter in letters:
        total = total * 26 + ord(letter.upper()) - 64
    return total - 1


def read_xlsx_rows(path):
    with ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("main:si", NS):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//main:t", NS)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in relationships.findall("rel:Relationship", REL_NS)
        }
        sheet = workbook.find("main:sheets/main:sheet", NS)
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        sheet_path = relationship_targets[rel_id].lstrip("/")
        if not sheet_path.startswith("xl/"):
            sheet_path = f"xl/{sheet_path}"

        root = ET.fromstring(archive.read(sheet_path))
        rows = []
        for row in root.findall("main:sheetData/main:row", NS):
            values = []
            for cell in row.findall("main:c", NS):
                index = column_index(cell.attrib.get("r", "A1"))
                while len(values) <= index:
                    values.append("")
                value = cell.find("main:v", NS)
                inline = cell.find("main:is/main:t", NS)
                if cell.attrib.get("t") == "inlineStr" and inline is not None:
                    values[index] = inline.text or ""
                elif value is None:
                    values[index] = ""
                elif cell.attrib.get("t") == "s":
                    values[index] = shared_strings[int(value.text)]
                else:
                    values[index] = value.text or ""
            rows.append(values)
        return rows


def load_tasks(path):
    rows = read_xlsx_rows(path)
    tasks = []
    for row in rows[1:]:
        if len(row) < 5 or not row[0].strip():
            continue
        tasks.append(
            {
                "occupation": row[0].strip(),
                "participant": row[1].strip(),
                "sentence": row[2].strip(),
                "pronoun_type": row[3].strip(),
                "word": row[4].strip(),
            }
        )
    return tasks


def load_contexts(path):
    rows = read_xlsx_rows(path)
    contexts = {}
    for row in rows[1:]:
        if len(row) < 4 or not row[0].strip():
            continue
        pronoun_type = row[0].strip()
        contexts.setdefault(pronoun_type, {"explicit": [], "implicit": []})
        index = len(contexts[pronoun_type]["explicit"])
        contexts[pronoun_type]["explicit"].append(
            {"id": index, "polarity": row[1].strip(), "template": row[2].strip()}
        )
        contexts[pronoun_type]["implicit"].append(
            {"id": index, "polarity": row[1].strip(), "template": row[3].strip()}
        )
    return contexts


def instantiate_context(template, entity, pronoun_type, pronoun):
    return collapse_spaces(
        template.replace("$OCCUPATION/PARTICIPANT", entity).replace(pronoun_type, pronoun)
    )


def build_row(task, pronoun, confuse_pronoun, context_parts, uid_parts):
    sentence = " ".join(
        [*(capitalize_sentence(part) for part in context_parts), task["sentence"]]
    )
    return {
        "occupation": task["occupation"],
        "participant": task["participant"],
        "sentence": collapse_spaces(sentence),
        "pronoun_type": task["pronoun_type"],
        "word": task["word"],
        "pronoun": pronoun,
        "uid": "_".join(uid_parts),
        "confuse_pronoun": confuse_pronoun,
    }


def random_condition_row(tasks, contexts, level, pronoun, confuse_pronoun, rng):
    task = rng.choice(tasks)
    pronoun_type = task["pronoun_type"]
    explicit_contexts = contexts[pronoun_type]["explicit"]
    implicit_contexts = contexts[pronoun_type]["implicit"]

    intro = rng.choice(explicit_contexts)
    context_parts = [
        instantiate_context(intro["template"], task["occupation"], pronoun_type, pronoun)
    ]
    uid_parts = [f"eo{intro['id']}"]

    if level == 0:
        return build_row(task, pronoun, "", context_parts, uid_parts)

    distractor_candidates = [
        item
        for item in explicit_contexts
        if item["polarity"] != intro["polarity"] and item["id"] % 5 != intro["id"] % 5
    ]
    distractor = rng.choice(distractor_candidates)
    context_parts.append(
        instantiate_context(
            distractor["template"], task["participant"], pronoun_type, confuse_pronoun
        )
    )
    uid_parts.append(f"ep{distractor['id']}")

    implicit_candidates = [
        item
        for item in implicit_contexts
        if item["polarity"] == distractor["polarity"]
        and item["id"] not in {intro["id"], distractor["id"]}
    ]
    for implicit in rng.sample(implicit_candidates, level - 1):
        context_parts.append(
            instantiate_context(
                implicit["template"], task["participant"], pronoun_type, confuse_pronoun
            )
        )
        uid_parts.append(f"ip{implicit['id']}")

    return build_row(task, pronoun, confuse_pronoun, context_parts, uid_parts)


def sample_group(tasks, contexts, level, pronoun, confuse_pronoun, size, rng):
    rows = []
    seen = set()
    attempts = 0
    while len(rows) < size and attempts < 1000:
        attempts += 1
        row = random_condition_row(tasks, contexts, level, pronoun, confuse_pronoun, rng)
        key = tuple(row[header] for header in BASE_HEADERS)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    if len(rows) < size:
        raise RuntimeError("Could not sample enough unique rows for a balanced group.")
    return rows


def sample_condition(tasks_by_word_type, contexts, level, seed):
    rng = random.Random(seed + level)
    rows = []
    for (word, pronoun_type), tasks in sorted(tasks_by_word_type.items()):
        pronouns = mapping[pronoun_type]
        for pronoun in pronouns:
            if level == 0:
                rows.extend(sample_group(tasks, contexts, level, pronoun, "", 3, rng))
            else:
                for confuse_pronoun in pronouns:
                    if confuse_pronoun == pronoun:
                        continue
                    rows.extend(
                        sample_group(tasks, contexts, level, pronoun, confuse_pronoun, 1, rng)
                    )
    return rows


def make_human_sentence(row):
    return row["sentence"].replace(row["pronoun_type"], "___")


def sample_for_humans(condition_rows, count_per_condition, seed):
    rng = random.Random(seed)
    sampled = []
    for condition_name in CONDITION_NAMES:
        rows = condition_rows[condition_name]
        if len(rows) < count_per_condition:
            raise RuntimeError(f"{condition_name} only has {len(rows)} rows.")
        for row in rng.sample(rows, count_per_condition):
            sampled.append({**row, "human_sentence": make_human_sentence(row)})
    return sampled


def write_tsv(path, rows, headers):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Vietnamese sampled_for_humans-style TSV."
    )
    parser.add_argument("--tasks", type=Path, default=Path("Instance-generator/tasks_vi.xlsx"))
    parser.add_argument("--contexts", type=Path, default=Path("Instance-generator/context_vi.xlsx"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("Instance-generator/sampled_for_humans_vietnamese.tsv"),
    )
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--template-seed", type=int, default=13)
    parser.add_argument("--human-seed", type=int, default=131719)
    args = parser.parse_args()

    if args.count % len(CONDITION_NAMES) != 0:
        raise SystemExit(f"--count must be divisible by {len(CONDITION_NAMES)}")

    tasks = [task for task in load_tasks(args.tasks) if task["occupation"] == task["word"]]
    contexts = load_contexts(args.contexts)
    tasks_by_word_type = defaultdict(list)
    for task in tasks:
        if task["pronoun_type"] in mapping and task["pronoun_type"] in contexts:
            tasks_by_word_type[(task["word"], task["pronoun_type"])].append(task)

    condition_rows = {
        condition_name: sample_condition(
            tasks_by_word_type, contexts, level, args.template_seed
        )
        for level, condition_name in enumerate(CONDITION_NAMES)
    }
    rows = sample_for_humans(
        condition_rows, args.count // len(CONDITION_NAMES), args.human_seed
    )
    write_tsv(args.output, rows, HUMAN_HEADERS)
    print(f"Wrote {len(rows)} rows to {args.output}")
    for condition_name in CONDITION_NAMES:
        print(f"{condition_name}: sampled from {len(condition_rows[condition_name])} rows")


if __name__ == "__main__":
    main()
