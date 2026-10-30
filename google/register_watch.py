from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Load the token specifically generated for your second account
creds = Credentials.from_authorized_user_file('token_second_account.json', ['https://www.googleapis.com/auth/gmail.readonly'])
service = build('gmail', 'v1', credentials=creds)

request_body = {
    "topicName": "projects/gen-lang-client-0958735221/topics/alza_case_study_email_inbox",
    "labelIds": ["INBOX"],
    "labelFilterBehavior": "INCLUDE"
}

response = service.users().watch(userId='me', body=request_body).execute()
print("Watch Response for Second Account:", response)