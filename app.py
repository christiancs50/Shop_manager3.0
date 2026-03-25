import io
import os
import sqlite3
from datetime import datetime, date
from functools import wraps
from dotenv import load_dotenv  # Ensure you ran 'pip install python-dotenv'

#The PDF specific imports
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

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

def get_shop_settings():
    db = get_db()
    # Returns the settings row as a dictionary-like object
    return db.execute("SELECT * FROM shop_settings WHERE id = 1").fetchone()

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        
        # Product Table
        db.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT NOT NULL,
            category TEXT DEFAULT 'General', 
            sell_price REAL NOT NULL, 
            quantity INTEGER NOT NULL CHECK(quantity >= 0),
            is_active INTEGER DEFAULT 1,
            min_stock_level INTEGER DEFAULT 5,
            date_added DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')))''')
            
        db.execute('''CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            product_id INTEGER,
            quantity INTEGER DEFAULT 1,
            total_price REAL, 
            grand_total REAL DEFAULT 0.0,
            vat_amount REAL DEFAULT 0.0,
            discount REAL DEFAULT 0.0,
            timestamp DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            user_id INTEGER,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE RESTRICT,
            FOREIGN KEY (user_id) REFERENCES users (id)
            )''')
            
        db.execute('''CREATE TABLE IF NOT EXISTS cash_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            amount REAL,
            type TEXT, 
            description TEXT, 
            timestamp DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')))''')
            
        db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL)''')

        db.execute('''CREATE TABLE IF NOT EXISTS shop_settings (
            id INTEGER PRIMARY KEY,
            shop_name TEXT,
            logo_path TEXT,
            tax_rate REAL DEFAULT 0.0,
            currency TEXT DEFAULT '$',
            delete_grace_period INTEGER DEFAULT 7,
            address TEXT,
            contact_number TEXT)''')
        
        db.execute('''CREATE TABLE IF NOT EXISTS inventory_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            old_quantity INTEGER,
            added_quantity INTEGER,
            new_quantity INTEGER,
            change_date DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
            FOREIGN KEY (product_id) REFERENCES products (id)
            )''')
        
        # Default Admin Setup
        if not db.execute("SELECT * FROM users WHERE username = 'admin'").fetchone():
            db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       ("admin", generate_password_hash("admin123"), "Admin"))

        # Default Shop setup
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
            session['user_id'] = user['id']
            session['user'] = user['username']
            session['role'] = user['role']
            return redirect(url_for("dashboard"))
        flash("Invalid username or password!")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.context_processor
def inject_shop():
    db = get_db()
    shop_data = db.execute("SELECT * FROM shop_settings WHERE id = 1").fetchone()
    # This allows you to use {{ shop.currency }} in any HTML file
    return dict(shop=shop_data)

@app.route("/delete_user/<int:id>", methods=["POST", "GET"])
@login_required
@admin_required # Crucial: Only an Admin should be able to delete people!
def delete_user(id):
    db = get_db()
    
    # 1. Safety Check: Don't let the user delete themselves
    # This prevents you from accidentally locking yourself out of the app.
    current_user_id = session.get('user_id') 
    if id == current_user_id:
        flash("Error: You cannot delete your own account while logged in!")
        return redirect(url_for('register'))

    # 2. Run the Delete Command
    try:
        db.execute("DELETE FROM users WHERE id = ?", (id,))
        db.commit()
        flash("Staff account removed successfully.")
    except Exception as e:
        flash(f"Error removing user: {str(e)}")
    
    # 3. Go back to the registration/staff list page
    return redirect(url_for('register'))

@app.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings():
    db = get_db()
    
    if request.method == "POST":
        # 1. Collect Form Data
        shop_name = request.form.get("shop_name")
        tax_rate = request.form.get("tax_rate")
        currency = request.form.get("currency")
        grace_period = request.form.get("grace_period")
        address = request.form.get("address")
        contact = request.form.get("contact")

        # 2. Handle Logo Upload
        file = request.files.get('logo')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            upload_path = os.path.join('static', 'uploads')
            if not os.path.exists(upload_path):
                os.makedirs(upload_path)
            file.save(os.path.join(upload_path, filename))
            
            db.execute('''
                UPDATE shop_settings 
                SET shop_name=?, tax_rate=?, currency=?, 
                    delete_grace_period=?, address=?, contact_number=?, logo_path=?
                WHERE id = 1
            ''', (shop_name, tax_rate, currency, grace_period, address, contact, filename))
        else:
            db.execute('''
                UPDATE shop_settings 
                SET shop_name=?, tax_rate=?, currency=?, 
                    delete_grace_period=?, address=?, contact_number=?
                WHERE id = 1
            ''', (shop_name, tax_rate, currency, grace_period, address, contact))
            
        db.commit()
        flash("Settings updated successfully!")
        return redirect(url_for('settings'))

    # GET request: shop data is now handled by the context_processor above
    return render_template("settings.html")

@app.route("/update_settings", methods=["POST"])
def update_settings():
    db = get_db()
    
    # Get values from your HTML form
    shop_name = request.form.get("shop_name")
    currency = request.form.get("currency")
    tax_rate = request.form.get("tax_rate")
    address = request.form.get("address")
    contact = request.form.get("contact")
    grace = request.form.get("grace_period")

    # Update the database (assuming your table is named 'shop')
    db.execute("""
        UPDATE shop_settings
        SET shop_name = ?, currency = ?, tax_rate = ?, 
            address = ?, contact_number = ?, delete_grace_period = ?
        WHERE id = 1
    """, (shop_name, currency, tax_rate, address, contact, grace))
    
    db.commit()
    
    # Flash a message to the user
    import flask
    flask.flash("Settings updated successfully!")
    
    # Redirect back to the settings page
    return flask.redirect("/settings")

# --- 4. POS & INVENTORY ---
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    
    # --- 1. FIX: Fetch the shop information so 'shop_info' exists! ---
    # We fetch the first row from your settings/shop table
    shop_info = db.execute("SELECT * FROM shop_settings LIMIT 1").fetchone()
    
    # --- 2. Your existing product logic ---
    products = db.execute("SELECT * FROM products WHERE quantity > 0").fetchall()
    
    # --- 3. Return everything together ---
    return render_template(
        "dashboard.html", 
        user=session.get('user', 'Staff'), 
        role=session.get('role', 'User'), 
        shop=dict(shop_info) if shop_info else {}, # Now shop_info is defined!
        products=[dict(p) for p in products]
    )


@app.route("/settle_payment", methods=["POST"])
@login_required
def settle_payment():
    data = request.json
    db = get_db()
    
    # 1. Fetch the official tax rate from settings
    settings = get_shop_settings()
    tax_rate = settings['tax_rate'] if settings else 0.0

    try:
        db.execute("BEGIN")
        subtotal = 0
        cart_items = []

        for item in data['cart']:
            prod = db.execute("SELECT name, sell_price, quantity FROM products WHERE id=? AND is_active=1", (item['id'],)).fetchone()
            if not prod or prod['quantity'] < item['qty']:
                raise Exception(f"Stock issue with {prod['name'] if prod else 'Item'}")
            
            db.execute("UPDATE products SET quantity = quantity - ? WHERE id=?", (item['qty'], item['id']))
            line_price = prod['sell_price'] * item['qty']
            subtotal += line_price
            cart_items.append((item['id'], item['qty'], line_price))

        # 2. Use the dynamic tax rate
        vat_amount = subtotal * (tax_rate / 100)
        final_total = subtotal + vat_amount - data.get('discount', 0)

        for i, (p_id, qty, price) in enumerate(cart_items):
            # Only store totals on the first row of the transaction to avoid double-counting
            g_total = final_total if i == 0 else 0.0 
            v_amt = vat_amount if i == 0 else 0.0
            disc = data.get('discount', 0) if i == 0 else 0.0
            
            db.execute('''INSERT INTO sales 
                (product_id, quantity, total_price, grand_total, vat_amount, discount, user_id) 
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (p_id, qty, price, g_total, v_amt, disc, session.get('user_id')))

        db.commit()
        last_id = db.execute("SELECT id FROM sales ORDER BY id DESC LIMIT 1").fetchone()
        return jsonify({"status": "success", "total": round(final_total, 2), "trans_id": last_id['id']})
    except Exception as e:
        db.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400

        
@app.route("/inventory")
@login_required
def inventory():
    db = get_db()
    products = db.execute("SELECT *, (quantity <= min_stock_level) as is_low FROM products").fetchall()
    total_val = sum(p['sell_price'] * p['quantity'] for p in products)
    return render_template("inventory.html", products=products, total_value=total_val)


@app.route("/edit_product", methods=["POST"])
@login_required
@admin_required
def edit_product():
    data = request.json
    product_id = data.get('id')
    new_name = data.get('name')
    new_price = data.get('price')
    new_qty = data.get('quantity')

    if not all([product_id, new_name, new_price is not None, new_qty is not None]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    db = get_db()
    try:
        db.execute('''
            UPDATE products 
            SET name = ?, sell_price = ?, quantity = ? 
            WHERE id = ?
        ''', (new_name, new_price, new_qty, product_id))
        db.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/delete_product/<int:product_id>", methods=["POST"])
@login_required
@admin_required
def delete_product(product_id):
    db = get_db() # Fixed: Added missing db connection
    
    # 1. Fetch your custom grace period from settings
    settings = get_shop_settings()
    DAYS_LIMIT = settings['delete_grace_period'] if settings else 7 

    try:
        # 2. Fetch the product
        product = db.execute("SELECT name, date_added FROM products WHERE id = ?", (product_id,)).fetchone()
        
        if not product:
            flash("Product not found!")
            return redirect(url_for('inventory'))

        # 3. Parse Date Safely
        added_date_str = product['date_added']
        added_date = None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                added_date = datetime.strptime(added_date_str, fmt)
                break
            except ValueError:
                continue

        if not added_date:
            flash("Error: Could not determine product age.")
            return redirect(url_for('inventory'))

        # 4. Calculate Age (Using UTC to match your init_db 'now')
        age_in_days = (datetime.utcnow() - added_date).days

        # 5. The "Business Logic" Check
        if age_in_days >= DAYS_LIMIT:
            flash(f"Security: '{product['name']}' is {age_in_days} days old. "
                  f"Limit is {DAYS_LIMIT} days. Please Archive instead.")
            return redirect(url_for('inventory'))

        # 6. Delete
        db.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
        flash(f"Successfully deleted '{product['name']}'.")

    except sqlite3.IntegrityError:
        flash("Database Error: Item has sales history and cannot be deleted.")
    except Exception as e:
        flash(f"Error: {str(e)}")
        
    return redirect(url_for('inventory'))


@app.route("/add_product", methods=["POST"])
@login_required
@admin_required
def add_product():
    name = request.form.get("name").strip()
    price = float(request.form.get("price"))
    added_qty = int(request.form.get("quantity"))
    db = get_db()
    
    # Check if the product exists
    existing = db.execute("SELECT id, quantity FROM products WHERE name = ?", (name,)).fetchone()

    if existing:
        old_qty = existing['quantity']
        new_qty = old_qty + added_qty
        
        # 1. Update the product table
        db.execute("UPDATE products SET quantity = ?, sell_price = ? WHERE id = ?", 
                   (new_qty, price, existing['id']))
        
        # 2. Record the history in the log
        db.execute("INSERT INTO inventory_log (product_id, old_quantity, added_quantity, new_quantity) VALUES (?, ?, ?, ?)",
                   (existing['id'], old_qty, added_qty, new_qty))
        
        flash(f"Restocked {name}: Was {old_qty}, now {new_qty}.")
    else:
        # For brand new products, we just insert into products
        db.execute("INSERT INTO products (name, sell_price, quantity) VALUES (?, ?, ?)", 
                   (name, price, added_qty))
        flash(f"New product {name} added to inventory.")

    db.commit()
    return redirect(url_for("inventory"))

@app.route("/delete_restock_log/<int:log_id>", methods=["POST"])
@login_required
@admin_required
def delete_restock_log(log_id):
    db = get_db()
    
    # 1. Find the log entry
    log = db.execute("SELECT * FROM inventory_log WHERE id = ?", (log_id,)).fetchone()
    
    if log:
        product_id = log['product_id']
        added_qty = log['added_quantity']
        
        # 2. Subtract the added quantity from the current product stock
        db.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?", (added_qty, product_id))
        
        # 3. Delete the log
        db.execute("DELETE FROM inventory_log WHERE id = ?", (log_id,))
        db.commit()
        flash("Restock log deleted and stock adjusted back.")
    
    return redirect(url_for('restock_history'))

@app.route("/restock_history")
@login_required
@admin_required
def restock_history():
    db = get_db()
    logs = db.execute('''
        SELECT l.id, p.name, l.old_quantity, l.added_quantity, l.new_quantity, l.change_date 
        FROM inventory_log l 
        JOIN products p ON l.product_id = p.id 
        ORDER BY l.change_date DESC
    ''').fetchall()
    return render_template("restock_history.html", logs=logs)

@app.route("/download_restock_pdf")
@login_required
@admin_required
def download_restock_pdf():
    db = get_db()
    logs = db.execute('''
        SELECT p.name, l.old_quantity, l.added_quantity, l.new_quantity, l.change_date 
        FROM inventory_log l 
        JOIN products p ON l.product_id = p.id 
        ORDER BY l.change_date DESC
    ''').fetchall()

    # Create a file-like buffer to receive PDF data
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Title
    styles = getSampleStyleSheet()
    elements.append(Paragraph("Inventory Restock Report", styles['Title']))
    elements.append(Paragraph(f"Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    
    # Table Data
    data = [["Date", "Product", "Old Stock", "Added", "New Total"]]
    for log in logs:
        data.append([
            log['change_date'][:16], # Shorten date string
            log['name'],
            str(log['old_quantity']),
            f"+{log['added_quantity']}",
            str(log['new_quantity'])
        ])

    # Styling the Table
    table = Table(data)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.dodgerblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])
    table.setStyle(style)
    elements.append(table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return Response(buffer, mimetype='application/pdf', 
                    headers={"Content-Disposition": "attachment;filename=restock_report.pdf"})

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
                           daily=daily, monthly=monthly, yearly=yearly, current_date=datetime.utcnow().strftime("%d %b %Y"), filter=report_filter)

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
    target_date = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))
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

@app.route("/register", methods=["GET", "POST"])
@login_required
@admin_required
def register():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        
        try:
            # Note: Ensure 'password_hash' is the correct column name in your table
            db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                       (username, generate_password_hash(password), role))
            db.commit()
            flash(f"Staff member {username} registered successfully!")
            return redirect(url_for('register'))
        except sqlite3.IntegrityError:
            flash("Username already exists!")
            pass
    # --- NEW: Fetch all users to display them on the page ---
    staff_list = db.execute("SELECT id, username, role FROM users").fetchall()
    
    # Pass 'staff' to the template
    return render_template("register.html", staff=staff_list)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)