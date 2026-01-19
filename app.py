from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, date
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Secret key for sessions
app.config["SECRET_KEY"] = "change_this_later"

# SQLite database
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///rides.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# -------------- MODELS --------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    whatsapp = db.Column(db.String(30), nullable=True)

    rides = db.relationship("Ride", backref="user", lazy=True)


class Ride(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    origin = db.Column(db.String(120), nullable=False)
    destination = db.Column(db.String(120), nullable=False)
    time = db.Column(db.Time, nullable=False)
    time_str = db.Column(db.String(5), nullable=False)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class RideRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ride_id = db.Column(db.Integer, db.ForeignKey("ride.id"), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending/accepted/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ride = db.relationship("Ride", backref="requests", lazy=True)
    requester = db.relationship("User", foreign_keys=[requester_id])


# -------------- HELPERS --------------

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()


def normalize_place(text):
    if not text:
        return ""
    return text.strip().lower()


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return User.query.get(uid)


def login_required_view(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


TIME_WINDOW_MINUTES = 30


def find_matches(origin, destination, ride_time, ride_date):
    time_window = timedelta(minutes=TIME_WINDOW_MINUTES)
    base_dt = datetime.combine(ride_date, ride_time)

    same_route = Ride.query.filter_by(
        origin=origin, destination=destination, date=ride_date
    ).all()

    matches = []
    for ride in same_route:
        existing_dt = datetime.combine(ride.date, ride.time)
        if abs(existing_dt - base_dt) <= time_window:
            matches.append(ride)
    return matches


def date_label(ride_date):
    today = date.today()
    if ride_date == today:
        return "Today"
    elif ride_date == today + timedelta(days=1):
        return "Tomorrow"
    else:
        return ride_date.strftime("%d %b %Y")


def get_user_request_for_ride(user_id, ride):
    if not ride.requests:
        return None
    for r in ride.requests:
        if r.requester_id == user_id:
            return r
    return None


# -------------- AUTH ROUTES --------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        whatsapp = request.form.get("whatsapp")
        password = request.form.get("password")

        if not (name and email and password):
            flash("Please fill all required fields.", "error")
            return redirect(url_for("register"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("register"))

        hashed_pw = generate_password_hash(password)

        user = User(
            name=name,
            email=email,
            password=hashed_pw,
            whatsapp=whatsapp,
        )
        db.session.add(user)
        db.session.commit()

        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", current_user=get_current_user())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        flash("Logged in successfully.", "success")
        return redirect(url_for("index"))

    return render_template("login.html", current_user=get_current_user())


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out.", "success")
    return redirect(url_for("login"))


# -------------- RIDE ROUTES --------------

@app.route("/", methods=["GET", "POST"])
@login_required_view
def index():
    current_user = get_current_user()

    if request.method == "POST":
        origin_raw = request.form.get("origin")
        destination_raw = request.form.get("destination")
        date_str = request.form.get("date")
        time_str = request.form.get("time")

        if not (origin_raw and destination_raw and time_str and date_str):
            flash("Please fill all fields.", "error")
            return redirect(url_for("index"))

        origin = normalize_place(origin_raw)
        destination = normalize_place(destination_raw)
        ride_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        ride_time = parse_time(time_str)

        new_ride = Ride(
            origin=origin,
            destination=destination,
            time=ride_time,
            time_str=time_str,
            date=ride_date,
            user_id=current_user.id,
        )
        db.session.add(new_ride)
        db.session.commit()

        matches = find_matches(origin, destination, ride_time, ride_date)

        return render_template(
            "results.html",
            new_ride=new_ride,
            matches=matches,
            current_user=current_user,
            date_label=date_label,
        )

    # GET filters
    origin_q = request.args.get("origin")
    destination_q = request.args.get("destination")
    date_q = request.args.get("date")

    query = Ride.query

    if origin_q:
        query = query.filter(Ride.origin == normalize_place(origin_q))
    if destination_q:
        query = query.filter(Ride.destination == normalize_place(destination_q))
    if date_q:
        try:
            d = datetime.strptime(date_q, "%Y-%m-%d").date()
            query = query.filter(Ride.date == d)
        except ValueError:
            pass

    rides = query.order_by(Ride.created_at.desc()).all()
    return render_template(
        "index.html",
        rides=rides,
        current_user=current_user,
        date_label=date_label,
        get_user_request_for_ride=get_user_request_for_ride,
    )


@app.route("/create", methods=["GET", "POST"])
@login_required_view
def create_ride():
    current_user = get_current_user()

    if request.method == "POST":
        origin_raw = request.form.get("origin")
        destination_raw = request.form.get("destination")
        date_str = request.form.get("date")
        time_str = request.form.get("time")

        if not (origin_raw and destination_raw and time_str and date_str):
            flash("Please fill all fields.", "error")
            return redirect(url_for("create_ride"))

        origin = normalize_place(origin_raw)
        destination = normalize_place(destination_raw)
        ride_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        ride_time = parse_time(time_str)

        new_ride = Ride(
            origin=origin,
            destination=destination,
            time=ride_time,
            time_str=time_str,
            date=ride_date,
            user_id=current_user.id,
        )
        db.session.add(new_ride)
        db.session.commit()

        matches = find_matches(origin, destination, ride_time, ride_date)

        return render_template(
            "results.html",
            new_ride=new_ride,
            matches=matches,
            current_user=current_user,
            date_label=date_label,
        )

    return render_template("create_ride.html", current_user=current_user)


@app.route("/request/<int:ride_id>", methods=["POST"])
@login_required_view
def request_join(ride_id):
    current_user = get_current_user()
    ride = Ride.query.get_or_404(ride_id)

    if ride.user_id == current_user.id:
        flash("You created this ride yourself.", "error")
        return redirect(url_for("index"))

    existing = RideRequest.query.filter_by(
        ride_id=ride.id,
        requester_id=current_user.id
    ).first()
    if existing and existing.status == "pending":
        flash("You already have a pending request for this ride.", "error")
        return redirect(url_for("index"))

    req = RideRequest(
        ride_id=ride.id,
        requester_id=current_user.id,
        status="pending",
    )
    db.session.add(req)
    db.session.commit()

    flash("Request sent to the ride owner.", "success")
    return redirect(url_for("index"))


@app.route("/my-requests")
@login_required_view
def my_requests():
    current_user = get_current_user()

    requests = (
        RideRequest.query
        .join(Ride)
        .filter(Ride.user_id == current_user.id)
        .order_by(RideRequest.created_at.desc())
        .all()
    )
    return render_template(
        "my_requests.html",
        current_user=current_user,
        requests=requests,
        date_label=date_label,
    )


@app.route("/my-requests/<int:req_id>/accept", methods=["POST"])
@login_required_view
def accept_request(req_id):
    current_user = get_current_user()
    req = RideRequest.query.get_or_404(req_id)

    if req.ride.user_id != current_user.id:
        flash("Not authorized.", "error")
        return redirect(url_for("my_requests"))

    req.status = "accepted"
    db.session.commit()
    flash(f"Accepted request from {req.requester.name}.", "success")
    return redirect(url_for("my_requests"))


@app.route("/my-requests/<int:req_id>/reject", methods=["POST"])
@login_required_view
def reject_request(req_id):
    current_user = get_current_user()
    req = RideRequest.query.get_or_404(req_id)

    if req.ride.user_id != current_user.id:
        flash("Not authorized.", "error")
        return redirect(url_for("my_requests"))

    req.status = "rejected"
    db.session.commit()
    flash(f"Rejected request from {req.requester.name}.", "success")
    return redirect(url_for("my_requests"))


# -------------- MAIN --------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
