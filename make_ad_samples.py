"""Write data/ad_performance.json: 40 synthetic past ads with performance metrics.

Copy is hand-written to the brand guides in data/brand_guidelines_*.md. Numbers in
the copy ({range}, {accel}) are filled from ev.db, so past ads agree with the spec
lookup. Metrics are random (fixed seed); on-brand ads are drawn from a better
distribution than off-brand ones, so the data rewards following the guide.
"""

import json
import random
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB_PATH = HERE / "ev.db"
OUT_PATH = HERE / "data" / "ad_performance.json"

DB_BRAND = {"Tesla": "Tesla", "Hyundai": "Hyundai", "Chevrolet": "GM/Chevrolet"}

# (ad_id, brand, db_model, channel, on_brand, cta, copy)
# social: headline, text | search: headline, description | email: subject, preheader, body
ADS = [
    # ---------------- Tesla: Model 3 ----------------
    ("TSL-01", "Tesla", "Model 3", "social", True, "Schedule a demo drive",
     {"headline": "Your commute, rewritten quietly",
      "text": "Charge at home overnight. Up to {range} miles of estimated range. Schedule a demo drive."}),
    ("TSL-02", "Tesla", "Model 3", "search", True, "Order now",
     {"headline": "Model 3: Quiet and Efficient",
      "description": "Up to {range} mi of estimated range. New features via software updates. Order now."}),
    ("TSL-03", "Tesla", "Model 3", "social", True, "Learn more",
     {"headline": "Skip the gas station for good",
      "text": "Plug in at home, wake up charged. Model 3 gets new features through software updates. Learn more."}),
    ("TSL-04", "Tesla", "Model 3", "email", True, "Schedule a demo drive",
     {"subject": "Your commute, minus the gas station",
      "preheader": "Model 3 charges at home overnight and installs software updates while parked.",
      "body": "Monday morning. You unplug, back out of the driveway and the battery is already full. "
              "No detour to the gas station, no waiting in line. "
              "Model 3 charges overnight from a Wall Connector in your garage, so every morning starts the same way. "
              "On the road, the cabin stays quiet and regenerative braking slows the car as you lift off the pedal, "
              "sending energy back to the battery. "
              "When the car is parked, software updates install over Wi-Fi and add new features over time. "
              "Model 3 Base offers up to {range} miles of estimated range, enough for a week of typical commuting for many drivers. "
              "Want to feel the difference for yourself? Schedule a demo drive at a location near you and take your usual route. "
              "Actual range varies with conditions and driving habits."}),
    ("TSL-05", "Tesla", "Model 3", "search", False, "Order now",
     {"headline": "Best Sedan Ever Made",
      "description": "FSD drives you everywhere. Revolutionary. Order now!"}),
    ("TSL-06", "Tesla", "Model 3", "social", True, "Schedule a demo drive",
     {"headline": "0-60 in {accel}s. Quietly.",
      "text": "Model 3 Base. Instant torque, a calm cabin and Supercharger stops on long trips. Schedule a demo drive."}),
    ("TSL-07", "Tesla", "Model 3", "social", False, "Order now",
     {"headline": "The REVOLUTIONARY Model 3!!",
      "text": "Never worry about range again. Self-driving fun for everyone!"}),
    # ---------------- Tesla: Model Y ----------------
    ("TSL-08", "Tesla", "Model Y", "social", True, "Schedule a demo drive",
     {"headline": "Room for the whole weekend",
      "text": "Bikes, bags and the dog. Up to {range} miles of estimated range. Schedule a demo drive."}),
    ("TSL-09", "Tesla", "Model Y", "search", True, "Order now",
     {"headline": "Model Y: Room for Seven",
      "description": "Space for the team and the gear, with Supercharger stops on the way. Order now."}),
    ("TSL-10", "Tesla", "Model Y", "email", True, "Schedule a demo drive",
     {"subject": "School run Monday, road trip Saturday",
      "preheader": "Model Y adds Supercharger stops to your route on longer drives.",
      "body": "Monday starts with backpacks, a forgotten lunch box and a quick loop to school. "
              "Saturday starts with a cooler, two bikes and four hours of highway. "
              "Model Y is built for both. "
              "Enter a destination in navigation and the car adds Supercharger stops along the route when you need them, "
              "with a charging estimate for each stop. "
              "Between trips, charge at home on a Wall Connector so the week begins with a full battery. "
              "The rear seats fold flat when the gear outnumbers the passengers, and the cabin stays quiet enough "
              "for the back row to fall asleep. "
              "Model Y Long Range offers up to {range} miles of estimated range. "
              "See how it fits your week: schedule a demo drive and bring the car seats. "
              "Actual range varies with conditions and driving habits."}),
    ("TSL-11", "Tesla", "Model Y", "social", True, "Learn more",
     {"headline": "Road trips, planned for you",
      "text": "Set a destination and Model Y adds Supercharger stops along the route. Learn more."}),
    ("TSL-12", "Tesla", "Model Y", "search", True, "Schedule a demo drive",
     {"headline": "Model Y Long Range",
      "description": "Up to {range} mi of estimated range. Actual range varies. Schedule a demo drive."}),
    ("TSL-13", "Tesla", "Model Y", "social", False, "Order now",
     {"headline": "Model Y drives itself!",
      "text": "Hands-free, worry-free family trips. Unlimited fun. Order now!"}),
    ("TSL-14", "Tesla", "Model Y", "email", True, "Order now",
     {"subject": "Room for seven, or one very large dog",
      "preheader": "Fold the seats, load the gear and let the car plan the charging stops.",
      "body": "Some weekends you need every seat. Other weekends you need the cargo floor for a crate, "
              "a stroller and a week of groceries. "
              "Model Y handles both: fold the rear seats flat and the space opens up in seconds. "
              "Charging fits around your plans instead of the other way around. "
              "Plug in at home overnight, and on longer trips the navigation adds Supercharger stops "
              "so you arrive with charge to spare. "
              "Sentry Mode can watch the car while you are away from it, and software updates install while "
              "it is parked in the driveway. "
              "On busy mornings, the car can be warmed up or cooled down from your phone before anyone gets in. "
              "If the family calendar is full, Model Y is ready for it. "
              "Order now and choose the seating layout that suits your household."}),
    # ---------------- Tesla: Cybertruck ----------------
    ("TSL-15", "Tesla", "Cybertruck", "social", True, "Learn more",
     {"headline": "Your job site just got quieter",
      "text": "Tow, haul and power your tools from the outlets, then drive home electric. Learn more."}),
    ("TSL-16", "Tesla", "Cybertruck", "search", True, "Learn more",
     {"headline": "Cybertruck: Built for Work",
      "description": "Power outlets for your tools and up to {range} mi of estimated range. Learn more."}),
    ("TSL-17", "Tesla", "Cybertruck", "email", True, "Learn more",
     {"subject": "Power tools, meet your truck",
      "preheader": "Run your tools from the outlets and drive home without a gas stop.",
      "body": "Early morning on the job site, and the generator stayed in the shed. "
              "Cybertruck has power outlets in the cabin and the bed, so saws, chargers and work lights "
              "plug straight into the truck. "
              "When the day ends, load the tools, hook up the trailer and drive home on electric power. "
              "Regenerative braking recovers energy on the way down hills, and the truck charges overnight "
              "on a Wall Connector so it is ready for tomorrow's early start. "
              "Cybertruck offers up to {range} miles of estimated range for the drive between sites and the trip home. "
              "Check the owner's manual for outlet ratings before you plug in heavy equipment. "
              "Learn more about how Cybertruck fits your work week. "
              "Actual range varies with conditions and driving habits."}),
    ("TSL-18", "Tesla", "Cybertruck", "social", True, "Learn more",
     {"headline": "Sentry Mode watches the truck",
      "text": "Parked at the trailhead? Sentry Mode records around the truck while you hike. Learn more."}),
    ("TSL-19", "Tesla", "Cybertruck", "search", False, "Order now",
     {"headline": "Bulletproof Cybertruck",
      "description": "Indestructible, self-driving and better than any competitor. Order now!"}),
    ("TSL-20", "Tesla", "Cybertruck", "social", True, "Order now",
     {"headline": "Haul Friday. Commute Monday.",
      "text": "Cybertruck tows the trailer on the weekend and handles the commute all week. Order now."}),
    # ---------------- Hyundai ----------------
    ("HYU-01", "Hyundai", "Ioniq 5", "social", True, "Explore IONIQ 5",
     {"headline": "Weekdays to weekends, sorted",
      "text": "Room for the car seat, the groceries and the dog. Up to {range} miles of estimated range. Explore IONIQ 5."}),
    ("HYU-02", "Hyundai", "Ioniq 5", "search", True, "Find a dealer",
     {"headline": "IONIQ 5: Room to Live",
      "description": "Fast charging that fits inside a coffee stop. Find a dealer."}),
    ("HYU-03", "Hyundai", "Ioniq 5", "email", True, "Explore IONIQ 5",
     {"subject": "One car for the commute and the road trip",
      "preheader": "A roomy cabin for weekdays, DC fast charging for the weekend away.",
      "body": "During the week, IONIQ 5 is the calm part of your day. "
              "You charge at home overnight, leave with a full battery and drive to work in a quiet, roomy cabin. "
              "On the weekend, it becomes the road-trip car. "
              "Pull into a DC fast charging station, grab a coffee and stretch your legs while the battery tops up. "
              "Lift your foot off the accelerator and regenerative braking slows the car while sending energy "
              "back to the battery, which makes stop-and-go traffic feel easier too. "
              "There is room in the back for the stroller, the weekend bags and the snacks nobody admits to packing. "
              "IONIQ 5 offers up to {range} miles of estimated range. "
              "Explore IONIQ 5 and see how one car can fit both halves of your week. "
              "Actual range varies with conditions and driving habits."}),
    ("HYU-04", "Hyundai", "Ioniq 5", "social", False, "Explore IONIQ 5",
     {"headline": "The Revolutionary IONIQ 5!",
      "text": "Zero emissions, unlimited range, best-in-class everything!"}),
    ("HYU-05", "Hyundai", "Ioniq 6", "search", True, "Find a dealer",
     {"headline": "IONIQ 6: Built for Long Drives",
      "description": "Streamlined design and up to {range} mi of estimated range. Find a dealer."}),
    ("HYU-06", "Hyundai", "Ioniq 6", "social", True, "Explore IONIQ 6",
     {"headline": "Long drives, fewer stops",
      "text": "A calm cabin and a streamlined shape made for the open road. Explore IONIQ 6."}),
    ("HYU-07", "Hyundai", "Ioniq 6", "social", False, "Find a dealer",
     {"headline": "Best EV Sedan Ever",
      "text": "Beats every competitor. No more range anxiety, ever!"}),
    ("HYU-08", "Hyundai", "Kona Electric", "email", True, "Build yours",
     {"subject": "Your first EV can be this simple",
      "preheader": "Plug in at home, wake up charged, and get on with your day.",
      "body": "Your morning looks the same as it always has: coffee, keys, out the door. "
              "The only difference is that you never stop for gas again. "
              "Kona Electric charges at home overnight, so most days start with a full battery. "
              "Plug the charging cable into the charging port when you get home, and the car takes care of the rest. "
              "In town, Kona Electric is easy to park and easy to drive, and regenerative braking helps you slow down "
              "smoothly in traffic while recovering energy. "
              "It offers up to {range} miles of estimated range, which covers errands, commutes and the occasional "
              "weekend visit. "
              "Switching to electric does not have to mean learning a whole new routine. Build yours today. "
              "Actual range varies with conditions and driving habits."}),
    ("HYU-09", "Hyundai", "Kona Electric", "social", True, "Build yours",
     {"headline": "City errands, sorted",
      "text": "Plug in at home tonight, run errands tomorrow. Kona Electric makes electric easy. Build yours."}),
    ("HYU-10", "Hyundai", "Kona Electric", "search", True, "Find a dealer",
     {"headline": "Kona Electric: Easy Switch",
      "description": "Up to {range} mi of estimated range. Charge at home overnight. Find a dealer."}),
    # ---------------- Chevrolet ----------------
    ("CHV-01", "Chevrolet", "Equinox EV", "social", True, "Build yours",
     {"headline": "Same routine. No gas station.",
      "text": "School runs, practice, groceries, then plug in at home. Up to {range} miles of estimated range. Build yours."}),
    ("CHV-02", "Chevrolet", "Equinox EV", "search", True, "Build yours",
     {"headline": "Equinox EV: Easy Switch",
      "description": "Level 2 home charging overnight, up to {range} mi of estimated range. Build yours."}),
    ("CHV-03", "Chevrolet", "Equinox EV", "email", True, "Build yours",
     {"subject": "Switching from gas? Here's your new routine",
      "preheader": "Plug in at home, check the charge in the myChevrolet app, and head out.",
      "body": "If you're driving a gas SUV today, here's what changes with Equinox EV: not much, except the gas station. "
              "You still do the school runs, the practice pickups and the big grocery trip on Sunday. "
              "At night, you plug into Level 2 home charging and check the charge from the myChevrolet app. "
              "On the road, One-Pedal Driving lets you slow down by easing off the accelerator, "
              "and Regen on Demand adds a little more slowing when you need it, sending energy back to the battery. "
              "Equinox EV offers up to {range} miles of estimated range, which covers a typical week of family driving for many households. "
              "It's the same family SUV routine you know, with fewer stops. Build yours today! "
              "Actual range varies with conditions and driving habits."}),
    ("CHV-04", "Chevrolet", "Equinox EV", "social", False, "Build yours",
     {"headline": "Unleash the REVOLUTIONARY Equinox EV!",
      "text": "Never worry about range. It basically drives itself on any road!"}),
    ("CHV-05", "Chevrolet", "Blazer EV", "social", True, "Build yours",
     {"headline": "Friday downtown. Saturday on the field.",
      "text": "Blazer EV has the look for date night and the room for the whole team. Build yours."}),
    ("CHV-06", "Chevrolet", "Blazer EV", "search", True, "Find a dealer",
     {"headline": "Blazer EV: Bold and Roomy",
      "description": "Sporty style with space for people and gear. Find a dealer."}),
    ("CHV-07", "Chevrolet", "Blazer EV", "email", True, "Build yours",
     {"subject": "Weekend plans, meet Blazer EV",
      "preheader": "Room for the team, the gear and a stop for dinner on the way home.",
      "body": "Early Saturday: three kids, two coolers and a folding chair for every parent on the sideline. "
              "Blazer EV has the room for all of it and still looks sharp in the parking lot. "
              "Around town, One-Pedal Driving makes stop-and-go easy. Ease off the accelerator and Blazer EV slows down "
              "on its own, sending energy back to the battery. "
              "After the last game, stop for dinner on the way home, then plug into Level 2 home charging overnight "
              "and check the charge from the myChevrolet app in the morning. "
              "Blazer EV offers up to {range} miles of estimated range, plenty for a full day of driving between "
              "fields. "
              "Bold enough for Friday night, practical enough for Saturday morning. Build yours. "
              "Actual range varies with conditions and driving habits."}),
    ("CHV-08", "Chevrolet", "Silverado EV", "search", True, "Find a dealer",
     {"headline": "Silverado EV: Power on Site",
      "description": "Run your tools from available bed outlets, then drive home electric. Find a dealer."}),
    ("CHV-09", "Chevrolet", "Silverado EV", "social", True, "See offers",
     {"headline": "Tow it. Power it. Drive home.",
      "text": "Silverado EV tows the trailer and runs your tools on site, when properly equipped. See offers."}),
    ("CHV-10", "Chevrolet", "Silverado EV", "search", False, "Find a dealer",
     {"headline": "Toughest Truck, Beats Cybertruck",
      "description": "Indestructible, self-driving and the cheapest EV truck around."}),
]

LIMITS = {
    "social": {"headline": 40, "text": 125},
    "search": {"headline": 30, "description": 90},
    "email": {"subject": 50, "preheader": 90},
}

# ponytail: short copy of the brand guides' section 3.3 lists, only for this self-check.
# The real off-brand checker (step 4) should read the guides themselves.
BANNED = ["revolutionary", "best", "unleash", "never worry", "worry-free", "unlimited", "self-driving",
          "drives itself", "drives you", "fsd", "bulletproof", "indestructible", "zero emissions",
          "cheapest", "range anxiety", "beats", "!!"]
BANNED_BY_BRAND = {"Tesla": [], "Hyundai": ["supercharg", "tesla"], "Chevrolet": ["supercharg", "tesla", "cybertruck"]}


def fill(copy, spec):
    values = {"range": int(spec["range_miles"]), "accel": spec["acceleration_0_60_mph"]}
    return {k: v.format(**values) for k, v in copy.items()}


def check(ad_id, brand, channel, on_brand, copy):
    text = " ".join(copy.values()).lower()
    hits = [w for w in BANNED + BANNED_BY_BRAND[brand] if w in text]
    if not on_brand:
        assert hits, f"{ad_id}: off-brand sample has no banned word"
        return
    assert not hits, f"{ad_id}: banned {hits}"
    for field, limit in LIMITS[channel].items():
        assert len(copy[field]) <= limit, f"{ad_id}: {field} is {len(copy[field])} > {limit}"
    if channel == "email":
        words = len(copy["body"].split())
        assert 120 <= words <= 200, f"{ad_id}: body has {words} words"
    if channel == "email" and "estimated range" in text:
        assert "actual range varies" in text, f"{ad_id}: missing range disclaimer"
    assert text.count("!") <= 1, f"{ad_id}: more than one exclamation mark"


def metrics(rng, channel, on_brand):
    lift = rng.uniform(1.0, 1.4) if on_brand else rng.uniform(0.5, 0.8)
    if channel == "email":
        delivered = rng.randint(40_000, 120_000)
        opens = int(delivered * rng.uniform(0.18, 0.30) * lift)
        clicks = int(opens * rng.uniform(0.08, 0.14) * lift)
        conversions = int(clicks * rng.uniform(0.02, 0.05))
        return {"delivered": delivered, "opens": opens, "open_rate": round(opens / delivered, 4),
                "clicks": clicks, "click_rate": round(clicks / delivered, 4), "conversions": conversions,
                "spend_usd": round(delivered * 0.002, 2)}
    impressions = rng.randint(80_000, 400_000)
    base_ctr = 0.009 if channel == "social" else 0.035
    clicks = int(impressions * base_ctr * rng.uniform(0.8, 1.2) * lift)
    conversions = int(clicks * rng.uniform(0.02, 0.05) * lift)
    spend = impressions / 1000 * 12 if channel == "social" else clicks * 2.5
    return {"impressions": impressions, "clicks": clicks, "ctr": round(clicks / impressions, 4),
            "conversions": conversions, "spend_usd": round(spend, 2)}


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rng = random.Random(5560)
    ads = []
    for i, (ad_id, brand, model, channel, on_brand, cta, copy) in enumerate(ADS):
        spec = con.execute("SELECT * FROM specs WHERE brand = ? AND model = ?", (DB_BRAND[brand], model)).fetchone()
        assert spec, f"{ad_id}: {brand} {model} not in ev.db"
        copy = fill(copy, spec)
        if on_brand and channel != "email" and "estimated range" in " ".join(copy.values()):
            copy["disclaimer"] = "Actual range varies with conditions and driving habits."
        check(ad_id, brand, channel, on_brand, copy)
        ads.append({
            "ad_id": ad_id, "brand": brand, "model": model, "channel": channel,
            "launch_date": f"2026-{1 + i % 10:02d}-{1 + (i * 7) % 28:02d}",
            "copy": copy, "cta": cta, "on_brand": on_brand,
            "approved": on_brand,
            "metrics": metrics(rng, channel, on_brand),
        })
    out = {
        "note": "SYNTHETIC sample data for the APAN 5560 class project. Copy written to the fictional "
                "brand guides; numbers in copy come from ev.db (synthetic); metrics are randomly generated.",
        "ads": ads,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(ads)} ads to {OUT_PATH}")


if __name__ == "__main__":
    main()
