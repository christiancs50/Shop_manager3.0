import os
import sqlite3
from datetime import datetime, date
from functools import wraps
from dotenv import load_dotenv  # Ensure you ran 'pip install python-dotenv'
from flask import Flask, render_template, request, redirect, url_for, g, session, jsonify, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash

# 1. Load environment variables FIRST
load_dotenv()

app = Flask(__name__)

# 2. Use os.getenv to pull from .env. 
# We REMOVE the hardcoded 'pos-system-secret-key' line.
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-dev-key-123')
DATABASE = os.getenv('DATABASE_URL', 'database.db')
UPLOAD_FOLDER = 'static/uploads'

# 3. Create upload folder if missing
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- 1. DATABASE MANAGEMENT ---
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        
        db.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT NOT NULL, 
            sell_price REAL NOT NULL, 
            quantity INTEGER NOT NULL CHECK(quantity >= 0),
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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE RESTRICT)''')
            
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
        
        db.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT NOT NULL, 
            category TEXT DEFAULT 'General',     -- New: For filtering
            sell_price REAL NOT NULL, 
            quantity INTEGER NOT NULL CHECK(quantity >= 0), 
            is_active INTEGER DEFAULT 1,         -- New: 1 = Active, 0 = Deleted
            min_stock_level INTEGER DEFAULT 5,
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        
        if not db.execute("SELECT * FROM users WHERE username = 'admin'").fetchone():
            db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("admin", generate_password_hash("admin123"), "Admin"))

        if not db.execute("SELECT * FROM shop_settings WHERE id = 1").fetchone():
            db.execute("INSERT INTO shop_settings (id, shop_name, logo_path) VALUES (1, 'My Shop', 'default_logo.png')")

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
        # Start the transaction to ensure all-or-nothing logic
        db.execute("BEGIN")
        
        subtotal = 0
        cart_items = []

        for item in data['cart']:
            # 1. Fetch price and current stock
            prod = db.execute("SELECT name, sell_price, quantity FROM products WHERE id=?", (item['id'],)).fetchone()
            
            if not prod:
                raise Exception(f"Item ID {item['id']} not found.")
            
            # 2. Check if enough stock exists before updating
            if prod['quantity'] < item['qty']:
                raise Exception(f"Low stock for {prod['name']} (Available: {prod['quantity']})")
            
            # 3. Deduct stock (This will also trigger the CHECK constraint if quantity < 0)
            db.execute("UPDATE products SET quantity = quantity - ? WHERE id=?", 
                       (item['qty'], item['id']))
            
            line_price = prod['sell_price'] * item['qty']
            subtotal += line_price
            cart_items.append((item['id'], item['qty'], line_price))

        # 4. Calculate Totals
        vat_percent = data.get('vat_percent', 0)
        vat_amount = subtotal * (vat_percent / 100)
        discount = data.get('discount', 0)
        final_total = subtotal + vat_amount - discount

        # 5. Record the sale entries
        for i, (p_id, qty, price) in enumerate(cart_items):
            if i == 0:
                # First item holds the grand total and tax info
                db.execute("INSERT INTO sales (product_id, quantity, total_price, grand_total, vat_amount, discount) VALUES (?, ?, ?, ?, ?, ?)",
                           (p_id, qty, price, final_total, vat_amount, discount))
            else:
                # Subsequent items in the same cart
                db.execute("INSERT INTO sales (product_id, quantity, total_price, grand_total) VALUES (?, ?, ?, ?)",
                           (p_id, qty, price, price))

        # 6. Commit and get the Transaction ID for the receipt
        db.commit()
        
        # Get the ID of the sale we just inserted
        last_id = db.execute("SELECT id FROM sales ORDER BY id DESC LIMIT 1").fetchone()
        
        return jsonify({
            "status": "success", 
            "total": round(final_total, 2),
            "trans_id": last_id['id']  # This connects to your JavaScript r-id
        })

    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({"status": "error", "message": "Transaction failed: Stock limit reached."}), 400
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
    
    # 1. Get the filter dates from the browser (if they exist)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Base Queries
    sales_query = "SELECT s.id, p.name, s.quantity, s.total_price, s.grand_total, s.vat_amount, s.timestamp FROM sales s JOIN products p ON s.product_id = p.id"
    totals_query = "SELECT IFNULL(SUM(grand_total), 0) as total_revenue, IFNULL(SUM(vat_amount), 0) as total_vat, IFNULL(SUM(discount), 0) as total_discount FROM sales"
    
    params = []
    
    # 2. Add the "WHERE" clause only if dates are provided
    if start_date and end_date:
        # We use DATE() to ignore the specific time and just look at the day
        filter_sql = " WHERE DATE(s.timestamp) BETWEEN ? AND ?"
        sales_query += filter_sql
        
        # Totals query doesn't have the 's' alias join, so we adjust slightly
        totals_query += " WHERE DATE(timestamp) BETWEEN ? AND ?"
        params = [start_date, end_date]

    # Always show newest sales first
    sales_query += " ORDER BY s.timestamp DESC"

    # 3. Execute with parameters to prevent SQL Injection
    sales_list = db.execute(sales_query, params).fetchall()
    totals = db.execute(totals_query, params).fetchone()

    return render_template("sales_report.html", sales=sales_list, totals=totals)

@app.route("/api/top_products")
@login_required
def top_products():
    db = get_db()
    # Join sales and products to get the names and total revenue per item
    query = '''
        SELECT p.name, SUM(s.total_price) as revenue, SUM(s.quantity) as units_sold
        FROM sales s
        JOIN products p ON s.product_id = p.id
        GROUP BY p.id
        ORDER BY revenue DESC
        LIMIT 5
    '''
    top_items = db.execute(query).fetchall()
    return jsonify([dict(ix) for ix in top_items])


    # Calculate the lifetime revenue for the banner
    total_revenue = db.execute("SELECT SUM(total_price) FROM sales").fetchone()[0] or 0
    
    return render_template("sales_report.html", sales=sales_data, total_revenue=total_revenue)

@app.route("/register", methods=["GET", "POST"]) # Changed to match your HTML action
@login_required
@admin_required
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        
        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       (username, generate_password_hash(password), role))
            db.commit()
            flash(f"Staff member {username} registered successfully!")
            return redirect(url_for('register')) # Stay on page to see success msg
        except sqlite3.IntegrityError:
            flash("Username already exists!")
            
    return render_template("register.html")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)