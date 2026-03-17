"""
setup_database.py
─────────────────────────────────────────────
Sets up the complete ATIA Supabase schema and seeds realistic data.
Run once from the project root:  python scripts/setup_database.py
"""

import os, sys, uuid, random, hashlib, json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ─── Load env ────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
REST_URL = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def db_insert(table: str, data):
    """Insert rows via Supabase REST API."""
    r = requests.post(f"{REST_URL}/{table}", headers=HEADERS, json=data)
    if r.status_code not in (200, 201):
        print(f"  ✗ INSERT {table} failed ({r.status_code}): {r.text}")
        raise RuntimeError(f"Insert into {table} failed")
    return r.json()

def db_upsert(table: str, data, on_conflict: str):
    """Upsert rows via Supabase REST API."""
    h = {**HEADERS, "Prefer": "return=representation,resolution=merge-duplicates"}
    # on_conflict is handled by the unique constraint; Supabase REST uses the Prefer header
    r = requests.post(f"{REST_URL}/{table}", headers=h, json=data)
    if r.status_code not in (200, 201):
        print(f"  ✗ UPSERT {table} failed ({r.status_code}): {r.text}")
        raise RuntimeError(f"Upsert into {table} failed")
    return r.json()

# ─── Helpers ─────────────────────────────────────────────────
def uid():
    return str(uuid.uuid4())

def ts(days_ago=0, hours_ago=0):
    """Return an ISO timestamp `days_ago` days before now."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)).isoformat()

def rand_date_between(days_ago_start, days_ago_end):
    """Random timestamp between two day-ago offsets."""
    days = random.uniform(days_ago_end, days_ago_start)
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

# ─── Fixed IDs for referential integrity ─────────────────────
AGENCY_IDS = {
    "talentbridge": uid(),
    "globalhire":   uid(),
    "quickstaff":   uid(),
    "apex":         uid(),
    "freshstart":   uid(),
    "metrojobs":    uid(),
}

print("Agency IDs:")
for name, aid in AGENCY_IDS.items():
    print(f"  {name}: {aid}")

# ─── Step 1: Insert Agencies ────────────────────────────────
print("\n[1/7] Inserting agencies...")
agencies_data = [
    {"id": AGENCY_IDS["talentbridge"], "name": "TalentBridge Recruiters",     "registration_date": ts(days_ago=540), "is_active": True},
    {"id": AGENCY_IDS["globalhire"],   "name": "GlobalHire Solutions",        "registration_date": ts(days_ago=420), "is_active": True},
    {"id": AGENCY_IDS["quickstaff"],   "name": "QuickStaff Pro",              "registration_date": ts(days_ago=300), "is_active": True},
    {"id": AGENCY_IDS["apex"],         "name": "Apex Workforce",              "registration_date": ts(days_ago=365), "is_active": True},
    {"id": AGENCY_IDS["freshstart"],   "name": "FreshStart Agency",           "registration_date": ts(days_ago=25),  "is_active": True},
    {"id": AGENCY_IDS["metrojobs"],    "name": "MetroJobs International",     "registration_date": ts(days_ago=480), "is_active": True},
]
db_upsert("agencies", agencies_data, "id")
print(f"  ✓ {len(agencies_data)} agencies inserted")

# ─── Step 2: Insert Users (reviewers) ───────────────────────
print("\n[2/7] Inserting users...")
users_data = []

# Legitimate long-standing accounts (70 users)
for i in range(70):
    users_data.append({
        "id": uid(),
        "email": f"user_{i+1}@example.com",
        "role": random.choice(["job_seeker", "job_seeker", "job_seeker", "hr_consultant"]),
        "account_age_days": random.randint(60, 900),
    })

# New/suspicious accounts for QuickStaff CHECK-C (30 users)
for i in range(30):
    users_data.append({
        "id": uid(),
        "email": f"newuser_{i+1}@tempmail.com",
        "role": "job_seeker",
        "account_age_days": random.randint(1, 25),
    })

db_upsert("users", users_data, "id")
print(f"  ✓ {len(users_data)} users inserted")

legitimate_users = [u["id"] for u in users_data[:70]]
suspicious_users = [u["id"] for u in users_data[70:]]

# ─── Step 3: Insert Reviews ─────────────────────────────────
print("\n[3/7] Inserting reviews...")
reviews_data = []

def add_reviews(agency_key, count, rating_range, days_range, user_pool, text_templates):
    agency_id = AGENCY_IDS[agency_key]
    for _ in range(count):
        rating = round(random.uniform(*rating_range), 1)
        rating = max(1.0, min(5.0, rating))
        reviews_data.append({
            "id": uid(),
            "agency_id": agency_id,
            "reviewer_id": random.choice(user_pool),
            "rating": float(rating),
            "review_text": random.choice(text_templates),
            "created_at": rand_date_between(*days_range),
        })

# TalentBridge: 92 reviews, high quality, spread over 18 months
talentbridge_texts = [
    "TalentBridge found me a great role within 3 weeks. Recruiter was very professional and responsive throughout the process.",
    "Excellent placement service. They understood my skills and matched me perfectly with the company culture.",
    "Very satisfied with TalentBridge. They negotiated a salary 15% higher than what I expected.",
    "Professional team, kept me updated at every stage. Landed a senior developer role through them.",
    "Good experience overall. The recruiter was knowledgeable about the tech industry and gave solid interview prep.",
    "Outstanding service! They didn't just find me a job, they found me a career path. Highly recommend.",
    "The process was smooth from start to finish. My recruiter Sarah was fantastic — she really advocated for me.",
    "TalentBridge helped me transition from banking to fintech. Great industry knowledge and connections.",
    "Decent experience. Could have communicated more frequently during the interview stages.",
    "Really impressed by their professionalism. They prepared me well and the placement was spot on.",
]
add_reviews("talentbridge", 92, (3.8, 5.0), (540, 0), legitimate_users, talentbridge_texts)

# GlobalHire: 45 reviews, mixed quality
globalhire_texts = [
    "GlobalHire has a wide network. Found me several interview opportunities within a week.",
    "Decent agency but the recruiter changed twice during my search which was a bit frustrating.",
    "Good job matching but follow-up after placement could be better. No check-ins after the first month.",
    "Mixed experience. The initial consultation was great but the roles they sent didn't always match my criteria.",
    "Solid agency for mid-level positions. They have good relationships with employers in the manufacturing sector.",
    "Average experience. They got me interviews but the preparation support was minimal.",
    "Happy with the outcome — got placed at a company I wouldn't have found on my own.",
    "Communication could improve. Sometimes waited days for a response to my emails.",
]
add_reviews("globalhire", 45, (3.0, 4.5), (420, 0), legitimate_users, globalhire_texts)

# QuickStaff: 85 total reviews — 42 old legitimate + 43 suspicious spike in last 14 days (CHECK-A trigger)
quickstaff_old_texts = [
    "QuickStaff helped me find temp work when I needed it. Decent agency for short-term roles.",
    "Average experience. They focus on quantity over quality in job matching.",
    "OK for basic admin and warehouse roles but don't expect much career guidance.",
    "QuickStaff was fine for temp work but I wouldn't use them for permanent placements.",
]
add_reviews("quickstaff", 42, (2.5, 4.0), (300, 15), legitimate_users, quickstaff_old_texts)

# QuickStaff suspicious spike: 43 reviews in last 14 days, suspiciously uniform 5-star, from new accounts
quickstaff_fake_texts = [
    "Amazing agency! Best recruiters ever! Highly recommend to everyone!",
    "5 stars! QuickStaff is the best agency in the country! Perfect service!",
    "Incredible experience! They found me my dream job instantly! 10/10!",
    "Best recruitment agency! Fast, professional, perfect! Cannot recommend enough!",
    "Outstanding! QuickStaff changed my life! Everyone should use them!",
]
for _ in range(43):
    reviews_data.append({
        "id": uid(),
        "agency_id": AGENCY_IDS["quickstaff"],
        "reviewer_id": random.choice(suspicious_users),
        "rating": 5.0,  # Uniform 5-star (CHECK-B trigger)
        "review_text": random.choice(quickstaff_fake_texts),
        "created_at": rand_date_between(13, 0),  # All in last 14 days
    })

# Apex: 58 reviews, declining quality
apex_texts = [
    "Apex was reasonable a year ago but service quality has dropped significantly lately.",
    "My recruiter at Apex seemed overloaded. Responses were slow and the roles didn't match my profile.",
    "Not satisfied. They sent me to an interview without proper briefing on the company or role.",
    "Disappointing experience. The agency seems understaffed and disorganized.",
    "Apex used to be good but I've heard from several friends that quality has declined.",
    "Below average. The recruiter didn't seem to understand my technical skills at all.",
    "OK for entry-level roles but terrible for anything requiring specialized skills.",
    "I had to follow up multiple times for basic updates. Won't use them again.",
    "Mediocre experience overall. They got me an interview but no support during the process.",
]
add_reviews("apex", 58, (1.5, 3.5), (365, 0), legitimate_users, apex_texts)

# FreshStart: only 4 reviews (InsufficientData)
freshstart_texts = [
    "New agency, only had one interaction so far. Seems promising but too early to tell.",
    "FreshStart is brand new. Had a positive initial consultation but no placement yet.",
    "Just started working with FreshStart. The recruiter is enthusiastic and helpful.",
    "Signed up recently. They took the time to understand my career goals which was nice.",
]
add_reviews("freshstart", 4, (3.5, 4.5), (25, 0), legitimate_users[:10], freshstart_texts)

# MetroJobs: 78 reviews, consistently good
metrojobs_texts = [
    "MetroJobs has an excellent team. They're thorough in understanding what you're looking for.",
    "Great experience with MetroJobs. The recruiter was professional, responsive, and well-informed.",
    "Solid agency. They have strong connections in the tech sector. Got me 3 interviews in a week.",
    "Good communication throughout the process. My recruiter gave excellent interview advice.",
    "MetroJobs helped me relocate for work. They handled everything from visa support to relocation tips.",
    "Very professional. They follow up regularly and genuinely care about candidate satisfaction.",
    "Recommended by a colleague and wasn't disappointed. Strong network of employers in the region.",
    "Efficient and professional. They matched me with a role that was exactly what I described.",
    "MetroJobs stands out for their attention to detail. They don't just send your CV everywhere.",
]
add_reviews("metrojobs", 78, (3.5, 5.0), (480, 0), legitimate_users, metrojobs_texts)

# Batch insert reviews (Supabase allows up to 1000 per request)
for i in range(0, len(reviews_data), 200):
    batch = reviews_data[i:i+200]
    db_insert("reviews", batch)
print(f"  ✓ {len(reviews_data)} reviews inserted")

# ─── Step 4: Insert Placements ───────────────────────────────
print("\n[4/7] Inserting placements...")
placements_data = []

def add_placements(agency_key, total, success_rate, source_mix, days_range):
    agency_id = AGENCY_IDS[agency_key]
    for _ in range(total):
        is_success = random.random() < success_rate
        source = "platform_tracked" if random.random() < source_mix else "self_reported"
        placements_data.append({
            "id": uid(),
            "agency_id": agency_id,
            "candidate_id": uid(),
            "outcome": "successful" if is_success else "unsuccessful",
            "placement_source": source,
            "created_at": rand_date_between(*days_range),
        })

add_placements("talentbridge", 48, 0.52, 0.70, (540, 0))  # 52% success, 70% tracked
add_placements("globalhire",   18, 0.28, 0.40, (420, 0))  # 28% success, 40% tracked
add_placements("quickstaff",   22, 0.17, 0.15, (300, 0))  # 17% success, mostly self-reported
add_placements("apex",         30, 0.15, 0.30, (365, 0))  # 15% success, declining
add_placements("freshstart",    2, 0.50, 0.00, (25, 0))   # 2 placements, all self-reported
add_placements("metrojobs",    31, 0.32, 0.55, (480, 0))  # 32% success, mixed source

db_insert("placements", placements_data)
print(f"  ✓ {len(placements_data)} placements inserted")

# ─── Step 5: Insert Feedback Ratings ─────────────────────────
print("\n[5/7] Inserting feedback ratings...")
feedback_data = []

def add_feedback(agency_key, count, score_range, days_range):
    agency_id = AGENCY_IDS[agency_key]
    for _ in range(count):
        score = round(random.uniform(*score_range), 1)
        score = max(1.0, min(5.0, score))
        feedback_data.append({
            "id": uid(),
            "agency_id": agency_id,
            "score": float(score),
            "created_at": rand_date_between(*days_range),
        })

add_feedback("talentbridge", 18, (3.8, 5.0), (540, 0))
add_feedback("globalhire",   12, (3.2, 4.3), (420, 0))
add_feedback("quickstaff",    8, (2.0, 3.5), (300, 0))
add_feedback("apex",         14, (1.5, 3.0), (365, 0))
add_feedback("freshstart",    1, (3.5, 4.0), (25, 0))
add_feedback("metrojobs",    15, (3.3, 4.8), (480, 0))

db_insert("feedback_ratings", feedback_data)
print(f"  ✓ {len(feedback_data)} feedback ratings inserted")

# ─── Step 6: Insert Trust Profiles ───────────────────────────
print("\n[6/7] Inserting trust profiles...")

def build_signal_summary(agency_key):
    agency_id = AGENCY_IDS[agency_key]
    r = [x for x in reviews_data if x["agency_id"] == agency_id]
    p = [x for x in placements_data if x["agency_id"] == agency_id]
    f = [x for x in feedback_data if x["agency_id"] == agency_id]

    now = datetime.now(timezone.utc)
    r30 = [x for x in r if (now - datetime.fromisoformat(x["created_at"])).days <= 30]
    r90 = [x for x in r if (now - datetime.fromisoformat(x["created_at"])).days <= 90]

    total_p = len(p)
    succ_p = len([x for x in p if x["outcome"] == "successful"])
    pr = round(succ_p / total_p, 4) if total_p > 0 else None

    ratings = [x["rating"] for x in r]
    ratings_30d = [x["rating"] for x in r30]
    scores = [x["score"] for x in f]

    # Determine placement source
    tracked = len([x for x in p if x["placement_source"] == "platform_tracked"])
    psource = "platform_tracked" if tracked > total_p / 2 else "self_reported"

    reg_date = [a for a in agencies_data if a["id"] == agency_id][0]["registration_date"]
    tenure = (now - datetime.fromisoformat(reg_date)).days

    return {
        "total_review_count": len(r),
        "reviews_last_30d": len(r30),
        "reviews_last_90d": len(r90),
        "avg_star_rating_all_time": round(sum(ratings)/len(ratings), 2) if ratings else None,
        "avg_star_rating_30d": round(sum(ratings_30d)/len(ratings_30d), 2) if ratings_30d else None,
        "total_placements": total_p,
        "successful_placements": succ_p,
        "placement_rate": pr,
        "placement_source": psource,
        "avg_feedback_score": round(sum(scores)/len(scores), 2) if scores else None,
        "agency_tenure_days": tenure,
        "anomalies_detected": agency_key == "quickstaff",
        "anomaly_count": 2 if agency_key == "quickstaff" else (1 if agency_key == "apex" else 0),
    }

profiles = [
    {
        "id": uid(),
        "agency_id": AGENCY_IDS["talentbridge"],
        "trust_tier": "High",
        "confidence_level": "High",
        "key_strengths": ["Consistently high placement success rate above 50%", "Strong employer feedback scores averaging 4.3+", "Excellent review quality with detailed candidate testimonials"],
        "key_concerns": [],
        "integrity_flags": [],
        "signal_summary": build_signal_summary("talentbridge"),
        "explanation": "TalentBridge Recruiters demonstrates exceptional performance across all measurable signals. With a placement rate above 50% — well above the platform average of 22% — and consistently positive employer feedback, this agency clearly delivers results. The 92 reviews spanning 18 months show a genuine, organic growth pattern with no integrity anomalies detected. High confidence is warranted given the robust data volume.",
        "audience_summaries": {
            "job_seeker": "TalentBridge Recruiters is one of the highest-rated agencies on the platform. They have a strong track record of successfully placing candidates — over half their placements result in a job offer. Reviews from candidates like you are overwhelmingly positive, praising their professionalism and interview preparation support.",
            "hr_consultant": "Your agency is performing solidly in the High tier. Your 52% placement rate is well above the platform average of 22%, and your 4.3+ star rating reflects consistent candidate satisfaction. Employer feedback is strong at 4.3+. To maintain this tier, continue your current approach — the data shows genuine organic growth over 18 months.",
            "admin": "TalentBridge Recruiters — High tier, High confidence. 92 reviews (avg 4.4★), 48 placements (52% rate, 70% platform-tracked), 18 feedback scores (avg 4.3). No integrity flags. Review velocity is organic — steady 5-6 reviews/month with no anomalous spikes. Account age distribution is clean (0% new accounts in recent reviews). Cross-signal consistency is strong: high ratings + high placement rate + positive feedback.",
            "licensing": "TalentBridge Recruiters meets all licensing criteria. Trust Tier: High. Confidence: High. Placement rate: 52% (threshold: ≥20%). Average feedback: 4.3 (threshold: ≥3.5). Review count: 92 (threshold: ≥25). No active integrity flags. Recommendation: PASS for license renewal."
        },
        "previous_tier": "High",
        "tier_change_note": None,
        "evaluated_at": ts(hours_ago=6),
        "evaluation_trigger": "CRON_DAILY",
        "data_window_start": ts(days_ago=540),
        "llm_model_version": "claude-sonnet-4-20250514",
        "data_is_stale": False,
    },
    {
        "id": uid(),
        "agency_id": AGENCY_IDS["globalhire"],
        "trust_tier": "Medium",
        "confidence_level": "Medium",
        "key_strengths": ["Good network coverage in manufacturing sector", "Reasonable placement outcomes with room for growth"],
        "key_concerns": ["Placement rate of 28% below top-tier threshold", "Self-reported placements reduce verification confidence"],
        "integrity_flags": [],
        "signal_summary": build_signal_summary("globalhire"),
        "explanation": "GlobalHire Solutions operates at a solid Medium tier. Their 28% placement rate exceeds the platform average but falls short of the 40% threshold for High tier. Reviews are mixed but generally positive, averaging 3.7 stars. The main concern is that 60% of placements are self-reported, which limits confidence. Employer feedback is decent at 3.7 but not exceptional. No integrity anomalies detected.",
        "audience_summaries": {
            "job_seeker": "GlobalHire Solutions is a mid-range agency with a decent track record. About 1 in 4 candidates they work with gets placed in a role. Reviews are mixed — some candidates praise their wide network while others note communication delays. They're particularly strong in the manufacturing sector.",
            "hr_consultant": "Your agency is performing solidly in the Medium tier. Your 28% placement rate is above the platform average of 22%, and your 3.9-star rating is competitive. To reach High tier: increase placement rate to 40%+ and switch to platform-tracked placements for higher confidence.",
            "admin": "GlobalHire Solutions — Medium tier, Medium confidence. 45 reviews (avg 3.7★), 18 placements (28% rate, 40% tracked), 12 feedback scores (avg 3.7). No integrity flags. Review pattern is organic. Confidence capped at Medium due to review count below 75 threshold and 60% self-reported placements.",
            "licensing": "GlobalHire Solutions meets minimum licensing criteria. Trust Tier: Medium. Confidence: Medium. Placement rate: 28% (threshold: ≥20%). Average feedback: 3.7 (threshold: ≥3.5). Review count: 45 (threshold: ≥25). No active integrity flags. Recommendation: PASS for license renewal."
        },
        "previous_tier": "Medium",
        "tier_change_note": None,
        "evaluated_at": ts(hours_ago=8),
        "evaluation_trigger": "CRON_DAILY",
        "data_window_start": ts(days_ago=420),
        "llm_model_version": "claude-sonnet-4-20250514",
        "data_is_stale": False,
    },
    {
        "id": uid(),
        "agency_id": AGENCY_IDS["quickstaff"],
        "trust_tier": "UnderReview",
        "confidence_level": "Low",
        "key_strengths": [],
        "key_concerns": ["Suspicious review velocity spike detected in last 14 days", "High proportion of reviewers from newly created accounts", "Poor placement rate of 17% — below platform average"],
        "integrity_flags": [
            {
                "flag_id": "CHECK-A",
                "severity": "P0",
                "label": "Review Velocity Anomaly",
                "description": "43 new reviews appeared in the last 14 days, compared to an average of 3 reviews per 14-day period historically. This 14× increase strongly suggests coordinated review activity.",
                "evidence_summary": "daily_avg_14d=3.07 vs baseline_daily_avg_90d=0.22 — ratio=13.9× (threshold: 3×). All 43 recent reviews are 5-star ratings from accounts less than 25 days old.",
                "detected_at": ts(days_ago=4),
                "weight_reduction_pct": 40
            },
            {
                "flag_id": "CHECK-C",
                "severity": "P0",
                "label": "Reviewer Account Age Anomaly",
                "description": "62% of reviewers in the last 14 days have accounts less than 30 days old, strongly suggesting fake or incentivized reviews.",
                "evidence_summary": "pct_new_accounts=0.62 (threshold: ≥0.40). 27 out of 43 recent reviewers have account ages between 1-25 days. Normal baseline is 8% new accounts.",
                "detected_at": ts(days_ago=4),
                "weight_reduction_pct": 40
            }
        ],
        "signal_summary": build_signal_summary("quickstaff"),
        "explanation": "QuickStaff Pro has been placed Under Review due to two critical integrity anomalies. A massive spike of 43 five-star reviews in the last 14 days — 14 times the historical average — from predominantly new accounts (62% under 30 days old) indicates coordinated review manipulation. Their underlying performance is weak: a 17% placement rate (below platform average) and poor employer feedback averaging 2.7. The agency's review signal weight has been reduced by 80% due to dual P0 flags.",
        "audience_summaries": {
            "job_seeker": "QuickStaff Pro is currently under review by our trust and safety team. We've detected unusual activity in their recent reviews that doesn't match their historical pattern. Until this review is complete, we recommend caution. Their actual placement track record shows below-average results.",
            "hr_consultant": "Your agency profile is under review due to detected anomalies in recent review activity. A significant spike of 43 reviews in 14 days, predominantly from new accounts, has triggered our integrity checks. We recommend stopping any review solicitation and contacting support to resolve this.",
            "admin": "QuickStaff Pro — UnderReview tier, Low confidence. 85 reviews (avg 3.8★ inflated by fake reviews), 22 placements (17% rate, 85% self-reported), 8 feedback scores (avg 2.7). TWO P0 FLAGS: CHECK-A (velocity 14× baseline) and CHECK-C (62% new accounts). Review signal weight reduced by 80%. Underlying performance is Low tier without the fake reviews.",
            "licensing": "QuickStaff Pro does NOT meet licensing criteria. Trust Tier: UnderReview. TWO active P0 integrity flags: Review Velocity Anomaly and Reviewer Account Age Anomaly. Placement rate: 17% (below 20% threshold). Average feedback: 2.7 (below 3.5 threshold). Recommendation: FAIL — do not renew license until integrity investigation is complete."
        },
        "previous_tier": "Low",
        "tier_change_note": "Downgraded from Low to UnderReview due to P0 integrity flags on CHECK-A and CHECK-C.",
        "evaluated_at": ts(days_ago=4),
        "evaluation_trigger": "NEW_REVIEW",
        "data_window_start": ts(days_ago=300),
        "llm_model_version": "claude-sonnet-4-20250514",
        "data_is_stale": False,
    },
    {
        "id": uid(),
        "agency_id": AGENCY_IDS["apex"],
        "trust_tier": "Low",
        "confidence_level": "Medium",
        "key_strengths": ["Long operational tenure on the platform"],
        "key_concerns": ["Declining review quality over last 6 months", "Placement rate of 15% well below platform average", "Cross-signal inconsistency between moderate ratings and poor placement outcomes"],
        "integrity_flags": [
            {
                "flag_id": "CHECK-E",
                "severity": "P1",
                "label": "Sentiment-Rating Mismatch",
                "description": "Review text sentiment is frequently negative despite moderate star ratings, suggesting inflated ratings or automatic default ratings by reviewers.",
                "evidence_summary": "mismatch_pct=0.34 (threshold: ≥0.30). 7 out of 20 recent reviews have negative text but 3+ star ratings. Examples: 'Disappointing experience' with 3-star, 'Not satisfied' with 3-star.",
                "detected_at": ts(days_ago=2),
                "weight_reduction_pct": 40
            }
        ],
        "signal_summary": build_signal_summary("apex"),
        "explanation": "Apex Workforce falls into the Low trust tier due to consistently poor performance metrics. Their 15% placement rate is significantly below the platform average of 22%, and their employer feedback score of 2.3 indicates systemic issues with service quality. Reviews show a clear downward trend over the last 6 months, with candidates reporting slow responsiveness and poor job matching. A P1 sentiment-rating mismatch flag suggests some rating inflation.",
        "audience_summaries": {
            "job_seeker": "Apex Workforce has a below-average track record on our platform. Their placement rate is lower than most agencies, and recent reviews suggest declining service quality. We recommend exploring other agencies with stronger performance records for your job search.",
            "hr_consultant": "Your agency is in the Low tier due to a 15% placement rate (below the 20% minimum for Medium) and declining review quality. Employer feedback at 2.3 is concerning. Focus areas: improve candidate-role matching, increase responsiveness, and address the sentiment-rating mismatch flagged in your reviews.",
            "admin": "Apex Workforce — Low tier, Medium confidence. 58 reviews (avg 2.5★), 30 placements (15% rate, 30% tracked), 14 feedback scores (avg 2.3). ONE P1 FLAG: CHECK-E (sentiment-rating mismatch 34%). Clear declining trend. Confidence is Medium (58 reviews, below 75 threshold).",
            "licensing": "Apex Workforce has concerns but may meet minimum licensing criteria conditionally. Trust Tier: Low. Confidence: Medium. Placement rate: 15% (BELOW 20% threshold). Average feedback: 2.3 (BELOW 3.5 threshold). One P1 integrity flag. Recommendation: REVIEW REQUIRED — conditional renewal pending performance improvement plan."
        },
        "previous_tier": "Low",
        "tier_change_note": None,
        "evaluated_at": ts(days_ago=2),
        "evaluation_trigger": "CRON_DAILY",
        "data_window_start": ts(days_ago=365),
        "llm_model_version": "claude-sonnet-4-20250514",
        "data_is_stale": False,
    },
    {
        "id": uid(),
        "agency_id": AGENCY_IDS["freshstart"],
        "trust_tier": "InsufficientData",
        "confidence_level": "N/A",
        "key_strengths": [],
        "key_concerns": [],
        "integrity_flags": [],
        "signal_summary": build_signal_summary("freshstart"),
        "explanation": "FreshStart Agency has insufficient data for a meaningful trust evaluation. With only 4 reviews and 2 placements in 25 days of operation, we cannot establish reliable statistical signals. The agency needs at least 10 reviews and 5 placements before a trust tier can be assigned. Initial indicators are neutral — the few reviews are positive but the sample size is too small to draw conclusions.",
        "audience_summaries": {
            "job_seeker": "FreshStart Agency is new to our platform and doesn't have enough reviews or placement data yet for us to provide a trust rating. This doesn't mean they're bad — they just haven't been around long enough for us to assess. Check back later as more data comes in.",
            "hr_consultant": "Your agency is too new for a trust evaluation. You need at least 10 reviews and 5 placements for an initial assessment. You currently have 4 reviews and 2 placements. Focus on building your track record and encouraging candidates to leave reviews.",
            "admin": "FreshStart Agency — InsufficientData tier, N/A confidence. 4 reviews (avg 4.0★), 2 placements (50% rate but statistically meaningless), 1 feedback score. No integrity flags. Agency registered 25 days ago. Needs 6 more reviews and 3 more placements for minimum evaluation threshold.",
            "licensing": "FreshStart Agency cannot be evaluated for licensing at this time. Trust Tier: InsufficientData. Data volume: 4 reviews (minimum: 10), 2 placements (minimum: 5). Insufficient data for a licensing decision. Recommendation: FAIL — reapply when minimum data thresholds are met."
        },
        "previous_tier": None,
        "tier_change_note": None,
        "evaluated_at": ts(days_ago=1),
        "evaluation_trigger": "ON_DEMAND",
        "data_window_start": ts(days_ago=25),
        "llm_model_version": "claude-sonnet-4-20250514",
        "data_is_stale": False,
    },
    {
        "id": uid(),
        "agency_id": AGENCY_IDS["metrojobs"],
        "trust_tier": "Medium",
        "confidence_level": "High",
        "key_strengths": ["Strong review quality and volume with 78 reviews", "Good employer feedback scores averaging 4.0", "Steady improvement in review quality over last 6 months"],
        "key_concerns": ["Placement rate of 32% is approaching but hasn't reached High threshold", "Mix of platform-tracked and self-reported placements"],
        "integrity_flags": [],
        "signal_summary": build_signal_summary("metrojobs"),
        "explanation": "MetroJobs International is a solid Medium tier agency approaching High tier territory. Their 32% placement rate exceeds the platform average and is trending upward. With 78 reviews showing consistent 4.1 star quality and no integrity concerns, confidence is High. The main gap to High tier is the placement rate — they need to reach 40% with majority platform-tracked placements. Employer feedback at 4.0 meets the High tier threshold.",
        "audience_summaries": {
            "job_seeker": "MetroJobs International is a well-regarded agency with a good placement track record. About 1 in 3 candidates they work with gets placed in a role, which is above the platform average. Reviews from candidates are consistently positive, especially praising their professionalism and industry knowledge.",
            "hr_consultant": "Your agency is performing well in the Medium tier with High confidence — you're close to High tier. Your 32% placement rate is strong (target: 40% for High). Your 4.1-star review average and 4.0 feedback score both meet High tier criteria. Focus on increasing successful placements and using platform tracking to earn the upgrade.",
            "admin": "MetroJobs International — Medium tier, High confidence. 78 reviews (avg 4.1★), 31 placements (32% rate, 55% tracked), 15 feedback scores (avg 4.0). No integrity flags. Clean review pattern over 16 months. Approaching High tier — placement rate is the bottleneck (32% vs 40% threshold). High confidence warranted by 78 reviews.",
            "licensing": "MetroJobs International meets licensing criteria. Trust Tier: Medium. Confidence: High. Placement rate: 32% (threshold: ≥20%). Average feedback: 4.0 (threshold: ≥3.5). Review count: 78 (threshold: ≥25). No active integrity flags. Recommendation: PASS for license renewal."
        },
        "previous_tier": "Medium",
        "tier_change_note": None,
        "evaluated_at": ts(hours_ago=10),
        "evaluation_trigger": "CRON_DAILY",
        "data_window_start": ts(days_ago=480),
        "llm_model_version": "claude-sonnet-4-20250514",
        "data_is_stale": False,
    },
]

for p in profiles:
    db_upsert("trust_profiles", p, "agency_id")
print(f"  ✓ {len(profiles)} trust profiles inserted")

# ─── Step 7: Insert Audit Log Entries ────────────────────────
print("\n[7/7] Inserting audit log entries...")
audit_entries = []

# Create realistic tier history for each agency
tier_histories = {
    "talentbridge": [
        ("Low",       "Low",  365, "ON_DEMAND"),
        ("Medium",    "Medium", 300, "NEW_REVIEW"),
        ("Medium",    "Medium", 240, "CRON_DAILY"),
        ("Medium",    "High",   180, "CRON_DAILY"),
        ("High",      "High",   120, "CRON_DAILY"),
        ("High",      "High",    60, "CRON_DAILY"),
        ("High",      "High",     0, "CRON_DAILY"),
    ],
    "globalhire": [
        ("Low",       "Low",  300, "ON_DEMAND"),
        ("Low",       "Medium", 240, "NEW_REVIEW"),
        ("Medium",    "Medium", 180, "CRON_DAILY"),
        ("Medium",    "Medium", 120, "CRON_DAILY"),
        ("Medium",    "Medium",  60, "CRON_DAILY"),
        ("Medium",    "Medium",   0, "CRON_DAILY"),
    ],
    "quickstaff": [
        ("InsufficientData", "N/A", 200, "ON_DEMAND"),
        ("Low",       "Low",  150, "NEW_REVIEW"),
        ("Low",       "Low",  100, "CRON_DAILY"),
        ("Low",       "Low",   50, "CRON_DAILY"),
        ("UnderReview","Low",    4, "NEW_REVIEW"),
    ],
    "apex": [
        ("Medium",    "Medium", 300, "ON_DEMAND"),
        ("Medium",    "Medium", 240, "CRON_DAILY"),
        ("Medium",    "Low",    180, "CRON_DAILY"),
        ("Low",       "Low",    120, "CRON_DAILY"),
        ("Low",       "Medium",  60, "CRON_DAILY"),
        ("Low",       "Medium",   2, "CRON_DAILY"),
    ],
    "freshstart": [
        ("InsufficientData", "N/A", 1, "ON_DEMAND"),
    ],
    "metrojobs": [
        ("Low",       "Low",  400, "ON_DEMAND"),
        ("Low",       "Low",  350, "NEW_REVIEW"),
        ("Medium",    "Low",  300, "CRON_DAILY"),
        ("Medium",    "Medium",250, "CRON_DAILY"),
        ("Medium",    "Medium",200, "CRON_DAILY"),
        ("Medium",    "Medium",150, "CRON_DAILY"),
        ("Medium",    "High",  100, "CRON_DAILY"),
        ("Medium",    "High",   50, "CRON_DAILY"),
        ("Medium",    "High",    0, "CRON_DAILY"),
    ],
}

for agency_key, history in tier_histories.items():
    agency_id = AGENCY_IDS[agency_key]
    profile_id = [p["id"] for p in profiles if p["agency_id"] == agency_id][0]

    for tier, confidence, days_ago, trigger in history:
        entry = {
            "id": uid(),
            "agency_id": agency_id,
            "trust_profile_id": profile_id,
            "evaluation_trigger": trigger,
            "triggered_by": None,
            "raw_signal_snapshot": {"note": "snapshot at evaluation time"},
            "integrity_checks_log": {},
            "weighted_signals": {},
            "llm_prompt_hash": hashlib.sha256(f"{agency_key}-{days_ago}".encode()).hexdigest()[:16],
            "llm_response_raw": "",
            "final_trust_tier": tier,
            "final_confidence": confidence,
            "override_applied": False,
            "override_by": None,
            "override_reason": None,
            "override_tier": None,
            "created_at": ts(days_ago=days_ago),
        }
        audit_entries.append(entry)

# Add one override entry for testing
audit_entries.append({
    "id": uid(),
    "agency_id": AGENCY_IDS["apex"],
    "trust_profile_id": [p["id"] for p in profiles if p["agency_id"] == AGENCY_IDS["apex"]][0],
    "evaluation_trigger": "OVERRIDE_CHK",
    "triggered_by": "admin-user-001",
    "raw_signal_snapshot": {},
    "integrity_checks_log": {},
    "weighted_signals": {},
    "llm_prompt_hash": "",
    "llm_response_raw": "",
    "final_trust_tier": "Medium",
    "final_confidence": "Low",
    "override_applied": True,
    "override_by": "admin-user-001",
    "override_reason": "Temporary upgrade pending investigation of service quality complaints. Agency has shown willingness to improve.",
    "override_tier": "Medium",
    "created_at": ts(days_ago=90),
})

db_insert("evaluation_audit_log", audit_entries)
print(f"  ✓ {len(audit_entries)} audit log entries inserted")

# ─── Summary ─────────────────────────────────────────────────
print("\n" + "═"*60)
print("✅ ATIA Database Setup Complete!")
print("═"*60)
print(f"  Agencies:          {len(agencies_data)}")
print(f"  Users:             {len(users_data)}")
print(f"  Reviews:           {len(reviews_data)}")
print(f"  Placements:        {len(placements_data)}")
print(f"  Feedback Ratings:  {len(feedback_data)}")
print(f"  Trust Profiles:    {len(profiles)}")
print(f"  Audit Log Entries: {len(audit_entries)}")
print(f"\nTotal records: {len(agencies_data)+len(users_data)+len(reviews_data)+len(placements_data)+len(feedback_data)+len(profiles)+len(audit_entries)}")
