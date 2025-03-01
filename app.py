# app.py
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import sqlite3
import json
import os
import hashlib
from datetime import datetime
import uuid
from functools import wraps
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# Database initialization
def init_db():
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # FinancingElements table
    c.execute('''
    CREATE TABLE IF NOT EXISTS financing_elements (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT,
        amount REAL NOT NULL,
        type TEXT NOT NULL,  -- "ingreso" or "egreso"
        state TEXT NOT NULL, -- "pending" or "paid"
        month TEXT NOT NULL,
        year INTEGER NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES users (id)
    )
    ''')
    
    # In init_db() function, add this table creation:
    c.execute('''
    CREATE TABLE IF NOT EXISTS activity_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        action_type TEXT NOT NULL,  -- "create", "update", "delete"
        entity_type TEXT NOT NULL,  -- "financing_element"
        entity_id TEXT NOT NULL,
        details TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')
    
    # Create config if it doesn't exist
    if not os.path.exists('config.json'):
        default_config = {
            "default_egresos": ["Rent", "Utilities", "WiFi", "Groceries"],
            "default_ingresos": ["Salary", "Other Income"]
        }
        with open('config.json', 'w') as f:
            json.dump(default_config, f)
    
    conn.commit()
    conn.close()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return render_template('dashboard.html')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    # Hash password
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    try:
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO users (id, username, password) VALUES (?, ?, ?)",
                 (user_id, username, hashed_password))
        conn.commit()
        return jsonify({"success": True, "message": "User registered successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 400
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    
    # Hash password
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    c.execute("SELECT id, username FROM users WHERE username = ? AND password = ?",
             (username, hashed_password))
    user = c.fetchone()
    conn.close()
    
    if user:
        session['user_id'] = user[0]
        session['username'] = user[1]
        return jsonify({"success": True, "redirect": "/"}), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "redirect": "/login"}), 200

@app.route('/api/config', methods=['GET'])
@login_required
def get_config():
    with open('config.json', 'r') as f:
        config = json.load(f)
    return jsonify(config)

@app.route('/api/elements', methods=['GET'])
@login_required
def get_elements():
    month = request.args.get('month', datetime.now().strftime('%B'))
    year = int(request.args.get('year', datetime.now().year))
    
    conn = sqlite3.connect('roommates.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
    SELECT * FROM financing_elements 
    WHERE month = ? AND year = ? 
    ORDER BY created_at DESC
    """, (month, year))
    
    elements = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(elements)

# Update create_element function:
@app.route('/api/elements', methods=['POST'])
@login_required
def create_element():
    data = request.json
    required_fields = ['title', 'amount', 'type', 'state', 'month', 'year']
    
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    element_id = str(uuid.uuid4())
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    c.execute("""
    INSERT INTO financing_elements 
    (id, title, description, amount, type, state, month, year, created_by) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        element_id,
        data['title'],
        data.get('description', ''),
        data['amount'],
        data['type'],
        data['state'],
        data['month'],
        data['year'],
        session['user_id']
    ))
    
    conn.commit()
    conn.close()
    
    # Log the activity
    log_activity("create", "financing_element", element_id, data)
    
    return jsonify({"success": True, "id": element_id}), 201

# Update update_element function:
@app.route('/api/elements/<element_id>', methods=['PUT'])
@login_required
def update_element(element_id):
    data = request.json
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    # Build dynamic update query based on provided fields
    fields = []
    values = []
    
    for field in ['title', 'description', 'amount', 'type', 'state']:
        if field in data:
            fields.append(f"{field} = ?")
            values.append(data[field])
    
    if not fields:
        return jsonify({"error": "No fields to update"}), 400
    
    query = f"UPDATE financing_elements SET {', '.join(fields)} WHERE id = ?"
    values.append(element_id)
    
    c.execute(query, values)
    
    if c.rowcount == 0:
        conn.close()
        return jsonify({"error": "Element not found"}), 404
    
    conn.commit()
    conn.close()
    
    # Log the activity
    log_activity("update", "financing_element", element_id, data)
    
    return jsonify({"success": True}), 200

@app.route('/api/elements/<element_id>', methods=['DELETE'])
@login_required
def delete_element(element_id):
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    # First get the element data for logging
    c.execute("SELECT * FROM financing_elements WHERE id = ?", (element_id,))
    element = c.fetchone()
    
    if not element:
        conn.close()
        return jsonify({"error": "Element not found"}), 404
    
    # Convert to dict for logging
    columns = [col[0] for col in c.description]
    element_data = {columns[i]: element[i] for i in range(len(columns))}
    
    # Delete the element
    c.execute("DELETE FROM financing_elements WHERE id = ?", (element_id,))
    conn.commit()
    conn.close()
    
    # Log the activity
    log_activity("delete", "financing_element", element_id, element_data)
    
    return jsonify({"success": True}), 200

@app.route('/api/balance/graph', methods=['GET'])
@login_required
def get_balance_graph():
    months_to_show = int(request.args.get('months', 6))
    
    # Get the current month and year
    current_date = datetime.now()
    
    # Generate the list of months to display
    dates = []
    balances = []
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    # Go back (months_to_show - 1) months from current month
    for i in range(months_to_show - 1, -1, -1):
        date = current_date - timedelta(days=30 * i)
        month = date.strftime('%B')
        year = date.year
        
        # Get balance for this month
        c.execute("""
        SELECT 
            SUM(CASE WHEN type = 'ingreso' AND state = 'paid' THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN type = 'egreso' AND state = 'paid' THEN amount ELSE 0 END) as expense
        FROM financing_elements 
        WHERE (year < ? OR (year = ? AND month <= ?))
        """, (year, year, month))
        
        result = c.fetchone()
        cumulative_income = result[0] or 0
        cumulative_expense = result[1] or 0
        cumulative_balance = cumulative_income - cumulative_expense
        
        dates.append(f"{month[:3]} {year}")
        balances.append(cumulative_balance)
    
    # Also get monthly income and expenses for the chart
    monthly_income = []
    monthly_expenses = []
    
    for i in range(months_to_show - 1, -1, -1):
        date = current_date - timedelta(days=30 * i)
        month = date.strftime('%B')
        year = date.year
        
        c.execute("""
        SELECT 
            SUM(CASE WHEN type = 'ingreso' AND state = 'paid' THEN amount ELSE 0 END) as income,
            SUM(CASE WHEN type = 'egreso' AND state = 'paid' THEN amount ELSE 0 END) as expense
        FROM financing_elements 
        WHERE month = ? AND year = ?
        """, (month, year))
        
        result = c.fetchone()
        income = result[0] or 0
        expense = result[1] or 0
        
        monthly_income.append(income)
        monthly_expenses.append(expense)
    
    conn.close()
    
    return jsonify({
        'labels': dates,
        'datasets': {
            'balance': balances,
            'income': monthly_income,
            'expenses': monthly_expenses
        }
    })

def log_activity(action_type, entity_type, entity_id, details=None):
    if 'user_id' not in session:
        return  # Can't log if no user is logged in
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    log_id = str(uuid.uuid4())
    c.execute("""
    INSERT INTO activity_logs 
    (id, user_id, action_type, entity_type, entity_id, details) 
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        log_id,
        session['user_id'],
        action_type,
        entity_type,
        entity_id,
        json.dumps(details) if details else None
    ))
    
    conn.commit()
    conn.close()
    
@app.route('/api/logs', methods=['GET'])
@login_required
def get_logs():
    limit = int(request.args.get('limit', 20))
    
    conn = sqlite3.connect('roommates.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("""
    SELECT l.*, u.username
    FROM activity_logs l
    JOIN users u ON l.user_id = u.id
    ORDER BY l.created_at DESC
    LIMIT ?
    """, (limit,))
    
    logs = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(logs)

@app.route('/logs')
@login_required
def logs_page():
    return render_template('logs.html')

# Replace the @app.before_first_request decorator with this pattern
def init_app(app):
    with app.app_context():
        init_db()
        

# Create a directory to store profile images if it doesn't exist
UPLOAD_FOLDER = 'static/profile_images'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/profile')
@login_required
def profile_page():
    return render_template('profile.html')

@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    conn = sqlite3.connect('roommates.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT username, email, profile_image FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    conn.close()
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Access using dictionary-like syntax but handle None values correctly
    email = user['email'] if 'email' in user.keys() else ''
    profile_image = user['profile_image'] if 'profile_image' in user.keys() else ''
    
    return jsonify({
        "displayName": user['username'],
        "email": email,
        "profileImage": profile_image
    })

@app.route('/api/profile', methods=['PUT'])
@login_required
def update_profile():
    data = request.json
    display_name = data.get('displayName')
    email = data.get('email')
    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    # First, check if we need to update the password
    if current_password and new_password:
        # Verify current password
        hashed_current = hashlib.sha256(current_password.encode()).hexdigest()
        c.execute("SELECT id FROM users WHERE id = ? AND password = ?", 
                 (session['user_id'], hashed_current))
        
        if not c.fetchone():
            conn.close()
            return jsonify({"error": "Contraseña actual incorrecta"}), 400
        
        # Hash the new password
        hashed_new = hashlib.sha256(new_password.encode()).hexdigest()
    else:
        hashed_new = None
    
    # Build update query
    update_fields = []
    update_values = []
    
    if display_name:
        update_fields.append("username = ?")
        update_values.append(display_name)
    
    if email:
        update_fields.append("email = ?")
        update_values.append(email)
    
    if hashed_new:
        update_fields.append("password = ?")
        update_values.append(hashed_new)
    
    if not update_fields:
        conn.close()
        return jsonify({"error": "No data to update"}), 400
    
    # Update user
    update_values.append(session['user_id'])
    c.execute(f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?", update_values)
    
    # Update session with new username if changed
    if display_name:
        session['username'] = display_name
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True}), 200

@app.route('/api/profile/image', methods=['POST'])
@login_required
def upload_profile_image():
    if 'profile_image' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['profile_image']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        # Secure the filename and create a unique filename with user ID
        filename = secure_filename(file.filename)
        extension = os.path.splitext(filename)[1]
        new_filename = f"profile_{session['user_id']}{extension}"
        
        filepath = os.path.join(UPLOAD_FOLDER, new_filename)
        file.save(filepath)
        
        # Update the user's profile image in the database
        profile_image_url = f"/static/profile_images/{new_filename}"
        
        conn = sqlite3.connect('roommates.db')
        c = conn.cursor()
        c.execute("UPDATE users SET profile_image = ? WHERE id = ?", 
                 (profile_image_url, session['user_id']))
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True, 
            "profileImage": profile_image_url
        }), 200
    
    return jsonify({"error": "Error procesando la imagen"}), 400

@app.route('/api/balance', methods=['GET'])
@login_required
def get_balance():
    month = request.args.get('month', datetime.now().strftime('%B'))
    year = int(request.args.get('year', datetime.now().year))
    
    conn = sqlite3.connect('roommates.db')
    c = conn.cursor()
    
    # Get monthly income and expenses
    c.execute("""
    SELECT 
        SUM(CASE WHEN type = 'ingreso' AND state = 'paid' THEN amount ELSE 0 END) as income,
        SUM(CASE WHEN type = 'egreso' AND state = 'paid' THEN amount ELSE 0 END) as expense
    FROM financing_elements 
    WHERE month = ? AND year = ?
    """, (month, year))
    
    result = c.fetchone()
    monthly_income = result[0] or 0
    monthly_expense = result[1] or 0
    monthly_balance = monthly_income - monthly_expense
    
    # Get cumulative balance up to this month
    c.execute("""
    SELECT 
        SUM(CASE WHEN type = 'ingreso' AND state = 'paid' THEN amount ELSE 0 END) as income,
        SUM(CASE WHEN type = 'egreso' AND state = 'paid' THEN amount ELSE 0 END) as expense
    FROM financing_elements 
    WHERE (year < ? OR (year = ? AND month <= ?))
    """, (year, year, month))
    
    result = c.fetchone()
    cumulative_income = result[0] or 0
    cumulative_expense = result[1] or 0
    cumulative_balance = cumulative_income - cumulative_expense
    
    conn.close()
    
    return jsonify({
        'monthly': {
            'income': monthly_income,
            'expense': monthly_expense,
            'balance': monthly_balance
        },
        'cumulative': {
            'income': cumulative_income,
            'expense': cumulative_expense,
            'balance': cumulative_balance
        }
    })

# Then modify your app.py file near the bottom like this:
if __name__ == '__main__':
    init_app(app)
    app.run(host='0.0.0.0', port=5000)