from flask import Flask, render_template, request, redirect, url_for, g, session, jsonify, flash, Response
import sqlite3
import os
import csv
import io
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'pos-system-secret-key' 
DATABASE = 'database.db'
UPLOAD_FOLDER = 'static/uploads'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- 1. DATABASE MANAGEMENT ---
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        # Create Tables
        db.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT NOT NULL, 
            sell_price REAL NOT NULL, 
            quantity INTEGER NOT NULL,
            min_stock_level INTEGER DEFAULT 5,
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            
        db.execute('''CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            product_id INTEGER,
            quantity INTEGER DEFAULT 1,
            total_price REAL, 
            grand_total REAL DEFAULT 0.0,
            vat_amount REAL DEFAULT 0.0,
            discount REAL DEFAULT 0.0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            
        db.execute('''CREATE TABLE IF NOT EXISTS cash_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            amount REAL,
            type TEXT, 
            description TEXT, 
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL)''')

        db.execute('''CREATE TABLE IF NOT EXISTS shop_settings (
            id INTEGER PRIMARY KEY,
            shop_name TEXT,
            logo_path TEXT)''')
        
        # MIGRATIONS: Ensures your DB has the columns that caused the "OperationalError"
        columns_to_add = [
            ("sales", "grand_total", "REAL DEFAULT 0.0"),
            ("sales", "vat_amount", "REAL DEFAULT 0.0"),
            ("sales", "discount", "REAL DEFAULT 0.0"),
            ("sales", "quantity", "INTEGER DEFAULT 1"),
            ("products", "min_stock_level", "INTEGER DEFAULT 5")
        ]
        for table, col, col_type in columns_to_add:
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass 

        # Default Admin
        admin_check = db.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        if not admin_check:
            db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("admin", generate_password_hash("admin123"), "Admin"))

        db.commit()

# --- 2. ACCESS CONTROL ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'Admin':
            flash("Unauthorized! Admin rights required.")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- 3. AUTHENTICATION ---
@app.route("/")
def index():
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user'] = user['username']
            session['role'] = user['role']
            return redirect(url_for("dashboard"))
        flash("Invalid username or password!")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- 4. POS & INVENTORY ---
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    shop_info = db.execute("SELECT * FROM shop_settings WHERE id = 1").fetchone()
    products = db.execute("SELECT * FROM products WHERE quantity > 0").fetchall()
    return render_template("dashboard.html", user=session['user'], role=session['role'], 
                           shop_info=dict(shop_info) if shop_info else {"shop_name": "My Shop"}, 
                           products=[dict(p) for p in products])

@app.route("/settle_payment", methods=["POST"])
@login_required
def settle_payment():
    data = request.json
    db = get_db()
    try:
        db.execute("BEGIN")
        subtotal = 0
        cart_items = []

        for item in data['cart']:
            prod = db.execute("SELECT sell_price, quantity FROM products WHERE id=?", (item['id'],)).fetchone()
            if not prod or prod['quantity'] < item['qty']:
                raise Exception(f"Low stock for item ID {item['id']}")
            
            line_price = prod['sell_price'] * item['qty']
            subtotal += line_price
            cart_items.append((item['id'], item['qty'], line_price))

        vat = subtotal * (data.get('vat_percent', 0) / 100)
        disc = data.get('discount', 0)
        final_total = subtotal + vat - disc

        for i, (p_id, qty, price) in enumerate(cart_items):
            db.execute("UPDATE products SET quantity = quantity - ? WHERE id=?", (qty, p_id))
            
            if i == 0:
                db.execute("INSERT INTO sales (product_id, quantity, total_price, grand_total, vat_amount, discount) VALUES (?, ?, ?, ?, ?, ?)",
                           (p_id, qty, price, final_total, vat, disc))
            else:
                db.execute("INSERT INTO sales (product_id, quantity, total_price, grand_total) VALUES (?, ?, ?, ?)",
                           (p_id, qty, price, price))

        db.commit()
        return jsonify({"status": "success", "total": round(final_total, 2)})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/inventory")
@login_required
def inventory():
    db = get_db()
    products = db.execute("SELECT * FROM products").fetchall()
    total_val = sum(p['sell_price'] * p['quantity'] for p in products)
    return render_template("inventory.html", products=products, total_value=total_val)

@app.route("/add_product", methods=["POST"])
@login_required
@admin_required
def add_product():
    db = get_db()
    db.execute("INSERT INTO products (name, sell_price, quantity) VALUES (?, ?, ?)", 
               (request.form.get("name"), request.form.get("price"), request.form.get("quantity")))
    db.commit()
    flash("Product added!")
    return redirect(url_for("inventory"))

# --- 5. FINANCE & REPORTS ---
@app.route('/reports')
@login_required
def reports():
    db = get_db()
    report_filter = request.args.get('filter')
    
    if report_filter == 'today':
        today_str = date.today().strftime('%Y-%m-%d')
        total_in = db.execute("SELECT SUM(grand_total) FROM sales WHERE DATE(timestamp) = ?", (today_str,)).fetchone()[0] or 0
        total_out = db.execute("SELECT SUM(amount) FROM cash_log WHERE DATE(timestamp) = ? AND type = 'OUT'", (today_str,)).fetchone()[0] or 0
    else:
        total_in = db.execute("SELECT SUM(grand_total) FROM sales").fetchone()[0] or 0
        total_out = db.execute("SELECT SUM(amount) FROM cash_log WHERE type = 'OUT'").fetchone()[0] or 0

    daily = db.execute("SELECT DATE(timestamp) as day, COUNT(id) as count, SUM(grand_total) as total FROM sales GROUP BY day ORDER BY day DESC LIMIT 30").fetchall()
    monthly = db.execute("SELECT strftime('%Y-%m', timestamp) as month, SUM(grand_total) as total FROM sales GROUP BY month ORDER BY month DESC").fetchall()
    
    yearly_raw = db.execute("SELECT strftime('%Y', timestamp) as year, strftime('%m', timestamp) as month_num, SUM(grand_total) as total FROM sales GROUP BY year, month_num ORDER BY year DESC").fetchall()
    yearly = [{'year': r['year'], 'month_name': datetime.strptime(r['month_num'], "%m").strftime("%B"), 'total': r['total']} for r in yearly_raw]

    return render_template('reports.html', total_in=total_in, total_out=total_out, balance=total_in-total_out,
                           daily=daily, monthly=monthly, yearly=yearly, current_date=datetime.now().strftime("%d %b %Y"), filter=report_filter)

@app.route("/cash", methods=["GET", "POST"])
@login_required
@admin_required
def cash():
    db = get_db()
    if request.method == "POST":
        db.execute("INSERT INTO cash_log (amount, type, description) VALUES (?, 'OUT', ?)", 
                   (request.form.get("amount"), request.form.get("description")))
        db.commit()
    
    logs = db.execute("SELECT * FROM cash_log ORDER BY timestamp DESC").fetchall()
    total_in = db.execute("SELECT SUM(grand_total) FROM sales").fetchone()[0] or 0
    total_out = db.execute("SELECT SUM(amount) FROM cash_log WHERE type = 'OUT'").fetchone()[0] or 0
    return render_template("cash.html", logs=logs, total_in=total_in, total_out=total_out, balance=total_in-total_out)

@app.route('/reports/daily_items')
@admin_required
def daily_items_report():
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    db = get_db()

    # Fixed query to use 'quantity' instead of 'current_stock'
    report_data = db.execute('''
        SELECT 
            p.name, 
            p.quantity, 
            p.min_stock_level,
            SUM(s.quantity) as total_sold,
            SUM(s.total_price) as revenue
        FROM products p
        LEFT JOIN sales s ON p.id = s.product_id AND DATE(s.timestamp) = ?
        GROUP BY p.id
        HAVING total_sold > 0 OR p.quantity <= p.min_stock_level
        ORDER BY (p.quantity <= p.min_stock_level) DESC, total_sold DESC
    ''', (target_date,)).fetchall()

    return render_template('daily_items.html', items=report_data, date=target_date)
@app.route("/sales")
@login_required
def sales_history():
    db = get_db()
    # This query joins sales and products so you can see the name of what was sold
    sales_data = db.execute('''
        SELECT s.id, p.name, s.quantity, s.total_price, s.timestamp 
        FROM sales s 
        JOIN products p ON s.product_id = p.id 
        ORDER BY s.timestamp DESC
    ''').fetchall()
    
    # Calculate the lifetime revenue for the banner
    total_revenue = db.execute("SELECT SUM(total_price) FROM sales").fetchone()[0] or 0
    
    return render_template("sales_report.html", sales=sales_data, total_revenue=total_revenue)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)