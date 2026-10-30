from google_auth_oauthlib.flow import InstalledAppFlow

# Path to your Google Cloud OAuth client credentials file
CLIENT_SECRETS_FILE = 'credentials.json'

# Required Gmail read-only scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, SCOPES
    )
    
    # open_browser=False prevents WSL from crashing trying to open a Linux GUI browser
    creds = flow.run_local_server(port=0, open_browser=False)

    # Save the resulting token to a unique filename for your second account
    with open('token_second_account.json', 'w') as token:
        token.write(creds.to_json())
    
    print("\n Success! Saved credentials to token_second_account.json")

if __name__ == '__main__':
    main()