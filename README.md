# 🏪 Shop Management & POS System

## 📌 Overview

The **Shop Management & POS System** is a robust desktop/web-based application designed to help small and medium-sized retail businesses efficiently manage **inventory, sales, and financial operations**.

Built using **Python (Flask) and SQLite**, the system provides a secure, scalable, and user-friendly solution for day-to-day shop management.

---

## 🚀 Core Features

### 🧾 Point of Sale (POS)
- Fast and intuitive sales processing
- Automatic inventory deduction after each sale
- Transaction grouping with unique IDs
- Receipt generation (thermal/PDF-ready)

---

### 📦 Inventory Management
- Add, edit, and delete products
- Real-time stock tracking
- Low-stock alerts
- Restocking with history logs
- Inventory audit trail

---

### 💰 Financial Management
- Track cash inflows (sales)
- Record expenses (cash outflows)
- View daily, weekly, monthly, and yearly reports
- Monitor overall business balance

---

### 📊 Reports & Analytics
- Sales reports (daily, monthly, yearly)
- Inventory movement reports
- Restock history reports (PDF export supported)
- Business performance insights

---

### 🔐 Security Features
- Password hashing (secure authentication)
- Role-based access control (Admin / Staff)
- Session protection
- Optional data encryption support
- Environment-based configuration (.env)

---

### ⚙️ System Utilities
- Automated database backups
- Shop settings customization (logo, tax, currency)
- File upload handling (secure)

---

## 🧰 Technology Stack

| Layer       | Technology              |
|------------|------------------------|
| Backend     | Python                 |
| Framework   | Flask                  |
| Database    | SQLite                 |
| Frontend    | HTML, CSS (Flask Templates) |
| Reporting   | ReportLab (PDF)        |
| Security    | Werkzeug, Flask-WTF    |

---

## 📁 Project Structure
```
shop_manager/
│
├── app.py # Main application file
├── database.db # SQLite database
├── backups/ # Automated backups
├── static/
│ └── uploads/ # Logo & file uploads
│
├── templates/ # HTML templates
│
├── .env # Environment variables
├── requirements.txt # Dependencies
└── README.md
```

---

## ⚙️ Installation & Setup
### 1. Clone the Repository
git clone https://github.com/yourusername/shop_manager.git
cd shop_manager

---

### 2. Create Virtual Environment
python -m venv venv
```
Activate: venv\Scripts\activate # Windows
```
---

### 3. Install Dependencies
```
pip install -r requirements.txt
```

### 4. Configure Environment Variables
```
Create a `.env` file: ASK ME"MESSAGE ME"
```
---

### 5. Run the Application

### 6. Open in Browser

## 🔑 Default Login

| Username | Password        |
|---------|----------------|
| admin   | (from `.env`)  |

---

## 🔐 Security Notes

- Always change the default admin password after first login
- Do not expose `.env` file publicly
- Use OS-level encryption (e.g., BitLocker) for database protection
- Backup your database regularly

---

## 📦 Deployment (Optional)

For production deployment:
- Use **Gunicorn or Waitress**
- Configure **Nginx (or reverse proxy)**
- Enable **HTTPS (SSL certificate)**

---

## 🧠 Future Enhancements

- 📱 Mobile app integration (Flutter)
- 📊 Advanced dashboard (charts & analytics)
- 📷 Barcode scanning system
- ☁️ Cloud database (PostgreSQL/MySQL)
- 📧 Email receipts & notifications
- 👥 Multi-branch management

---

## 🎯 Purpose

This system is designed to provide a **simple yet powerful POS solution** for retail businesses that need:
- Accurate inventory tracking
- Reliable sales recording
- Clear financial visibility

without the complexity of enterprise-level systems.

---

## 👨‍💻 Author

**Chriddle**  

## 📄 License

This project is open-source and available for modification and use.
