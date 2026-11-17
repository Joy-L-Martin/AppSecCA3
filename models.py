
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), nullable=False)

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        default="customer",
        nullable=False
    )

class AppointmentSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    date = db.Column(db.String(20), nullable=False)

    time = db.Column(db.String(20), nullable=False)

    is_available = db.Column(db.Boolean, default=True)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    slot_id = db.Column(
        db.Integer,
        db.ForeignKey("appointment_slot.id"),
        unique=True,
        nullable=False
    )

    user = db.relationship("User")
    slot = db.relationship("AppointmentSlot")
