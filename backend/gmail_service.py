import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from flask import current_app
from models import User, db
import json

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify'
]


def get_gmail_service(user):
    """Get Gmail service for a specific user"""
    creds = None
    
    # Load credentials from database
    if user.gmail_credentials:
        try:
            creds_data = json.loads(user.gmail_credentials)
            creds = Credentials(
                token=creds_data['token'],
                refresh_token=creds_data['refresh_token'],
                token_uri=creds_data['token_uri'],
                client_id=creds_data['client_id'],
                client_secret=creds_data['client_secret'],
                scopes=SCOPES
            )
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return None
    
    # Check if credentials are valid
    if creds and creds.valid:
        return build('gmail', 'v1', credentials=creds)
    
    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed credentials
            save_gmail_credentials(user, creds)
            return build('gmail', 'v1', credentials=creds)
        except Exception as e:
            print(f"Error refreshing token: {e}")
            return None
    
    return None


def save_gmail_credentials(user, creds):
    """Save Gmail credentials to database"""
    try:
        creds_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret
        }
        user.gmail_credentials = json.dumps(creds_data)
        user.gmail_refresh_token = creds.refresh_token
        db.session.commit()
    except Exception as e:
        print(f"Error saving credentials: {e}")
        db.session.rollback()


def initiate_gmail_oauth(user, credentials_path='credentials.json'):
    """Initiate OAuth flow for Gmail"""
    try:
        if not os.path.exists(credentials_path):
            raise Exception("credentials.json not found")
        
        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_path,
            SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
        
        return {
            'auth_url': auth_url,
            'flow_data': {
                'client_id': flow.client_config['client_id'],
                'client_secret': flow.client_config['client_secret']
            }
        }
    except Exception as e:
        raise Exception(f"Failed to initiate OAuth: {str(e)}")


def complete_gmail_oauth(user, auth_code, flow_data):
    """Complete OAuth flow with authorization code"""
    try:
        import requests
        
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            'code': auth_code,
            'client_id': flow_data['client_id'],
            'client_secret': flow_data['client_secret'],
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(token_url, data=data)
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.text}")
        
        token_data = response.json()
        
        if 'access_token' not in token_data:
            raise Exception("No access token received")
        
        # Create credentials
        creds = Credentials(
            token=token_data['access_token'],
            refresh_token=token_data.get('refresh_token'),
            token_uri='https://oauth2.googleapis.com/token',
            client_id=flow_data['client_id'],
            client_secret=flow_data['client_secret'],
            scopes=SCOPES
        )
        
        # Save to database
        save_gmail_credentials(user, creds)
        
        return True
    except Exception as e:
        raise Exception(f"OAuth completion failed: {str(e)}")


def fetch_emails(service, max_results=50):
    """Fetch emails from Gmail"""
    try:
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        
        email_list = []
        for msg in messages:
            try:
                msg_detail = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='full'
                ).execute()
                
                headers = {h['name']: h['value'] 
                          for h in msg_detail['payload'].get('headers', [])}
                
                sender = headers.get('From', '')
                if '<' in sender:
                    email = sender.split('<')[1].split('>')[0]
                    sender_name = sender.split('<')[0].strip().strip('"')
                else:
                    email = sender.split()[0] if sender else 'unknown'
                    sender_name = sender
                
                subject = headers.get('Subject', '(No Subject)')
                snippet = msg_detail.get('snippet', '')
                date_str = headers.get('Date', '')
                
                email_data = {
                    'id': msg['id'],
                    'sender': email,
                    'sender_name': sender_name,
                    'subject': subject,
                    'snippet': snippet,
                    'date': date_str
                }
                
                email_list.append(email_data)
                
            except Exception as e:
                print(f"Error processing message: {e}")
                continue
        
        return email_list
        
    except Exception as e:
        raise Exception(f"Failed to fetch emails: {str(e)}")


def analyze_email_patterns(emails):
    """Analyze email patterns to build engagement profiles"""
    from collections import defaultdict
    from email.utils import parsedate_to_datetime
    
    profiles = defaultdict(lambda: {
        'sent_times': [],
        'topics': []
    })
    
    for email_data in emails:
        try:
            sender = email_data['sender']
            subject = email_data['subject']
            date_str = email_data['date']
            
            if date_str:
                msg_time = parsedate_to_datetime(date_str)
                profiles[sender]['sent_times'].append({
                    'hour': msg_time.hour,
                    'day': msg_time.strftime('%A'),
                    'timestamp': msg_time.isoformat()
                })
            
            profiles[sender]['topics'].append(subject)
            
        except Exception as e:
            print(f"Error analyzing pattern: {e}")
            continue
    
    return dict(profiles)