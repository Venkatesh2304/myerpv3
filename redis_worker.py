import redis
import json
import traceback
import time
import os

from ikea_token import get_enterprise_token
from orderpage import UnileverLogin, MicrosoftNotLoggedIn

def process_ikea_token(req_id):
    """Processes a request for an IKEA Enterprise Recaptcha token."""
    print(f"[IKEA Worker] Generating token for req_id: {req_id}")
    try:
        token = get_enterprise_token()
        if "Error" in token:
            return {"error": token}
        return {"token": token}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

def process_unilever_cookies(req_id, username, password):
    """Processes a request for SAP cookies via Selenium. Will only do fast-path SAP login."""
    print(f"[Unilever Worker] Generating cookies for req_id: {req_id}")
    try:
        # We enforce fast-path: only SAP, no interactive SSO OTPs allowed on the server worker
        with UnileverLogin(headless=True, sap_user=username, sap_pass=password) as bot:
            try:
                print("Attempting SAP login (Background)...")
                cookies = bot.get_sap_cookies()
                return {"cookies": cookies}
                
            except MicrosoftNotLoggedIn as e:
                # We cannot solve MS interactive SSO from a background worker safely without human input.
                return {"error": "Microsoft SSO intercept detected. Full interactive login required."}
                
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}

def start_worker():
    print("Starting Unified Redis Worker...")
    r = redis.Redis(host='localhost', port=6379, db=0)
    
    # We listen to two queues using blocking pop (blpop)
    queues = ['token_requests', 'unilever_requests']
    
    print(f"Worker is listening on queues: {queues}")
    
    while True:
        try:
            # Block until a message arrives on either queue
            queue_name, message = r.blpop(queues)
            queue_name = queue_name.decode('utf-8')
            
            print(f"\n--- Received job from {queue_name} ---")
            
            if queue_name == 'token_requests':
                req_id = message.decode('utf-8')
                result = process_ikea_token(req_id)
                
                # Send the response back using the req_id to route it
                # Set a TTL of 60 seconds so old responses don't clutter Redis
                r.setex(f'token_response:{req_id}', 60, json.dumps(result))
                print(f"[IKEA Worker] Replied to req_id: {req_id}")
                
            elif queue_name == 'unilever_requests':
                # Unilever queue sends JSON dicts because we need additional data (username/pass)
                payload = json.loads(message.decode('utf-8'))
                req_id = payload.get('req_id')
                username = payload.get('username')
                password = payload.get('password')
                
                result = process_unilever_cookies(req_id, username, password)
                
                # Route it back to the Uniliver session
                r.setex(f'unilever_response:{req_id}', 300, json.dumps(result))
                print(f"[Unilever Worker] Replied to req_id: {req_id}")
                
        except Exception as e:
            print(f"Worker crashed on a job: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    start_worker()
