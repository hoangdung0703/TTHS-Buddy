# TTHS Buddy: hướng dẫn cho agent

File này được nạp ở mọi session. Quy tắc ở đây luôn có hiệu lực, kể cả khi prompt không nhắc lại.
Nếu prompt mâu thuẫn với một quy tắc cứng bên dưới: dừng và hỏi, không tự chọn.

## Dự án

TTHS Buddy là trợ lý học Luật Tố tụng hình sự cho sinh viên luật. Các tính năng: Trợ lý AI (Chat RAG có guard Rule 9), Vở ghi, Trắc nghiệm, Tổng quan, Phiên tòa giả định (vai KSV, Luật sư bào chữa, Người xem, Thư ký, Bị cáo, Chủ tọa).

| Thành phần | Ghi chú |
|---|---|
| Frontend | Next.js 15 / React 19 trong `frontend/`, Vercel **tự deploy khi push main** (tths-buddyy.vercel.app) |
| Backend | FastAPI trong `backend/`, Render Free, **chỉ người dùng deploy tay** (Manual Deploy), cold boot khoảng 45 giây; `GET /api/health` trả `version` = 7 ký tự đầu của commit đang chạy |
| Dữ liệu | Supabase (Auth, Postgres, RLS bật; service-role key chỉ ở backend), Qdrant Cloud (corpus = `ingestion/chunks.json`, gitignored) |
| LLM | Gemini (embedding + sinh) qua header `x-goog-api-key`. **Số dư trả trước dùng chung** cho Chat, Vở ghi và Phiên tòa: hết số dư (402) là hỏng cả ba |

Tài liệu phiên tòa (đọc trước khi sửa bất kỳ gì của phiên tòa, cập nhật khi đổi API hoặc hành vi):
- `docs/phien-toa-gia-dinh/THIET-KE.md`: thiết kế và các quyết định đã chốt (Mục 11.8; các mục "Quyết định" có ngày ghi đè phần thân khi mâu thuẫn). Không tự đổi quyết định đã chốt; thiếu chi tiết thì chọn phương án an toàn và ghi vào "Giả định đã dùng".
- `docs/phien-toa-gia-dinh/API-CONTRACT.md`: hợp đồng API giữa frontend và backend. Backend giả của e2e (`frontend/tests/e2e/*.mjs`) mô phỏng theo hợp đồng này: đổi hai bên cùng lúc.

Bất biến quan trọng của phiên tòa (chi tiết trong THIET-KE): state machine giữ ở code, LLM không ghi state; request mang `expected_step`/`expected_version` (409 khi lệch); `verdict_json` **không bao giờ** trả ra ngoài; guard Rule 9, verdict guard, money guard, name-consistency; breaker sau 3 lần tạm nghỉ liên tiếp.

## Quy tắc cứng

### Secret
- Không in, không dán, không ghi vào bất kỳ file nào giá trị secret: key Supabase, key Google dạng `AIza...`, JWT, header `apikey` / `authorization` / `x-goog-api-key`.
- Không chạy log DEBUG. Không `cat .env`. Mọi đầu ra nhìn thấy được của backend phải qua bộ lọc che.

### Dữ liệu
- Không đọc, in hay commit `data/private/`.
- Không chạy script ingestion.
- Không in nội dung câu hỏi, câu trả lời, ghi chép hay phiên tòa của sinh viên. Lưu đầu ra thô (nếu cần để phân tích) ở thư mục tạm **ngoài repo**, không commit.
- Tài khoản test chỉ tạo qua Admin API với tên `tthsdiag-*`, và xóa khi xong. Không bao giờ xóa dữ liệu người dùng thật, không `DROP` bảng.

### Git
- Mỗi việc làm trên một nhánh mới từ `origin/main` mới nhất (`git fetch` trước).
- **Không merge vào main, không push main, không deploy** nếu prompt hiện tại không cho phép rõ ràng. Khi được phép: theo skill `deploy-main`.
- Không force-push. Không amend commit đã báo cáo. Merge chỉ `--ff-only`.
- Trước khi commit: `git status` sạch secret, `.env`, `data/private/`, PDF, ảnh, `.next`.
- `.gitignore` loại `*.md`. File `.md` mới cần `git add -f`, trừ các file đã có ngoại lệ trong `.gitignore` (README, `frontend.md`, `DEPLOYMENT.md`, `THIET-KE.md`, `API-CONTRACT.md`, `CLAUDE.md`, `.claude/skills/**/SKILL.md`, ...). Các file `.md` đã được theo dõi thì sửa và commit bình thường.
- Không bao giờ commit `ingestion/raw_documents/` hay `ingestion/chunks*.json` (PDF có bản quyền và văn bản dẫn xuất). Repo không được để public trước khi viết lại lịch sử như README mô tả.

### Migration
- Chỉ viết file mới `backend/migrations/00NN_*.sql`, chạy lại được an toàn, bọc trong transaction. Người dùng tự chạy trong Supabase SQL Editor.
- Ưu tiên không cần migration (ví dụ dùng cột `user_work jsonb` của phiên tòa).

### Môi trường
- Không bao giờ đặt `RAG_EXPERIMENT_DISABLE_HYDE` hay `ENABLE_API_DOCS` trên Render.
- **Không chạy `next build` trong `frontend/`** khi người dùng có thể đang chạy `next dev` (đã từng ghi đè `.next` của người dùng). Build trong bản sao ở thư mục tạm.
- Không thêm dependency mới khi prompt không cho phép.

### Gemini và pháp lý
- Mặc định **0 lời gọi Gemini**. Chỉ gọi khi prompt cho phép và có trần: theo skill `gemini-live-run`. Gặp 402 hoặc 429: dừng ngay, không thử lại.
- Mọi script trong `backend/evaluation/` (kể cả các file `test_*.py` ở đó) gọi backend thật hoặc Gemini thật: chúng **không** phải unit test và chịu quy tắc trên.
- Mọi Điều, khoản, điểm, mức hình phạt, thời hạn: theo skill `legal-citation-check`. Không dựa vào trí nhớ.

### Code
- Comment code bằng tiếng Anh. Văn bản giao diện bằng tiếng Việt, ngắn gọn, đúng giọng các màn hiện có. Giữ nguyên thuật ngữ pháp lý (Điều, khoản, điểm, BLHS, BLTTHS).
- Thay đổi tối thiểu, đúng gốc; dùng lại component và cơ chế sẵn có thay vì dựng mới.

## Lệnh hay dùng

Nếu lệnh dưới đây không khớp với repo, đọc `package.json` / script trong repo để lấy lệnh đúng, đừng đoán, và báo lại để cập nhật file này.

| Việc | Lệnh |
|---|---|
| Test backend | `cd backend && ENVIRONMENT=test ../.venv/bin/python -m unittest discover -s tests` (stdlib unittest, không có pytest; không gọi mạng; test cần văn bản luật đọc `ingestion/chunks.json` và tự skip khi thiếu) |
| Một module / một ca backend | `python -m unittest tests.test_trial_state_machine`, `python -m unittest tests.test_trial_state_machine.SomeClass.test_x` (từ `backend/`) |
| Test ingestion | chỉ `python -m unittest ingestion.test_registry_templates` từ gốc repo (`test_chuong_muc` đang đỏ do PDF trên máy trích khác vị trí, đã biết) |
| Typecheck frontend | `npx tsc --noEmit` trong `frontend/` (không có script npm) |
| Test đơn vị frontend | `npm test` trong `frontend/` (= `node --test tests/*.test.mjs`, test logic thuần của `src/lib/trial*.ts`) |
| Lint frontend | repo chưa có cấu hình ESLint: dùng cấu hình tạm đặt **ngoài repo** (`next/core-web-vitals` + typescript). Có 1 cảnh báo có sẵn ở `dashboard/page.tsx` |
| E2e frontend | theo skill `frontend-e2e` (`tests/e2e/build.sh && node tests/e2e/suite.mjs` trong `frontend/`, build bản sao ở `$TMPDIR/ttths-e2e`, cổng 3011) |
| Dev server | backend: `uvicorn app.main:app --reload` trong `backend/` (khi khởi động kiểm Supabase + Qdrant); frontend: `npm run dev` (cổng 3000) |

Không ghi cứng số test kỳ vọng vào code hay tài liệu. Số kỳ vọng = số của lần chạy gần nhất trên main cộng ca mới.

Pipeline ingestion (`python -m ingestion.parse_law --all`, `--file "<x>.pdf"`, `python -m ingestion.embed_and_upsert`) chỉ để tham khảo: **người dùng tự chạy**, agent không chạy (xem Quy tắc cứng).

## Báo cáo

Khi xong việc: **BÁO CÁO rồi DỪNG**, bằng tiếng Việt, ngắn gọn:
- commit hash (và nhánh);
- số test pass/tổng của từng phần đã chạy (không nói "xanh" nếu chưa chạy);
- số lời gọi Gemini (ước lượng và thực tế), nếu có;
- giả định đã dùng khi tài liệu thiếu hoặc mâu thuẫn;
- rủi ro còn lại;
- đường dẫn các file đầu ra để ngoài repo (ảnh, log, dữ liệu đo).

Gặp việc không thể hoàn tác, phải đổi quyết định đã chốt, hay phải vi phạm một quy tắc ở trên để làm tiếp: dừng và báo, không tìm đường vòng.

## Skills của repo

| Skill | Khi nào dùng |
|---|---|
| `deploy-main` | Đưa nhánh đã duyệt lên main |
| `legal-citation-check` | Bất cứ khi nào viết hay kiểm nội dung có điều luật |
| `gemini-live-run` | Bất cứ khi nào gọi Gemini thật |
| `frontend-e2e` | Chạy, thêm hoặc sửa e2e frontend |
| `ui-bug-measure` | Sửa lỗi hiển thị, bố cục, cuộn, focus, z-index |

## Kiến trúc và mã nguồn

Mô tả kỹ thuật, không phải quy tắc. Setup, biến môi trường và bảng API: `README.md`; deploy: `DEPLOYMENT.md`, `render.yaml`. Phần này giữ tiếng Anh ở chỗ dịch sẽ mất chính xác.

### Backend layout
`app/api/*` routers: auth (`require_supabase_user`, Supabase JWT via JWKS), `@limiter.limit` (slowapi), SSE framing. `app/services/*` hold the logic. `app/prompts/*` hold every LLM prompt. `app/models/*` are Pydantic schemas. `app/core/` has settings (`config.py`, pydantic-settings, env aliases; `ENVIRONMENT` is required and must be `development`, `test` or `production`), data access, rate limits, middleware, log redaction, and request telemetry. `main.py` builds clients in `lifespan` and stores them on `app.state`.

Streaming routes follow one pattern, and new routes reuse it: auth and rate limit run outside the SSE generator, and all I/O runs inside it. `CancelledError` is logged as the outcome `cancelled`. Other errors emit an `error` event and close cleanly. Ownership failures return 404, not 403. Telemetry records lengths and counts, never the text a user wrote.

### RAG chat (`services/rag_service.py`, `query_understanding_service.py`, `api/chat.py`)
Query understanding (rewrite, scope check, sub-question split, anonymisation) → retrieval → generation → guards → `chat_log_service`. Retrieval mixes an exact Điều lookup (`detect_dieu_number` / `detect_source_document`), HyDE-embedded semantic search, and an LLM re-rank over `legal_text` chunks, plus `academic_reference` chunks with neighbour expansion. Aggregate-structure questions ("how many chapters…") and repealed Điều are answered deterministically from Qdrant payloads.

**Rule 9** is the core invariant: an answer may only cite Điều numbers that retrieval returned in `legal_primary`. The prompt alone does not enforce it (measured), so `_rule9_ungrounded_dieu_numbers` runs in code. Answers that used `academic_reference`, and every multi-part answer, are buffered instead of token-streamed. A violation replaces the whole answer with a fixed fallback; the code never patches individual spots. Ordinary single answers stream and only log a Rule 9 miss. The HyDE disable switch (`RAG_EXPERIMENT_DISABLE_HYDE`) is honoured only outside production; in production it is ignored and logged at startup.

### Mock trial (`services/trial_*.py`, `api/trials.py`)
Gated by `TRIAL_ENABLED` (off means every `/api/trials*` route returns 404) and optionally by `TRIAL_ALLOWED_EMAILS`. There is a per-user and a global daily case quota (`trial_usage_log`, migration 0014).

- `trial_state_machine.py` is a pure, deterministic 11-step hearing. Each step is a list of slots (role, kind `speech`/`qa_loop`/`long_speech`, end conditions). A slot whose role equals the user's role is the user's turn; every other slot is an AI turn. Every write carries `expected_step` + `expected_version`, and any mismatch or disallowed action is a 409. Skip requests made in words are caught by a keyword detector before any LLM call.
- User roles (`ENABLED_USER_ROLES`): `ksv`, `luat_su` (Luật sư bào chữa), `nguoi_xem` (Người xem), `thu_ky` (`trial_clerk.py`), `bi_cao` (`trial_defendant.py`), `chu_toa` (`trial_presiding.py` for steps 2–9, `trial_chair_decision.py` for deliberation and the structured decision). Adding a role adds slot behaviour and UI, not a new engine.
- One LLM call generates a run of AI utterances, with the speaker enum restricted per slot via the response schema. Legally weighty long speeches (indictment, defence, judgment) get one call each. Everything is buffered and passed through guards before it is sent or saved: role/fact/name guards, Rule 9 by (Điều, statute) pair in `trial_rule9.py`, the verdict guard in `trial_verdict_guard.py`, the money guard (`trial_money.py`). Sentencing rules shared by the AI deliberation guard and the Chủ tọa form live in `trial_sentencing_rules.py`. A half-generated segment is never persisted.
- The case file is JSON validated by Pydantic (`extra="forbid"`, `trial_case_validator.py`). The legal pack is built from real chunks (`trial_legal_pack.py`). The record follows form Mẫu 22-HS (`trial_record*.py`).

### Frontend
App Router pages in `src/app/*` (`/dashboard`, `/chat`, `/chat/[conversationId]`, `/notes`, `/quiz`, `/quiz/[setId]`, `/trial`, `/trial/new`, `/trial/[id]`, `/trial/[id]/record`, `/login`, `/register`). All backend calls go through `src/lib/api.ts`. Mock data (`src/lib/mockData.ts`) is on unless `NEXT_PUBLIC_USE_MOCK_DATA` is exactly `"false"` (unset = mock on); quiz v2 and notes always call the real backend. `NEXT_PUBLIC_*` vars must be in `frontend/.env.local`, not the root `.env`. The Supabase session comes from `useAuthSession`. Modal layers (dialogs, drawers) use the shared `useModalLayer` hook and portal to `document.body`; z-index scale in `tailwind.config.ts` (`z-dialog` = 60). Trial UI lives in `src/components/trial/*`. Pure trial logic sits in `src/lib/trial*.ts`, which is the part the `node --test` suite covers. The UI renders only the `allowed_actions` the server returns, never a client-side guess. `frontend.md` has the design-system notes. The app is a PWA (`public/sw.js`).

### Ingestion and corpus
`ingestion/parse_law.py` turns the PDFs listed in `document_registry.py` (nothing scans the directory) into `ingestion/chunks.json`; `embed_and_upsert.py` upserts with deterministic point IDs (idempotent). Chunk fields: `source_type` (`legal_text` / `academic_reference`), `source_document`, `law_version`, `dieu_number`, `khoan_number`, `chuong_*`, `chunk_text`. `ingestion/question_bank.json` is committed and edited by hand (`question_bank.TEMPLATE.md`).

### Docs and conventions
- `requirements.md` is the phase-by-phase spec and build log. Long-form rationale goes there or in the trial design doc, not in commit messages.
- Commit style: Conventional Commits with scopes such as `feat(trial)`, `feat(trial-ui)`, `fix(ui)`, `test(e2e)`, `docs`.
- Migrations have no runner. New tables get RLS enabled with no policies (the backend uses the service-role key). Code that reads or writes a table must still work if the migration has not been applied yet (log and continue).
- A GitHub Action (`.github/workflows/keep-supabase-alive.yml`) pings Supabase every 3 days to keep the free tier awake.
