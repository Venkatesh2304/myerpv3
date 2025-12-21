import datetime
import requests
from urllib.parse import urljoin
import time
import json
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dateutil import parser

# Setup Logger
log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'scheduler')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'scheduler.log')

logger = logging.getLogger('scheduler')
logger.setLevel(logging.INFO)

# Check if handler already exists to avoid duplicate logs if script is reloaded (though less likely in this script structure)
if not logger.handlers:
    handler = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=7)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Also log to console for immediate feedback during development/running
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


COMPANIES = ["devaki_hul","lakme_rural","lakme_urban"]
class BaseSession(requests.Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = "http://127.0.0.1:8080/"
        self.username = f"auto"
        self.password = "1"
        self.login()

    def request(self, method, url, *args, **kwargs):
        # If url is relative (doesn't start with http), join it with base_url
        if self.base_url and not url.startswith(('http://', 'https://')):
            url = urljoin(self.base_url, url)
        res = super().request(method, url, *args, **kwargs)
        return res

    def login(self):
        if self.username and self.password:
            self.post("/login", data={"username": self.username, "password": self.password})
            for cookie in self.cookies:
                cookie.secure = False

def load_config(filename):
    config_path = os.path.join(os.path.dirname(__file__), filename)
    with open(config_path, 'r') as f:
        return json.load(f)

def billing(company):
    logger.info(f"Running job for {company} at {datetime.datetime.now()}")    
    time.sleep(2)
    return 
    try:
        s = BaseSession()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        logger.info(f"Fetching orders for {company} on {today_str}")
        
        get_order_payload = {
            "company": company,
            "order_date": today_str
        }
        
        response = s.post("/get_order/", json=get_order_payload)
        if response.status_code != 200:
            logger.error(f"Error fetching orders: {response.text}")
            return

        data = response.json()
        orders = data.get("orders")
        data_hash = data.get("hash")
        
        if not orders:
            logger.info("No orders found.")
            return

        # 2. Filter orders to post
        orders_to_post = [order['order_no'] for order in orders if order.get('allow_order')]
        
        if not orders_to_post:
            logger.info("No orders to post (allow_order=True).")
            return
            
        logger.info(f"Posting {len(orders_to_post)} orders: {orders_to_post}")

        # 3. Post Orders
        post_order_payload = {
            "company": company,
            "hash": data_hash,
            "order_date": today_str,
            "order_numbers": orders_to_post,
            "delete_orders": [] # Assuming no delete orders for now
        }
        
        post_response = s.post("/post_order/", json=post_order_payload)
        
        if post_response.status_code == 200:
            logger.info("Orders posted successfully.")
            logger.info(post_response.json())
        else:
            logger.error(f"Error posting orders: {post_response.text}")
    except Exception as e:
        logger.error(f"Error posting orders: {e}")

def sync_daily():
    reports = ["party", "beat", "bill_ageing", "outstanding", "salesregister", "collection"]
    reports_str = ",".join(reports)
    
    for company in COMPANIES:
        logger.info(f"Syncing reports for {company}")
        try:
            s = BaseSession()
            response = s.get("/sync_reports/", params={"company": company, "reports": reports_str})
            logger.info(f"Sync result for {company}: {response.json()}")
        except Exception as e:
            logger.error(f"Error syncing {company}: {e}")

def main():
    scheduler = BlockingScheduler()

    # Billing Jobs    
    billing_config = load_config("billing_config.json")
    for company, times in billing_config.items():
        for t in times:
            try:
                time_obj = parser.parse(t)
                scheduler.add_job(
                    billing,
                    trigger=CronTrigger(hour=time_obj.hour, minute=time_obj.minute, second=time_obj.second),
                    args=[company],
                    name=f"{company}_{t}"
                )
            except Exception as e:
                logger.error(f"Error scheduling {company} at {t}: {e}")

    # Schedule Daily Sync at 23:30
    scheduler.add_job(
        sync_daily,
        trigger=CronTrigger(hour=12, minute=35,second=0),
        name="daily_sync"
    )

    logger.info("Starting scheduler...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()

