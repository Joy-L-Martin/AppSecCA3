from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from flask import Flask, render_template, request, redirect, flash, url_for
from werkzeug.security import generate_password_hash

from models import db, User, AppointmentSlot, Booking

app = Flask(__name__)

# Application configuration
app.config["SECRET_KEY"] = "local-development-key-change-later"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"

# Connect database to Flask
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Create database tables
with app.app_context():
    db.create_all()


@app.route("/")
def home():
    return render_template("index.html")



@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

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
    logout_user()
    return redirect(url_for("home"))


@app.route("/book")
@login_required
def book():
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


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():

    if current_user.role != "admin":
        return redirect(url_for("dashboard"))

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

    if current_user.role != "admin":
        return redirect(url_for("dashboard"))

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

    if current_user.role != "admin":
        return redirect(url_for("dashboard"))

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

    if booking.user_id != current_user.id:
        flash("You cannot cancel this appointment.", "danger")
        return redirect(url_for("my_appointments"))

    # Make the appointment slot available again
    booking.slot.is_available = True

    # Remove the booking
    db.session.delete(booking)
    db.session.commit()

    flash("Appointment cancelled successfully!", "success")

    return redirect(url_for("my_appointments"))


if __name__ == "__main__":
    app.run(debug=True)

