from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, Payment
import stripe
from config import Config
import os

stripe.api_key = Config.STRIPE_SECRET_KEY

payment_bp = Blueprint('payment', __name__)

# Pricing plans
PLANS = {
    'pro_monthly': {
        'name': 'Pro Monthly',
        'price': 2900,  # $29.00
        'currency': 'usd',
        'interval': 'month',
        'tier': 'pro'
    },
    'pro_yearly': {
        'name': 'Pro Yearly',
        'price': 29000,  # $290.00 (save $58)
        'currency': 'usd',
        'interval': 'year',
        'tier': 'pro'
    },
    'enterprise': {
        'name': 'Enterprise',
        'price': 'custom',
        'tier': 'enterprise'
    }
}


@payment_bp.route('/plans', methods=['GET'])
def get_plans():
    """Get available pricing plans"""
    return jsonify({'plans': PLANS}), 200


@payment_bp.route('/create-checkout-session', methods=['POST'])
@jwt_required()
def create_checkout_session():
    """Create Stripe checkout session"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.json
        plan_id = data.get('plan_id')
        
        if plan_id not in PLANS:
            return jsonify({'error': 'Invalid plan'}), 400
        
        plan = PLANS[plan_id]
        
        # Create or get Stripe customer
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email,
                metadata={'user_id': user.id}
            )
            user.stripe_customer_id = customer.id
            db.session.commit()
        
        # Create checkout session
        session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': plan['currency'],
                    'product_data': {
                        'name': plan['name'],
                        'description': f"BOB 2 Email AI - {plan['name']}"
                    },
                    'unit_amount': plan['price'],
                    'recurring': {
                        'interval': plan['interval']
                    } if plan['interval'] != 'custom' else None
                },
                'quantity': 1
            }],
            mode='subscription' if plan['interval'] != 'custom' else 'payment',
            success_url=f"{Config.FRONTEND_URL}/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{Config.FRONTEND_URL}/pricing",
            metadata={
                'user_id': user.id,
                'plan_id': plan_id,
                'tier': plan['tier']
            }
        )
        
        return jsonify({'checkout_url': session.url}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@payment_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks"""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, Config.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle different event types
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)
    
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        handle_subscription_update(subscription)
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        handle_subscription_cancel(subscription)
    
    return jsonify({'status': 'success'}), 200


def handle_successful_payment(session):
    """Handle successful payment"""
    try:
        user_id = int(session['metadata']['user_id'])
        tier = session['metadata']['tier']
        
        user = User.query.get(user_id)
        if user:
            user.subscription_tier = tier
            user.subscription_status = 'active'
            user.stripe_subscription_id = session.get('subscription')
            
            # Reset monthly usage
            user.emails_analyzed_this_month = 0
            
            # Log payment
            payment = Payment(
                user_id=user.id,
                stripe_payment_id=session['payment_intent'],
                amount=session['amount_total'],
                currency=session['currency'],
                status='succeeded',
                description=f"Subscription: {tier}"
            )
            
            db.session.add(payment)
            db.session.commit()
            
    except Exception as e:
        print(f"Error handling payment: {e}")
        db.session.rollback()


def handle_subscription_update(subscription):
    """Handle subscription update"""
    try:
        customer_id = subscription['customer']
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        
        if user:
            user.subscription_status = subscription['status']
            db.session.commit()
            
    except Exception as e:
        print(f"Error updating subscription: {e}")
        db.session.rollback()


def handle_subscription_cancel(subscription):
    """Handle subscription cancellation"""
    try:
        customer_id = subscription['customer']
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        
        if user:
            user.subscription_tier = 'free'
            user.subscription_status = 'canceled'
            user.emails_analyzed_this_month = 0
            db.session.commit()
            
    except Exception as e:
        print(f"Error canceling subscription: {e}")
        db.session.rollback()


@payment_bp.route('/subscription', methods=['GET'])
@jwt_required()
def get_subscription():
    """Get user's subscription details"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        subscription_data = {
            'tier': user.subscription_tier,
            'status': user.subscription_status,
            'usage': {
                'current': user.emails_analyzed_this_month,
                'limit': user.get_usage_limit(),
                'percentage': (user.emails_analyzed_this_month / user.get_usage_limit()) * 100
            }
        }
        
        # Get Stripe subscription if exists
        if user.stripe_subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(user.stripe_subscription_id)
                subscription_data['stripe'] = {
                    'current_period_end': subscription['current_period_end'],
                    'cancel_at_period_end': subscription['cancel_at_period_end']
                }
            except:
                pass
        
        return jsonify(subscription_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@payment_bp.route('/cancel-subscription', methods=['POST'])
@jwt_required()
def cancel_subscription():
    """Cancel user's subscription"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user or not user.stripe_subscription_id:
            return jsonify({'error': 'No active subscription'}), 404
        
        # Cancel at period end (don't cancel immediately)
        subscription = stripe.Subscription.modify(
            user.stripe_subscription_id,
            cancel_at_period_end=True
        )
        
        return jsonify({
            'message': 'Subscription will be canceled at period end',
            'cancel_at': subscription['current_period_end']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500