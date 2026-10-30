# Deploying to Google Cloud (Cloud Run + Pub/Sub)

How a customer email reaches the agent, with no polling:

```text
Customer email -> Gmail inbox -> Gmail "watch" -> Pub/Sub topic -> push subscription
               -> POST /pubsub/push on Cloud Run -> EmailHandler -> reply
```

Gmail only publishes "something changed" to the topic. The app then asks Gmail for inbox
mail that doesn't yet carry the `alza-ai-processed` label, so duplicate or late
notifications are harmless.

Replace the placeholder values below (`PROJECT_ID`, `REGION`, ...) with your own.

```bash
export PROJECT_ID=your-project-id
export REGION=europe-west1
export SERVICE=alza-email-agent
gcloud config set project $PROJECT_ID
```

## 1. Enable APIs

```bash
gcloud services enable run.googleapis.com pubsub.googleapis.com gmail.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com aiplatform.googleapis.com
```

## 2. Gmail OAuth credentials

The Gmail API cannot use the IMAP app password. It needs an OAuth refresh token for the support mailbox.

1. Console -> *APIs & Services* -> *OAuth consent screen*: configure it (Internal if the mailbox is in a Google Workspace org; otherwise External and add the mailbox as a test user. Move to *In production* later, because "Testing" refresh tokens expire after 7 days).
2. *Credentials* -> *Create credentials* -> *OAuth client ID* -> **Desktop app**. Download the JSON.
3. Locally, signed in to the support mailbox in your browser:
   ```bash
   python scripts/get_gmail_token.py client_secret.json
   ```
4. Store the three printed values as secrets:
   ```bash
   printf '%s' 'VALUE' | gcloud secrets create gmail-client-id --data-file=-
   printf '%s' 'VALUE' | gcloud secrets create gmail-client-secret --data-file=-
   printf '%s' 'VALUE' | gcloud secrets create gmail-refresh-token --data-file=-
   ```

## 3. Gemini access

Easiest on GCP: Vertex AI with the Cloud Run service account (no API key); see `GEMINI_USE_VERTEX` below.
Alternative: store your key with `gcloud secrets create gemini-api-key ...` and swap
`GEMINI_USE_VERTEX=true,...` for `--set-secrets GEMINI_API_KEY=gemini-api-key:latest`.

## 4. Service accounts

```bash
# identity the Cloud Run service runs as
gcloud iam service-accounts create email-agent-run
RUN_SA=email-agent-run@$PROJECT_ID.iam.gserviceaccount.com
for role in roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$RUN_SA --role=$role
done

# identity Pub/Sub and Cloud Scheduler use to call the service
gcloud iam service-accounts create email-agent-invoker
INVOKER_SA=email-agent-invoker@$PROJECT_ID.iam.gserviceaccount.com
```

## 5. Build and deploy

```bash
gcloud artifacts repositories create apps --repository-format=docker --location=$REGION
IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/apps/$SERVICE

gcloud builds submit --tag $IMAGE

gcloud run deploy $SERVICE \
  --image $IMAGE --region $REGION \
  --service-account $RUN_SA \
  --no-allow-unauthenticated \
  --memory 512Mi --cpu 1 \
  --min-instances 0 --max-instances 1 \
  --timeout 300 \
  --set-env-vars "GEMINI_USE_VERTEX=true,GCP_PROJECT=$PROJECT_ID,GCP_LOCATION=$REGION,GEMINI_MODEL=gemini-2.5-flash,SUPPORT_ADDRESS=support@yourdomain.com,PUBSUB_TOPIC=projects/$PROJECT_ID/topics/gmail-notifications,SEND_MODE=draft" \
  --set-secrets "GMAIL_CLIENT_ID=gmail-client-id:latest,GMAIL_CLIENT_SECRET=gmail-client-secret:latest,GMAIL_REFRESH_TOKEN=gmail-refresh-token:latest"
```

* `--max-instances 1` is deliberate: it guarantees only one instance works on the mailbox at a time,
  so an email can never be answered twice by two instances.
* `--min-instances 1` removes the cold start (start-up takes a couple of seconds) if the 2-minute SLA matters. It costs a few euros a month.
* Keep `SEND_MODE=draft` until you have reviewed real drafts, then switch to `send`.

Then give the service its address as the expected token audience:

```bash
URL=$(gcloud run services describe $SERVICE --region $REGION --format='value(status.url)')
gcloud run services update $SERVICE --region $REGION \
  --update-env-vars "PUBSUB_OIDC_AUDIENCE=$URL,PUBSUB_OIDC_SERVICE_ACCOUNT=$INVOKER_SA"
gcloud run services add-iam-policy-binding $SERVICE --region $REGION \
  --member=serviceAccount:$INVOKER_SA --role=roles/run.invoker
```

## 6. Pub/Sub topic and push subscription

```bash
gcloud pubsub topics create gmail-notifications
gcloud pubsub topics create gmail-notifications-dead-letter

# let Gmail publish to the topic
gcloud pubsub topics add-iam-policy-binding gmail-notifications \
  --member=serviceAccount:gmail-api-push@system.gserviceaccount.com --role=roles/pubsub.publisher

gcloud pubsub subscriptions create gmail-push \
  --topic gmail-notifications \
  --push-endpoint "$URL/pubsub/push" \
  --push-auth-service-account $INVOKER_SA \
  --push-auth-token-audience $URL \
  --ack-deadline 300 \
  --min-retry-delay 10 --max-retry-delay 300 \
  --dead-letter-topic gmail-notifications-dead-letter --max-delivery-attempts 5
```

The dead-letter topic stops a message that always fails from being retried forever. (Pub/Sub also needs
publisher/subscriber rights for its own service agent on the dead-letter resources; the console offers to add them.)

## 7. Start the Gmail watch and keep it alive

A Gmail watch expires after **7 days**. Register it now and renew it daily with Cloud Scheduler:

```bash
gcloud scheduler jobs create http renew-gmail-watch \
  --location $REGION --schedule "0 3 * * *" --time-zone "Europe/Prague" \
  --uri "$URL/admin/renew-watch" --http-method POST \
  --oidc-service-account-email $INVOKER_SA --oidc-token-audience $URL

gcloud scheduler jobs run renew-gmail-watch --location $REGION   # register the first watch now
```

## 8. Verify

```bash
# health (needs an identity token because the service is private)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" $URL/health

# send a test email to the support mailbox, then watch the logs
gcloud run services logs read $SERVICE --region $REGION --limit 50
```

With `SEND_MODE=draft`, a reply appears in the mailbox's *Drafts* folder in the same thread.

## Operating notes

| Topic | Behaviour |
|---|---|
| Failed email | The endpoint returns 500, Pub/Sub redelivers with back-off, and the email is not labelled so it is retried. After 5 attempts the notification goes to the dead-letter topic. |
| Complaints / unclear requests | Still answered: the reply acknowledges the message and says a specialist will follow up. |
| Mail older than 2 days | Ignored (`LOOKBACK` in `app/gmail_client.py`), so a fresh deployment can't answer an old inbox. |
| Knowledge base update | Re-run `scripts/preprocess_files.py` and `scripts/create_indices.py`, commit `knowledge_base/vector_index/`, rebuild and redeploy. The service refuses to start if the index doesn't match `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS`. |
| Logs | Plain stdout logging, shown in Cloud Logging. |
