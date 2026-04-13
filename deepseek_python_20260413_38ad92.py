# app.py - User Website
import os
import uuid
import random
import re
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from supabase import create_client, Client
from bcrypt import hashpw, gensalt, checkpw

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = 30 * 24 * 60 * 60
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Supabase Configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://your-project.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'your-anon-key')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Admin Configuration (only for contact info)
ADMIN_NAME = "Rohit Singh"
ADMIN_MOBILE = "7392026692"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        try:
            response = supabase.table('user_profiles').select('*').eq('id', session['user_id']).execute()
            if response.data:
                return response.data[0]
        except Exception as e:
            print(f"Error getting user: {e}")
    return None

def validate_mobile(mobile):
    pattern = r'^[6-9]\d{9}$'
    return bool(re.match(pattern, mobile))

def generate_transaction_id():
    return f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"

def update_wallet(user_id, amount, transaction_type, description, reference_id=None):
    try:
        user_response = supabase.table('user_profiles').select('wallet_balance').eq('id', user_id).execute()
        if not user_response.data:
            return False
        
        current_balance = user_response.data[0]['wallet_balance']
        
        if transaction_type == 'DEBIT' and current_balance < amount:
            return False
        
        if transaction_type == 'CREDIT':
            new_balance = current_balance + amount
        elif transaction_type == 'DEBIT':
            new_balance = current_balance - amount
        else:
            return False
        
        supabase.table('user_profiles').update({'wallet_balance': new_balance}).eq('id', user_id).execute()
        
        wallet_txn = {
            'user_id': user_id,
            'amount': amount,
            'type': transaction_type,
            'description': description,
            'reference_id': reference_id,
            'date': datetime.utcnow().isoformat()
        }
        supabase.table('wallet_transactions').insert(wallet_txn).execute()
        
        return True
    except Exception as e:
        print(f"Error updating wallet: {e}")
        return False

def dummy_recharge_api(mobile, operator, amount):
    result = random.choices(['SUCCESS', 'FAILED', 'PENDING'], weights=[70, 20, 10])[0]
    return {
        'status': result,
        'api_reference': str(uuid.uuid4()),
        'message': f'API {result} for {mobile} with {operator}',
        'timestamp': datetime.now().isoformat()
    }

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not all([name, mobile, password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))
        
        if len(name) < 2 or len(name) > 100:
            flash('Name must be between 2 and 100 characters', 'danger')
            return redirect(url_for('register'))
        
        if not validate_mobile(mobile):
            flash('Invalid mobile number. Must be 10 digits starting with 6-9', 'danger')
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
        
        try:
            existing_user = supabase.table('user_profiles').select('*').eq('mobile', mobile).execute()
            if existing_user.data:
                flash('Mobile number already registered', 'danger')
                return redirect(url_for('register'))
            
            hashed_password = hashpw(password.encode('utf-8'), gensalt())
            new_user = {
                'name': name,
                'mobile': mobile,
                'password': hashed_password.decode('utf-8'),
                'wallet_balance': 0.0,
                'is_active': True,
                'is_admin': False,
                'created_at': datetime.utcnow().isoformat()
            }
            
            supabase.table('user_profiles').insert(new_user).execute()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            print(f"Registration error: {e}")
            flash('Registration failed. Please try again.', 'danger')
            return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        mobile = request.form.get('mobile', '').strip()
        password = request.form.get('password', '')
        
        if not mobile or not password:
            flash('Mobile and password are required', 'danger')
            return redirect(url_for('login'))
        
        try:
            response = supabase.table('user_profiles').select('*').eq('mobile', mobile).eq('is_active', True).execute()
            
            if response.data:
                user = response.data[0]
                if checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
                    session.permanent = True
                    session['user_id'] = user['id']
                    session['user_name'] = user['name']
                    session['user_mobile'] = user['mobile']
                    session['is_admin'] = False
                    flash(f'Welcome back, {user["name"]}!', 'success')
                    return redirect(url_for('dashboard'))
            
            flash('Invalid mobile number or password', 'danger')
            
        except Exception as e:
            print(f"Login error: {e}")
            flash('Login failed. Please try again.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    try:
        recent_transactions = supabase.table('transactions')\
            .select('*')\
            .eq('user_id', session['user_id'])\
            .order('date', desc=True)\
            .limit(5)\
            .execute()
        recent_transactions = recent_transactions.data if recent_transactions else []
    except Exception as e:
        print(f"Error fetching transactions: {e}")
        recent_transactions = []
    
    return render_template('dashboard.html', user=user, recent_transactions=recent_transactions)

@app.route('/wallet')
@login_required
def wallet():
    user = get_current_user()
    try:
        wallet_transactions = supabase.table('wallet_transactions')\
            .select('*')\
            .eq('user_id', session['user_id'])\
            .order('date', desc=True)\
            .limit(50)\
            .execute()
        wallet_transactions = wallet_transactions.data if wallet_transactions else []
    except Exception as e:
        print(f"Error fetching wallet transactions: {e}")
        wallet_transactions = []
    
    return render_template('wallet.html', user=user, transactions=wallet_transactions, admin_name=ADMIN_NAME, admin_mobile=ADMIN_MOBILE)

@app.route('/add-money-request', methods=['POST'])
@login_required
def add_money_request():
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount', 'danger')
        return redirect(url_for('wallet'))
    
    if amount <= 0:
        flash('Amount must be greater than 0', 'danger')
        return redirect(url_for('wallet'))
    
    if amount > 10000:
        flash('Maximum amount per request is ₹10,000', 'danger')
        return redirect(url_for('wallet'))
    
    user = get_current_user()
    
    request_id = f"REQ{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
    
    money_request = {
        'request_id': request_id,
        'user_id': session['user_id'],
        'user_name': user['name'],
        'user_mobile': user['mobile'],
        'amount': amount,
        'status': 'PENDING',
        'created_at': datetime.utcnow().isoformat()
    }
    
    try:
        supabase.table('money_requests').insert(money_request).execute()
        flash(f'Money request of ₹{amount:.2f} sent to admin. Please call {ADMIN_NAME} at {ADMIN_MOBILE} for approval.', 'info')
    except Exception as e:
        print(f"Error creating money request: {e}")
        flash('Failed to create money request. Please try again.', 'danger')
    
    return redirect(url_for('wallet'))

@app.route('/mobile-recharge')
@login_required
def mobile_recharge():
    operators = ['Airtel', 'Jio', 'Vi', 'BSNL']
    plans = [10, 50, 100, 199, 299, 399, 499, 599, 699, 999, 1499, 1999]
    return render_template('mobile_recharge.html', operators=operators, plans=plans)

@app.route('/process-recharge', methods=['POST'])
@login_required
def process_recharge():
    mobile = request.form.get('mobile', '').strip()
    confirm_mobile = request.form.get('confirm_mobile', '').strip()
    operator = request.form.get('operator', '').strip()
    
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount selected', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    if not mobile or not confirm_mobile:
        flash('Mobile number is required', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    if mobile != confirm_mobile:
        flash('Mobile numbers do not match', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    if not validate_mobile(mobile):
        flash('Invalid mobile number. Must be 10 digits starting with 6-9', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    if not operator:
        flash('Please select an operator', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    if amount <= 0:
        flash('Invalid amount', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    user = get_current_user()
    if user['wallet_balance'] < amount:
        flash(f'Insufficient balance. Available: ₹{user["wallet_balance"]:.2f}', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    session['pending_recharge'] = {
        'mobile': mobile,
        'operator': operator,
        'amount': amount,
        'type': 'MOBILE'
    }
    
    return render_template('confirm_recharge.html', 
                         mobile=mobile, 
                         operator=operator, 
                         amount=amount,
                         wallet_balance=user['wallet_balance'])

@app.route('/do-recharge', methods=['POST'])
@login_required
def do_recharge():
    pending = session.get('pending_recharge')
    if not pending:
        flash('No recharge data found. Please start again.', 'danger')
        return redirect(url_for('mobile_recharge'))
    
    mobile = pending['mobile']
    operator = pending['operator']
    amount = pending['amount']
    recharge_type = pending.get('type', 'MOBILE')
    user = get_current_user()
    
    if user['wallet_balance'] < amount:
        flash('Insufficient balance', 'danger')
        session.pop('pending_recharge', None)
        return redirect(url_for('mobile_recharge'))
    
    txn_id = generate_transaction_id()
    
    transaction = {
        'txn_id': txn_id,
        'user_id': user['id'],
        'number': mobile,
        'operator': operator,
        'amount': amount,
        'status': 'PENDING',
        'type': recharge_type,
        'date': datetime.utcnow().isoformat()
    }
    
    try:
        supabase.table('transactions').insert(transaction).execute()
    except Exception as e:
        print(f"Error creating transaction: {e}")
        flash('Failed to create transaction', 'danger')
        session.pop('pending_recharge', None)
        return redirect(url_for('mobile_recharge'))
    
    api_response = dummy_recharge_api(mobile, operator, amount)
    
    if api_response['status'] == 'SUCCESS':
        if update_wallet(user['id'], amount, 'DEBIT', 
                        f'{recharge_type} recharge to {mobile} ({operator})', txn_id):
            supabase.table('transactions').update({'status': 'SUCCESS'}).eq('txn_id', txn_id).execute()
            flash('Recharge successful! Amount deducted from wallet.', 'success')
        else:
            supabase.table('transactions').update({'status': 'FAILED'}).eq('txn_id', txn_id).execute()
            flash('Failed to deduct wallet balance', 'danger')
            
    elif api_response['status'] == 'FAILED':
        supabase.table('transactions').update({'status': 'FAILED'}).eq('txn_id', txn_id).execute()
        flash('Recharge failed. Please try again.', 'danger')
        
    else:
        supabase.table('transactions').update({'status': 'PENDING'}).eq('txn_id', txn_id).execute()
        flash('Recharge is pending. Please check status later.', 'warning')
    
    session.pop('pending_recharge', None)
    return redirect(url_for('recharge_status', txn_id=txn_id))

@app.route('/recharge-status/<txn_id>')
@login_required
def recharge_status(txn_id):
    try:
        response = supabase.table('transactions')\
            .select('*')\
            .eq('txn_id', txn_id)\
            .eq('user_id', session['user_id'])\
            .execute()
        
        if not response.data:
            abort(404)
        
        transaction = response.data[0]
    except Exception as e:
        print(f"Error fetching transaction: {e}")
        abort(404)
    
    return render_template('recharge_status.html', transaction=transaction)

@app.route('/dth-recharge')
@login_required
def dth_recharge():
    operators = ['Tata Sky', 'Airtel DTH', 'Dish TV', 'Sun Direct', 'Videocon d2h']
    plans = [100, 200, 300, 500, 1000, 1500, 2000, 2500, 5000]
    return render_template('dth_recharge.html', operators=operators, plans=plans)

@app.route('/process-dth-recharge', methods=['POST'])
@login_required
def process_dth_recharge():
    subscriber_id = request.form.get('subscriber_id', '').strip()
    confirm_subscriber_id = request.form.get('confirm_subscriber_id', '').strip()
    operator = request.form.get('operator', '').strip()
    
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount selected', 'danger')
        return redirect(url_for('dth_recharge'))
    
    if not subscriber_id or not confirm_subscriber_id:
        flash('Subscriber ID is required', 'danger')
        return redirect(url_for('dth_recharge'))
    
    if subscriber_id != confirm_subscriber_id:
        flash('Subscriber IDs do not match', 'danger')
        return redirect(url_for('dth_recharge'))
    
    if len(subscriber_id) < 8 or len(subscriber_id) > 15:
        flash('Invalid subscriber ID length', 'danger')
        return redirect(url_for('dth_recharge'))
    
    if not operator:
        flash('Please select an operator', 'danger')
        return redirect(url_for('dth_recharge'))
    
    if amount <= 0:
        flash('Invalid amount', 'danger')
        return redirect(url_for('dth_recharge'))
    
    user = get_current_user()
    if user['wallet_balance'] < amount:
        flash(f'Insufficient balance. Available: ₹{user["wallet_balance"]:.2f}', 'danger')
        return redirect(url_for('dth_recharge'))
    
    session['pending_recharge'] = {
        'mobile': subscriber_id,
        'operator': operator,
        'amount': amount,
        'type': 'DTH'
    }
    
    return render_template('confirm_dth_recharge.html',
                         subscriber_id=subscriber_id,
                         operator=operator,
                         amount=amount,
                         wallet_balance=user['wallet_balance'])

@app.route('/do-dth-recharge', methods=['POST'])
@login_required
def do_dth_recharge():
    pending = session.get('pending_recharge')
    if not pending or pending.get('type') != 'DTH':
        flash('No DTH recharge data found', 'danger')
        return redirect(url_for('dth_recharge'))
    
    subscriber_id = pending['mobile']
    operator = pending['operator']
    amount = pending['amount']
    user = get_current_user()
    
    if user['wallet_balance'] < amount:
        flash('Insufficient balance', 'danger')
        session.pop('pending_recharge', None)
        return redirect(url_for('dth_recharge'))
    
    txn_id = generate_transaction_id()
    
    transaction = {
        'txn_id': txn_id,
        'user_id': user['id'],
        'number': subscriber_id,
        'operator': operator,
        'amount': amount,
        'status': 'PENDING',
        'type': 'DTH',
        'date': datetime.utcnow().isoformat()
    }
    
    try:
        supabase.table('transactions').insert(transaction).execute()
    except Exception as e:
        print(f"Error creating transaction: {e}")
        flash('Failed to create transaction', 'danger')
        session.pop('pending_recharge', None)
        return redirect(url_for('dth_recharge'))
    
    api_response = dummy_recharge_api(subscriber_id, operator, amount)
    
    if api_response['status'] == 'SUCCESS':
        if update_wallet(user['id'], amount, 'DEBIT', 
                        f'DTH recharge to {subscriber_id} ({operator})', txn_id):
            supabase.table('transactions').update({'status': 'SUCCESS'}).eq('txn_id', txn_id).execute()
            flash('DTH recharge successful!', 'success')
        else:
            supabase.table('transactions').update({'status': 'FAILED'}).eq('txn_id', txn_id).execute()
            flash('Failed to deduct wallet balance', 'danger')
    elif api_response['status'] == 'FAILED':
        supabase.table('transactions').update({'status': 'FAILED'}).eq('txn_id', txn_id).execute()
        flash('DTH recharge failed. Please try again.', 'danger')
    else:
        supabase.table('transactions').update({'status': 'PENDING'}).eq('txn_id', txn_id).execute()
        flash('DTH recharge is pending. Please check status later.', 'warning')
    
    session.pop('pending_recharge', None)
    return redirect(url_for('recharge_status', txn_id=txn_id))

@app.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    try:
        count_response = supabase.table('transactions')\
            .select('*', count='exact')\
            .eq('user_id', session['user_id'])\
            .execute()
        
        total = len(count_response.data) if count_response.data else 0
        
        start = (page - 1) * per_page
        end = start + per_page - 1
        
        response = supabase.table('transactions')\
            .select('*')\
            .eq('user_id', session['user_id'])\
            .order('date', desc=True)\
            .range(start, end)\
            .execute()
        
        transactions = response.data if response.data else []
        
        class Pagination:
            def __init__(self, items, page, per_page, total):
                self.items = items
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = (total + per_page - 1) // per_page if total > 0 else 1
            
            def has_prev(self):
                return self.page > 1
            
            def has_next(self):
                return self.page < self.pages
            
            def prev_num(self):
                return self.page - 1
            
            def next_num(self):
                return self.page + 1
        
        paginated_transactions = Pagination(transactions, page, per_page, total)
        
    except Exception as e:
        print(f"Error fetching history: {e}")
        paginated_transactions = Pagination([], page, per_page, 0)
    
    return render_template('history.html', transactions=paginated_transactions)

# Create templates directory
os.makedirs('templates', exist_ok=True)

# Template: base.html
with open('templates/base.html', 'w') as f:
    f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Recharge Website</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .bottom-nav {
            position: fixed;
            bottom: 0;
            width: 100%;
            background: white;
            border-top: 1px solid #e0e0e0;
            padding: 8px 0;
            z-index: 1000;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
        }
        .nav-item {
            text-align: center;
            color: #6c757d;
            text-decoration: none;
            font-size: 12px;
            transition: all 0.3s;
        }
        .nav-item:hover {
            color: #007bff;
        }
        .nav-item.active {
            color: #007bff;
        }
        .nav-item i {
            font-size: 24px;
            display: block;
            margin-bottom: 4px;
        }
        .content {
            margin-bottom: 80px;
        }
        .wallet-balance {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 25px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .card {
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            border: none;
        }
        .btn {
            border-radius: 8px;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="container content mt-3">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category if category != 'message' else 'info' }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>
    
    {% if session.user_id %}
    <div class="bottom-nav">
        <div class="row text-center g-0">
            <div class="col">
                <a href="{{ url_for('dashboard') }}" class="nav-item d-block {% if request.endpoint == 'dashboard' %}active{% endif %}">
                    <i class="fas fa-home"></i>
                    <div>Home</div>
                </a>
            </div>
            <div class="col">
                <a href="{{ url_for('mobile_recharge') }}" class="nav-item d-block {% if request.endpoint == 'mobile_recharge' %}active{% endif %}">
                    <i class="fas fa-mobile-alt"></i>
                    <div>Mobile</div>
                </a>
            </div>
            <div class="col">
                <a href="{{ url_for('dth_recharge') }}" class="nav-item d-block {% if request.endpoint == 'dth_recharge' %}active{% endif %}">
                    <i class="fas fa-tv"></i>
                    <div>DTH</div>
                </a>
            </div>
            <div class="col">
                <a href="{{ url_for('history') }}" class="nav-item d-block {% if request.endpoint == 'history' %}active{% endif %}">
                    <i class="fas fa-history"></i>
                    <div>History</div>
                </a>
            </div>
            <div class="col">
                <a href="{{ url_for('wallet') }}" class="nav-item d-block {% if request.endpoint == 'wallet' %}active{% endif %}">
                    <i class="fas fa-wallet"></i>
                    <div>Wallet</div>
                </a>
            </div>
        </div>
    </div>
    {% endif %}
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
''')

# Template: register.html
with open('templates/register.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h4 class="mb-0">Create Account</h4>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Full Name</label>
                        <input type="text" name="name" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Mobile Number</label>
                        <input type="tel" name="mobile" class="form-control" pattern="[6-9][0-9]{9}" required>
                        <small class="text-muted">10 digit mobile number starting with 6-9</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Password</label>
                        <input type="password" name="password" class="form-control" required>
                        <small class="text-muted">Minimum 6 characters</small>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Confirm Password</label>
                        <input type="password" name="confirm_password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Register</button>
                </form>
                <p class="mt-3 text-center">Already have an account? <a href="{{ url_for('login') }}">Login</a></p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
''')

# Template: login.html
with open('templates/login.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header bg-primary text-white">
                <h4 class="mb-0">Login</h4>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Mobile Number</label>
                        <input type="tel" name="mobile" class="form-control" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Password</label>
                        <input type="password" name="password" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary w-100">Login</button>
                </form>
                <p class="mt-3 text-center">New user? <a href="{{ url_for('register') }}">Register</a></p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
''')

# Template: dashboard.html
with open('templates/dashboard.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<div class="wallet-balance">
    <h6>Wallet Balance</h6>
    <h2>₹{{ "%.2f"|format(user.wallet_balance) }}</h2>
    <a href="{{ url_for('wallet') }}" class="btn btn-light btn-sm mt-2">Add Money</a>
</div>

<div class="row mb-4">
    <div class="col-md-6 mb-3">
        <div class="card text-center">
            <div class="card-body">
                <i class="fas fa-mobile-alt fa-3x text-primary mb-3"></i>
                <h5>Mobile Recharge</h5>
                <p>Recharge prepaid/postpaid mobile</p>
                <a href="{{ url_for('mobile_recharge') }}" class="btn btn-primary">Recharge Now</a>
            </div>
        </div>
    </div>
    <div class="col-md-6 mb-3">
        <div class="card text-center">
            <div class="card-body">
                <i class="fas fa-tv fa-3x text-success mb-3"></i>
                <h5>DTH Recharge</h5>
                <p>Recharge your DTH connection</p>
                <a href="{{ url_for('dth_recharge') }}" class="btn btn-success">Recharge Now</a>
            </div>
        </div>
    </div>
</div>

{% if recent_transactions %}
<div class="card">
    <div class="card-header">
        <h6>Recent Transactions</h6>
    </div>
    <div class="card-body">
        {% for txn in recent_transactions %}
        <div class="d-flex justify-content-between mb-2">
            <div>
                <small>{{ txn.number }}</small><br>
                <small class="text-muted">{{ txn.date[:16]|replace('T', ' ') }}</small>
            </div>
            <div class="text-end">
                <small>₹{{ "%.2f"|format(txn.amount) }}</small><br>
                {% if txn.status == 'SUCCESS' %}
                    <span class="badge bg-success">Success</span>
                {% elif txn.status == 'FAILED' %}
                    <span class="badge bg-danger">Failed</span>
                {% else %}
                    <span class="badge bg-warning">Pending</span>
                {% endif %}
            </div>
        </div>
        {% if not loop.last %}<hr>{% endif %}
        {% endfor %}
    </div>
</div>
{% endif %}
{% endblock %}
''')

# Template: mobile_recharge.html
with open('templates/mobile_recharge.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<h4>Mobile Recharge</h4>
<form method="POST" action="{{ url_for('process_recharge') }}">
    <div class="card">
        <div class="card-body">
            <div class="mb-3">
                <label class="form-label">Mobile Number</label>
                <input type="tel" name="mobile" class="form-control" pattern="[6-9][0-9]{9}" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Confirm Mobile Number</label>
                <input type="tel" name="confirm_mobile" class="form-control" pattern="[6-9][0-9]{9}" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Operator</label>
                <select name="operator" class="form-control" required>
                    <option value="">Select Operator</option>
                    {% for op in operators %}
                    <option value="{{ op }}">{{ op }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">Select Amount</label>
                <select name="amount" class="form-control" required>
                    <option value="">Select Amount</option>
                    {% for plan in plans %}
                    <option value="{{ plan }}">₹{{ plan }}</option>
                    {% endfor %}
                </select>
            </div>
            <button type="submit" class="btn btn-primary w-100">Proceed</button>
        </div>
    </div>
</form>
{% endblock %}
''')

# Template: confirm_recharge.html
with open('templates/confirm_recharge.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<h4>Confirm Recharge</h4>
<div class="card">
    <div class="card-body">
        <h6>Recharge Details</h6>
        <table class="table table-borderless">
            <tr><td><strong>Mobile Number:</strong></td><td>{{ mobile }}</td></tr>
            <tr><td><strong>Operator:</strong></td><td>{{ operator }}</td></tr>
            <tr><td><strong>Amount:</strong></td><td>₹{{ "%.2f"|format(amount) }}</td></tr>
            <tr><td><strong>Wallet Balance:</strong></td><td>₹{{ "%.2f"|format(wallet_balance) }}</td></tr>
            <tr class="table-info"><td><strong>Balance After:</strong></td><td>₹{{ "%.2f"|format(wallet_balance - amount) }}</td></tr>
        </table>
        <form method="POST" action="{{ url_for('do_recharge') }}">
            <button type="submit" class="btn btn-success w-100 mb-2">Confirm & Recharge</button>
            <a href="{{ url_for('mobile_recharge') }}" class="btn btn-secondary w-100">Cancel</a>
        </form>
    </div>
</div>
{% endblock %}
''')

# Template: dth_recharge.html
with open('templates/dth_recharge.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<h4>DTH Recharge</h4>
<form method="POST" action="{{ url_for('process_dth_recharge') }}">
    <div class="card">
        <div class="card-body">
            <div class="mb-3">
                <label class="form-label">Subscriber ID</label>
                <input type="text" name="subscriber_id" class="form-control" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Confirm Subscriber ID</label>
                <input type="text" name="confirm_subscriber_id" class="form-control" required>
            </div>
            <div class="mb-3">
                <label class="form-label">Operator</label>
                <select name="operator" class="form-control" required>
                    <option value="">Select Operator</option>
                    {% for op in operators %}
                    <option value="{{ op }}">{{ op }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="mb-3">
                <label class="form-label">Select Amount</label>
                <select name="amount" class="form-control" required>
                    <option value="">Select Amount</option>
                    {% for plan in plans %}
                    <option value="{{ plan }}">₹{{ plan }}</option>
                    {% endfor %}
                </select>
            </div>
            <button type="submit" class="btn btn-primary w-100">Proceed</button>
        </div>
    </div>
</form>
{% endblock %}
''')

# Template: confirm_dth_recharge.html
with open('templates/confirm_dth_recharge.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<h4>Confirm DTH Recharge</h4>
<div class="card">
    <div class="card-body">
        <h6>Recharge Details</h6>
        <table class="table table-borderless">
            <tr><td><strong>Subscriber ID:</strong></td><td>{{ subscriber_id }}</td></tr>
            <tr><td><strong>Operator:</strong></td><td>{{ operator }}</td></tr>
            <tr><td><strong>Amount:</strong></td><td>₹{{ "%.2f"|format(amount) }}</td></tr>
            <tr><td><strong>Wallet Balance:</strong></td><td>₹{{ "%.2f"|format(wallet_balance) }}</td></tr>
            <tr class="table-info"><td><strong>Balance After:</strong></td><td>₹{{ "%.2f"|format(wallet_balance - amount) }}</td></tr>
        </table>
        <form method="POST" action="{{ url_for('do_dth_recharge') }}">
            <button type="submit" class="btn btn-success w-100 mb-2">Confirm & Recharge</button>
            <a href="{{ url_for('dth_recharge') }}" class="btn btn-secondary w-100">Cancel</a>
        </form>
    </div>
</div>
{% endblock %}
''')

# Template: recharge_status.html
with open('templates/recharge_status.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<div class="card">
    <div class="card-body text-center">
        {% if transaction.status == 'SUCCESS' %}
            <i class="fas fa-check-circle fa-5x text-success mb-3"></i>
            <h4 class="text-success">Recharge Successful!</h4>
        {% elif transaction.status == 'FAILED' %}
            <i class="fas fa-times-circle fa-5x text-danger mb-3"></i>
            <h4 class="text-danger">Recharge Failed!</h4>
        {% else %}
            <i class="fas fa-clock fa-5x text-warning mb-3"></i>
            <h4 class="text-warning">Recharge Pending</h4>
            <p>Your recharge is being processed</p>
        {% endif %}
        
        <hr>
        <div class="text-start">
            <p><strong>Transaction ID:</strong> {{ transaction.txn_id }}</p>
            <p><strong>Number/ID:</strong> {{ transaction.number }}</p>
            <p><strong>Operator:</strong> {{ transaction.operator }}</p>
            <p><strong>Amount:</strong> ₹{{ "%.2f"|format(transaction.amount) }}</p>
            <p><strong>Date:</strong> {{ transaction.date[:16]|replace('T', ' ') }}</p>
        </div>
        
        <div class="mt-3">
            <a href="{{ url_for('dashboard') }}" class="btn btn-primary">Go to Dashboard</a>
            <a href="{{ url_for('history') }}" class="btn btn-info">View History</a>
        </div>
    </div>
</div>
{% endblock %}
''')

# Template: history.html
with open('templates/history.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<h4>Transaction History</h4>
<div class="card">
    <div class="card-body">
        {% if transactions.items %}
            {% for txn in transactions.items %}
            <div class="d-flex justify-content-between align-items-center mb-3 pb-2 border-bottom">
                <div>
                    <strong>{{ txn.type }} Recharge</strong><br>
                    <small>{{ txn.number }}</small><br>
                    <small class="text-muted">{{ txn.date[:16]|replace('T', ' ') }}</small>
                </div>
                <div class="text-end">
                    <strong>₹{{ "%.2f"|format(txn.amount) }}</strong><br>
                    {% if txn.status == 'SUCCESS' %}
                        <span class="badge bg-success">Success</span>
                    {% elif txn.status == 'FAILED' %}
                        <span class="badge bg-danger">Failed</span>
                    {% else %}
                        <span class="badge bg-warning">Pending</span>
                    {% endif %}
                    <br>
                    <a href="{{ url_for('recharge_status', txn_id=txn.txn_id) }}" class="small">Details</a>
                </div>
            </div>
            {% endfor %}
            
            <nav>
                <ul class="pagination justify-content-center">
                    {% if transactions.has_prev %}
                    <li class="page-item"><a class="page-link" href="?page={{ transactions.prev_num }}">Previous</a></li>
                    {% endif %}
                    
                    <li class="page-item active"><span class="page-link">Page {{ transactions.page }} of {{ transactions.pages }}</span></li>
                    
                    {% if transactions.has_next %}
                    <li class="page-item"><a class="page-link" href="?page={{ transactions.next_num }}">Next</a></li>
                    {% endif %}
                </ul>
            </nav>
        {% else %}
            <p class="text-center text-muted">No transactions found</p>
        {% endif %}
    </div>
</div>
{% endblock %}
''')

# Template: wallet.html
with open('templates/wallet.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block content %}
<div class="wallet-balance">
    <h6>Current Balance</h6>
    <h2>₹{{ "%.2f"|format(user.wallet_balance) }}</h2>
</div>

<div class="card mb-4">
    <div class="card-header">
        <h6>Add Money to Wallet</h6>
    </div>
    <div class="card-body">
        <div class="alert alert-info">
            <i class="fas fa-info-circle"></i> To add money to your wallet, please contact admin:
            <strong>{{ admin_name }}</strong> at <strong>{{ admin_mobile }}</strong>
        </div>
        <form method="POST" action="{{ url_for('add_money_request') }}">
            <div class="input-group">
                <span class="input-group-text">₹</span>
                <input type="number" name="amount" class="form-control" placeholder="Enter amount" min="1" max="10000" step="1" required>
                <button type="submit" class="btn btn-warning">Request Money</button>
            </div>
            <small class="text-muted">Min: ₹1 | Max: ₹10,000 per request | You need to call admin after requesting</small>
        </form>
    </div>
</div>

<div class="card">
    <div class="card-header">
        <h6>Wallet Transactions</h6>
    </div>
    <div class="card-body">
        {% if transactions %}
            {% for txn in transactions %}
            <div class="d-flex justify-content-between mb-3 pb-2 border-bottom">
                <div>
                    {% if txn.type == 'CREDIT' %}
                        <i class="fas fa-plus-circle text-success"></i> Added
                    {% else %}
                        <i class="fas fa-minus-circle text-danger"></i> Debited
                    {% endif %}
                    <br>
                    <small class="text-muted">{{ txn.description }}</small><br>
                    <small class="text-muted">{{ txn.date[:16]|replace('T', ' ') }}</small>
                </div>
                <div class="{% if txn.type == 'CREDIT' %}text-success{% else %}text-danger{% endif %}">
                    <strong>{% if txn.type == 'CREDIT' %}+{% else %}-{% endif %} ₹{{ "%.2f"|format(txn.amount) }}</strong>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p class="text-center text-muted">No wallet transactions</p>
        {% endif %}
    </div>
</div>
{% endblock %}
''')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)