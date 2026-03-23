# # Shop Inventory POS System

## Overview

The Shop Inventory POS System is a lightweight web-based application designed to help small retail businesses manage their inventory, sales, and cash flow efficiently. The system provides an easy-to-use interface for recording products, processing sales, and monitoring financial activity within a shop.

Built with **Python, Flask, and SQLite**, the application serves as a simple Point-of-Sale (POS) and inventory management tool that helps shop owners maintain accurate records of stock levels and cash inflows.

---

## Key Features

### Inventory Management

* Add new products to the inventory
* View all products in a structured table
* Edit product information (name, price, quantity)
* Delete products from inventory
* Automatic stock updates when sales are recorded

### Point of Sale (POS)

* Record product sales quickly
* Automatically deduct sold items from inventory
* Generate a simple record of daily sales

### Cash Flow Tracking

* Track **cash inflows** from product sales
* Record **cash outflows** such as shop expenses
* Monitor daily financial activity

---

## Technology Stack

* **Backend:** Python
* **Framework:** Flask
* **Database:** SQLite
* **Frontend:** HTML (Flask templates)

---

## Project Structure

```
shop_manager/
│
├── app.py
├── create_db.py
├── database.db
├── templates/
│   ├── index.html
│   └── edit.html
│
├── venv/
└── README.md
```

---

## Installation and Setup

### 1. Clone the repository

```
git clone https://github.com/yourusername/shop_inventory_pos.git
cd shop_inventory_pos
```

### 2. Create a virtual environment

```
python -m venv venv
```

### 3. Install dependencies

```
pip install flask
```

### 4. Create the database

```
python create_db.py
```

### 5. Run the application

```
python app.py
```

### 6. Open the application in your browser

```
http://127.0.0.1:5000
```

---

## Future Improvements

* Sales history tracking
* Daily sales reports
* Barcode scanning for products
* Mobile-friendly interface
* User login and authentication
* Export sales reports to Excel or PDF

---

## Purpose of the Project

This project was developed as a practical solution for small retail businesses that require a simple system to manage inventory, process sales, and monitor cash flow without the complexity of large enterprise POS systems.

---

## Author

Christian Gaoso Avayi

Industrial Promotion Officer
Ministry of Trade, Agribusiness and Industry – Ghana
