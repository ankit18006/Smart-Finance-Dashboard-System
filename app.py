import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "finance_secret"
DB = "finance.db"

# ---------------- DATABASE INIT ----------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        type TEXT,
        category TEXT,
        amount REAL,
        date TEXT,
        recurring INTEGER DEFAULT 0
    )""")

    # Default Admin
    c.execute("SELECT * FROM users WHERE role='admin'")
    if not c.fetchone():
        c.execute("""
        INSERT INTO users(name,email,password,role)
        VALUES(?,?,?,?)
        """,(
            "Finance Admin",
            "admin@finance.com",
            generate_password_hash("admin123"),
            "admin"
        ))

    conn.commit()
    conn.close()

init_db()

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return redirect("/login")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("""
        INSERT INTO users(name,email,password,role)
        VALUES(?,?,?,?)
        """,(request.form["name"],
             request.form["email"],
             generate_password_hash(request.form["password"]),
             "user"))
        conn.commit()
        conn.close()
        return redirect("/login")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (request.form["email"],))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[3], request.form["password"]):
            session["user_id"] = user[0]
            session["role"] = user[4]
            return redirect("/admin" if user[4]=="admin" else "/dashboard")

    return render_template("login.html")

@app.route("/dashboard", methods=["GET","POST"])
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    if session["role"]=="admin":
        return redirect("/admin")

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    if request.method == "POST":
        c.execute("""
        INSERT INTO transactions(user_id,type,category,amount,date,recurring)
        VALUES(?,?,?,?,?,?)
        """,(session["user_id"],
             request.form["type"],
             request.form["category"],
             float(request.form["amount"]),
             request.form["date"],
             1 if request.form.get("recurring") else 0))
        conn.commit()

    c.execute("SELECT * FROM transactions WHERE user_id=?", (session["user_id"],))
    data = c.fetchall()

    income = sum(t[4] for t in data if t[2]=="Income")
    expense = sum(t[4] for t in data if t[2]=="Expense")
    savings = income - expense

    budget_limit = 50000
    alert = expense >= 0.8 * budget_limit

    conn.close()

    return render_template("dashboard.html",
                           transactions=data,
                           income=income,
                           expense=expense,
                           savings=savings,
                           alert=alert)

@app.route("/admin")
def admin():
    if session.get("role")!="admin":
        return redirect("/dashboard")

    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT * FROM users")
    users = c.fetchall()

    c.execute("SELECT * FROM transactions")
    all_tx = c.fetchall()

    total_income = sum(t[4] for t in all_tx if t[2]=="Income")
    total_expense = sum(t[4] for t in all_tx if t[2]=="Expense")

    conn.close()

    return render_template("admin.html",
                           users=users,
                           total_income=total_income,
                           total_expense=total_expense)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000)
