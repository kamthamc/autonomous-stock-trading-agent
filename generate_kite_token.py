import os
import sys
from kiteconnect import KiteConnect

# Try reading from .env manually first
try:
    from dotenv import load_dotenv, set_key, find_dotenv
    load_dotenv()
    env_file = find_dotenv()
    if not env_file:
        with open(".env", "w"): pass
        env_file = ".env"
except ImportError:
    print("Please run: pip install python-dotenv kiteconnect")
    sys.exit(1)

api_key = os.getenv("KITE_API_KEY")
api_secret = os.getenv("KITE_API_SECRET")

print("--- Zerodha Kite Connect Token Generator ---")
print(f"Current API KEY: {api_key}")
if api_secret:
    print(f"Current API SECRET: {'*' * len(api_secret)}")
else:
    print("Current API SECRET: N/A")

if not api_key:
    api_key = input("Enter your Kite API Key: ").strip()
    set_key(env_file, "KITE_API_KEY", api_key)

if not api_secret:
    api_secret = input("Enter your Kite API Secret: ").strip()
    set_key(env_file, "KITE_API_SECRET", api_secret)

kite = KiteConnect(api_key=api_key)

print(f"\n1. Click this link to login: {kite.login_url()}")
print("2. After login, you will be redirected to your redirect URL.")
print("3. Copy the 'request_token' value from the browser address bar.")
print("   (e.g., https://.../?status=success&request_token=THIS_PART_HERE&action=...)")

request_token = input("\nEnter Request Token: ").strip()

try:
    set_key(env_file, "KITE_REQUEST_TOKEN", request_token)
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]
    print(f"\n✅ Success! Access Token Generated.")
    # print(f"Access Token: {access_token}")
    
    set_key(env_file, "KITE_ACCESS_TOKEN", access_token)
    print("✅ updated .env with new access token.")
    
except Exception as e:
    print(f"\n❌ Error during session generation: {e}")
    if "Token is invalid" in str(e):
        print("Tip: The request token expires very quickly. Try generating a new login link and doing it faster.")
