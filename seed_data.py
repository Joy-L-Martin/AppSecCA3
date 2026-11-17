
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from app import app
from models import db, User, AppointmentSlot, Booking


with app.app_context():

    # Create fictional admin and customer accounts
    demo_users = [
        ("Admin One", "admin1@example.com", "admin"),
        ("Admin Two", "admin2@example.com", "admin"),
        ("Alice Smith", "alice@example.com", "customer"),
        ("Bob Jones", "bob@example.com", "customer"),
        ("Charlie Brown", "charlie@example.com", "customer"),
        ("Diana Green", "diana@example.com", "customer"),
        ("Emma White", "emma@example.com", "customer"),
    ]

    for username, email, role in demo_users:
        if not User.query.filter_by(email=email).first():
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash("Demo123!"),
                role=role
            )
            db.session.add(user)

    db.session.commit()

    # Create 15 appointment slots on future dates
    slots = []

    for day in range(1, 6):
        appointment_date = (
            date.today() + timedelta(days=day)
        ).isoformat()

        for appointment_time in ["09:00", "11:00", "14:00"]:
            slot = AppointmentSlot.query.filter_by(
                date=appointment_date,
                time=appointment_time
            ).first()

            if slot is None:
                slot = AppointmentSlot(
                    date=appointment_date,
                    time=appointment_time,
                    is_available=True
                )
                db.session.add(slot)

            slots.append(slot)

    db.session.commit()

    # Create sample bookings for fictional customers
    customer_emails = [
        "alice@example.com",
        "bob@example.com",
        "charlie@example.com",
        "diana@example.com",
        "emma@example.com",
    ]

    for email, slot in zip(customer_emails, slots):
        customer = User.query.filter_by(email=email).first()

        existing_booking = Booking.query.filter_by(
            slot_id=slot.id
        ).first()

        if not existing_booking:
            booking = Booking(
                user_id=customer.id,
                slot_id=slot.id
            )

            slot.is_available = False
            db.session.add(booking)

    db.session.commit()

    print("Synthetic data added successfully!")
    print("Admin login: admin1@example.com")
    print("Customer login: alice@example.com")
    print("Demo password: Demo123!")
