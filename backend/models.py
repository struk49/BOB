from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
import secrets

db = SQLAlchemy()
bcrypt = Bcrypt()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255))
    
    # Subscription
    subscription_tier = db.Column(db.String(50), default='free')  # free, pro, enterprise
    subscription_status = db.Column(db.String(50), default='active')  # active, canceled, expired
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))
    
    # Usage tracking
    emails_analyzed_this_month = db.Column(db.Integer, default=0)
    total_emails_analyzed = db.Column(db.Integer, default=0)
    
    # API Key
    api_key = db.Column(db.String(255), unique=True)
    
    # Gmail OAuth
    gmail_refresh_token = db.Column(db.Text)
    gmail_credentials = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Email verification
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(255))
    
    # Relationships
    analyses = db.relationship('EmailAnalysis', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def generate_api_key(self):
        self.api_key = f"bob_{secrets.token_urlsafe(32)}"
        return self.api_key
    
    def get_usage_limit(self):
        limits = {
            'free': 10,
            'pro': 500,
            'enterprise': 10000
        }
        return limits.get(self.subscription_tier, 10)
    
    def can_analyze_email(self):
        return self.emails_analyzed_this_month < self.get_usage_limit()
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'subscription_tier': self.subscription_tier,
            'subscription_status': self.subscription_status,
            'emails_analyzed_this_month': self.emails_analyzed_this_month,
            'usage_limit': self.get_usage_limit(),
            'api_key': self.api_key,
            'email_verified': self.email_verified,
            'created_at': self.created_at.isoformat()
        }


class EmailAnalysis(db.Model):
    __tablename__ = 'email_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Email details
    email_id = db.Column(db.String(255))  # Gmail message ID
    sender = db.Column(db.String(255))
    sender_name = db.Column(db.String(255))
    subject = db.Column(db.Text)
    snippet = db.Column(db.Text)
    
    # Analysis results
    optimal_day = db.Column(db.String(50))
    optimal_hour = db.Column(db.Integer)
    confidence = db.Column(db.String(50))
    
    # Personalization
    tone = db.Column(db.String(100))
    greeting = db.Column(db.String(255))
    key_topics = db.Column(db.JSON)
    content_hooks = db.Column(db.JSON)
    cta = db.Column(db.String(255))
    notes = db.Column(db.Text)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email_id': self.email_id,
            'sender': self.sender,
            'senderName': self.sender_name,
            'subject': self.subject,
            'snippet': self.snippet,
            'optimalTime': {
                'day': self.optimal_day,
                'hour': self.optimal_hour,
                'confidence': self.confidence
            },
            'personalization': {
                'tone': self.tone,
                'greeting': self.greeting,
                'keyTopics': self.key_topics or [],
                'contentHooks': self.content_hooks or [],
                'cta': self.cta,
                'notes': self.notes
            },
            'created_at': self.created_at.isoformat()
        }


class UsageLog(db.Model):
    __tablename__ = 'usage_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100))  # email_analyzed, export, etc.
    details = db.Column(db.JSON)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='usage_logs')


class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    stripe_payment_id = db.Column(db.String(255))
    amount = db.Column(db.Integer)  # in cents
    currency = db.Column(db.String(10), default='usd')
    status = db.Column(db.String(50))  # succeeded, failed, pending
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='payments')