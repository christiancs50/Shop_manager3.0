from flask import Flask, render_template, request, redirect, url_for, g
import sqlite3

app = Flask(__name__)
DATABASE = 'database.db'

# --- Database Helpers ---

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database and creates the products table."""
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sell_price REAL NOT NULL,
                quantity INTEGER NOT NULL
            )
        ''')
        db.commit()

# --- Routes ---

@app.route("/")
def index():
    db = get_db()
    search_query = request.args.get('search', '').strip() #Strip whitespace
    
    if search_query:
        # Using LIKE for basic search functionality
        query = "SELECT * FROM products WHERE name LIKE ?"
        products = db.execute(query, ('%' + search_query + '%',)).fetchall()
    else:
        products = db.execute("SELECT * FROM products").fetchall()
        
    # Calculate total value: sum of (price * quatity) for all displayed products and cast to float/int to prevent TypeError if DB returns a string
    total_value = sum(float(p['sell_price']) * int(p['quantity']) for p in products)

    return render_template("index.html", products=products, total_value=total_value)

@app.route("/add_product", methods=["POST"])
def add_product():
    #Using .get() is good, but let's ensure we don't insert empty strings
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
    
    except ValueError:
        # Handle cases where price/qty aren't valid numbers
        pass

    
    return redirect(url_for("index"))

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_product(id):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (id,)).fetchone()

    if product is None:
        return "Product not found", 404

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        quantity = request.form.get("quantity")
        
        db.execute(
            "UPDATE products SET name = ?, sell_price = ?, quantity = ? WHERE id = ?",
            (name, price, quantity, id)
        )
        db.commit()
        return redirect(url_for("index"))

    return render_template("edit.html", product=product)

@app.route("/delete/<int:id>")
def delete_product(id):
    db = get_db()
    db.execute("DELETE FROM products WHERE id = ?", (id,))
    db.commit()
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()  # Run the table creator
    app.run(debug=True)