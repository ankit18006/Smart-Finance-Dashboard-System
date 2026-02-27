from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
import datetime
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_finance_secret"


# ---------------- AUTO CATEGORY DETECTION ----------------
def auto_detect_category(description):
    description = description.lower()

    rules = {
        "Food": ["swiggy", "zomato", "restaurant", "food"],
        "Travel": ["uber", "ola", "bus", "train", "flight"],
        "Shopping": ["amazon", "flipkart", "mall"],
        "Salary": ["salary", "credited", "income"],
        "Bills": ["electricity", "water", "rent", "bill"]
    }

    for category, words in rules.items():
        for word in words:
            if word in description:
                return category
    return "Others"


# ---------------- DATABASE INIT ----------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        category TEXT,
        description TEXT,
        amount REAL,
        date TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budgets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        category TEXT,
        limit_amount REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS savings_goal(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        goal_amount REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS networth_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        asset REAL,
        liability REAL,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        entered_password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], entered_password):
            session["user_id"] = user[0]
            return redirect("/dashboard")

    return render_template("login.html")


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users(name,email,password) VALUES (?,?,?)",
            (name, email, password)
        )
        conn.commit()
        conn.close()
        return redirect("/")

    return render_template("register.html")


# ---------------- DASHBOARD ----------------
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user_id" not in session:
        return redirect("/")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # Add transaction
    if request.method == "POST" and "description" in request.form:
        description = request.form["description"]
        category = auto_detect_category(description)

        cursor.execute("""
        INSERT INTO transactions(user_id,type,category,description,amount,date)
        VALUES (?,?,?,?,?,?)
        """, (
            session["user_id"],
            request.form["type"],
            category,
            description,
            request.form["amount"],
            datetime.datetime.now().strftime("%Y-%m")
        ))
        conn.commit()

    # Fetch data
    cursor.execute("SELECT * FROM transactions WHERE user_id=?", (session["user_id"],))
    data = cursor.fetchall()

    # Income
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='Income'",
                   (session["user_id"],))
    income = cursor.fetchone()[0] or 0

    # Expense
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='Expense'",
                   (session["user_id"],))
    expense = cursor.fetchone()[0] or 0

    balance = income - expense

    # Expense Category Pie
    cursor.execute("""
    SELECT category, SUM(amount) FROM transactions
    WHERE user_id=? AND type='Expense'
    GROUP BY category
    """, (session["user_id"],))
    chart_data = cursor.fetchall()

    labels = [c[0] for c in chart_data]
    values = [c[1] for c in chart_data]

    # Budget Alerts + Progress
    alerts = []
    progress_data = []

    for category, total_spent in chart_data:
        cursor.execute("""
        SELECT limit_amount FROM budgets
        WHERE user_id=? AND category=?
        """, (session["user_id"], category))

        budget = cursor.fetchone()

        if budget:
            limit_amount = budget[0]
            percent_used = (total_spent / limit_amount) * 100

            progress_data.append({
                "category": category,
                "spent": total_spent,
                "limit": limit_amount,
                "percent": round(percent_used, 1)
            })

            if percent_used >= 80 and percent_used < 100:
                alerts.append(f"{category} above 80%!")
            if percent_used >= 100:
                alerts.append(f"{category} budget exceeded!")

    # Savings Goal
    cursor.execute("SELECT goal_amount FROM savings_goal WHERE user_id=?",
                   (session["user_id"],))
    goal_row = cursor.fetchone()

    goal_amount = goal_row[0] if goal_row else 0
    goal_progress = round((balance / goal_amount) * 100, 1) if goal_amount > 0 else 0

    # Net Worth Trend
    cursor.execute("""
    SELECT date, (asset - liability)
    FROM networth_history
    WHERE user_id=?
    """, (session["user_id"],))
    nw_data = cursor.fetchall()

    nw_labels = [r[0] for r in nw_data]
    nw_values = [r[1] for r in nw_data]

    # Prediction
    cursor.execute("""
    SELECT SUM(amount) FROM transactions
    WHERE user_id=? AND type='Expense'
    GROUP BY date
    """, (session["user_id"],))
    monthly_data = cursor.fetchall()

    prediction = 0
    if monthly_data:
        total = sum([m[0] for m in monthly_data])
        prediction = round(total / len(monthly_data), 2)

    conn.close()

    return render_template("dashboard.html",
                           data=data,
                           income=income,
                           expense=expense,
                           balance=balance,
                           labels=labels,
                           values=values,
                           alerts=alerts,
                           progress_data=progress_data,
                           goal_amount=goal_amount,
                           goal_progress=goal_progress,
                           prediction=prediction,
                           nw_labels=nw_labels,
                           nw_values=nw_values)


# ---------------- ADD BUDGET ----------------
@app.route("/add_budget", methods=["POST"])
def add_budget():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO budgets(user_id,category,limit_amount)
    VALUES (?,?,?)
    """, (session["user_id"],
          request.form["category"],
          request.form["limit"]))
    conn.commit()
    conn.close()
    return redirect("/dashboard")


# ---------------- SET SAVINGS GOAL ----------------
@app.route("/set_goal", methods=["POST"])
def set_goal():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM savings_goal WHERE user_id=?",
                   (session["user_id"],))
    cursor.execute("""
    INSERT INTO savings_goal(user_id,goal_amount)
    VALUES (?,?)
    """, (session["user_id"], request.form["goal"]))
    conn.commit()
    conn.close()
    return redirect("/dashboard")


# ---------------- UPDATE NET WORTH ----------------
@app.route("/update_networth", methods=["POST"])
def update_networth():
    asset = float(request.form["asset"])
    liability = float(request.form["liability"])

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO networth_history(user_id,asset,liability,date)
    VALUES (?,?,?,?)
    """, (session["user_id"],
          asset,
          liability,
          datetime.datetime.now().strftime("%Y-%m")))
    conn.commit()
    conn.close()
    return redirect("/dashboard")


# ---------------- DELETE TRANSACTION ----------------
@app.route("/delete/<int:id>")
def delete(id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/dashboard")


# ---------------- CSV IMPORT ----------------
@app.route("/import_csv", methods=["POST"])
def import_csv():
    file = request.files["file"]
    if file:
        df = pd.read_csv(file)

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        for _, row in df.iterrows():
            cursor.execute("""
            INSERT INTO transactions(user_id,type,category,description,amount,date)
            VALUES (?,?,?,?,?,?)
            """, (session["user_id"],
                  row["Type"],
                  row["Category"],
                  row["Description"],
                  row["Amount"],
                  row["Date"]))
        conn.commit()
        conn.close()

    return redirect("/dashboard")


# ---------------- EXPORT ----------------
@app.route("/export")
def export():
    conn = sqlite3.connect("database.db")
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()

    file = "finance_export.xlsx"
    df.to_excel(file, index=False)

    return send_file(file, as_attachment=True)


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)