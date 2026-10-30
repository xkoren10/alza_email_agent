"""One-off helper: logs in as the support mailbox and prints the OAuth refresh token.

Usage (on your own machine, signed in to the support mailbox in the browser):
    python scripts/get_gmail_token.py path/to/client_secret.json

Store the printed values in Secret Manager (see docs/DEPLOYMENT.md). Never commit them.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main(client_secret_path: str) -> None:
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    print(
        json.dumps(
            {
                "GMAIL_CLIENT_ID": credentials.client_id,
                "GMAIL_CLIENT_SECRET": credentials.client_secret,
                "GMAIL_REFRESH_TOKEN": credentials.refresh_token,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
