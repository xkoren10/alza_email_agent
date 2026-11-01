# Alza Aerospace Email Support Agent

An AI assistant that answers customer emails about the AeroSpace Pulsar-1 shuttle. It runs as a
small Flask service on Google Cloud Run and is woken by Gmail push notifications through Pub/Sub,
so it never polls the inbox.

For each email it:

1. **classifies** it with Gemini (looking at the text and any attachments),
2. **gathers evidence** from the knowledge base (manual, error codes, spare-parts list) if needed,
3. **drafts** a reply grounded in that evidence, and
4. **sends** it as a threaded reply (or saves it as a Gmail draft for human review).

Every email gets a reply. For complaints, refunds, safety issues or anything the knowledge base can't answer,
the reply acknowledges the message and says a specialist will follow up; the agent never guesses.


## Project structure

```text
├── main.py                  # Entry point: wires the classes together, exposes the Flask `app`
├── app/
│   ├── config.py            # Settings: every option comes from an environment variable
│   ├── models.py            # IncomingEmail, Attachment, Classification, Evidence, Reply
│   ├── agent.py             # SupportAgent: Gemini connection + knowledge base access
│   │                        #   classify(), search_knowledge_base(), draft_reply()
│   ├── knowledge_base.py    # KnowledgeBase: hybrid search (Gemini embeddings + BM25)
│   ├── embeddings.py        # Gemini embedding calls, shared by the service and the index build
│   ├── email_handler.py     # EmailHandler: classify -> evidence -> draft -> send
│   ├── gmail_client.py      # GmailClient: Gmail API read / label / draft / send / watch
│   ├── attachments.py       # Attachment security checks (whitelist, size, magic bytes)
│   └── server.py            # Flask routes: /health, /pubsub/push, /admin/renew-watch
├── knowledge_base/
│   ├── raw_files/           # Source documents (PDF manual, spare-parts xlsx, control panel photo)
│   ├── knowledge_chunks.json
│   └── vector_index/        # embeddings.npy, bm25.pkl, chunks.pkl, loaded at start-up
├── scripts/                 # Offline tools (not part of the running service)
│   ├── preprocess_files.py  # raw files -> knowledge_chunks.json
│   ├── create_indices.py    # chunks -> vector_index/
│   └── get_gmail_token.py   # one-off OAuth login that prints the Gmail refresh token
├── google/                  # helper scripts (not part of the running service)
│   ├── auth_second.py       # get credentials for a second test user in the project 
│   └── register_watch.py    # one time execution for registering the Gmail watch on email
├── tests/                   # pytest unit tests (fakes, no network needed)
├── docs/DEPLOYMENT.md       # Step-by-step GCP setup (Cloud Run, Pub/Sub, Scheduler)
├── Dockerfile
└── .env.example
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check. Returns `{"status": "ok", "knowledge_chunks": N}`. Makes no external calls. |
| POST | `/pubsub/push` | Receives the Pub/Sub push, then processes all unhandled inbox mail. 200 = done; 500 = at least one email failed (Pub/Sub retries). |
| POST | `/admin/renew-watch` | Re-registers the Gmail watch (it expires every 7 days). Called daily by Cloud Scheduler. |

The two POST endpoints verify the Google-signed OIDC token that Pub/Sub / Scheduler attach.

## Safety measures

* **Default is `SEND_MODE=draft`**: nothing reaches customers until you switch to `send`.
* **No guessing**: when the knowledge base has no answer, or the matter is a complaint or legal/safety issue, the reply only acknowledges and promises a specialist follow-up.
* **Loop protection**: mail from the support address, `noreply`-style senders, and mail marked
  `Auto-Submitted`, `Precedence: bulk` or `List-Unsubscribe` is not answered, to avoid mail loops between robots.
* **Prompt-injection hardening**: the system prompt tells the model that email content is data, not instructions.
  Replies are grounded in retrieved extracts; if there is none the model must hand over to a specialist.
* **Attachments** (`.pdf .png .jpg .jpeg .webp .gif .mp3 .wav .m4a`) are checked for extension, size
  (10 MB each, 18 MB total) and magic bytes, and kept in memory only.
* **No lost or duplicate mail**: an email is labelled `alza-ai-processed` only after the reply succeeded.
  Failures stay pending and are retried; `--max-instances 1` plus a lock prevents double replies.

## Configuration

Copy `.env.example` to `.env` for local use; on Cloud Run use env vars and Secret Manager.

| Variable | Purpose |
|---|---|
| `GEMINI_MODEL` | Gemini model name (default `gemini-2.5-flash`) |
| `GEMINI_API_KEY` or `GEMINI_USE_VERTEX=true` + `GCP_PROJECT`, `GCP_LOCATION` | How to authenticate to Gemini |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | OAuth credentials of the support mailbox |
| `SUPPORT_ADDRESS` | The mailbox's own address (ignored as a sender) |
| `PUBSUB_TOPIC` | `projects/<id>/topics/<name>` used when registering the Gmail watch |
| `PUBSUB_OIDC_AUDIENCE`, `PUBSUB_OIDC_SERVICE_ACCOUNT` | Enable and tighten request authentication |
| `SEND_MODE` | `draft` (default) or `send` |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | Embedding model for knowledge base search (default `gemini-embedding-001`, 768). Changing either requires rebuilding the index |
| `MAX_EMAILS_PER_RUN`, `KB_TOP_K`, `LOG_LEVEL`, `INDEX_DIR` | Optional tuning |

## Local development

```bash
pip install -r requirements-dev.txt
cp .env.example .env              # fill it in
python scripts/get_gmail_token.py client_secret.json   # once, to obtain the Gmail refresh token
python main.py                    # serves on http://localhost:8080
pytest                            # unit tests
```

Trigger a run by hand (in local mode request authentication is off):

```bash
curl -X POST http://localhost:8080/pubsub/push -H "Content-Type: application/json" -d "{}"
```

Leave `SEND_MODE=draft` while testing and check the Drafts folder of the mailbox.

## Rebuilding the knowledge base

```bash
python scripts/preprocess_files.py   # needs GEMINI_API_KEY (describes the control panel photo)
python scripts/create_indices.py    # embeds the chunks through the Gemini API
```

The container has no ML libraries (no torch / CUDA), so the image stays small (a few hundred MB).
Query embeddings are computed by the Gemini API at request time.

Commit the updated `knowledge_base/vector_index/`, then rebuild and redeploy the container.

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
