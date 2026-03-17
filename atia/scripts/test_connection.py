"""Test Supabase connection with both key formats."""
import os, requests, jwt, time
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
url = os.environ["SUPABASE_URL"]
sb_key = os.environ["SUPABASE_KEY"]
jwt_secret = "50f9136c-ca53-4451-9050-4626cc2bf5b2"

# Generate service_role JWT
payload = {
    "role": "service_role",
    "iss": "supabase",
    "iat": int(time.time()),
    "exp": int(time.time()) + 60*60*24*365*10
}
jwt_token = jwt.encode(payload, jwt_secret, algorithm="HS256")

# Generate anon JWT
anon_payload = {
    "role": "anon",
    "iss": "supabase",
    "iat": int(time.time()),
    "exp": int(time.time()) + 60*60*24*365*10
}
anon_token = jwt.encode(anon_payload, jwt_secret, algorithm="HS256")

print(f"JWT service_role token: {jwt_token[:40]}...")
print(f"JWT anon token: {anon_token[:40]}...")

# Test 1: sb_secret key — GET
print("\n--- Test 1: sb_secret key (GET) ---")
r = requests.get(f"{url}/rest/v1/agencies?select=id,name&limit=1",
    headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"})
print(f"  Status: {r.status_code} | Body: {r.text[:200]}")

# Test 2: sb_secret key — POST
print("\n--- Test 2: sb_secret key (POST) ---")
r = requests.post(f"{url}/rest/v1/agencies",
    headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}",
             "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"},
    json=[{"id": "a0000000-0000-0000-0000-000000000001", "name": "Test", "is_active": True}])
print(f"  Status: {r.status_code} | Body: {r.text[:200]}")

# Test 3: JWT service_role key — GET
print("\n--- Test 3: JWT service_role (GET) ---")
r = requests.get(f"{url}/rest/v1/agencies?select=id,name&limit=1",
    headers={"apikey": jwt_token, "Authorization": f"Bearer {jwt_token}"})
print(f"  Status: {r.status_code} | Body: {r.text[:200]}")

# Test 4: JWT service_role key — POST
print("\n--- Test 4: JWT service_role (POST) ---")
r = requests.post(f"{url}/rest/v1/agencies",
    headers={"apikey": jwt_token, "Authorization": f"Bearer {jwt_token}",
             "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"},
    json=[{"id": "a0000000-0000-0000-0000-000000000001", "name": "Test", "is_active": True}])
print(f"  Status: {r.status_code} | Body: {r.text[:200]}")

# Test 5: Mixed — sb_secret as apikey, JWT as bearer
print("\n--- Test 5: Mixed (sb_secret apikey + JWT bearer) ---")
r = requests.post(f"{url}/rest/v1/agencies",
    headers={"apikey": sb_key, "Authorization": f"Bearer {jwt_token}",
             "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"},
    json=[{"id": "a0000000-0000-0000-0000-000000000001", "name": "Test", "is_active": True}])
print(f"  Status: {r.status_code} | Body: {r.text[:200]}")

# Test 6: Anon key
print("\n--- Test 6: Anon JWT (POST) ---")
r = requests.post(f"{url}/rest/v1/agencies",
    headers={"apikey": anon_token, "Authorization": f"Bearer {anon_token}",
             "Content-Type": "application/json", "Prefer": "return=representation,resolution=merge-duplicates"},
    json=[{"id": "a0000000-0000-0000-0000-000000000001", "name": "Test", "is_active": True}])
print(f"  Status: {r.status_code} | Body: {r.text[:200]}")

# Clean up test row if any succeeded
print("\n--- Cleanup ---")
r = requests.delete(f"{url}/rest/v1/agencies?id=eq.a0000000-0000-0000-0000-000000000001",
    headers={"apikey": jwt_token, "Authorization": f"Bearer {jwt_token}"})
print(f"  Cleanup status: {r.status_code}")
