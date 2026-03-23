import sqlite3

# Connect to SQLite database (creates file if it doesn't exist)
conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Create products table
cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sell_price REAL NOT NULL,
    quantity INTEGER NOT NULL
)
""")

conn.commit()
conn.close()

print("Database and products table created successfully.")