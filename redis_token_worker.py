import sys
import os
import json
import time

# Ensure we can import ikea_token.py from the same directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import ikea_token as token_module

def worker():
    import redis
    r = redis.Redis(host='localhost', port=6379, db=0)
    print("Redis token worker started. Listening on 'token_requests' queue...")
    
    while True:
        try:
            # Wait for a request. The queue will contain a request ID
            result = r.blpop('token_requests', timeout=0)
            if result:
                _, req_id = result
                req_id = req_id.decode('utf-8')
                print(f"Received request for token: {req_id}")
                
                try:
                    # Generate token
                    print("Executing get_enterprise_token()...")
                    token_value = token_module.get_enterprise_token()
                    status = 'success'
                except Exception as e:
                    print(f"Error generating token: {e}")
                    token_value = str(e)
                    status = 'error'
                    
                # Publish response back to a specific channel/key for this req_id
                response = json.dumps({'status': status, 'token': token_value})
                r.set(f'token_response:{req_id}', response, ex=120) # Expire in 120s
                print(f"Token generated and stored for {req_id}")
        except Exception as e:
            print(f"Worker encountered a top-level error: {e}")
            time.sleep(5) # Prevent tight loop on Redis connection failure

if __name__ == "__main__":
    worker()
