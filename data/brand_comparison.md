# Brand Comparison: Tone, Terms and Key Points

Reference for writing feature cards (`feature_cards.json`) and prompts. Tone comes from the
fictional brand guides (`brand_guidelines_*.md`). Feature terms were checked against the real
owner's manuals in `data/manuals/` by counting how often each term appears (counts across the
brand's three manuals, 2026-11-23). A term not found in a brand's manuals is not used for that brand.

---

## 1. Tone at a Glance

| | Tesla | Hyundai | Chevrolet |
|---|---|---|---|
| Persona | Engineer proud of the product | Knowledgeable friend who owns an EV | Capable neighbor who uses the vehicle for work and weekends |
| Three traits | Direct · Precise · Understated | Clear · Warm · Confident, not loud | Plainspoken · Practical · Upbeat |
| Opens with | The product or what it does | An everyday moment for "you" | A real job or a real trip |
| Sentence style | Short, verb-led, few adjectives | Short, plain words, one idea per sentence | Everyday American English, conversational |
| Humor | Dry, one line at most | None needed | Light, about everyday life |
| Exclamation marks | None in headlines, one per piece | None in headlines, one per piece | None in headlines or subjects, one in body |
| Typical scenes | Commute, road trip with Supercharger stops, job site (Cybertruck) | School run, weekend drive, quiet morning commute | Job site, hardware store run, soccer tournament, lake weekend |
| Calls to action | Order now · Schedule a demo drive · Learn more | Explore IONIQ 5 · Find a dealer · Build yours | Build yours · Find a dealer · See offers |
| Compares against | The reader's current routine | The reader's current routine | The reader's current **gas** vehicle |

---

## 2. Feature Terms by Brand

Use these names in cards and copy. "—" means the brand's manuals have no matching feature:
do not write a card for it and do not borrow another brand's name.

| Feature key | Tesla | Hyundai | Chevrolet |
|---|---|---|---|
| home_charging | Wall Connector, Mobile Connector | Level 2 charging, portable charging cable (ICCB) | Level 2 charging, portable charge cord |
| fast_charging | Supercharger, Supercharging; third-party fast chargers | DC charging; Plug n Charge | DC fast charging, DC charging |
| charging_how_to | charge port, charge port light | charging door, charging connector | charge port |
| scheduled_charging | Scheduled Charging, charge limit | Scheduled Charging, departure time | charge schedule, Target Charge Level |
| regen_braking | regenerative braking, Deceleration Mode | regenerative braking, Smart Regeneration System, i-PEDAL, paddle shifters | One-Pedal Driving, Regen on Demand |
| adaptive_cruise | Traffic-Aware Cruise Control | Smart Cruise Control, Navigation-based Smart Cruise Control | Adaptive Cruise Control |
| steering_assist | Autosteer | Lane Following Assist, Lane Keeping Assist | Lane Keep Assist |
| advanced_driver_assist | Full Self-Driving (Supervised), Auto Lane Change, Navigate on Autosteer | Highway Driving Assist, Lane Change Assist | Super Cruise (hands-free driving assistance on compatible roads) |
| route_planning | Trip Planner | charging station search in navigation | charging station search in navigation |
| preconditioning | Precondition, Scheduled Precondition | Battery Conditioning | preconditioning, battery conditioning |
| mobile_app | Tesla mobile app, phone key | Bluelink, Digital Key | myChevrolet app, OnStar, digital key |
| software_updates | software updates | software updates (over-the-air) | software updates |
| security_camera | Sentry Mode, Dashcam | — | — |
| climate_parked | Keep Climate On, Pet Mode, Camp Mode | Utility Mode | — |
| power_outlets | power outlets (Cybertruck) | V2L (vehicle-to-load) | power outlets, PowerBase |
| towing | Trailer Mode | trailer towing | trailering |
| cargo_space | front trunk (frunk) | front trunk | eTrunk, Midgate (Silverado EV) |
| energy_tips | Energy app, Low Power Mode | energy consumption, distance to empty, ECO drive mode | energy usage, efficiency |
| cabin_climate | climate controls (Auto), seat heaters, heated steering wheel, climate in the Tesla mobile app | Automatic Climate Control System (AUTO), remote start, heated steering wheel | automatic climate control (AUTO), remote start, heated and ventilated seats, heated steering wheel |

Notes from the manuals:
- **Tesla** 2026 manuals never use "Autopilot". Use the three feature names above.
- **Hyundai** uses "hands-free" only for the smart liftgate, never for driving.
- **Chevrolet** uses "hands-free" only together with Super Cruise, limited to "Super Cruise mapped and enabled roads".
- **Hyundai** says V2L use reduces driving range; mention it when V2L appears in copy.
- Many features are "if equipped". Tesla says availability depends on region, hardware and
  software; Hyundai and Chevrolet mark "(if equipped)". Copy says "available".

---

## 3. What Each Brand Leads With

Strengths that show up across the brand's manuals and fit its guide.

### Tesla
- **Charging network built into the car:** Supercharger stops planned by Trip Planner, battery warmed on the way.
- **Car that improves over time:** software updates and the mobile app run much of the ownership experience.
- **Parked features:** Sentry Mode, Camp Mode and Pet Mode have no direct equivalent in the other two brands' manuals.
- **Cybertruck only:** power outlets and towing for work use.

### Hyundai
- **Power out of the car:** V2L runs devices from the battery (camping, outdoor work, power outages).
- **Driver-tunable regeneration:** paddle shifters, Smart Regeneration System and i-PEDAL.
- **Smart Cruise + Highway Driving Assist:** comfortable highway driving with steering help, hands on.
- **Phone as key:** Digital Key and remote control through Bluelink, including Battery Conditioning.

### Chevrolet
- **Super Cruise:** the only brand of the three whose manuals describe hands-free driving assistance (on compatible roads).
- **One-Pedal Driving and Regen on Demand:** simple, physical control over slowing down.
- **Work and home power:** bed and cabin power outlets, PowerBase, Midgate (Silverado EV).
- **Connected services:** OnStar and the myChevrolet app.

---

## 4. Driver Assistance: How Each Brand May Say It

The highest-risk claims in this project. The checker should treat these as rules.

| | Allowed | Required with it | Never |
|---|---|---|---|
| Tesla | Traffic-Aware Cruise Control, Autosteer, Full Self-Driving (Supervised) | "(Supervised)" on first mention of Full Self-Driving; a line that the driver stays attentive; Autosteer is hands-on | Autopilot, FSD, self-driving, autonomous, hands-free, drives itself |
| Hyundai | Smart Cruise Control, Lane Following Assist, Highway Driving Assist | a line that the driver keeps hands on the wheel and stays in control | hands-free (for driving), self-driving, autonomous, autopilot |
| Chevrolet | Adaptive Cruise Control, Lane Keep Assist, Super Cruise hands-free driving assistance | "on compatible roads" with any hands-free mention; "Always pay attention to the road" | self-driving, autonomous, autopilot, hands-free without Super Cruise and compatible roads |

---

## 5. Rules for Feature Cards

1. Use the brand's own term from section 2 in the `title` and `summary`. Never another brand's term
   (no "Supercharger" in a Hyundai or Chevrolet card, no "Autosteer" in a Chevrolet card).
2. Keep the summary neutral and factual. Brand tone is added at the copy step, not in cards.
3. Put brand-specific limits from sections 2 and 4 in `caution`.
4. If a feature is marked "—" for a brand, skip the card.
5. No numbers; 2–4 sentences; no run of 8 or more words copied from the manual (`check_cards.py`).
