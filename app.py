# app.py - Complete Recharge Website (Updated - No Template Creation)
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
