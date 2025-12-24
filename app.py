from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime, timedelta

app = Flask(__name__)

# simple in-memory storage (server band hoga to data reset)
rides = []

def parse_time(time_str):
    # "HH:MM" ko datetime.time me convert
    return datetime.strptime(time_str, "%H:%M").time()

def time_close(t1, t2, minutes=30):
    # t1, t2 = time objects; difference <= minutes?
    dt1 = datetime.combine(datetime.today(), t1)
    dt2 = datetime.combine(datetime.today(), t2)
    diff = abs(dt1 - dt2)
    return diff <= timedelta(minutes=minutes)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name")
        source = request.form.get("source")
        dest = request.form.get("dest")
        time_str = request.form.get("time")

        if not (name and source and dest and time_str):
            return render_template("index.html", error="Sab fields bharo!", rides_count=len(rides))

        try:
            ride_time = parse_time(time_str)
        except ValueError:
            return render_template("index.html", error="Time format HH:MM me do (e.g. 07:30).", rides_count=len(rides))

        new_ride = {
            "name": name,
            "source": source.strip().lower(),
            "dest": dest.strip().lower(),
            "time_str": time_str,
            "time": ride_time
        }

        # matches dhoondo
        matches = []
        for r in rides:
            same_source = r["source"] == new_ride["source"]
            same_dest = r["dest"] == new_ride["dest"]
            close_time = time_close(r["time"], new_ride["time"], minutes=30)
            if same_source and same_dest and close_time:
                matches.append(r)

        # current ride ko list me add karo
        rides.append(new_ride)

        return render_template("results.html", ride=new_ride, matches=matches)

    return render_template("index.html", error=None, rides_count=len(rides))

if __name__ == "__main__":
    app.run(debug=True)
