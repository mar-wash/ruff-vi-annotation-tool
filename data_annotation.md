## Annotator identity: unique username system

Replace the simple "enter your name" flow with a proper username system 
that supports session persistence and progress resumption.

### Username onboarding flow

On first visit (no username in localStorage), show a fullscreen welcome modal 
before anything else:

  Title: "Welcome to RUFF-VI Annotation"
  Subtitle: "Choose a unique annotator username to begin. 
             You can return anytime and pick up where you left off."

  Input field:
    - Placeholder: "e.g. annotator_01, nguyen_ha, marshall_w"
    - Validation: 3–24 characters, alphanumeric + underscores only 
      (regex: /^[a-zA-Z0-9_]{3,24}$/)
    - On submit: POST /api/annotators/check to verify uniqueness
        If taken: show inline error "Username already taken — try another"
        If available: POST /api/annotators/register, store username in 
          localStorage as "ruffvi_username", close modal, begin annotation

  "Continue as [username]" shortcut: if username exists in localStorage, 
  show a smaller returning-user banner instead of the full modal:
    "Welcome back, [username]. You have X instances remaining."
    [Continue] [Switch user] buttons
    "Switch user" clears localStorage and shows the full modal again.

### Database changes

Add an annotators table:
  id, username (unique), created_at, last_seen_at

Update annotations table:
  Replace annotator_name text field with annotator_id (foreign key → annotators.id)
  Keep a username denormalized field for easy querying without joins.

### Session persistence: resume where you left off

On load, after username is confirmed:
  GET /api/instances/queue?username=X
  Returns the list of instance IDs not yet annotated by this user, 
  in a stable random order seeded by username (so the order is consistent 
  across sessions for the same user — use a seeded shuffle, e.g. 
  seed = sum of char codes of username).
  
  The frontend stores this queue in localStorage as "ruffvi_queue_[username]".
  On resume, restore position from localStorage. If localStorage queue is 
  missing or stale (server has new instances), re-fetch and merge: 
  already-annotated instances go to the end marked complete, 
  unannotated ones come first.

Progress indicator in top bar:
  "X of Y annotated" with a filled progress bar.
  On hover/tap: show a small popover "Y-X remaining · Session started [date]"

### Submission flow

Add a "Submit annotations" button in the top bar (only visible once the 
annotator has completed at least 1 annotation).

On click, show a confirmation modal:
  Title: "Submit your annotations"
  Body:
    "You have completed X of Y instances.
     Submitted annotations are locked and cannot be changed.
     Unsubmitted work is saved automatically — you can always 
     come back and submit more later."
  
  Two options:
    [Submit completed work] — submits all annotations made so far
    [Cancel]

POST /api/annotations/submit { username }
  Sets a submitted_at timestamp on all annotations by this user 
  that don't already have one.
  Returns { submitted_count: N }

After submission: show a success banner
  "✓ X annotations submitted. Thank you, [username]!"
  The progress bar segment for submitted work turns a darker color 
  (e.g. solid blue vs lighter blue for saved-but-unsubmitted).

### Progress visualization (top bar)

Replace the simple progress bar with a segmented bar:
  - Dark blue  = submitted annotations
  - Light blue = saved but not yet submitted  
  - Gray       = remaining

Show counts below: "12 submitted · 4 saved · 9 remaining"

### API routes to add

POST /api/annotators/check      { username } → { available: bool }
POST /api/annotators/register   { username } → { id, username, created_at }
GET  /api/instances/queue       ?username=X  → { queue: [id, ...], completed: [id, ...] }
POST /api/annotations/submit    { username } → { submitted_count: N }
GET  /api/annotators            → list of all annotators with counts 
                                  (for researcher dashboard)

### Results dashboard changes

Add an "Annotators" section to /results:
  Table: username | registered | last seen | saved | submitted | accuracy %
  
  Clicking a username filters the entire results dashboard 
  (charts + annotation table + reasoning browser) to that annotator only.
  Show a "[username] only — clear filter" chip when filtered.

### localStorage keys used (document these in README)

  ruffvi_username              — current annotator username
  ruffvi_queue_[username]      — ordered instance queue for this user
  ruffvi_skip_warning_shown    — whether the "skip reasoning" warning 
                                 has been shown this session

## Instance management: CSV import system

### CSV format

The canonical import format is a CSV file with these exact headers:

  occupation, occupation_en, participant_role, participant_role_en,
  term_set, narrator_position, distractor_level,
  intro_vi, intro_en,
  distractor_1_vi, distractor_1_en,
  distractor_2_vi, distractor_2_en,
  distractor_3_vi, distractor_3_en,
  distractor_4_vi, distractor_4_en,
  distractor_5_vi, distractor_5_en,
  target_vi, target_en,
  correct_answer

Rules:
  - distractor_level must be 0–5
  - distractor columns beyond distractor_level are ignored on import
  - correct_answer must be one of: anh, chị, cô, chú, ông, bà, em, nó, hắn, chanh
  - Rows with missing required fields are rejected with a row number and reason
  - Duplicate detection: if a row matches an existing instance on 
    (occupation + term_set + narrator_position + distractor_level + intro_vi), 
    skip it and report it as a duplicate rather than erroring

### API route

POST /api/instances/import
  - Accepts multipart/form-data with a single field "file" (CSV)
  - Parses with csv-parse (npm)
  - Validates every row before inserting any (all-or-nothing per batch, 
    duplicates excepted)
  - Returns:
    {
      inserted: N,
      skipped_duplicates: N,
      errors: [{ row: N, field: "...", message: "..." }]
    }

### Admin import UI at /admin/import

Simple page, no auth (researcher use only — note this in README).

  Drag-and-drop CSV upload zone (or click to browse)
  On upload: preview the first 5 rows in a table before confirming
  
  Preview table columns:
    occupation | term set | narrator | D-level | intro (truncated) | correct answer

  Two buttons below preview:
    [Import X rows] — proceeds with import
    [Cancel]

  After import: show result summary
    "✓ 47 instances imported · 3 duplicates skipped · 0 errors"
    If there are errors, show them in a collapsible red panel:
      "Row 12 — correct_answer: 'ong' is not a valid term (did you mean ông?)"

  Link back to main annotation view.

### Queue refresh after import

When new instances are added, existing annotators' queues are automatically 
extended on their next login:
  - GET /api/instances/queue re-fetches if localStorage queue length 
    doesn't match server's unannotated count for that user
  - New instances are appended to the end of the existing queue 
    (don't reshuffle already-ordered items)
  - Top bar shows a subtle "X new instances added since your last session" 
    notice on resume if the queue grew

### Template download

On /admin/import, include a "Download CSV template" button that serves 
a pre-filled CSV with one example row (the bác sĩ / anh instance from 
the seed data) and all headers, so you always have a valid starting point 
for new batches.

### README section to add

  ## Loading new instances

  1. Fill out instances.csv using the template (download from /admin/import)
  2. Go to /admin/import in the browser
  3. Drag in your CSV and confirm the preview
  4. Existing annotator queues will automatically extend on next login
  
  Alternatively, import from the command line:
    curl -X POST http://localhost:3000/api/instances/import \
      -F "file=@instances.csv"

      Instance 1:
  occupation: "bác sĩ", occupation_en: "doctor"
  participant_role: "bệnh nhân", participant_role_en: "patient"
  term_set: "anh", narrator_position: "younger"
  distractor_level: 2
  intro_vi: "Tôi gặp anh bác sĩ hôm nay tại phòng khám."
  intro_en: "I met the anh doctor at the clinic today."
  distractor_1_vi: "Phòng khám hôm nay khá đông bệnh nhân."
  distractor_1_en: "The clinic was quite busy with patients today."
  distractor_2_vi: "Trời bên ngoài rất nóng và oi bức."
  distractor_2_en: "The weather outside was very hot and humid."
  target_vi: "Bệnh nhân đã hỏi _____ về lịch hẹn tiếp theo."
  target_en: "The patient asked _____ about the next appointment."
  correct_answer: "anh"

Instance 2:
  occupation: "giáo viên", occupation_en: "teacher"
  participant_role: "học sinh", participant_role_en: "student"
  term_set: "cô", narrator_position: "younger"
  distractor_level: 1
  intro_vi: "Học sinh chào cô giáo trước khi vào lớp."
  intro_en: "The student greeted the cô teacher before entering class."
  distractor_1_vi: "Cửa sổ lớp học để mở vì trời mát."
  distractor_1_en: "The classroom windows were open because the weather was cool."
  target_vi: "Học sinh hỏi _____ về bài tập về nhà."
  target_en: "The student asked _____ about the homework."
  correct_answer: "cô"

Instance 3:
  occupation: "kỹ sư", occupation_en: "engineer"
  participant_role: "thực tập sinh", participant_role_en: "intern"
  term_set: "chanh", narrator_position: "equal"
  distractor_level: 0
  intro_vi: "Thực tập sinh làm việc cùng chanh kỹ sư trong dự án mới."
  intro_en: "The intern worked with the chanh engineer on the new project."
  target_vi: "Thực tập sinh hỏi _____ về tiến độ công việc."
  target_en: "The intern asked _____ about the work progress."
  correct_answer: "chanh"

## UI — Annotation view (main screen)

Layout: centered single column, max-width 720px

Top bar:
  - "RUFF-VI Annotation Tool" title left
  - Annotator name right (click to change)
  - Progress: "X / Y annotated" with a thin progress bar below the bar

Instance card:
  - Metadata chips row: occupation | term set | narrator position | 
    distractor level (colored badges)
  - Color-coded sentence display:
      Green background  → Introduction sentence (Vietnamese bold, English italic below)
      Yellow background → Each distractor sentence (labeled D1, D2...)
      Red/pink background → Target sentence, with "____" displayed prominently
  - Below the target: 10 forced-choice buttons in a 2×5 grid:
      anh, chị, cô, chú, ông, bà, em, nó, hắn, chanh
  - On selection: immediately show feedback
      Correct: green flash + "✓ Correct — [term] is right because [brief reason]"
      Incorrect: red flash + "✗ [selected] is not correct here. The answer is [correct]."
  - "Next instance →" button appears after selection

Brief reason strings to hardcode by (term_set, narrator_position):
  anh/younger: "narrator is younger → anh shows respect to the older male referent"
  cô/younger: "narrator is younger → cô is the appropriate form for an adult female elder"
  chanh/equal: "chanh is a gender-neutral term used by and for queer speakers"
  (for any other combo: "this term fits the social relationship between narrator and referent")

## UI — Results dashboard (/results)

Accessible via a "View results" link in the top bar.

Show:
  - Overall accuracy % (big number)
  - Table: instance id | occupation | term set | distractor level | 
    annotator answer | correct answer | ✓/✗ | response time
  - Bar chart (use Recharts) of accuracy by distractor level (0–5)
  - Bar chart of accuracy by term set
  - Export CSV button (downloads all annotations as CSV)

## API routes

POST /api/annotations        — save an annotation
GET  /api/annotations        — return all annotations
GET  /api/instances          — return all instances
GET  /api/instances/:id      — return single instance
GET  /api/stats              — return accuracy by distractor_level and by term_set

## Additional requirements

- Timer: record response_time_ms from when the instance renders to when 
  the annotator clicks an answer
- Instances are served in random order, never repeating within a session 
  until all are exhausted
- Vietnamese text must render correctly — use font-family: 
  'Noto Sans', 'Be Vietnam Pro', sans-serif with proper Unicode support
- Mobile-friendly (works on tablet for annotators)
- No build/deploy complexity: runs with `npm install && npm run dev` from root
- Include a README with setup instructions and a brief description of the task

A few things worth calling out for when you paste this in:
The reason strings — I hardcoded brief explanations only for the three seed instances' combinations. You'll want to expand that lookup table as you add more instances, or eventually pull the rationale from the database itself.
CSV export — useful for feeding annotations directly into your inter-annotator agreement calculations (you mentioned targeting ≥95% human accuracy ceiling).
Response time tracking — Codex will wire this up, but it's worth double-checking the timer resets properly between instances, since that's a meaningful signal for difficulty analysis by distractor level.
Scaling up — once you move past the 3 seed instances to the full ~600-instance annotation sample, you'll want to swap the hardcoded seed data for a CSV import route. You can ask Codex to add POST /api/import-csv as a follow-up.You said: can you make it so that the users can put in and save reasonscan you make it so that the users can put in and save reasons9:40 PMClaude responded: Here's the addition to append to your Codex prompt:Here's the addition to append to your Codex prompt:

Append to your existing prompt:
## Additional feature: annotator reasoning field

After the annotator selects a term and sees the correct/incorrect feedback, 
show a text area for them to record their reasoning before proceeding.

### UI changes

After answer selection, below the feedback banner, add:

  Label: "Why did you choose this? (optional)"
  - Multiline textarea, min 3 rows, max ~500 characters
  - Placeholder: "Explain your reasoning — e.g. the narrator seems younger 
    based on the introduction, so anh is appropriate..."
  - Character counter bottom-right of textarea (e.g. "142 / 500")
  - Vietnamese keyboard-friendly: same Noto Sans / Be Vietnam Pro font stack
  - The textarea should appear with a smooth fade-in after answer selection

  Below the textarea:
  - "Next instance →" button (disabled until answer is selected, 
    enabled regardless of whether reasoning is filled in)
  - If the annotator clicks "Next" with an empty reasoning field, show a 
    soft one-time prompt: "No reason entered — are you sure? 
    [Skip anyway] [Add reason]". After the first skip, never show this 
    prompt again in the session (store in localStorage as 
    "ruffvi_skip_warning_shown").

### Database changes

Add a `reasoning` TEXT column (nullable) to the annotations table.
Update the seed migration to include this column.

### API changes

POST /api/annotations body now accepts an optional `reasoning` field.
Store it as-is (no sanitization beyond trimming whitespace).

### Results dashboard changes

In the annotations table on /results, add a "Reasoning" column. 
If reasoning is present, show the first 60 characters with a "..." 
tooltip/popover that reveals the full text on hover.

In the CSV export, include the `reasoning` column.

### Inter-annotator view (add to /results)

Add a new section below the charts called "Reasoning browser":
  - A filterable list of all annotations that have non-empty reasoning
  - Filter controls: by term set (dropdown), by correct/incorrect (toggle), 
    by distractor level (0–5 pills)
  - Each entry shows:
      [occupation chip] [term set chip] [D-level chip]
      Annotator answer (✓ or ✗) | Correct answer
      Reasoning text (full, not truncated)
  - This section is intended for the researcher to review qualitative 
    patterns in annotator reasoning

The reasoning browser is the most useful addition beyond just storing the field — it lets you spot patterns qualitatively, like whether annotators consistently give different explanations for chanh errors vs. nó/hắn errors, which would be hard to see just from accuracy numbers.You said: the annotator should choose a unique user name and there should be the ability to submit your annotations and see where you left offthe annotator should choose a unique user name and there should be the ability to submit your annotations and see where you left off9:41 PMClaude responded: Add this to your prompt:Add this to your prompt:

Append to your existing prompt:
## Annotator identity: unique username system

Replace the simple "enter your name" flow with a proper username system 
that supports session persistence and progress resumption.

### Username onboarding flow

On first visit (no username in localStorage), show a fullscreen welcome modal 
before anything else:

  Title: "Welcome to RUFF-VI Annotation"
  Subtitle: "Choose a unique annotator username to begin. 
             You can return anytime and pick up where you left off."

  Input field:
    - Placeholder: "e.g. annotator_01, nguyen_ha, marshall_w"
    - Validation: 3–24 characters, alphanumeric + underscores only 
      (regex: /^[a-zA-Z0-9_]{3,24}$/)
    - On submit: POST /api/annotators/check to verify uniqueness
        If taken: show inline error "Username already taken — try another"
        If available: POST /api/annotators/register, store username in 
          localStorage as "ruffvi_username", close modal, begin annotation

  "Continue as [username]" shortcut: if username exists in localStorage, 
  show a smaller returning-user banner instead of the full modal:
    "Welcome back, [username]. You have X instances remaining."
    [Continue] [Switch user] buttons
    "Switch user" clears localStorage and shows the full modal again.

### Database changes

Add an annotators table:
  id, username (unique), created_at, last_seen_at

Update annotations table:
  Replace annotator_name text field with annotator_id (foreign key → annotators.id)
  Keep a username denormalized field for easy querying without joins.

### Session persistence: resume where you left off

On load, after username is confirmed:
  GET /api/instances/queue?username=X
  Returns the list of instance IDs not yet annotated by this user, 
  in a stable random order seeded by username (so the order is consistent 
  across sessions for the same user — use a seeded shuffle, e.g. 
  seed = sum of char codes of username).
  
  The frontend stores this queue in localStorage as "ruffvi_queue_[username]".
  On resume, restore position from localStorage. If localStorage queue is 
  missing or stale (server has new instances), re-fetch and merge: 
  already-annotated instances go to the end marked complete, 
  unannotated ones come first.

Progress indicator in top bar:
  "X of Y annotated" with a filled progress bar.
  On hover/tap: show a small popover "Y-X remaining · Session started [date]"

### Submission flow

Add a "Submit annotations" button in the top bar (only visible once the 
annotator has completed at least 1 annotation).

On click, show a confirmation modal:
  Title: "Submit your annotations"
  Body:
    "You have completed X of Y instances.
     Submitted annotations are locked and cannot be changed.
     Unsubmitted work is saved automatically — you can always 
     come back and submit more later."
  
  Two options:
    [Submit completed work] — submits all annotations made so far
    [Cancel]

POST /api/annotations/submit { username }
  Sets a submitted_at timestamp on all annotations by this user 
  that don't already have one.
  Returns { submitted_count: N }

After submission: show a success banner
  "✓ X annotations submitted. Thank you, [username]!"
  The progress bar segment for submitted work turns a darker color 
  (e.g. solid blue vs lighter blue for saved-but-unsubmitted).

### Progress visualization (top bar)

Replace the simple progress bar with a segmented bar:
  - Dark blue  = submitted annotations
  - Light blue = saved but not yet submitted  
  - Gray       = remaining

Show counts below: "12 submitted · 4 saved · 9 remaining"

### API routes to add

POST /api/annotators/check      { username } → { available: bool }
POST /api/annotators/register   { username } → { id, username, created_at }
GET  /api/instances/queue       ?username=X  → { queue: [id, ...], completed: [id, ...] }
POST /api/annotations/submit    { username } → { submitted_count: N }
GET  /api/annotators            → list of all annotators with counts 
                                  (for researcher dashboard)

### Results dashboard changes

Add an "Annotators" section to /results:
  Table: username | registered | last seen | saved | submitted | accuracy %
  
  Clicking a username filters the entire results dashboard 
  (charts + annotation table + reasoning browser) to that annotator only.
  Show a "[username] only — clear filter" chip when filtered.

### localStorage keys used (document these in README)

  ruffvi_username              — current annotator username
  ruffvi_queue_[username]      — ordered instance queue for this user
  ruffvi_skip_warning_shown    — whether the "skip reasoning" warning 
                                 has been shown this session

A couple of things to flag when Codex builds this:
The seeded shuffle is important — without it, every time an annotator returns their queue reshuffles and you lose the stable ordering, which makes it harder to analyze whether performance degrades across a session. Make sure Codex implements a proper seeded PRNG (a simple mulberry32 or similar is fine) rather than Math.random().
The segmented progress bar gives annotators a clear sense of what's saved locally vs. what's actually been transmitted to the database, which reduces anxiety about losing work.
The annotator table on /results is mainly for you as the researcher — you can see at a glance who has submitted, who is partway through, and pull per-annotator accuracy to compute inter-annotator agreement before running your Welch's t-tests.You said: how can i load more instances in the future?how can i load more instances in the future?9:44 PMClaude responded: The cleanest approach is a CSV import route.The cleanest approach is a CSV import route. Add this to your prompt:

Append to your existing prompt:
## Instance management: CSV import system

### CSV format

The canonical import format is a CSV file with these exact headers:

  occupation, occupation_en, participant_role, participant_role_en,
  term_set, narrator_position, distractor_level,
  intro_vi, intro_en,
  distractor_1_vi, distractor_1_en,
  distractor_2_vi, distractor_2_en,
  distractor_3_vi, distractor_3_en,
  distractor_4_vi, distractor_4_en,
  distractor_5_vi, distractor_5_en,
  target_vi, target_en,
  correct_answer

Rules:
  - distractor_level must be 0–5
  - distractor columns beyond distractor_level are ignored on import
  - correct_answer must be one of: anh, chị, cô, chú, ông, bà, em, nó, hắn, chanh
  - Rows with missing required fields are rejected with a row number and reason
  - Duplicate detection: if a row matches an existing instance on 
    (occupation + term_set + narrator_position + distractor_level + intro_vi), 
    skip it and report it as a duplicate rather than erroring

### API route

POST /api/instances/import
  - Accepts multipart/form-data with a single field "file" (CSV)
  - Parses with csv-parse (npm)
  - Validates every row before inserting any (all-or-nothing per batch, 
    duplicates excepted)
  - Returns:
    {
      inserted: N,
      skipped_duplicates: N,
      errors: [{ row: N, field: "...", message: "..." }]
    }

### Admin import UI at /admin/import

Simple page, no auth (researcher use only — note this in README).

  Drag-and-drop CSV upload zone (or click to browse)
  On upload: preview the first 5 rows in a table before confirming
  
  Preview table columns:
    occupation | term set | narrator | D-level | intro (truncated) | correct answer

  Two buttons below preview:
    [Import X rows] — proceeds with import
    [Cancel]

  After import: show result summary
    "✓ 47 instances imported · 3 duplicates skipped · 0 errors"
    If there are errors, show them in a collapsible red panel:
      "Row 12 — correct_answer: 'ong' is not a valid term (did you mean ông?)"

  Link back to main annotation view.

### Queue refresh after import

When new instances are added, existing annotators' queues are automatically 
extended on their next login:
  - GET /api/instances/queue re-fetches if localStorage queue length 
    doesn't match server's unannotated count for that user
  - New instances are appended to the end of the existing queue 
    (don't reshuffle already-ordered items)
  - Top bar shows a subtle "X new instances added since your last session" 
    notice on resume if the queue grew

### Template download

On /admin/import, include a "Download CSV template" button that serves 
a pre-filled CSV with one example row (the bác sĩ / anh instance from 
the seed data) and all headers, so you always have a valid starting point 
for new batches.

### README section to add

  ## Loading new instances

  1. Fill out instances.csv using the template (download from /admin/import)
  2. Go to /admin/import in the browser
  3. Drag in your CSV and confirm the preview
  4. Existing annotator queues will automatically extend on next login
  
  Alternatively, import from the command line:
    curl -X POST http://localhost:3000/api/instances/import \
      -F "file=@instances.csv"

Here are the instances:

---

**Instance 1**
occupation: "bác sĩ", occupation_en: "doctor"
participant_role: "bệnh nhân", participant_role_en: "patient"
term_set: "anh", narrator_position: "younger"
distractor_level: 2
intro_vi: "Tôi gặp anh bác sĩ hôm nay tại phòng khám."
intro_en: "I met the anh doctor at the clinic today."
distractor_1_vi: "Phòng khám hôm nay khá đông bệnh nhân."
distractor_1_en: "The clinic was quite busy with patients today."
distractor_2_vi: "Trời bên ngoài rất nóng và oi bức."
distractor_2_en: "The weather outside was very hot and humid."
target_vi: "Bệnh nhân đã hỏi _____ về lịch hẹn tiếp theo."
target_en: "The patient asked _____ about the next appointment."
correct_answer: "anh"

---

**Instance 2**
occupation: "giáo viên", occupation_en: "teacher"
participant_role: "học sinh", participant_role_en: "student"
term_set: "cô", narrator_position: "younger"
distractor_level: 1
intro_vi: "Học sinh chào cô giáo trước khi vào lớp."
intro_en: "The student greeted the cô teacher before entering class."
distractor_1_vi: "Cửa sổ lớp học để mở vì trời mát."
distractor_1_en: "The classroom windows were open because the weather was cool."
target_vi: "Học sinh hỏi _____ về bài tập về nhà."
target_en: "The student asked _____ about the homework."
correct_answer: "cô"

---

**Instance 3**
occupation: "kỹ sư", occupation_en: "engineer"
participant_role: "thực tập sinh", participant_role_en: "intern"
term_set: "chanh", narrator_position: "equal"
distractor_level: 0
intro_vi: "Thực tập sinh làm việc cùng chanh kỹ sư trong dự án mới."
intro_en: "The intern worked with the chanh engineer on the new project."
target_vi: "Thực tập sinh hỏi _____ về tiến độ công việc."
target_en: "The intern asked _____ about the work progress."
correct_answer: "chanh"

---

**Instance 4**
occupation: "nông dân", occupation_en: "farmer"
participant_role: "người mua", participant_role_en: "buyer"
term_set: "ông", narrator_position: "younger"
distractor_level: 3
intro_vi: "Tôi gặp ông nông dân tại chợ buổi sáng."
intro_en: "I met the ông farmer at the morning market."
distractor_1_vi: "Chợ hôm nay có nhiều loại rau củ tươi."
distractor_1_en: "The market had many kinds of fresh vegetables today."
distractor_2_vi: "Một vài người bán hàng đang sắp xếp lại quầy."
distractor_2_en: "Some vendors were rearranging their stalls."
distractor_3_vi: "Trời sáng sớm nên không khí còn mát mẻ."
distractor_3_en: "It was early morning so the air was still cool."
target_vi: "Người mua hỏi _____ về giá rau hôm nay."
target_en: "The buyer asked _____ about the price of vegetables today."
correct_answer: "ông"

---

**Instance 5**
occupation: "bác sĩ", occupation_en: "doctor"
participant_role: "bệnh nhân", participant_role_en: "patient"
term_set: "bà", narrator_position: "younger"
distractor_level: 4
intro_vi: "Tôi được gặp bà bác sĩ phụ trách ca trực hôm nay."
intro_en: "I got to meet the bà doctor on duty today."
distractor_1_vi: "Hành lang bệnh viện khá yên tĩnh vào buổi chiều."
distractor_1_en: "The hospital hallway was quite quiet in the afternoon."
distractor_2_vi: "Có mùi thuốc sát trùng nhẹ trong không khí."
distractor_2_en: "There was a faint smell of antiseptic in the air."
distractor_3_vi: "Một y tá đang đẩy xe thuốc qua hành lang."
distractor_3_en: "A nurse was pushing a medicine cart through the hallway."
distractor_4_vi: "Ánh đèn trong phòng khám sáng và trắng."
distractor_4_en: "The lights in the examination room were bright and white."
target_vi: "Bệnh nhân hỏi _____ về kết quả xét nghiệm."
target_en: "The patient asked _____ about the test results."
correct_answer: "bà"

---

**Instance 6**
occupation: "giáo viên", occupation_en: "teacher"
participant_role: "học sinh", participant_role_en: "student"
term_set: "chú", narrator_position: "younger"
distractor_level: 2
intro_vi: "Học sinh chào chú giáo viên ở cổng trường."
intro_en: "The student greeted the chú teacher at the school gate."
distractor_1_vi: "Sân trường vắng vì giờ học chưa bắt đầu."
distractor_1_en: "The schoolyard was empty because class hadn't started yet."
distractor_2_vi: "Tiếng chuông vào lớp vừa mới vang lên."
distractor_2_en: "The bell to enter class had just rung."
target_vi: "Học sinh hỏi _____ về lịch kiểm tra tuần tới."
target_en: "The student asked _____ about next week's exam schedule."
correct_answer: "chú"

---

**Instance 7**
occupation: "kỹ sư", occupation_en: "engineer"
participant_role: "đồng nghiệp", participant_role_en: "colleague"
term_set: "chị", narrator_position: "younger"
distractor_level: 1
intro_vi: "Tôi làm việc cùng chị kỹ sư trong nhóm dự án."
intro_en: "I work with the chị engineer in the project team."
distractor_1_vi: "Văn phòng hôm nay có nhiều cuộc họp liên tiếp."
distractor_1_en: "The office had many back-to-back meetings today."
target_vi: "Đồng nghiệp nhờ _____ kiểm tra lại bản thiết kế."
target_en: "The colleague asked _____ to review the design blueprint."
correct_answer: "chị"

---

**Instance 8**
occupation: "nông dân", occupation_en: "farmer"
participant_role: "hàng xóm", participant_role_en: "neighbor"
term_set: "em", narrator_position: "older"
distractor_level: 5
intro_vi: "Tôi nói chuyện với em nông dân trẻ ở đầu làng."
intro_en: "I spoke with the em young farmer at the edge of the village."
distractor_1_vi: "Buổi chiều ở làng rất yên tĩnh và mát mẻ."
distractor_1_en: "The village afternoon was very quiet and cool."
distractor_2_vi: "Tiếng gà gáy vang lên từ phía cánh đồng."
distractor_2_en: "The sound of roosters came from the direction of the fields."
distractor_3_vi: "Mấy đứa trẻ đang chạy chơi gần bờ ao."
distractor_3_en: "Some children were running around near the pond."
distractor_4_vi: "Khói bếp tỏa ra từ những mái nhà tranh."
distractor_4_en: "Cooking smoke rose from the thatched rooftops."
distractor_5_vi: "Con đường đất nhỏ dẫn vào làng còn ướt sau cơn mưa."
distractor_5_en: "The small dirt road leading into the village was still wet after the rain."
target_vi: "Hàng xóm hỏi _____ về mùa thu hoạch năm nay."
target_en: "The neighbor asked _____ about this year's harvest."
correct_answer: "em"

---

**Instance 9**
occupation: "bác sĩ", occupation_en: "doctor"
participant_role: "đồng nghiệp", participant_role_en: "colleague"
term_set: "nó", narrator_position: "equal"
distractor_level: 3
intro_vi: "Tôi nhắc đến nó — người bác sĩ trẻ mới vào ca."
intro_en: "I mentioned nó — the young doctor who just started the shift."
distractor_1_vi: "Ca trực đêm thường bắt đầu lúc mười một giờ."
distractor_1_en: "The night shift usually starts at eleven o'clock."
distractor_2_vi: "Phòng cấp cứu hôm nay tiếp nhận nhiều ca khó."
distractor_2_en: "The emergency room received many difficult cases today."
distractor_3_vi: "Các y tá đang bàn giao ca cho nhau ở cuối hành lang."
distractor_3_en: "The nurses were handing over shifts at the end of the hallway."
target_vi: "Đồng nghiệp hỏi tôi liệu _____ có rảnh để hỗ trợ không."
target_en: "The colleague asked me whether _____ was free to help."
correct_answer: "nó"

---

**Instance 10**
occupation: "kỹ sư", occupation_en: "engineer"
participant_role: "sinh viên thực tập", participant_role_en: "intern"
term_set: "hắn", narrator_position: "equal"
distractor_level: 2
intro_vi: "Tôi kể với bạn về hắn — tay kỹ sư hay làm trễ deadline."
intro_en: "I told my friend about hắn — the engineer who always misses deadlines."
distractor_1_vi: "Văn phòng gần đây hay có chuyện lặt vặt xảy ra."
distractor_1_en: "The office has had a lot of small incidents recently."
distractor_2_vi: "Mọi người trong nhóm đều biết vấn đề này từ lâu."
distractor_2_en: "Everyone in the team has known about this issue for a long time."
target_vi: "Sinh viên thực tập hỏi tôi liệu _____ có phụ trách dự án mới không."
target_en: "The intern asked me whether _____ would be in charge of the new project."
correct_answer: "hắn"