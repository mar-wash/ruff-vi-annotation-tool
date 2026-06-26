#!/usr/bin/env python3
import csv
import io
import json
import os
import random
import re
import sqlite3
import sys
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).parent.resolve()
STATIC = ROOT / "static"


def load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        print("Missing required environment variables:", ", ".join(missing), file=sys.stderr)
        print("Copy .env.example to .env and fill in the required values.", file=sys.stderr)
        sys.exit(1)


load_dotenv()
require_env(["PORT", "NODE_ENV", "DATABASE_PATH", "ADMIN_SECRET"])

DB_PATH = Path(os.environ["DATABASE_PATH"])
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
DATA = DB_PATH.parent
ADMIN_SECRET = os.environ["ADMIN_SECRET"]

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,24}$")
VALID_TERMS = {"anh", "chị", "cô", "chú", "ông", "bà", "em", "nó", "hắn", "chanh"}
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

CANONICAL_INSTANCES = [
    {
        "occupation": "bác sĩ",
        "occupation_en": "doctor",
        "participant_role": "bệnh nhân",
        "participant_role_en": "patient",
        "term_set": "anh",
        "narrator_position": "younger",
        "distractor_level": 2,
        "intro_vi": "Tôi gặp anh bác sĩ hôm nay tại phòng khám.",
        "intro_en": "I met the anh doctor at the clinic today.",
        "distractor_1_vi": "Phòng khám hôm nay khá đông bệnh nhân.",
        "distractor_1_en": "The clinic was quite busy with patients today.",
        "distractor_2_vi": "Trời bên ngoài rất nóng và oi bức.",
        "distractor_2_en": "The weather outside was very hot and humid.",
        "target_vi": "Bệnh nhân đã hỏi _____ về lịch hẹn tiếp theo.",
        "target_en": "The patient asked _____ about the next appointment.",
        "correct_answer": "anh",
    },
    {
        "occupation": "giáo viên",
        "occupation_en": "teacher",
        "participant_role": "học sinh",
        "participant_role_en": "student",
        "term_set": "cô",
        "narrator_position": "younger",
        "distractor_level": 1,
        "intro_vi": "Học sinh chào cô giáo trước khi vào lớp.",
        "intro_en": "The student greeted the cô teacher before entering class.",
        "distractor_1_vi": "Cửa sổ lớp học để mở vì trời mát.",
        "distractor_1_en": "The classroom windows were open because the weather was cool.",
        "target_vi": "Học sinh hỏi _____ về bài tập về nhà.",
        "target_en": "The student asked _____ about the homework.",
        "correct_answer": "cô",
    },
    {
        "occupation": "kỹ sư",
        "occupation_en": "engineer",
        "participant_role": "thực tập sinh",
        "participant_role_en": "intern",
        "term_set": "chanh",
        "narrator_position": "equal",
        "distractor_level": 0,
        "intro_vi": "Thực tập sinh làm việc cùng chanh kỹ sư trong dự án mới.",
        "intro_en": "The intern worked with the chanh engineer on the new project.",
        "target_vi": "Thực tập sinh hỏi _____ về tiến độ công việc.",
        "target_en": "The intern asked _____ about the work progress.",
        "correct_answer": "chanh",
    },
    {
        "occupation": "nông dân",
        "occupation_en": "farmer",
        "participant_role": "người mua",
        "participant_role_en": "buyer",
        "term_set": "ông",
        "narrator_position": "younger",
        "distractor_level": 3,
        "intro_vi": "Tôi gặp ông nông dân tại chợ buổi sáng.",
        "intro_en": "I met the ông farmer at the morning market.",
        "distractor_1_vi": "Chợ hôm nay có nhiều loại rau củ tươi.",
        "distractor_1_en": "The market had many kinds of fresh vegetables today.",
        "distractor_2_vi": "Một vài người bán hàng đang sắp xếp lại quầy.",
        "distractor_2_en": "Some vendors were rearranging their stalls.",
        "distractor_3_vi": "Trời sáng sớm nên không khí còn mát mẻ.",
        "distractor_3_en": "It was early morning so the air was still cool.",
        "target_vi": "Người mua hỏi _____ về giá rau hôm nay.",
        "target_en": "The buyer asked _____ about the price of vegetables today.",
        "correct_answer": "ông",
    },
    {
        "occupation": "bác sĩ",
        "occupation_en": "doctor",
        "participant_role": "bệnh nhân",
        "participant_role_en": "patient",
        "term_set": "bà",
        "narrator_position": "younger",
        "distractor_level": 4,
        "intro_vi": "Tôi được gặp bà bác sĩ phụ trách ca trực hôm nay.",
        "intro_en": "I got to meet the bà doctor on duty today.",
        "distractor_1_vi": "Hành lang bệnh viện khá yên tĩnh vào buổi chiều.",
        "distractor_1_en": "The hospital hallway was quite quiet in the afternoon.",
        "distractor_2_vi": "Có mùi thuốc sát trùng nhẹ trong không khí.",
        "distractor_2_en": "There was a faint smell of antiseptic in the air.",
        "distractor_3_vi": "Một y tá đang đẩy xe thuốc qua hành lang.",
        "distractor_3_en": "A nurse was pushing a medicine cart through the hallway.",
        "distractor_4_vi": "Ánh đèn trong phòng khám sáng và trắng.",
        "distractor_4_en": "The lights in the examination room were bright and white.",
        "target_vi": "Bệnh nhân hỏi _____ về kết quả xét nghiệm.",
        "target_en": "The patient asked _____ about the test results.",
        "correct_answer": "bà",
    },
    {
        "occupation": "giáo viên",
        "occupation_en": "teacher",
        "participant_role": "học sinh",
        "participant_role_en": "student",
        "term_set": "chú",
        "narrator_position": "younger",
        "distractor_level": 2,
        "intro_vi": "Học sinh chào chú giáo viên ở cổng trường.",
        "intro_en": "The student greeted the chú teacher at the school gate.",
        "distractor_1_vi": "Sân trường vắng vì giờ học chưa bắt đầu.",
        "distractor_1_en": "The schoolyard was empty because class hadn't started yet.",
        "distractor_2_vi": "Tiếng chuông vào lớp vừa mới vang lên.",
        "distractor_2_en": "The bell to enter class had just rung.",
        "target_vi": "Học sinh hỏi _____ về lịch kiểm tra tuần tới.",
        "target_en": "The student asked _____ about next week's exam schedule.",
        "correct_answer": "chú",
    },
    {
        "occupation": "kỹ sư",
        "occupation_en": "engineer",
        "participant_role": "đồng nghiệp",
        "participant_role_en": "colleague",
        "term_set": "chị",
        "narrator_position": "younger",
        "distractor_level": 1,
        "intro_vi": "Tôi làm việc cùng chị kỹ sư trong nhóm dự án.",
        "intro_en": "I work with the chị engineer in the project team.",
        "distractor_1_vi": "Văn phòng hôm nay có nhiều cuộc họp liên tiếp.",
        "distractor_1_en": "The office had many back-to-back meetings today.",
        "target_vi": "Đồng nghiệp nhờ _____ kiểm tra lại bản thiết kế.",
        "target_en": "The colleague asked _____ to review the design blueprint.",
        "correct_answer": "chị",
    },
    {
        "occupation": "nông dân",
        "occupation_en": "farmer",
        "participant_role": "hàng xóm",
        "participant_role_en": "neighbor",
        "term_set": "em",
        "narrator_position": "older",
        "distractor_level": 5,
        "intro_vi": "Tôi nói chuyện với em nông dân trẻ ở đầu làng.",
        "intro_en": "I spoke with the em young farmer at the edge of the village.",
        "distractor_1_vi": "Buổi chiều ở làng rất yên tĩnh và mát mẻ.",
        "distractor_1_en": "The village afternoon was very quiet and cool.",
        "distractor_2_vi": "Tiếng gà gáy vang lên từ phía cánh đồng.",
        "distractor_2_en": "The sound of roosters came from the direction of the fields.",
        "distractor_3_vi": "Mấy đứa trẻ đang chạy chơi gần bờ ao.",
        "distractor_3_en": "Some children were running around near the pond.",
        "distractor_4_vi": "Khói bếp tỏa ra từ những mái nhà tranh.",
        "distractor_4_en": "Cooking smoke rose from the thatched rooftops.",
        "distractor_5_vi": "Con đường đất nhỏ dẫn vào làng còn ướt sau cơn mưa.",
        "distractor_5_en": "The small dirt road leading into the village was still wet after the rain.",
        "target_vi": "Hàng xóm hỏi _____ về mùa thu hoạch năm nay.",
        "target_en": "The neighbor asked _____ about this year's harvest.",
        "correct_answer": "em",
    },
    {
        "occupation": "bác sĩ",
        "occupation_en": "doctor",
        "participant_role": "đồng nghiệp",
        "participant_role_en": "colleague",
        "term_set": "nó",
        "narrator_position": "equal",
        "distractor_level": 3,
        "intro_vi": "Tôi nhắc đến nó — người bác sĩ trẻ mới vào ca.",
        "intro_en": "I mentioned nó — the young doctor who just started the shift.",
        "distractor_1_vi": "Ca trực đêm thường bắt đầu lúc mười một giờ.",
        "distractor_1_en": "The night shift usually starts at eleven o'clock.",
        "distractor_2_vi": "Phòng cấp cứu hôm nay tiếp nhận nhiều ca khó.",
        "distractor_2_en": "The emergency room received many difficult cases today.",
        "distractor_3_vi": "Các y tá đang bàn giao ca cho nhau ở cuối hành lang.",
        "distractor_3_en": "The nurses were handing over shifts at the end of the hallway.",
        "target_vi": "Đồng nghiệp hỏi tôi liệu _____ có rảnh để hỗ trợ không.",
        "target_en": "The colleague asked me whether _____ was free to help.",
        "correct_answer": "nó",
    },
    {
        "occupation": "kỹ sư",
        "occupation_en": "engineer",
        "participant_role": "sinh viên thực tập",
        "participant_role_en": "intern",
        "term_set": "hắn",
        "narrator_position": "equal",
        "distractor_level": 2,
        "intro_vi": "Tôi kể với bạn về hắn — tay kỹ sư hay làm trễ deadline.",
        "intro_en": "I told my friend about hắn — the engineer who always misses deadlines.",
        "distractor_1_vi": "Văn phòng gần đây hay có chuyện lặt vặt xảy ra.",
        "distractor_1_en": "The office has had a lot of small incidents recently.",
        "distractor_2_vi": "Mọi người trong nhóm đều biết vấn đề này từ lâu.",
        "distractor_2_en": "Everyone in the team has known about this issue for a long time.",
        "target_vi": "Sinh viên thực tập hỏi tôi liệu _____ có phụ trách dự án mới không.",
        "target_en": "The intern asked me whether _____ would be in charge of the new project.",
        "correct_answer": "hắn",
    },
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    DATA.mkdir(exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS annotators (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              username TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS instances (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              occupation TEXT NOT NULL,
              occupation_en TEXT NOT NULL,
              participant_role TEXT NOT NULL,
              participant_role_en TEXT NOT NULL,
              term_set TEXT NOT NULL,
              narrator_position TEXT NOT NULL,
              distractor_level INTEGER NOT NULL,
              intro_vi TEXT NOT NULL,
              intro_en TEXT NOT NULL,
              distractor_1_vi TEXT,
              distractor_1_en TEXT,
              distractor_2_vi TEXT,
              distractor_2_en TEXT,
              distractor_3_vi TEXT,
              distractor_3_en TEXT,
              distractor_4_vi TEXT,
              distractor_4_en TEXT,
              distractor_5_vi TEXT,
              distractor_5_en TEXT,
              target_vi TEXT NOT NULL,
              target_en TEXT NOT NULL,
              correct_answer TEXT NOT NULL,
              created_at TEXT NOT NULL,
              UNIQUE (occupation, term_set, narrator_position, distractor_level, intro_vi)
            );

            CREATE TABLE IF NOT EXISTS annotations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              instance_id INTEGER NOT NULL,
              annotator_id INTEGER NOT NULL,
              username TEXT NOT NULL,
              answer TEXT NOT NULL,
              reasoning TEXT,
              is_correct INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              submitted_at TEXT,
              FOREIGN KEY (instance_id) REFERENCES instances(id),
              FOREIGN KEY (annotator_id) REFERENCES annotators(id),
              UNIQUE (instance_id, annotator_id)
            );
            """
        )
        sync_canonical_instances(conn)


def seed_instances(conn):
    for row in CANONICAL_INSTANCES:
        insert_instance(conn, row)


def canonical_signature():
    return [(row["occupation"], row["term_set"], row["narrator_position"], int(row["distractor_level"]), row["intro_vi"]) for row in CANONICAL_INSTANCES]


def sync_canonical_instances(conn):
    existing = [
        (row["occupation"], row["term_set"], row["narrator_position"], int(row["distractor_level"]), row["intro_vi"])
        for row in conn.execute("SELECT occupation, term_set, narrator_position, distractor_level, intro_vi FROM instances ORDER BY id")
    ]
    if existing == canonical_signature():
        return
    conn.execute("DELETE FROM annotations")
    conn.execute("DELETE FROM instances")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('instances', 'annotations')")
    seed_instances(conn)


def row_to_dict(row):
    return dict(row) if row else None


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler, message, status=HTTPStatus.BAD_REQUEST):
    json_response(handler, {"error": message}, status)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def get_annotator(conn, username):
    return conn.execute("SELECT * FROM annotators WHERE username = ?", (username,)).fetchone()


def stable_queue(instance_ids, username):
    seed = sum(ord(char) for char in username)
    shuffled = list(instance_ids)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def instance_counts(conn, annotator_id):
    total = conn.execute("SELECT COUNT(*) FROM instances").fetchone()[0]
    saved = conn.execute(
        "SELECT COUNT(*) FROM annotations WHERE annotator_id = ? AND submitted_at IS NULL",
        (annotator_id,),
    ).fetchone()[0]
    submitted = conn.execute(
        "SELECT COUNT(*) FROM annotations WHERE annotator_id = ? AND submitted_at IS NOT NULL",
        (annotator_id,),
    ).fetchone()[0]
    return {"total": total, "saved": saved, "submitted": submitted, "remaining": total - saved - submitted}


def queue_for_user(conn, username):
    annotator = get_annotator(conn, username)
    if not annotator:
        raise ValueError("Unknown username")
    conn.execute("UPDATE annotators SET last_seen_at = ? WHERE id = ?", (now_iso(), annotator["id"]))
    all_ids = [r["id"] for r in conn.execute("SELECT id FROM instances ORDER BY id")]
    completed = [
        r["instance_id"]
        for r in conn.execute(
            "SELECT instance_id FROM annotations WHERE annotator_id = ? ORDER BY updated_at",
            (annotator["id"],),
        )
    ]
    completed_set = set(completed)
    remaining = [id_ for id_ in all_ids if id_ not in completed_set]
    return {
        "queue": stable_queue(remaining, username),
        "completed": completed,
        "counts": instance_counts(conn, annotator["id"]),
    }


def validate_username(username):
    return isinstance(username, str) and USERNAME_RE.match(username)


def insert_instance(conn, row):
    values = {header: row.get(header, "") for header in CSV_HEADERS}
    values["distractor_level"] = int(values["distractor_level"])
    values["created_at"] = now_iso()
    placeholders = ", ".join("?" for _ in values)
    columns = ", ".join(values.keys())
    sql = f"INSERT OR IGNORE INTO instances ({columns}) VALUES ({placeholders})"
    cur = conn.execute(sql, tuple(values.values()))
    return cur.rowcount == 1


def validate_csv_row(row, row_number):
    errors = []
    missing_headers = [header for header in CSV_HEADERS if header not in row]
    if missing_headers:
        return [{"row": row_number, "field": "headers", "message": f"Missing headers: {', '.join(missing_headers)}"}]
    required = [
        "occupation",
        "occupation_en",
        "participant_role",
        "participant_role_en",
        "term_set",
        "narrator_position",
        "distractor_level",
        "intro_vi",
        "intro_en",
        "target_vi",
        "target_en",
        "correct_answer",
    ]
    for field in required:
        if not (row.get(field) or "").strip():
            errors.append({"row": row_number, "field": field, "message": "Required field is missing"})
    try:
        level = int(row.get("distractor_level", ""))
        if level < 0 or level > 5:
            errors.append({"row": row_number, "field": "distractor_level", "message": "Must be between 0 and 5"})
    except ValueError:
        errors.append({"row": row_number, "field": "distractor_level", "message": "Must be a number between 0 and 5"})
    if row.get("correct_answer") not in VALID_TERMS:
        message = f"'{row.get('correct_answer')}' is not a valid term"
        if row.get("correct_answer") == "ong":
            message += " (did you mean ông?)"
        errors.append({"row": row_number, "field": "correct_answer", "message": message})
    return errors


def parse_multipart_csv(handler):
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length)
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    for part in message.iter_parts():
        params = dict(part.get_params(header="content-disposition", failobj=[]))
        if params.get("name") == "file":
            return part.get_payload(decode=True).decode("utf-8-sig")
    raise ValueError("Expected multipart field named file")


def request_secret(handler, query=None):
    query = query or parse_qs(urlparse(handler.path).query)
    authorization = handler.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "", 1).strip()
    return (
        handler.headers.get("X-Admin-Secret")
        or handler.headers.get("X-Admin-Key")
        or query.get("key", [""])[0]
    )


def is_admin_request(handler, query=None):
    return request_secret(handler, query) == ADMIN_SECRET


def require_admin(handler, query=None):
    if is_admin_request(handler, query):
        return True
    error_response(handler, "Admin key required", HTTPStatus.UNAUTHORIZED)
    return False


def annotator_rows(conn):
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT
              u.username,
              u.created_at AS registered,
              u.last_seen_at,
              SUM(CASE WHEN a.id IS NOT NULL AND a.submitted_at IS NULL THEN 1 ELSE 0 END) AS saved,
              SUM(CASE WHEN a.submitted_at IS NOT NULL THEN 1 ELSE 0 END) AS submitted,
              ROUND(100.0 * SUM(CASE WHEN a.is_correct = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(a.id), 0), 1) AS accuracy
            FROM annotators u
            LEFT JOIN annotations a ON a.annotator_id = u.id
            GROUP BY u.id
            ORDER BY u.created_at DESC
            """
        )
    ]


def annotation_rows(conn, username=""):
    params = []
    where = ""
    if username:
        where = "WHERE a.username = ?"
        params.append(username)
    return [
        dict(r)
        for r in conn.execute(
            f"""
            SELECT a.*, i.correct_answer, i.occupation, i.participant_role, i.term_set, i.distractor_level
            FROM annotations a
            JOIN instances i ON i.id = a.instance_id
            {where}
            ORDER BY a.updated_at DESC
            """,
            params,
        )
    ]


def cohen_kappa(answers_a, answers_b):
    total = len(answers_a)
    if total == 0:
        return None
    observed = sum(1 for a, b in zip(answers_a, answers_b) if a == b) / total
    labels = sorted(set(answers_a) | set(answers_b))
    expected = 0
    for label in labels:
        pa = answers_a.count(label) / total
        pb = answers_b.count(label) / total
        expected += pa * pb
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return (observed - expected) / (1 - expected)


def agreement_summary(conn):
    rows = annotation_rows(conn)
    by_user = {}
    by_instance = {}
    for row in rows:
        by_user.setdefault(row["username"], {})[row["instance_id"]] = row["answer"]
        by_instance.setdefault(row["instance_id"], []).append(row)

    users = sorted(by_user)
    pairs = []
    for index, user_a in enumerate(users):
        for user_b in users[index + 1 :]:
            shared = sorted(set(by_user[user_a]) & set(by_user[user_b]))
            answers_a = [by_user[user_a][instance_id] for instance_id in shared]
            answers_b = [by_user[user_b][instance_id] for instance_id in shared]
            agreements = sum(1 for a, b in zip(answers_a, answers_b) if a == b)
            total = len(shared)
            pairs.append(
                {
                    "annotator_a": user_a,
                    "annotator_b": user_b,
                    "shared_instances": total,
                    "agreements": agreements,
                    "percent_agreement": round((agreements / total) * 100, 1) if total else None,
                    "cohen_kappa": round(cohen_kappa(answers_a, answers_b), 3) if total else None,
                }
            )

    comparable_pairs = [pair for pair in pairs if pair["shared_instances"]]
    overall = {
        "annotators": len(users),
        "pair_count": len(comparable_pairs),
        "mean_percent_agreement": round(
            sum(pair["percent_agreement"] for pair in comparable_pairs) / len(comparable_pairs), 1
        )
        if comparable_pairs
        else None,
        "mean_cohen_kappa": round(sum(pair["cohen_kappa"] for pair in comparable_pairs) / len(comparable_pairs), 3)
        if comparable_pairs
        else None,
    }

    instance_agreement = []
    for instance_id, annotations in sorted(by_instance.items()):
        answers = [row["answer"] for row in annotations]
        majority_answer = max(set(answers), key=answers.count)
        instance_agreement.append(
            {
                "instance_id": instance_id,
                "annotations": len(answers),
                "unique_answers": len(set(answers)),
                "unanimous": len(set(answers)) == 1,
                "majority_answer": majority_answer,
                "majority_count": answers.count(majority_answer),
            }
        )
    return {"overall": overall, "pairs": pairs, "instances": instance_agreement}


def admin_payload(conn):
    return {
        "instances": [dict(r) for r in conn.execute("SELECT * FROM instances ORDER BY id")],
        "annotators": annotator_rows(conn),
        "annotations": annotation_rows(conn),
        "agreement": agreement_summary(conn),
    }


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/api/instances/queue":
                username = query.get("username", [""])[0]
                with connect() as conn:
                    json_response(self, queue_for_user(conn, username))
                return
            if path == "/api/instances":
                with connect() as conn:
                    rows = [dict(r) for r in conn.execute("SELECT * FROM instances ORDER BY id")]
                    json_response(self, {"instances": rows})
                return
            if path == "/api/annotations":
                if not require_admin(self, query):
                    return
                username = query.get("username", [""])[0]
                with connect() as conn:
                    json_response(self, {"annotations": annotation_rows(conn, username)})
                return
            if path == "/api/annotators":
                if not require_admin(self, query):
                    return
                with connect() as conn:
                    json_response(self, {"annotators": annotator_rows(conn)})
                return
            if path == "/api/admin":
                if not require_admin(self, query):
                    return
                with connect() as conn:
                    json_response(self, admin_payload(conn))
                return
            if path == "/api/agreement":
                if not require_admin(self, query):
                    return
                with connect() as conn:
                    json_response(self, {"agreement": agreement_summary(conn)})
                return
            if path == "/api/instances/template":
                body = io.StringIO()
                writer = csv.DictWriter(body, fieldnames=CSV_HEADERS)
                writer.writeheader()
                writer.writerow(CANONICAL_INSTANCES[0])
                data = body.getvalue().encode("utf-8-sig")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="instances_template.csv"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/results":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/admin")
                self.end_headers()
                return
            if path in {"/", "/admin", "/admin/import"}:
                filename = "index.html" if path == "/" else path.strip("/") + ".html"
                self.serve_file(STATIC / filename)
                return
            if path.startswith("/static/"):
                self.serve_file(ROOT / path.strip("/"))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            error_response(self, str(exc), HTTPStatus.BAD_REQUEST)
        except ValueError as exc:
            error_response(self, str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            error_response(self, str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/annotators/check":
                data = read_json(self)
                username = data.get("username", "")
                if not validate_username(username):
                    error_response(self, "Invalid username")
                    return
                with connect() as conn:
                    available = get_annotator(conn, username) is None
                    json_response(self, {"available": available})
                return
            if path == "/api/annotators/register":
                data = read_json(self)
                username = data.get("username", "")
                if not validate_username(username):
                    error_response(self, "Invalid username")
                    return
                with connect() as conn:
                    try:
                        conn.execute(
                            "INSERT INTO annotators (username, created_at, last_seen_at) VALUES (?, ?, ?)",
                            (username, now_iso(), now_iso()),
                        )
                    except sqlite3.IntegrityError:
                        error_response(self, "Username already taken", HTTPStatus.CONFLICT)
                        return
                    annotator = row_to_dict(get_annotator(conn, username))
                    json_response(self, annotator, HTTPStatus.CREATED)
                return
            if path == "/api/annotations":
                data = read_json(self)
                username = data.get("username", "")
                instance_id = int(data.get("instance_id", 0))
                answer = data.get("answer", "")
                reasoning = data.get("reasoning", "")
                if answer not in VALID_TERMS:
                    error_response(self, "Invalid answer")
                    return
                with connect() as conn:
                    annotator = get_annotator(conn, username)
                    instance = conn.execute("SELECT * FROM instances WHERE id = ?", (instance_id,)).fetchone()
                    if not annotator or not instance:
                        error_response(self, "Unknown annotator or instance")
                        return
                    existing = conn.execute(
                        "SELECT submitted_at FROM annotations WHERE instance_id = ? AND annotator_id = ?",
                        (instance_id, annotator["id"]),
                    ).fetchone()
                    if existing and existing["submitted_at"]:
                        error_response(self, "Submitted annotations are locked", HTTPStatus.CONFLICT)
                        return
                    is_correct = 1 if answer == instance["correct_answer"] else 0
                    stamp = now_iso()
                    conn.execute("UPDATE annotators SET last_seen_at = ? WHERE id = ?", (stamp, annotator["id"]))
                    conn.execute(
                        """
                        INSERT INTO annotations
                          (instance_id, annotator_id, username, answer, reasoning, is_correct, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(instance_id, annotator_id) DO UPDATE SET
                          answer = excluded.answer,
                          reasoning = excluded.reasoning,
                          is_correct = excluded.is_correct,
                          updated_at = excluded.updated_at
                        """,
                        (instance_id, annotator["id"], username, answer, reasoning, is_correct, stamp, stamp),
                    )
                    json_response(self, {"ok": True, "is_correct": bool(is_correct), "counts": instance_counts(conn, annotator["id"])})
                return
            if path == "/api/annotations/submit":
                data = read_json(self)
                username = data.get("username", "")
                with connect() as conn:
                    annotator = get_annotator(conn, username)
                    if not annotator:
                        error_response(self, "Unknown username")
                        return
                    cur = conn.execute(
                        "UPDATE annotations SET submitted_at = ? WHERE annotator_id = ? AND submitted_at IS NULL",
                        (now_iso(), annotator["id"]),
                    )
                    json_response(self, {"submitted_count": cur.rowcount, "counts": instance_counts(conn, annotator["id"])})
                return
            if path == "/api/instances/import":
                if not require_admin(self):
                    return
                text = parse_multipart_csv(self)
                reader = csv.DictReader(io.StringIO(text))
                rows = list(reader)
                errors = []
                for index, row in enumerate(rows, start=2):
                    errors.extend(validate_csv_row(row, index))
                if errors:
                    json_response(self, {"inserted": 0, "skipped_duplicates": 0, "errors": errors}, HTTPStatus.BAD_REQUEST)
                    return
                inserted = 0
                skipped = 0
                with connect() as conn:
                    for row in rows:
                        for level in range(int(row["distractor_level"]) + 1, 6):
                            row[f"distractor_{level}_vi"] = ""
                            row[f"distractor_{level}_en"] = ""
                        if insert_instance(conn, row):
                            inserted += 1
                        else:
                            skipped += 1
                json_response(self, {"inserted": inserted, "skipped_duplicates": skipped, "errors": []})
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            error_response(self, str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_file(self, path):
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8"
        if path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        if path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    init_db()
    port = int(os.environ["PORT"])
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"RUFF-VI Annotation running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
