import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"  # TODO: load from env var before any real deployment

init_db()
seed_db()

CATEGORIES = ["Food", "Bills", "Travel", "Shopping", "Entertainment", "Health", "Other"]

CATEGORY_COLORS = {
    "Food": "#c4861c",
    "Bills": "#7268c5",
    "Travel": "#4a88d4",
    "Shopping": "#d9534f",
    "Entertainment": "#1a472a",
    "Health": "#2f9e8f",
    "Other": "#8a8f98",
}
TOP_CATEGORY_LIMIT = 6
DAY_BUCKET_THRESHOLD_DAYS = 45
TOP_TIME_BUCKET_LIMIT = 10


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def resolve_category(form):
    category = form.get("category", "").strip()
    if category == "Other":
        return form.get("category_custom", "").strip()
    return category


def build_category_totals(expenses):
    sums = {}
    for e in expenses:
        sums[e["category"]] = sums.get(e["category"], 0.0) + e["amount"]

    ranked = sorted(sums.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > TOP_CATEGORY_LIMIT:
        head = dict(ranked[:TOP_CATEGORY_LIMIT])
        tail = ranked[TOP_CATEGORY_LIMIT:]
        head["Other"] = head.get("Other", 0.0) + sum(v for _, v in tail)
        ranked = sorted(head.items(), key=lambda kv: (-kv[1], kv[0]))

    max_total = max(v for _, v in ranked)
    return [
        {
            "label": label,
            "amount": amount,
            "pct": round(amount / max_total * 100),
            "color": CATEGORY_COLORS.get(label, CATEGORY_COLORS["Other"]),
        }
        for label, amount in ranked
    ]


def build_time_totals(expenses):
    dates = sorted({date.fromisoformat(e["expense_date"]) for e in expenses})
    by_month = (dates[-1] - dates[0]).days >= DAY_BUCKET_THRESHOLD_DAYS

    sums = {}
    for e in expenses:
        d = date.fromisoformat(e["expense_date"])
        key = d.strftime("%Y-%m") if by_month else d.isoformat()
        sums[key] = sums.get(key, 0.0) + e["amount"]

    truncated = len(sums) > TOP_TIME_BUCKET_LIMIT
    if truncated:
        top_keys = sorted(sums, key=lambda k: (-sums[k], k))[:TOP_TIME_BUCKET_LIMIT]
        sums = {k: sums[k] for k in top_keys}

    max_total = max(sums.values())
    fmt_in, fmt_out = ("%Y-%m", "%b %Y") if by_month else ("%Y-%m-%d", "%b %d")
    points = [
        {
            "label": datetime.strptime(key, fmt_in).strftime(fmt_out),
            "amount": sums[key],
            "pct": round(sums[key] / max_total * 100),
        }
        for key in sorted(sums)
    ]
    return points, ("month" if by_month else "day"), truncated


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("expenses_list"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or not password:
        return render_template("register.html", error="All fields are required")

    conn = get_db()
    if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        conn.close()
        return render_template("register.html", error="Email already registered")

    if conn.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone():
        conn.close()
        return render_template("register.html", error="Username taken")

    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return render_template("register.html", error="Email or username already in use")

    conn.close()
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("expenses_list"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password")

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return redirect(url_for("expenses_list"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
@login_required
def profile():
    conn = get_db()
    user = conn.execute(
        "SELECT username, email, created_at FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    conn.close()
    return render_template("profile.html", user=user)


@app.route("/expenses")
@login_required
def expenses_list():
    conn = get_db()
    expenses = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY expense_date DESC, id DESC",
        (session["user_id"],),
    ).fetchall()
    user = conn.execute(
        "SELECT username, email, created_at FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    conn.close()

    category_totals = build_category_totals(expenses) if expenses else []
    time_totals, time_bucket_mode, time_truncated = (
        build_time_totals(expenses) if expenses else ([], "day", False)
    )
    highlight_id = request.args.get("highlight", type=int)

    return render_template(
        "expenses.html", expenses=expenses, categories=CATEGORIES, user=user,
        category_totals=category_totals, time_totals=time_totals,
        time_bucket_mode=time_bucket_mode, time_truncated=time_truncated,
        highlight_id=highlight_id,
    )


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "GET":
        return render_template("expense_form.html", expense=None, categories=CATEGORIES)

    amount_raw = request.form.get("amount", "").strip()
    category = resolve_category(request.form)
    description = request.form.get("description", "").strip() or None
    expense_date = request.form.get("expense_date", "").strip()

    if not category or not expense_date or not amount_raw:
        return render_template(
            "expense_form.html", expense=None, categories=CATEGORIES,
            error="Amount, category, and date are required",
        )

    try:
        amount = float(amount_raw)
    except ValueError:
        return render_template(
            "expense_form.html", expense=None, categories=CATEGORIES,
            error="Amount must be a valid number",
        )

    if amount <= 0:
        return render_template(
            "expense_form.html", expense=None, categories=CATEGORIES,
            error="Amount must be positive",
        )

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, description, expense_date) "
        "VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], amount, category, description, expense_date),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return redirect(url_for("expenses_list", highlight=new_id))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    conn = get_db()
    expense = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
        (id, session["user_id"]),
    ).fetchone()

    if expense is None:
        conn.close()
        expenses = []
        return render_template(
            "expenses.html", expenses=expenses, categories=CATEGORIES,
            error="Expense not found",
        )

    if request.method == "GET":
        conn.close()
        return render_template("expense_form.html", expense=expense, categories=CATEGORIES)

    amount_raw = request.form.get("amount", "").strip()
    category = resolve_category(request.form)
    description = request.form.get("description", "").strip() or None
    expense_date = request.form.get("expense_date", "").strip()

    if not category or not expense_date or not amount_raw:
        conn.close()
        return render_template(
            "expense_form.html", expense=expense, categories=CATEGORIES,
            error="Amount, category, and date are required",
        )

    try:
        amount = float(amount_raw)
    except ValueError:
        conn.close()
        return render_template(
            "expense_form.html", expense=expense, categories=CATEGORIES,
            error="Amount must be a valid number",
        )

    if amount <= 0:
        conn.close()
        return render_template(
            "expense_form.html", expense=expense, categories=CATEGORIES,
            error="Amount must be positive",
        )

    conn.execute(
        "UPDATE expenses SET amount = ?, category = ?, description = ?, expense_date = ? "
        "WHERE id = ? AND user_id = ?",
        (amount, category, description, expense_date, id, session["user_id"]),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("expenses_list", highlight=id))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
@login_required
def delete_expense(id):
    conn = get_db()
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (id, session["user_id"]),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("expenses_list"))


@app.route("/terms/")
def terms():
    return render_template("terms.html")


@app.route("/privacy/")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
