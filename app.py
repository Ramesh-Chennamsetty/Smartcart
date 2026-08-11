from flask import Flask, render_template, request, redirect, session, flash, jsonify, make_response, url_for
from flask_mail import Mail, Message
import sqlite3
import decimal
import datetime

# Custom SQLite Wrapper to behave like mysql-connector
class SQLiteCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def description(self):
        return self._cursor.description

    def execute(self, sql, params=None):
        sql = sql.replace('%s', '?')
        if params is not None:
            # Convert decimal.Decimal in params to float for SQLite compatibility
            clean_params = []
            for p in params:
                if isinstance(p, decimal.Decimal):
                    clean_params.append(float(p))
                else:
                    clean_params.append(p)
            self._cursor.execute(sql, clean_params)
        else:
            self._cursor.execute(sql)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

class SQLiteConnectionWrapper:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = self._dict_factory
        # Ensure password_resets table is created automatically
        self._conn.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL,
            expiry TEXT NOT NULL,
            role TEXT NOT NULL
        );
        """)
        try:
            cur = self._conn.cursor()
            cur.execute("PRAGMA table_info(orders)")
            rows = cur.fetchall()
            existing_cols = set()
            for r in rows:
                if isinstance(r, dict) and 'name' in r:
                    existing_cols.add(r['name'])
                elif isinstance(r, (list, tuple)) and len(r) > 1:
                    existing_cols.add(r[1])
            for col in ['full_name', 'phone', 'address_line', 'city', 'state', 'postal_code']:
                if col not in existing_cols:
                    self._conn.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT;")
        except Exception as e:
            print("Auto-migration error:", e)
        self._conn.commit()

    @staticmethod
    def _dict_factory(cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def cursor(self, dictionary=True):
        return SQLiteCursorWrapper(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def is_connected(self):
        return True

Error = sqlite3.Error
import bcrypt
import random
import os
import uuid
import config
import razorpay
from werkzeug.utils import secure_filename

from utils.pdf_generator import generate_pdf


app = Flask(__name__)
app.secret_key = config.SECRET_KEY


# =========================================================
# SESSION SECURITY CONFIGURATION
# =========================================================

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = datetime.timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


@app.context_processor
def cart_template_values():
    cart = session.get('cart', {}) if session.get('user_id') else {}
    return {
        'cart_count': sum(
            max(0, int(item.get('quantity', 0))) for item in cart.values()
        )
    }

# Enable this only after deploying with HTTPS
# app.config["SESSION_COOKIE_SECURE"] = True


# =========================================================
# EMAIL CONFIGURATION
# =========================================================

app.config["MAIL_SERVER"] = config.MAIL_SERVER
app.config["MAIL_PORT"] = config.MAIL_PORT
app.config["MAIL_USE_TLS"] = config.MAIL_USE_TLS
app.config["MAIL_USERNAME"] = config.MAIL_USERNAME
app.config["MAIL_PASSWORD"] = config.MAIL_PASSWORD

mail = Mail(app)


def get_razorpay_client():
    """Build a client only when credentials are configured."""
    key_id = config.RAZORPAY_KEY_ID.strip()
    key_secret = config.RAZORPAY_KEY_SECRET.strip()
    if not key_id or not key_secret:
        return None
    return razorpay.Client(auth=(key_id, key_secret))


# =========================================================
# DATABASE CONNECTION FUNCTION
# =========================================================

def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), "smartcart.db")
    return SQLiteConnectionWrapper(db_path)



# HOME ROUTE


@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# PASSWORD RESET ROUTES
# =========================================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    role = request.args.get("role", "user")
    if role not in ["user", "admin"]:
        role = "user"

    if request.method == "GET":
        return render_template("user/forgot_password.html", role=role)

    email = request.form.get("email", "").strip().lower()
    if not email:
        flash("Email address is required.", "danger")
        return redirect(url_for("forgot_password", role=role))

    # Check if email exists in database
    conn = None
    cursor = None
    user_exists = False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if role == "admin":
            cursor.execute("SELECT admin_id FROM eadmin WHERE email = %s", (email,))
        else:
            cursor.execute("SELECT user_id FROM susers WHERE email = %s", (email,))
        user_exists = cursor.fetchone() is not None
    except Exception as e:
        app.logger.exception("Database error checking email: %s", e)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("forgot_password", role=role))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Generate OTP and store it
    otp = str(random.randint(100000, 999999))
    expiry = (datetime.datetime.utcnow() + datetime.timedelta(minutes=15)).isoformat()

    if user_exists:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Clean up old tokens first
            cursor.execute("DELETE FROM password_resets WHERE email = %s AND role = %s", (email, role))
            cursor.execute(
                "INSERT INTO password_resets (email, token, expiry, role) VALUES (%s, %s, %s, %s)",
                (email, otp, expiry, role)
            )
            conn.commit()

            # Send Email
            msg = Message(
                subject="SmartCart Password Reset Code",
                sender=app.config["MAIL_USERNAME"],
                recipients=[email],
                body=(
                    f"Your password reset code is: {otp}\n\n"
                    "This code will expire in 15 minutes. Do not share it with anyone."
                )
            )
            mail.send(msg)
        except Exception as e:
            app.logger.exception("Error sending password reset email: %s", e)
            # Do not display error to user, just proceed to verify page
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    # Flash message and redirect (always show success to avoid user enumeration)
    flash("If that email is registered, we have sent a 6-digit password reset code to it.", "success")
    return render_template("user/verify_reset_otp.html", email=email, role=role)


@app.route("/verify-reset-otp", methods=["POST"])
def verify_reset_otp():
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "user")
    otp = request.form.get("otp", "").strip()

    if not email or not otp:
        flash("Email and code are required.", "danger")
        return redirect(url_for("forgot_password", role=role))

    conn = None
    cursor = None
    reset_record = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM password_resets WHERE email = %s AND token = %s AND role = %s",
            (email, otp, role)
        )
        reset_record = cursor.fetchone()
    except Exception as e:
        app.logger.exception("Error checking reset OTP: %s", e)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("forgot_password", role=role))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if not reset_record:
        flash("Invalid reset code. Please try again.", "danger")
        return render_template("user/verify_reset_otp.html", email=email, role=role)

    # Check expiry
    expiry_time = datetime.datetime.fromisoformat(reset_record["expiry"])
    if datetime.datetime.utcnow() > expiry_time:
        flash("Reset code has expired. Please request a new one.", "danger")
        return redirect(url_for("forgot_password", role=role))

    # OTP is valid! Convert it to a secure unique token for the final reset form
    secure_token = uuid.uuid4().hex
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE password_resets SET token = %s WHERE email = %s AND role = %s",
            (secure_token, email, role)
        )
        conn.commit()
    except Exception as e:
        app.logger.exception("Error updating reset token: %s", e)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("forgot_password", role=role))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template("user/reset_password.html", email=email, role=role, token=secure_token)


@app.route("/resend-reset-otp", methods=["POST"])
def resend_reset_otp():
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "user")

    if not email:
        flash("Email is required.", "danger")
        return redirect(url_for("forgot_password", role=role))

    # Generate new OTP and update
    otp = str(random.randint(100000, 999999))
    expiry = (datetime.datetime.utcnow() + datetime.timedelta(minutes=15)).isoformat()

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM password_resets WHERE email = %s AND role = %s", (email, role))
        cursor.execute(
            "INSERT INTO password_resets (email, token, expiry, role) VALUES (%s, %s, %s, %s)",
            (email, otp, expiry, role)
        )
        conn.commit()

        # Send Email
        msg = Message(
            subject="SmartCart Password Reset Code",
            sender=app.config["MAIL_USERNAME"],
            recipients=[email],
            body=(
                f"Your new password reset code is: {otp}\n\n"
                "This code will expire in 15 minutes. Do not share it with anyone."
            )
        )
        mail.send(msg)
        flash("A new reset code has been sent to your email.", "success")
    except Exception as e:
        app.logger.exception("Error resending password reset email: %s", e)
        flash("Unable to resend code. Please try again.", "danger")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return render_template("user/verify_reset_otp.html", email=email, role=role)


@app.route("/reset-password", methods=["POST"])
def reset_password():
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "user")
    token = request.form.get("token", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not email or not token or not password:
        flash("Missing required fields.", "danger")
        return redirect(url_for("forgot_password", role=role))

    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return render_template("user/reset_password.html", email=email, role=role, token=token)

    if len(password) < 6:
        flash("Password must be at least 6 characters long.", "danger")
        return render_template("user/reset_password.html", email=email, role=role, token=token)

    # Verify the token is valid
    conn = None
    cursor = None
    reset_record = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM password_resets WHERE email = %s AND token = %s AND role = %s",
            (email, token, role)
        )
        reset_record = cursor.fetchone()
    except Exception as e:
        app.logger.exception("Error verifying reset token: %s", e)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("forgot_password", role=role))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if not reset_record:
        flash("Invalid or expired password reset session.", "danger")
        return redirect(url_for("forgot_password", role=role))

    # Check expiry
    expiry_time = datetime.datetime.fromisoformat(reset_record["expiry"])
    if datetime.datetime.utcnow() > expiry_time:
        flash("Password reset session has expired. Please start over.", "danger")
        return redirect(url_for("forgot_password", role=role))

    # Hash the new password and update in appropriate table
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if role == "admin":
            cursor.execute(
                "UPDATE eadmin SET password = %s WHERE email = %s",
                (hashed_password, email)
            )
        else:
            cursor.execute(
                "UPDATE susers SET password = %s WHERE email = %s",
                (hashed_password, email)
            )
        # Delete reset token so it cannot be reused
        cursor.execute("DELETE FROM password_resets WHERE email = %s AND role = %s", (email, role))
        conn.commit()
        flash("Your password has been reset successfully! You can now log in.", "success")
    except Exception as e:
        app.logger.exception("Error resetting password in DB: %s", e)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("forgot_password", role=role))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    if role == "admin":
        return redirect(url_for("admin_login"))
    else:
        return redirect(url_for("user_login"))



# ROUTE 1: ADMIN SIGNUP AND SEND OTP


@app.route("/admin-signup", methods=["GET", "POST"])
def admin_signup():

    if request.method == "GET":
        return render_template("admin/admin_signup.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()

    # Validate form data
    if not name or not email:
        flash("Name and email are required.", "danger")
        return redirect("/admin-signup")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check whether email already exists
        cursor.execute(
            "SELECT admin_id FROM eadmin WHERE email = %s",
            (email,)
        )

        existing_admin = cursor.fetchone()

        if existing_admin:
            flash(
                "This email is already registered. Please login instead.",
                "danger"
            )
            return redirect("/admin-signup")

    except Error as error:
        print("Database error:", error)
        flash("Unable to process signup. Please try again.", "danger")
        return redirect("/admin-signup")

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

    # Store signup information temporarily
    session["signup_name"] = name
    session["signup_email"] = email

    # Generate six-digit OTP
    otp = random.randint(100000, 999999)
    session["otp"] = str(otp)

    # Send OTP through email
    try:
        message = Message(
            subject="SmartCart Admin OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )

        message.body = (
            f"Hello {name},\n\n"
            f"Your OTP for SmartCart Admin Registration is: {otp}\n\n"
            "Do not share this OTP with anyone."
        )

        mail.send(message)

        flash("OTP sent to your email successfully.", "success")
        return redirect("/verify-otp")

    except Exception as error:
        print("Email error:", error)

        session.pop("signup_name", None)
        session.pop("signup_email", None)
        session.pop("otp", None)

        flash("Unable to send OTP. Please check your email settings.", "danger")
        return redirect("/admin-signup")



# ROUTE 2: DISPLAY OTP PAGE


@app.route("/verify-otp", methods=["GET"])
def verify_otp_get():

    # Prevent direct access without signup
    if "signup_email" not in session or "otp" not in session:
        flash("Please complete the signup form first.", "danger")
        return redirect("/admin-signup")

    return render_template(
        "admin/verify_otp.html",
        email=session.get("signup_email")
    )


# ROUTE 3: VERIFY OTP AND REGISTER ADMIN


@app.route("/verify-otp", methods=["POST"])
def verify_otp_post():

    user_otp = request.form.get("otp", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    signup_name = session.get("signup_name")
    signup_email = session.get("signup_email")
    stored_otp = session.get("otp")

    # Check signup session
    if not signup_name or not signup_email or not stored_otp:
        flash("Signup session expired. Please register again.", "danger")
        return redirect("/admin-signup")

    # Validate OTP
    if user_otp != str(stored_otp):
        flash("Invalid OTP. Please try again.", "danger")
        return redirect("/verify-otp")

    # Validate password
    if not password:
        flash("Password is required.", "danger")
        return redirect("/verify-otp")

    if len(password) < 6:
        flash("Password must contain at least 6 characters.", "danger")
        return redirect("/verify-otp")

    # This validation works if confirm_password exists in HTML
    if confirm_password and password != confirm_password:
        flash("Password and confirm password do not match.", "danger")
        return redirect("/verify-otp")

    # Convert hashed password bytes into string
    hashed_password = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check email again before inserting
        cursor.execute(
            "SELECT admin_id FROM eadmin WHERE email = %s",
            (signup_email,)
        )

        existing_admin = cursor.fetchone()

        if existing_admin:
            flash("This email is already registered.", "danger")
            return redirect("/admin-login")

        # Insert admin data
        cursor.execute(
            """
            INSERT INTO eadmin (name, email, password)
            VALUES (%s, %s, %s)
            """,
            (
                signup_name,
                signup_email,
                hashed_password
            )
        )

        conn.commit()

    except Error as error:
        print("Database error:", error)

        if conn:
            conn.rollback()

        flash("Unable to register admin. Please try again.", "danger")
        return redirect("/verify-otp")

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

    # Clear temporary signup session
    session.pop("otp", None)
    session.pop("signup_name", None)
    session.pop("signup_email", None)

    flash("Admin registered successfully. Please login.", "success")
    return redirect("/admin-login")


# ROUTE 4: RESEND OTP


@app.route("/resend-otp", methods=["POST"])
def resend_otp():

    signup_name = session.get("signup_name")
    signup_email = session.get("signup_email")

    if not signup_name or not signup_email:
        flash("Please complete the signup form first.", "danger")
        return redirect("/admin-signup")

    new_otp = random.randint(100000, 999999)
    session["otp"] = str(new_otp)

    try:
        message = Message(
            subject="SmartCart Admin New OTP",
            sender=config.MAIL_USERNAME,
            recipients=[signup_email]
        )

        message.body = (
            f"Hello {signup_name},\n\n"
            f"Your new OTP is: {new_otp}\n\n"
            "Do not share this OTP with anyone."
        )

        mail.send(message)

        flash("A new OTP has been sent to your email.", "success")

    except Exception as error:
        print("Email error:", error)
        flash("Unable to resend OTP.", "danger")

    return redirect("/verify-otp")



# ROUTE 5: ADMIN LOGIN


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    # Redirect already logged-in admin
    if request.method == "GET":

        if "admin_id" in session:
            return redirect("/admin-dashboard")

        return render_template("admin/admin_login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email and password are required.", "danger")
        return redirect("/admin-login")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM eadmin WHERE email = %s",
            (email,)
        )

        admin = cursor.fetchone()

    except Error as error:
        print("Database error:", error)
        flash("Unable to login. Please try again.", "danger")
        return redirect("/admin-login")

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

    # Check whether admin exists
    if admin is None:
        flash("Email not found. Please register first.", "danger")
        return redirect("/admin-login")

    stored_password = admin.get("password")

    if not stored_password:
        flash("Password information is unavailable.", "danger")
        return redirect("/admin-login")

    # Compare entered password with stored bcrypt password
    try:
        password_correct = bcrypt.checkpw(
            password.encode("utf-8"),
            stored_password.encode("utf-8")
        )

    except ValueError:
        flash("Stored password format is invalid.", "danger")
        return redirect("/admin-login")

    if not password_correct:
        flash("Incorrect password. Please try again.", "danger")
        return redirect("/admin-login")

    # Clear old session and create admin session
    session.clear()

    session["admin_id"] = admin["admin_id"]
    session["admin_name"] = admin["name"]
    session["admin_email"] = admin["email"]
    session.permanent = True

    flash("Login successful.", "success")
    return redirect("/admin-dashboard")


# ROUTE 6: ADMIN DASHBOARD


@app.route("/admin-dashboard")
def admin_dashboard():

    if "admin_id" not in session:
        flash("Please login to access the dashboard.", "danger")
        return redirect("/admin-login")

    return render_template(
        "admin/dashboard.html",
        admin_name=session.get("admin_name"),
        admin_email=session.get("admin_email")
    )


# ROUTE 7: ADMIN LOGOUT


@app.route("/admin-logout")
def admin_logout():

    session.clear()

    flash("Logged out successfully.", "success")
    return redirect("/admin-login")

# ------------------- IMAGE UPLOAD PATH -------------------
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'product_images')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ADMIN_UPLOAD_FOLDER = os.path.join(
    app.root_path,
    'static',
    'uploads',
    'admin_profiles'
)
os.makedirs(ADMIN_UPLOAD_FOLDER, exist_ok=True)
app.config['ADMIN_UPLOAD_FOLDER'] = ADMIN_UPLOAD_FOLDER

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


def save_image(uploaded_file, destination):
    original_name = secure_filename(uploaded_file.filename or '')
    extension = os.path.splitext(original_name)[1].lower()

    if not original_name or extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Please upload a JPG, PNG, GIF, or WEBP image.")

    filename = f"{uuid.uuid4().hex}{extension}"
    uploaded_file.save(os.path.join(destination, filename))
    return filename


def remove_uploaded_image(destination, filename):
    if not filename:
        return

    image_path = os.path.join(destination, os.path.basename(filename))
    if os.path.isfile(image_path):
        os.remove(image_path)


# =================================================================
# ROUTE 7: SHOW ADD PRODUCT PAGE (Protected Route)
# =================================================================
@app.route('/admin/add-item', methods=['GET'])
def add_item_page():

    # Only logged-in admin can access
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    return render_template("admin/add_item.html")



# =================================================================
# ROUTE 8: ADD PRODUCT INTO DATABASE
# =================================================================
@app.route('/admin/add-item', methods=['POST'])
def add_item():

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    price = request.form.get('price', '').strip()
    image_file = request.files.get('image')

    if not name or not description or not category or not price:
        flash("All product fields are required.", "danger")
        return redirect('/admin/add-item')

    if not image_file or not image_file.filename:
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')

    try:
        filename = save_image(image_file, app.config['UPLOAD_FOLDER'])
    except ValueError as error:
        flash(str(error), "danger")
        return redirect('/admin/add-item')

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO products (name, description, category, price, image)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (name, description, category, price, filename)
        )
        conn.commit()

    except Error as error:
        print("Database error:", error)
        if conn:
            conn.rollback()
        remove_uploaded_image(app.config['UPLOAD_FOLDER'], filename)
        flash("Unable to add product. Please try again.", "danger")
        return redirect('/admin/add-item')

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    flash("Product added successfully!", "success")
    return redirect('/admin/products')


# =================================================================
# ROUTE 9: VIEW PRODUCTS (Protected Route)
# =================================================================
@app.route('/admin/products')
def view_products():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '').strip()
    selected_category = request.args.get('category', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT category
        FROM products
        WHERE category IS NOT NULL AND category != ''
        ORDER BY category ASC
    """)
    categories = cursor.fetchall()

    conditions = []
    parameters = []

    if search:
        conditions.append("name LIKE %s")
        parameters.append(f"%{search}%")

    if selected_category:
        conditions.append("category = %s")
        parameters.append(selected_category)

    query = "SELECT * FROM products"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY product_id ASC"

    cursor.execute(query, tuple(parameters))
    products = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        "admin/view_products.html",
        products=products,
        categories=categories
    )


# =================================================================
# ROUTE 9: DISPLAY ALL PRODUCTS (Admin)
# =================================================================
@app.route('/admin/item-list')
def item_list():

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '').strip()
    selected_category = request.args.get('category', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT DISTINCT category
        FROM products
        WHERE category IS NOT NULL AND category != ''
        ORDER BY category ASC
    """)
    categories = cursor.fetchall()

    conditions = []
    parameters = []

    if search:
        conditions.append("name LIKE %s")
        parameters.append(f"%{search}%")

    if selected_category:
        conditions.append("category = %s")
        parameters.append(selected_category)

    query = "SELECT * FROM products"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY product_id ASC"

    cursor.execute(query, tuple(parameters))
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories
    )



#=========================================
# ROUTE 10: VIEW SINGLE PRODUCT DETAILS
#=========================================
@app.route('/admin/view-item/<int:item_id>')
def view_item(item_id):

    # Check admin session
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        cursor.close()
        conn.close()
        flash("Product not found!", "danger")
        return redirect('/admin/products')

    return render_template("admin/view_item.html", product=product)

# =================================================================
# ROUTE 11: SHOW UPDATE FORM WITH EXISTING DATA
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['GET'])
def update_item_page(item_id):

    # Check login
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    # Fetch product data
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    cursor.close()
    conn.close()

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/products')

    return render_template("admin/update_item.html", product=product)

# =================================================================
# ROUTE-12: UPDATE PRODUCT + OPTIONAL IMAGE REPLACE
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['POST'])
def update_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    price = request.form.get('price', '').strip()

    new_image = request.files.get('image')

    if not name or not description or not category or not price:
        flash("All product fields are required.", "danger")
        return redirect(request.url)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        flash("Product not found!", "danger")
        return redirect('/admin/products')

    old_image_name = product['image']

    uploaded_image_name = None
    old_image_to_remove = None

    if new_image and new_image.filename != "":
        try:
            new_filename = save_image(new_image, app.config['UPLOAD_FOLDER'])
            uploaded_image_name = new_filename
        except ValueError as error:
            cursor.close()
            conn.close()
            flash(str(error), "danger")
            return redirect(request.url)

        if old_image_name and old_image_name != new_filename:
            old_image_to_remove = old_image_name

        final_image_name = new_filename

    else:
        final_image_name = old_image_name

    try:
        cursor.execute("""
            UPDATE products
            SET name=%s, description=%s, category=%s, price=%s, image=%s
            WHERE product_id=%s
        """, (name, description, category, price, final_image_name, item_id))
        conn.commit()

    except Error as error:
        conn.rollback()
        remove_uploaded_image(
            app.config['UPLOAD_FOLDER'],
            uploaded_image_name
        )
        print("Database error:", error)
        flash("Unable to update product. Please try again.", "danger")
        return redirect(request.url)

    finally:
        cursor.close()
        if conn.is_connected():
            conn.close()

    remove_uploaded_image(app.config['UPLOAD_FOLDER'], old_image_to_remove)

    flash("Product updated successfully!", "success")
    return redirect('/admin/products')


# =================================================================
# ADMIN PROFILE
# =================================================================
@app.route('/admin/profile', methods=['GET', 'POST'])
def admin_profile():

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    uploaded_profile_image = None

    try:
        cursor.execute(
            "SELECT * FROM eadmin WHERE admin_id = %s",
            (admin_id,)
        )
        admin = cursor.fetchone()

        if not admin:
            session.clear()
            flash("Admin account not found. Please login again.", "danger")
            return redirect('/admin-login')

        if request.method == 'GET':
            return render_template("admin/admin_profile.html", admin=admin)

        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        new_password = request.form.get('password', '')
        new_image = request.files.get('profile_image')

        if not name or not email:
            flash("Name and email are required.", "danger")
            return redirect('/admin/profile')

        cursor.execute(
            """
            SELECT admin_id
            FROM eadmin
            WHERE email = %s AND admin_id != %s
            """,
            (email, admin_id)
        )
        if cursor.fetchone():
            flash("That email is already used by another admin.", "danger")
            return redirect('/admin/profile')

        password = admin['password']
        if new_password:
            if len(new_password) < 6:
                flash(
                    "New password must contain at least 6 characters.",
                    "danger"
                )
                return redirect('/admin/profile')
            password = bcrypt.hashpw(
                new_password.encode('utf-8'),
                bcrypt.gensalt()
            ).decode('utf-8')

        old_image_name = admin.get('profile_image')
        final_image_name = old_image_name
        old_image_path = None

        if new_image and new_image.filename:
            try:
                final_image_name = save_image(
                    new_image,
                    app.config['ADMIN_UPLOAD_FOLDER']
                )
                uploaded_profile_image = final_image_name
            except ValueError as error:
                flash(str(error), "danger")
                return redirect('/admin/profile')

            if old_image_name:
                old_image_path = os.path.join(
                    app.config['ADMIN_UPLOAD_FOLDER'],
                    os.path.basename(old_image_name)
                )

        cursor.execute(
            """
            UPDATE eadmin
            SET name = %s, email = %s, password = %s, profile_image = %s
            WHERE admin_id = %s
            """,
            (name, email, password, final_image_name, admin_id)
        )
        conn.commit()

        if old_image_path and os.path.isfile(old_image_path):
            os.remove(old_image_path)

        session['admin_name'] = name
        session['admin_email'] = email

        flash("Profile updated successfully!", "success")
        return redirect('/admin/profile')

    except Error as error:
        conn.rollback()
        remove_uploaded_image(
            app.config['ADMIN_UPLOAD_FOLDER'],
            uploaded_profile_image
        )
        print("Database error:", error)
        flash("Unable to update profile. Please try again.", "danger")
        return redirect('/admin/profile')

    finally:
        cursor.close()
        if conn.is_connected():
            conn.close()



# =================================================================
# ROUTE 13: DELETE PRODUCT
# =================================================================
@app.route('/admin/delete-item/<int:item_id>', methods=['POST'])
def delete_item(item_id):

    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT image FROM products WHERE product_id = %s",
        (item_id,)
    )
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        flash("Product not found!", "danger")
        return redirect('/admin/products')

    cursor.execute("DELETE FROM products WHERE product_id = %s", (item_id,))
    deleted_rows = cursor.rowcount

    if deleted_rows:
        cursor.execute("SELECT product_id FROM products ORDER BY product_id ASC")
        product_ids = [row["product_id"] for row in cursor.fetchall()]

        for new_id, old_id in enumerate(product_ids, start=1):
            if new_id != old_id:
                cursor.execute(
                    "UPDATE products SET product_id = %s WHERE product_id = %s",
                    (new_id, old_id)
                )

        cursor.execute("ALTER TABLE products AUTO_INCREMENT = 1")

    conn.commit()
    cursor.close()
    conn.close()

    if deleted_rows:
        image_name = product.get("image")
        remove_uploaded_image(app.config['UPLOAD_FOLDER'], image_name)
        flash("Product deleted successfully!", "success")
    else:
        flash("Product not found!", "danger")

    return redirect('/admin/products')


# RUN APPLICATION


# =================================================================
# USER REGISTRATION
# =================================================================
@app.route('/user-register', methods=['GET', 'POST'])
def user_register():
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect('/user-dashboard')
        return render_template('user/user_register.html')

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not name or not email or not password:
        flash('Name, email, and password are required.', 'danger')
        return redirect('/user-register')
    if len(password) < 6:
        flash('Password must contain at least 6 characters.', 'danger')
        return redirect('/user-register')
    if password != confirm_password:
        flash('Password and confirm password do not match.', 'danger')
        return redirect('/user-register')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT user_id FROM susers WHERE email = %s', (email,))
        if cursor.fetchone():
            flash('Email already registered. Please login.', 'danger')
            return redirect('/user-register')

        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')
        cursor.execute(
            'INSERT INTO susers (name, email, password) VALUES (%s, %s, %s)',
            (name, email, hashed_password)
        )
        conn.commit()
    except Error as error:
        print('Database error:', error)
        if conn:
            conn.rollback()
        flash('Unable to register. Please try again.', 'danger')
        return redirect('/user-register')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    flash('Registration successful. Please login.', 'success')
    return redirect('/user-login')


# =================================================================
# USER LOGIN
# =================================================================
@app.route('/user-login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect('/user-dashboard')
        return render_template('user/user_login.html')

    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    if not email or not password:
        flash('Email and password are required.', 'danger')
        return redirect('/user-login')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM susers WHERE email = %s', (email,))
        user = cursor.fetchone()
    except Error as error:
        print('Database error:', error)
        flash('Unable to login. Please try again.', 'danger')
        return redirect('/user-login')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if not user:
        flash('Email not found. Please register.', 'danger')
        return redirect('/user-login')

    stored_password = user.get('password') or ''
    try:
        password_correct = bcrypt.checkpw(
            password.encode('utf-8'), stored_password.encode('utf-8')
        )
    except ValueError:
        password_correct = False

    if not password_correct:
        flash('Incorrect password.', 'danger')
        return redirect('/user-login')

    session.clear()
    session['user_id'] = user['user_id']
    session['user_name'] = user['name']
    session['user_email'] = user['email']
    session.permanent = True
    flash('Login successful.', 'success')
    return redirect('/user-dashboard')


# =================================================================
# USER DASHBOARD AND LOGOUT
# =================================================================
@app.route('/user-dashboard')
def user_dashboard():
    if 'user_id' not in session:
        flash('Please login to access your dashboard.', 'danger')
        return redirect('/user-login')
    return render_template(
        'user/user_home.html',
        user_name=session.get('user_name'),
        user_email=session.get('user_email')
    )


@app.route('/user/products')
def user_products():
    if 'user_id' not in session:
        flash('Please login to view products.', 'danger')
        return redirect('/user-login')

    search = request.args.get('search', '').strip()
    selected_category = request.args.get('category', '').strip()
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT DISTINCT category FROM products
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category ASC
            """
        )
        categories = cursor.fetchall()

        conditions = []
        parameters = []
        if search:
            conditions.append('name LIKE %s')
            parameters.append(f'%{search}%')
        if selected_category:
            conditions.append('category = %s')
            parameters.append(selected_category)

        query = 'SELECT * FROM products'
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY product_id DESC'
        cursor.execute(query, tuple(parameters))
        products = cursor.fetchall()
    except Error as error:
        print('Database error:', error)
        flash('Unable to load products. Please try again.', 'danger')
        return redirect('/user-dashboard')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return render_template(
        'user/user_products.html',
        products=products,
        categories=categories
    )


@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):
    if 'user_id' not in session:
        flash('Please login to view product details.', 'danger')
        return redirect('/user-login')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT * FROM products WHERE product_id = %s',
            (product_id,)
        )
        product = cursor.fetchone()
    except Error as error:
        print('Database error:', error)
        flash('Unable to load the product. Please try again.', 'danger')
        return redirect('/user/products')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if not product:
        flash('Product not found.', 'danger')
        return redirect('/user/products')

    return render_template('user/product_details.html', product=product)


@app.route('/user/cart')
def user_cart():
    if 'user_id' not in session:
        flash('Please login to view your cart.', 'danger')
        return redirect('/user-login')

    cart = session.get('cart', {})
    cart_items = []
    grand_total = 0
    for product_id, item in cart.items():
        quantity = max(1, int(item.get('quantity', 1)))
        price = float(item.get('price', 0))
        item_total = price * quantity
        cart_items.append({
            'product_id': product_id,
            'name': item.get('name', 'Product'),
            'price': price,
            'image': item.get('image'),
            'quantity': quantity,
            'item_total': item_total
        })
        grand_total += item_total

    return render_template(
        'user/user_cart.html',
        cart_items=cart_items,
        grand_total=grand_total
    )


@app.route('/user/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    wants_json = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if 'user_id' not in session:
        if wants_json:
            return jsonify(success=False, message='Please login first.'), 401
        flash('Please login first.', 'danger')
        return redirect('/user-login')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT product_id, name, price, image FROM products '
            'WHERE product_id = %s',
            (product_id,)
        )
        product = cursor.fetchone()
    except Error as error:
        print('Database error:', error)
        if wants_json:
            return jsonify(success=False, message='Unable to add this product.'), 500
        flash('Unable to add this product. Please try again.', 'danger')
        return redirect('/user/products')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    if not product:
        if wants_json:
            return jsonify(success=False, message='Product not found.'), 404
        flash('Product not found.', 'danger')
        return redirect('/user/products')

    key = str(product_id)
    cart = session.get('cart', {})
    if key in cart:
        cart[key]['quantity'] = int(cart[key].get('quantity', 0)) + 1
    else:
        cart[key] = {
            'name': product['name'],
            'price': float(product['price']),
            'image': product.get('image'),
            'quantity': 1
        }
    session['cart'] = cart
    session.modified = True
    count = sum(int(item.get('quantity', 0)) for item in cart.values())

    if wants_json:
        return jsonify(
            success=True,
            message=f"{product['name']} added to your cart.",
            cart_count=count
        )
    flash(f"{product['name']} added to your cart.", 'success')
    return redirect('/user/cart')


def update_cart_quantity(product_id, change):
    key = str(product_id)
    cart = session.get('cart', {})
    if key not in cart:
        flash('That product is not in your cart.', 'danger')
        return redirect('/user/cart')
    new_quantity = int(cart[key].get('quantity', 1)) + change
    if new_quantity <= 0:
        cart.pop(key)
    else:
        cart[key]['quantity'] = new_quantity
    session['cart'] = cart
    session.modified = True
    return redirect('/user/cart')


@app.route('/user/cart/increase/<int:product_id>', methods=['POST'])
def increase_cart_item(product_id):
    if 'user_id' not in session:
        flash('Please login first.', 'danger')
        return redirect('/user-login')
    return update_cart_quantity(product_id, 1)


@app.route('/user/cart/decrease/<int:product_id>', methods=['POST'])
def decrease_cart_item(product_id):
    if 'user_id' not in session:
        flash('Please login first.', 'danger')
        return redirect('/user-login')
    return update_cart_quantity(product_id, -1)


@app.route('/user/cart/remove/<int:product_id>', methods=['POST'])
def remove_cart_item(product_id):
    if 'user_id' not in session:
        flash('Please login first.', 'danger')
        return redirect('/user-login')
    cart = session.get('cart', {})
    removed = cart.pop(str(product_id), None)
    session['cart'] = cart
    session.modified = True
    flash('Product removed from your cart.' if removed else 'Product not found in your cart.', 'success' if removed else 'danger')
    return redirect('/user/cart')


@app.route('/user/checkout', methods=['GET', 'POST'])
def user_checkout():
    if 'user_id' not in session:
        flash('Please login before checkout.', 'danger')
        return redirect('/user-login')

    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty.', 'danger')
        return redirect('/user/products')

    address = session.get('shipping_address', {})
    return render_template(
        'user/address.html',
        address=address,
        grand_total=sum(
            float(item.get('price', 0)) * max(1, int(item.get('quantity', 1)))
            for item in cart.values()
        )
    )


@app.route('/user/pay', methods=['POST'])
def user_pay():
    if 'user_id' not in session:
        flash('Please login before checkout.', 'danger')
        return redirect('/user-login')

    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty.', 'danger')
        return redirect('/user/products')

    address = {
        'full_name': request.form.get('full_name', '').strip(),
        'phone': request.form.get('phone', '').strip(),
        'address_line': request.form.get('address_line', '').strip(),
        'city': request.form.get('city', '').strip(),
        'state': request.form.get('state', '').strip(),
        'postal_code': request.form.get('postal_code', '').strip()
    }
    required_fields = ('full_name', 'phone', 'address_line', 'city', 'state', 'postal_code')
    if any(not address[field] for field in required_fields):
        session['shipping_address'] = address
        flash('Please complete every delivery address field.', 'danger')
        return redirect('/user/checkout')
    if not address['phone'].isdigit() or not 10 <= len(address['phone']) <= 15:
        session['shipping_address'] = address
        flash('Enter a valid phone number containing 10 to 15 digits.', 'danger')
        return redirect('/user/checkout')
    if not address['postal_code'].isdigit() or not 4 <= len(address['postal_code']) <= 10:
        session['shipping_address'] = address
        flash('Enter a valid postal code.', 'danger')
        return redirect('/user/checkout')

    session['shipping_address'] = address

    client = get_razorpay_client()
    if client is None:
        flash(
            'Payment is not configured. Set RAZORPAY_KEY_ID and '
            'RAZORPAY_KEY_SECRET, then restart SmartCart.',
            'danger'
        )
        return redirect('/user/cart')

    # Razorpay accepts integer paise. Recalculate on the server instead of
    # trusting an amount supplied by the browser.
    amount_paise = sum(
        round(float(item.get('price', 0)) * 100)
        * max(1, int(item.get('quantity', 1)))
        for item in cart.values()
    )
    if amount_paise <= 0:
        flash('The cart total is invalid.', 'danger')
        return redirect('/user/cart')

    try:
        razorpay_order = client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'receipt': f"sc-{session['user_id']}-{uuid.uuid4().hex[:12]}",
            'notes': {'user_id': str(session['user_id'])}
        })
    except Exception as error:
        print('Razorpay order error:', error)
        flash('Unable to start payment. Please try again.', 'danger')
        return redirect('/user/cart')

    session['razorpay_order_id'] = razorpay_order['id']
    session['razorpay_amount'] = amount_paise
    session.modified = True

    return render_template(
        'user/payment.html',
        amount_paise=amount_paise,
        key_id=config.RAZORPAY_KEY_ID,
        order_id=razorpay_order['id'],
        address=address
    )


@app.route('/verify-payment', methods=['POST'])
@app.route('/payment-success', methods=['POST'])
def verify_payment():
    if 'user_id' not in session:
        flash('Please login again to complete payment.', 'danger')
        return redirect('/user-login')

    payment_id = request.form.get('razorpay_payment_id', '').strip()
    order_id = request.form.get('razorpay_order_id', '').strip()
    signature = request.form.get('razorpay_signature', '').strip()
    expected_order_id = session.get('razorpay_order_id')

    if not payment_id or not order_id or not signature or order_id != expected_order_id:
        flash('Payment details could not be validated.', 'danger')
        return redirect('/user/cart')

    client = get_razorpay_client()
    if client is None:
        flash('Payment verification is not configured.', 'danger')
        return redirect('/user/cart')

    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        })
    except razorpay.errors.SignatureVerificationError:
        flash('Payment verification failed. Your cart has been preserved.', 'danger')
        return redirect('/user/cart')
    except Exception as error:
        app.logger.exception('Razorpay verification error: %s', error)
        flash('We could not verify the payment. Your cart has been preserved.', 'danger')
        return redirect('/user/cart')

    cart = session.get('cart', {})
    expected_amount = session.get('razorpay_amount')
    if not cart or not isinstance(expected_amount, int) or expected_amount <= 0:
        flash('Your checkout session expired. Please contact support.', 'danger')
        return redirect('/user/cart')

    current_amount = sum(
        round(float(item.get('price', 0)) * 100)
        * max(1, int(item.get('quantity', 1)))
        for item in cart.values()
    )
    if current_amount != expected_amount:
        flash('Your cart changed during payment. Please contact support.', 'danger')
        return redirect('/user/cart')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # The unique payment ID makes callback retries idempotent.
        cursor.execute(
            'SELECT order_id FROM orders WHERE razorpay_payment_id = %s',
            (payment_id,)
        )
        existing_order = cursor.fetchone()
        if existing_order:
            conn.rollback()
            session.pop('cart', None)
            session.pop('razorpay_order_id', None)
            session.pop('razorpay_amount', None)
            session.modified = True
            return redirect(
                f"/user/order-success/{existing_order['order_id']}"
            )

        address = session.get('shipping_address', {})
        cursor.execute(
            'INSERT INTO orders '
            '(user_id, razorpay_order_id, razorpay_payment_id, amount, payment_status, full_name, phone, address_line, city, state, postal_code) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (
                session['user_id'], order_id, payment_id,
                expected_amount / 100, 'paid',
                address.get('full_name', ''),
                address.get('phone', ''),
                address.get('address_line', ''),
                address.get('city', ''),
                address.get('state', ''),
                address.get('postal_code', '')
            )
        )
        database_order_id = cursor.lastrowid

        for product_id, item in cart.items():
            cursor.execute(
                'INSERT INTO order_items '
                '(order_id, product_id, product_name, quantity, price) '
                'VALUES (%s, %s, %s, %s, %s)',
                (
                    database_order_id, int(product_id), item.get('name', 'Product'),
                    max(1, int(item.get('quantity', 1))),
                    float(item.get('price', 0))
                )
            )

        conn.commit()
    except Exception as error:
        if conn:
            conn.rollback()
        app.logger.exception('Order storage failed: %s', error)
        flash(
            'Your payment was verified, but the order could not be saved. '
            'Please contact support and provide your payment ID.',
            'danger'
        )
        return redirect('/user/cart')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    # Never clear the cart until both order records commit successfully.
    session.pop('cart', None)
    session.pop('razorpay_order_id', None)
    session.pop('razorpay_amount', None)
    session.modified = True
    flash('Payment successful and order placed!', 'success')
    return redirect(f'/user/order-success/{database_order_id}')


@app.route('/user/order-success/<int:database_order_id>')
def order_success(database_order_id):
    if 'user_id' not in session:
        flash('Please login to view your order.', 'danger')
        return redirect('/user-login')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT * FROM orders WHERE order_id = %s AND user_id = %s',
            (database_order_id, session['user_id'])
        )
        order = cursor.fetchone()
        if not order:
            flash('Order not found.', 'danger')
            return redirect('/user/my-orders')

        cursor.execute(
            'SELECT * FROM order_items WHERE order_id = %s ORDER BY id',
            (database_order_id,)
        )
        items = cursor.fetchall()
    except Error as error:
        app.logger.exception('Unable to load order: %s', error)
        flash('Unable to load this order.', 'danger')
        return redirect('/user/my-orders')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return render_template('user/order_success.html', order=order, items=items)


@app.route('/user/download-invoice/<int:order_id>')
def download_invoice(order_id):
    if 'user_id' not in session:
        flash('Please login to download your invoice.', 'danger')
        return redirect('/user-login')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT * FROM orders WHERE order_id = %s AND user_id = %s',
            (order_id, session['user_id'])
        )
        order = cursor.fetchone()

        if not order:
            flash('Order not found.', 'danger')
            return redirect('/user/my-orders')

        cursor.execute(
            'SELECT * FROM order_items WHERE order_id = %s ORDER BY id',
            (order_id,)
        )
        items = cursor.fetchall()
    except Error as error:
        app.logger.exception('Unable to generate invoice: %s', error)
        flash('Unable to generate invoice.', 'danger')
        return redirect('/user/my-orders')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    html = render_template('user/invoice.html', order=order, items=items)
    pdf_buffer = generate_pdf(html)

    if pdf_buffer is None:
        flash('Unable to generate PDF invoice.', 'danger')
        return redirect('/user/my-orders')

    from flask import send_file
    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"invoice_{order_id}.pdf",
        mimetype="application/pdf"
    )


@app.route('/user/order/<int:order_id>/update-address', methods=['GET', 'POST'])
def update_order_address(order_id):
    if 'user_id' not in session:
        flash('Please login to update your order address.', 'danger')
        return redirect('/user-login')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT * FROM orders WHERE order_id = %s AND user_id = %s',
            (order_id, session['user_id'])
        )
        order = cursor.fetchone()
        if not order:
            flash('Order not found.', 'danger')
            return redirect('/user/my-orders')

        if request.method == 'GET':
            return render_template('user/update_order_address.html', order=order)

        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address_line = request.form.get('address_line', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        postal_code = request.form.get('postal_code', '').strip()

        if not all([full_name, phone, address_line, city, state, postal_code]):
            flash('Please fill in all address fields.', 'danger')
            return render_template('user/update_order_address.html', order=order)

        if not phone.isdigit() or not 10 <= len(phone) <= 15:
            flash('Enter a valid phone number containing 10 to 15 digits.', 'danger')
            return render_template('user/update_order_address.html', order=order)

        if not postal_code.isdigit() or not 4 <= len(postal_code) <= 10:
            flash('Enter a valid postal code.', 'danger')
            return render_template('user/update_order_address.html', order=order)

        cursor.execute(
            '''UPDATE orders 
               SET full_name = %s, phone = %s, address_line = %s, city = %s, state = %s, postal_code = %s 
               WHERE order_id = %s AND user_id = %s''',
            (full_name, phone, address_line, city, state, postal_code, order_id, session['user_id'])
        )
        conn.commit()
        flash('Order delivery address updated successfully!', 'success')
        return redirect(url_for('my_orders'))
    except Error as error:
        if conn:
            conn.rollback()
        app.logger.exception('Failed to update order address: %s', error)
        flash('Unable to update order address.', 'danger')
        return redirect('/user/my-orders')
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/user/my-orders')
def my_orders():
    if 'user_id' not in session:
        flash('Please login to view your orders.', 'danger')
        return redirect('/user-login')

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            'SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC',
            (session['user_id'],)
        )
        orders = cursor.fetchall()
    except Error as error:
        app.logger.exception('Unable to load orders: %s', error)
        flash('Unable to load your orders.', 'danger')
        orders = []
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return render_template('user/my_orders.html', orders=orders)


@app.route('/user-logout')
def user_logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect('/user-login')


if __name__ == "__main__":
    app.run(debug=True)
