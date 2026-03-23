from flask import Flask, render_template, request, redirect, url_for, g, flash
import sqlite3

app = Flask(__name__)
app.secret_key = 'dev-key-123' # Necessary for flash messages to work
DATABASE = 'database.db'

# --- Database Helpers ---

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
        # 1. Products Table
        db.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cost_price REAL DEFAULT 0,
                sell_price REAL NOT NULL,
                quantity INTEGER NOT NULL
            )
        ''')

        # 2. Sales Table
        db.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                quantity_sold INTEGER,
                total_price REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        ''')

        # 3. Cash Log (Fixed the "EXIST" typo here)
        db.execute('''
            CREATE TABLE IF NOT EXISTS cash_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL,
                type TEXT, 
                description TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.commit()

# --- Routes ---

@app.route("/")
def index():
    db = get_db()
    search_query = request.args.get('search', '').strip()
    
    if search_query:
        query = "SELECT * FROM products WHERE name LIKE ?"
        products = db.execute(query, ('%' + search_query + '%',)).fetchall()
    else:
        products = db.execute("SELECT * FROM products").fetchall()
        
    total_value = sum(float(p['sell_price']) * int(p['quantity']) for p in products)
    return render_template("index.html", products=products, total_value=total_value)

@app.route("/add_product", methods=["POST"])
def add_product():
    name = request.form.get("name")
    try:
        price = float(request.form.get("price", 0))
        quantity = int(request.form.get("quantity", 0))

        if name and name.strip():
            db = get_db()
            db.execute(
                "INSERT INTO products (name, sell_price, quantity) VALUES (?, ?, ?)",
                (name, price, quantity)
            )   
            db.commit()
            flash(f"Product '{name}' added successfully!")
    except ValueError:
        flash("Error: Invalid price or quantity.")
    
    return redirect(url_for("index"))

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_product(id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()

    if product is None:
        return "Product not found", 404

    if request.method == "POST":
        name = request.form.get("name")
        try:
            price = float(request.form.get("price"))
            quantity = int(request.form.get("quantity"))
            
            db.execute(
                "UPDATE products SET name = ?, sell_price = ?, quantity = ? WHERE id = ?",
                (name, price, quantity, id)
            )
            db.commit()
            flash(f"Updated {name}!")
            return redirect(url_for("index"))
        except ValueError:
            flash("Update failed: Invalid numbers.")

    return render_template("edit.html", product=product)

@app.route("/delete/<int:id>")
def delete_product(id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (id,))
    db.commit()
    flash("Item deleted.")
    return redirect(url_for("index"))

@app.route("/sell/<int:id>", methods=["POST"])
def sell_product(id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()
    
    if product and product['quantity'] > 0:
        try:
            # Atomic update: Inventory + Sales Record + Cash Record
            db.execute("UPDATE products SET quantity = quantity - 1 WHERE id = ?", (id,))
            db.execute(
                "INSERT INTO sales (product_id, quantity_sold, total_price) VALUES (?, ?, ?)",
                (id, 1, product['sell_price'])
            )
            db.execute(
                "INSERT INTO cash_log (amount, type, description) VALUES (?, ?, ?)",
                (product['sell_price'], 'IN', f"Sale: {product['name']}")
            )
            db.commit()
            flash(f"Sold 1 {product['name']}!")
        except Exception as e:
            db.rollback()
            flash("Error processing sale.")
    else:
        flash("Out of stock!")
        
    return redirect(url_for("index"))

@app.route("/cash", methods=["GET", "POST"])
def cash_management():
    db = get_db()
    #Handle adding an expense (Cash OUT)
    if request.method == "POST":
        description = request.form.get("description")
        try:
                amount = float(request.form.get("amount", 0))
                if description and amount > 0:
                    db.execute(
                        "INSERT INTO cash_log (amount, type, description) VALUES (?, ?, ?)",
                        (amount, 'OUT', description)
                    )
                    db.commit()
                    flash(f"Recorded expense: {description}")
        except ValueError:
            flash("Invalid amount entered.")

    # Get all logs for display
    logs = db.execute("SELECT * FROM cash_log ORDER BY timestamp DESC").fetchall()

    # Calculate Totals
    total_in = db.execute("SELECT SUM(amount) FROM cash_log WHERE type = 'IN'").fetchone()[0] or 0
    total_out = db.execute("SELECT SUM(amount) FROM cash_log WHERE type = 'OUT'").fetchone()[0] or 0
    balance = total_in - total_out

    return render_template("cash.html", logs=logs, total_in=total_in, total_out=total_out, balance=balance)
@app.route("/sales")
def sales_report():
    db = get_db()
    # This query links the sales to the products so you see names, not just IDs
    sales = db.execute('''
        SELECT sales.id, products.name, sales.total_price, sales.timestamp 
        FROM sales 
        JOIN products ON sales.product_id = products.id 
        ORDER BY sales.timestamp DESC
    ''').fetchall()
    
    # Calculate the sum of all sales
    total_revenue = sum(sale['total_price'] for sale in sales)
    
    return render_template("sales.html", sales=sales, total_revenue=total_revenue) 
if __name__ == "__main__":
    init_db()
    app.run(debug=True)