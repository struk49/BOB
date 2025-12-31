from openai import OpenAI
from config import Config
import json

client = OpenAI(api_key=Config.OPENAI_API_KEY)


def predict_optimal_send_time(email_address, profiles):
    """Use AI to predict optimal send time"""
    profile = profiles.get(email_address, {})
    
    if not profile or not profile.get('sent_times'):
        return {
            'recommended_hour': 10,
            'recommended_day': 'Tuesday',
            'confidence': 'low',
            'reasoning': 'No historical data available. Using industry best practices.'
        }
    
    sent_times = profile.get('sent_times', [])
    time_data = {
        'hours': [t['hour'] for t in sent_times],
        'days': [t['day'] for t in sent_times],
        'count': len(sent_times)
    }
    
    prompt = f"""Analyze this email engagement data and predict the optimal time to send an email:
    
    Recipient: {email_address}
    Historical data points: {time_data['count']}
    Hours when emails were received: {time_data['hours']}
    Days when emails were received: {time_data['days']}
    
    Based on this data, provide:
    1. Best hour to send (in 24h format, integer)
    2. Best day of week
    3. Confidence level (high/medium/low)
    4. Brief reasoning (one sentence)
    
    Respond in JSON format:
    {{
        "recommended_hour": 10,
        "recommended_day": "Tuesday",
        "confidence": "high",
        "reasoning": "Most emails received between 9-11am on weekdays"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an email marketing optimization expert. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        print(f"AI prediction error: {e}")
        return {
            'recommended_hour': 10,
            'recommended_day': 'Tuesday',
            'confidence': 'low',
            'reasoning': 'Using default timing due to analysis error'
        }


def generate_personalized_content(recipient_email, subject, snippet, profiles):
    """Generate personalized email content based on recipient behavior"""
    profile = profiles.get(recipient_email, {})
    topics = profile.get('topics', [])
    
    context = f"""
    Recipient: {recipient_email}
    Previous email topics: {topics[-5:] if topics else 'No history'}
    Total interactions: {len(topics)}
    """
    
    prompt = f"""You are an email personalization expert. Create a personalized response strategy.
    
    RECIPIENT CONTEXT:
    {context}
    
    CURRENT EMAIL:
    Subject: {subject}
    Preview: {snippet}
    
    Provide a personalization strategy including:
    1. Tone recommendation (e.g., "professional-friendly", "casual", "formal")
    2. Key topics to emphasize (array of 2-3 topics)
    3. Personalized greeting suggestion
    4. Content hooks that would resonate (array of 2-3 hooks)
    5. Call-to-action recommendation
    6. Brief personalization notes
    
    Format as JSON:
    {{
        "tone": "professional-friendly",
        "keyTopics": ["topic1", "topic2"],
        "greeting": "Hi [Name]",
        "contentHooks": ["hook1", "hook2"],
        "cta": "Schedule a call",
        "notes": "Brief explanation of personalization strategy"
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert in email personalization and engagement optimization. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.8
        )
        
        return json.loads(response.choices[0].message.content)
        
    except Exception as e:
        print(f"Personalization error: {e}")
        return {
            "tone": "professional",
            "keyTopics": ["general inquiry"],
            "greeting": "Hello",
            "contentHooks": ["value proposition"],
            "cta": "Reply at your convenience",
            "notes": "Standard approach due to analysis error"
        }


def analyze_email_batch(emails, profiles):
    """Analyze a batch of emails with AI"""
    analyzed_emails = []
    
    for email_data in emails:
        try:
            sender = email_data['sender']
            subject = email_data['subject']
            snippet = email_data['snippet']
            
            # Predict optimal send time
            send_time = predict_optimal_send_time(sender, profiles)
            
            # Generate personalization
            personalization = generate_personalized_content(
                sender, subject, snippet, profiles
            )
            
            analyzed_email = {
                'id': email_data['id'],
                'sender': sender,
                'senderName': email_data['sender_name'],
                'subject': subject,
                'snippet': snippet,
                'optimalTime': {
                    'day': send_time.get('recommended_day', 'Tuesday'),
                    'hour': send_time.get('recommended_hour', 10),
                    'confidence': send_time.get('confidence', 'medium')
                },
                'personalization': {
                    'tone': personalization.get('tone', 'professional'),
                    'greeting': personalization.get('greeting', 'Hello'),
                    'keyTopics': personalization.get('keyTopics', []),
                    'contentHooks': personalization.get('contentHooks', []),
                    'cta': personalization.get('cta', 'Reply'),
                    'notes': personalization.get('notes', 'N/A')
                }
            }
            
            analyzed_emails.append(analyzed_email)
            
        except Exception as e:
            print(f"Error analyzing email {email_data.get('id')}: {e}")
            continue
    
    return analyzed_emails