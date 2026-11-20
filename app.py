from flask import abort
import secrets
from flask import session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from flask import Flask, render_template, request, redirect, flash, url_for
from werkzeug.security import generate_password_hash

from models import db, User, AppointmentSlot, Booking, LoginSecurityEvent, UserSession, AccessSecurityEvent

from datetime import datetime, timedelta, timezone
import hashlib
import hmac


app = Flask(__name__)

# Application configuration
app.config["SECRET_KEY"] = "local-development-key-change-later"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"

SESSION_TIMEOUT = timedelta(minutes=10)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False

# Brute-force login protection settings
MAX_FAILED_ATTEMPTS = 5
FAILED_LOGIN_WINDOW = timedelta(minutes=30)
LOGIN_LOCK_DURATION = timedelta(minutes=15)
LOGIN_ERROR_MESSAGE = "Invalid login details or login temporarily unavailable."


# Connect database to Flask
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.before_request
def validate_secure_session():

    # Allow login, registration and home page without a session
    if request.endpoint in ("login", "register", "home", "static"):
        return

    if not current_user.is_authenticated:
        return

    token = session.get("session_token")

    if not token:
        logout_user()
        session.clear()
        return redirect(url_for("login"))

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    stored_session = UserSession.query.filter_by(
        user_id=current_user.id,
        token_hash=token_hash
    ).first()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if stored_session is None:
        logout_user()
        session.clear()
        return redirect(url_for("login"))

    if now - stored_session.last_activity >= SESSION_TIMEOUT:

        db.session.delete(stored_session)
        db.session.commit()

        logout_user()
        session.clear()

        return redirect(url_for("login"))

    # Update activity timestamp
    stored_session.last_activity = now
    db.session.commit()


# Create database tables
with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return render_template("index.html")


def get_login_identifier(email):
    # Generate a consistent identifier without storing the email
    return hmac.new(
        app.config["SECRET_KEY"].encode("utf-8"),
        email.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def create_secure_session(user):

    # Generate a cryptographically secure random token
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Replace any existing session for this user
    UserSession.query.filter_by(user_id=user.id).delete()

    new_session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        last_activity=datetime.now(timezone.utc).replace(tzinfo=None)
    )

    db.session.add(new_session)
    db.session.commit()

    # Clear previous Flask session information
    session.clear()

    # Store the token in Flask's signed session cookie
    session["session_token"] = token

    login_user(user)


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        identifier = get_login_identifier(email)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Check for an active login restriction
        active_lock = LoginSecurityEvent.query.filter(
            LoginSecurityEvent.identifier_hash == identifier,
            LoginSecurityEvent.event_type == "restricted",
            LoginSecurityEvent.locked_until > now
        ).first()

        if active_lock:
            db.session.add(LoginSecurityEvent(
                identifier_hash=identifier,
                event_type="blocked",
                occurred_at=now
            ))
            db.session.commit()

            flash(LOGIN_ERROR_MESSAGE, "danger")
            return redirect(url_for("login"))

        # Check submitted credentials
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):

            # Clear previous failures after a successful login
            LoginSecurityEvent.query.filter(
                LoginSecurityEvent.identifier_hash == identifier,
                LoginSecurityEvent.event_type == "failed"
            ).delete(synchronize_session=False)

            db.session.commit()

            create_secure_session(user)
            return redirect(url_for("dashboard"))

        # Record the failed login
        db.session.add(LoginSecurityEvent(
            identifier_hash=identifier,
            event_type="failed",
            occurred_at=now
        ))
        db.session.flush()

        # Count failures within the last 30 minutes
        window_start = now - FAILED_LOGIN_WINDOW

        failed_count = LoginSecurityEvent.query.filter(
            LoginSecurityEvent.identifier_hash == identifier,
            LoginSecurityEvent.event_type == "failed",
            LoginSecurityEvent.occurred_at >= window_start
        ).count()

        # Restrict login after five failed attempts
        if failed_count >= MAX_FAILED_ATTEMPTS:

            db.session.add(LoginSecurityEvent(
                identifier_hash=identifier,
                event_type="restricted",
                occurred_at=now,
                locked_until=now + LOGIN_LOCK_DURATION
            ))

        db.session.commit()

        flash(LOGIN_ERROR_MESSAGE, "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not username or not email or not password:
            flash("Please complete all fields.", "danger")
            return redirect(url_for("register"))

        # Check if email already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("Email is already registered.", "danger")
            return redirect(url_for("register"))

        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role="customer"
        )

        # Save user to database
        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully! Please log in.", "success")

        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")



@app.route("/logout", methods=["POST"])
@login_required
def logout():

    # Invalidate the active token in the database
    UserSession.query.filter_by(
        user_id=current_user.id
    ).delete()

    db.session.commit()

    logout_user()
    session.clear()

    return redirect(url_for("home"))



@app.route("/book")
@login_required
def book():
    if current_user.role != "customer":
        log_unauthorised_access("unauthorised_booking_access")
        abort(403)

    slots = AppointmentSlot.query.filter_by(
        is_available=True
    ).order_by(
        AppointmentSlot.date,
        AppointmentSlot.time
    ).all()

    return render_template("book.html", slots=slots)




@app.route("/book/<int:slot_id>", methods=["POST"])
@login_required
def book_slot(slot_id):

    if current_user.role != "customer":
        log_unauthorised_access("unauthorised_booking_access")
        abort(403)

    slot = db.session.get(AppointmentSlot, slot_id)

    if not slot or not slot.is_available:
        flash("This appointment is no longer available.", "danger")
        return redirect(url_for("book"))

    new_booking = Booking(
        user_id=current_user.id,
        slot_id=slot.id
    )

    slot.is_available = False

    db.session.add(new_booking)
    db.session.commit()

    flash("Appointment booked successfully!", "success")

    return redirect(url_for("dashboard"))


def log_unauthorised_access(event_type):

    event = AccessSecurityEvent(
        user_id=current_user.id if current_user.is_authenticated else None,
        event_type=event_type,
        endpoint=request.endpoint or "unknown",
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )

    db.session.add(event)
    db.session.commit()


def require_admin():

    if current_user.role != "admin":
        log_unauthorised_access("unauthorised_admin_access")
        abort(403)



def require_booking_owner(booking):

    if current_user.role != "customer" or booking.user_id != current_user.id:
        log_unauthorised_access("unauthorised_booking_access")
        abort(403)


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():

    require_admin()

    if request.method == "POST":

        date = request.form["date"]
        time = request.form["time"]

        new_slot = AppointmentSlot(
            date=date,
            time=time,
            is_available=True
        )

        db.session.add(new_slot)
        db.session.commit()

        flash("Appointment slot added successfully!", "success")
        return redirect(url_for("admin"))

    slots = AppointmentSlot.query.order_by(
        AppointmentSlot.date,
        AppointmentSlot.time
    ).all()

    return render_template("admin.html", slots=slots)



@app.route("/admin/edit/<int:slot_id>", methods=["GET", "POST"])
@login_required
def edit_slot(slot_id):

    require_admin()

    slot = db.get_or_404(AppointmentSlot, slot_id)

    if not slot.is_available:
        flash("Booked appointments cannot be edited.", "danger")
        return redirect(url_for("admin"))

    if request.method == "POST":

        slot.date = request.form["date"]
        slot.time = request.form["time"]

        db.session.commit()

        flash("Appointment updated successfully!", "success")
        return redirect(url_for("admin"))

    return render_template("edit_slot.html", slot=slot)


@app.route("/admin/delete/<int:slot_id>", methods=["POST"])
@login_required
def delete_slot(slot_id):

    require_admin()

    slot = db.get_or_404(AppointmentSlot, slot_id)

    if not slot.is_available:
        flash("Booked appointments cannot be deleted.", "danger")
        return redirect(url_for("admin"))

    db.session.delete(slot)
    db.session.commit()

    flash("Appointment deleted successfully!", "success")

    return redirect(url_for("admin"))


@app.route("/my-appointments")
@login_required
def my_appointments():

    if current_user.role != "customer":
        log_unauthorised_access("unauthorised_booking_access")
        abort(403)

    bookings = Booking.query.filter_by(
        user_id=current_user.id
    ).all()

    return render_template(
        "my_appointments.html",
        bookings=bookings
    )


@app.route("/cancel/<int:booking_id>", methods=["POST"])
@login_required
def cancel_booking(booking_id):

    booking = db.get_or_404(Booking, booking_id)

    require_booking_owner(booking)

    booking.slot.is_available = True

    db.session.delete(booking)
    db.session.commit()

    flash("Appointment cancelled successfully!", "success")

    return redirect(url_for("my_appointments"))


if __name__ == "__main__":
    app.run(debug=True)

