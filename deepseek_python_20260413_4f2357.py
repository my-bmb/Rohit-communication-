# app.py - Complete Recharge Website
import os
import uuid
import random
import re
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
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

# Admin Configuration
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
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

# Create static CSS file
with open('static/css/style.css', 'w') as f:
    f.write('''/* Custom CSS for Recharge Website */
:root {
    --primary-color: #4361ee;
    --secondary-color: #3f37c9;
    --success-color: #4caf50;
    --danger-color: #f44336;
    --warning-color: #ff9800;
    --info-color: #2196f3;
    --dark-color: #333;
    --light-color: #f8f9fa;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
}

/* Custom Animations */
@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes slideIn {
    from {
        transform: translateX(-100%);
    }
    to {
        transform: translateX(0);
    }
}

@keyframes pulse {
    0% {
        transform: scale(1);
    }
    50% {
        transform: scale(1.05);
    }
    100% {
        transform: scale(1);
    }
}

/* Card Styles */
.card {
    border-radius: 15px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    animation: fadeIn 0.5s ease-out;
}

.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 15px 40px rgba(0, 0, 0, 0.15);
}

.card-header {
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    color: white;
    border-radius: 15px 15px 0 0 !important;
    padding: 20px;
    font-weight: 600;
}

/* Wallet Balance Section */
.wallet-balance {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 30px;
    border-radius: 20px;
    margin-bottom: 25px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
    animation: fadeIn 0.6s ease-out;
    text-align: center;
}

.wallet-balance h6 {
    font-size: 14px;
    opacity: 0.9;
    margin-bottom: 10px;
}

.wallet-balance h2 {
    font-size: 48px;
    font-weight: bold;
    margin-bottom: 20px;
}

/* Bottom Navigation */
.bottom-nav {
    position: fixed;
    bottom: 0;
    width: 100%;
    background: white;
    border-top: 1px solid #e0e0e0;
    padding: 10px 0;
    z-index: 1000;
    box-shadow: 0 -5px 20px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(10px);
}

.nav-item {
    text-align: center;
    color: #6c757d;
    text-decoration: none;
    font-size: 12px;
    transition: all 0.3s ease;
    padding: 5px 0;
}

.nav-item:hover {
    color: var(--primary-color);
    transform: translateY(-2px);
}

.nav-item.active {
    color: var(--primary-color);
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.nav-item i {
    font-size: 24px;
    display: block;
    margin-bottom: 4px;
    transition: transform 0.3s ease;
}

.nav-item:hover i {
    transform: scale(1.1);
}

/* Content Area */
.content {
    margin-bottom: 80px;
    padding: 20px;
}

/* Button Styles */
.btn {
    border-radius: 10px;
    font-weight: 600;
    padding: 10px 20px;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}

.btn::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.3);
    transform: translate(-50%, -50%);
    transition: width 0.6s, height 0.6s;
}

.btn:hover::before {
    width: 300px;
    height: 300px;
}

.btn-primary {
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    border: none;
}

.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 5px 15px rgba(67, 97, 238, 0.3);
}

/* Form Controls */
.form-control, .form-select {
    border-radius: 10px;
    border: 2px solid #e0e0e0;
    padding: 10px 15px;
    transition: all 0.3s ease;
}

.form-control:focus, .form-select:focus {
    border-color: var(--primary-color);
    box-shadow: 0 0 0 0.2rem rgba(67, 97, 238, 0.25);
}

/* Alert Styles */
.alert {
    border-radius: 10px;
    animation: slideIn 0.3s ease-out;
    border: none;
    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
}

/* Transaction List */
.transaction-item {
    padding: 15px;
    border-bottom: 1px solid #e0e0e0;
    transition: background 0.3s ease;
}

.transaction-item:hover {
    background: var(--light-color);
}

/* Badge Styles */
.badge {
    padding: 5px 10px;
    border-radius: 20px;
    font-weight: 500;
}

.badge-success {
    background: linear-gradient(135deg, var(--success-color), #45a049);
}

.badge-danger {
    background: linear-gradient(135deg, var(--danger-color), #da190b);
}

.badge-warning {
    background: linear-gradient(135deg, var(--warning-color), #fb8c00);
}

/* Loading Spinner */
.spinner {
    border: 3px solid rgba(0, 0, 0, 0.1);
    border-radius: 50%;
    border-top: 3px solid var(--primary-color);
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* Responsive Design */
@media (max-width: 768px) {
    .wallet-balance h2 {
        font-size: 32px;
    }
    
    .btn {
        padding: 8px 16px;
        font-size: 14px;
    }
    
    .card-header h4 {
        font-size: 18px;
    }
    
    .nav-item i {
        font-size: 20px;
    }
    
    .nav-item div {
        font-size: 10px;
    }
}

/* Custom Scrollbar */
::-webkit-scrollbar {
    width: 8px;
}

::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 10px;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    border-radius: 10px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--secondary-color);
}

/* Toast Notification */
.toast-custom {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 9999;
    animation: slideIn 0.3s ease-out;
}

/* Service Cards */
.service-card {
    text-align: center;
    padding: 20px;
    cursor: pointer;
    transition: all 0.3s ease;
}

.service-card:hover {
    transform: translateY(-10px);
}

.service-card i {
    font-size: 48px;
    margin-bottom: 15px;
    transition: transform 0.3s ease;
}

.service-card:hover i {
    transform: scale(1.1);
}

/* Pagination */
.pagination .page-link {
    border-radius: 10px;
    margin: 0 5px;
    color: var(--primary-color);
    transition: all 0.3s ease;
}

.pagination .page-link:hover {
    background: var(--primary-color);
    color: white;
    transform: translateY(-2px);
}

.pagination .active .page-link {
    background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
    border-color: var(--primary-color);
}

/* Money Request Alert */
.money-request-alert {
    background: linear-gradient(135deg, #ffeaa7, #fdcb6e);
    border-left: 5px solid var(--warning-color);
    animation: pulse 1s ease infinite;
}
''')

# Create static JavaScript file
with open('static/js/main.js', 'w') as f:
    f.write('''// Main JavaScript for Recharge Website

// Auto-dismiss alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            setTimeout(function() {
                bsAlert.close();
            }, 5000);
        });
    }, 1000);
    
    // Add loading effect to forms
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
                
                // Re-enable after 5 seconds if form doesn't submit
                setTimeout(function() {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = submitBtn.getAttribute('data-original-text') || 'Submit';
                }, 5000);
                
                // Store original text
                if (!submitBtn.getAttribute('data-original-text')) {
                    submitBtn.setAttribute('data-original-text', submitBtn.innerHTML);
                }
            }
        });
    });
    
    // Mobile number validation with formatting
    const mobileInputs = document.querySelectorAll('input[type="tel"]');
    mobileInputs.forEach(function(input) {
        input.addEventListener('input', function(e) {
            let value = this.value.replace(/\\D/g, '');
            if (value.length > 10) value = value.slice(0, 10);
            this.value = value;
        });
    });
    
    // Amount validation
    const amountInputs = document.querySelectorAll('input[type="number"]');
    amountInputs.forEach(function(input) {
        input.addEventListener('change', function() {
            let value = parseFloat(this.value);
            if (isNaN(value)) value = 0;
            if (value < 0) this.value = 0;
            if (this.max && value > parseFloat(this.max)) {
                this.value = this.max;
                showToast('Maximum amount is ₹' + this.max, 'warning');
            }
            if (this.min && value < parseFloat(this.min)) {
                this.value = this.min;
                showToast('Minimum amount is ₹' + this.min, 'warning');
            }
        });
    });
    
    // Add active class to current nav item
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-item');
    navLinks.forEach(function(link) {
        const href = link.getAttribute('href');
        if (href && currentPath.includes(href) && href !== '/') {
            link.classList.add('active');
        } else if (href === '/' && currentPath === '/') {
            link.classList.add('active');
        }
    });
    
    // Copy text functionality
    const copyButtons = document.querySelectorAll('.copy-btn');
    copyButtons.forEach(function(btn) {
        btn.addEventListener('click', function() {
            const textToCopy = this.getAttribute('data-copy');
            if (textToCopy) {
                navigator.clipboard.writeText(textToCopy).then(function() {
                    showToast('Copied to clipboard!', 'success');
                });
            }
        });
    });
    
    // Confirm dialog for important actions
    const confirmBtns = document.querySelectorAll('[data-confirm]');
    confirmBtns.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || 'Are you sure?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
    
    // Format currency inputs
    const currencyInputs = document.querySelectorAll('.currency-input');
    currencyInputs.forEach(function(input) {
        input.addEventListener('blur', function() {
            let value = parseFloat(this.value);
            if (!isNaN(value)) {
                this.value = value.toFixed(2);
            }
        });
    });
    
    // Add smooth scrolling
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href !== '#') {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth'
                    });
                }
            }
        });
    });
    
    // Live search functionality
    const searchInput = document.getElementById('liveSearch');
    if (searchInput) {
        searchInput.addEventListener('keyup', function() {
            const searchText = this.value.toLowerCase();
            const items = document.querySelectorAll('.search-item');
            items.forEach(function(item) {
                const text = item.textContent.toLowerCase();
                if (text.includes(searchText)) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }
});

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.style.position = 'fixed';
        container.style.top = '20px';
        container.style.right = '20px';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    toast.className = `toast-custom alert alert-${type}`;
    toast.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-circle' : 'info-circle'} me-2"></i>
                ${message}
            </div>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    
    document.getElementById('toast-container').appendChild(toast);
    
    setTimeout(function() {
        toast.remove();
    }, 5000);
}

// Format date for display
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Format currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 2
    }).format(amount);
}

// Validate mobile number
function validateMobile(mobile) {
    const pattern = /^[6-9]\\d{9}$/;
    return pattern.test(mobile);
}

// Validate email
function validateEmail(email) {
    const pattern = /^[^\\s@]+@([^\\s@.,]+\\.)+[^\\s@.,]{2,}$/;
    return pattern.test(email);
}

// Get query parameter
function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

// Show loading overlay
function showLoading() {
    const overlay = document.createElement('div');
    overlay.id = 'loading-overlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.background = 'rgba(0, 0, 0, 0.7)';
    overlay.style.zIndex = '99999';
    overlay.style.display = 'flex';
    overlay.style.justifyContent = 'center';
    overlay.style.alignItems = 'center';
    overlay.innerHTML = '<div class="spinner"></div>';
    document.body.appendChild(overlay);
}

// Hide loading overlay
function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}

// AJAX request helper
async function makeRequest(url, method = 'GET', data = null) {
    showLoading();
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        if (data && (method === 'POST' || method === 'PUT')) {
            options.body = JSON.stringify(data);
        }
        
        const response = await fetch(url, options);
        const result = await response.json();
        hideLoading();
        return result;
    } catch (error) {
        hideLoading();
        console.error('Error:', error);
        showToast('An error occurred. Please try again.', 'danger');
        return null;
    }
}

// Add to cart animation
function addToCartAnimation(element) {
    element.classList.add('animate__animated', 'animate__pulse');
    setTimeout(() => {
        element.classList.remove('animate__animated', 'animate__pulse');
    }, 1000);
}

// Initialize tooltips
var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
    return new bootstrap.Tooltip(tooltipTriggerEl)
});

// Initialize popovers
var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
    return new bootstrap.Popover(popoverTriggerEl)
});
''')

# Template: base.html
with open('templates/base.html', 'w') as f:
    f.write('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <meta name="description" content="Fast & Secure Mobile and DTH Recharge Platform">
    <meta name="theme-color" content="#4361ee">
    <title>{% block title %}Recharge Website{% endblock %}</title>
    
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <!-- Animate.css -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css">
    <!-- Custom CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    
    {% block extra_css %}{% endblock %}
</head>
<body>
    <!-- Toast Container -->
    <div id="toast-container"></div>
    
    <!-- Main Content -->
    <div class="container content mt-3">
        <!-- Flash Messages -->
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category if category != 'message' else 'info' }} alert-dismissible fade show animate__animated animate__fadeInDown" role="alert">
                        <i class="fas fa-{% if category == 'success' %}check-circle{% elif category == 'danger' %}exclamation-circle{% elif category == 'warning' %}exclamation-triangle{% else %}info-circle{% endif %} me-2"></i>
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <!-- Page Content -->
        {% block content %}{% endblock %}
    </div>
    
    <!-- Bottom Navigation (only for logged in users) -->
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
    
    <!-- Scripts -->
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    
    {% block extra_js %}{% endblock %}
</body>
</html>
''')

# Template: register.html
with open('templates/register.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block title %}Register - Recharge Website{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6 col-lg-5">
        <div class="card animate__animated animate__fadeInUp">
            <div class="card-header text-center">
                <i class="fas fa-user-plus fa-2x mb-2"></i>
                <h4 class="mb-0">Create Account</h4>
                <p class="mb-0 small">Join us for fast & secure recharges</p>
            </div>
            <div class="card-body">
                <form method="POST" id="registerForm">
                    <div class="mb-3">
                        <label class="form-label">
                            <i class="fas fa-user"></i> Full Name
                        </label>
                        <input type="text" name="name" class="form-control" required 
                               placeholder="Enter your full name" minlength="2" maxlength="100">
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">
                            <i class="fas fa-phone"></i> Mobile Number
                        </label>
                        <input type="tel" name="mobile" class="form-control" 
                               pattern="[6-9][0-9]{9}" required 
                               placeholder="10 digit mobile number" maxlength="10">
                        <small class="text-muted">
                            <i class="fas fa-info-circle"></i> Must be 10 digits starting with 6-9
                        </small>
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">
                            <i class="fas fa-lock"></i> Password
                        </label>
                        <input type="password" name="password" class="form-control" required 
                               placeholder="Minimum 6 characters" minlength="6">
                        <small class="text-muted">
                            <i class="fas fa-shield-alt"></i> At least 6 characters
                        </small>
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">
                            <i class="fas fa-check-circle"></i> Confirm Password
                        </label>
                        <input type="password" name="confirm_password" class="form-control" required>
                    </div>
                    
                    <div class="mb-3 form-check">
                        <input type="checkbox" class="form-check-input" id="terms" required>
                        <label class="form-check-label small" for="terms">
                            I agree to the <a href="#" data-bs-toggle="modal" data-bs-target="#termsModal">Terms & Conditions</a>
                        </label>
                    </div>
                    
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-user-plus"></i> Register
                    </button>
                </form>
                
                <hr>
                
                <p class="text-center mb-0">
                    Already have an account? 
                    <a href="{{ url_for('login') }}" class="text-primary">Login here</a>
                </p>
            </div>
        </div>
    </div>
</div>

<!-- Terms Modal -->
<div class="modal fade" id="termsModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Terms & Conditions</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <p>By registering on our platform, you agree to:</p>
                <ul>
                    <li>Provide accurate information</li>
                    <li>Maintain confidentiality of your account</li>
                    <li>Use services for legitimate purposes only</li>
                    <li>Comply with all applicable laws</li>
                </ul>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-primary" data-bs-dismiss="modal">I Agree</button>
            </div>
        </div>
    </div>
</div>
{% endblock %}
''')

# Template: login.html
with open('templates/login.html', 'w') as f:
    f.write('''{% extends "base.html" %}
{% block title %}Login - Recharge Website{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6 col-lg-5">
        <div class="card animate__animated animate__fadeInUp">
            <div class="card-header text-center">
                <i class="fas fa-sign-in-alt fa-2x mb-2"></i>
                <h4 class="mb-0">Welcome Back</h4>
                <p class="mb-0 small">Login to your account</p>
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">
                            <i class="fas fa-phone"></i> Mobile Number
                        </label>
                        <input type="tel" name="mobile" class="form-control" required 
                               placeholder="Enter registered mobile number" maxlength="10">
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">
                            <i class="fas fa-lock"></i> Password
                        </label>
                        <input type="password" name="password" class="form-control" required 
                               placeholder="Enter your password">
                    </div>
                    
                    <div class="mb-3 form-check">
                        <input type="checkbox" class="form-check-input" id="remember">
                        <label class="form-check-label" for="remember">Remember me</label>
                    </div>
                    
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-sign-in-alt"></i> Login
                    </button>
                </form>
                
                <hr>
                
                <p class="text-center mb-0">
                    New user? 
                    <a href="{{ url_for('register') }}" class="text-primary">Create an account</a>
                </p>
            </div>
        </div>
    </div>
</div>
{% endblock %}
''')

# Continue with remaining templates in next message due to length limit...