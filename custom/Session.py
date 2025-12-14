from abc import ABC, abstractmethod
import os
import re
from io import BytesIO
import json
from logging import Handler
from logging.handlers import TimedRotatingFileHandler
from typing import Generic, TypeVar
from urllib.parse import urljoin, urlparse
import requests
import curlify
import logging
from requests.models import Response
from uuid import uuid1
import toml
import shutil
import urllib3
from core.models import UserSession
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class StatusCodeError(Exception):
    pass

class Session(requests.Session, ABC):

    ## Default attributes
    logging_enabled = True
    base_url:str = ""
    load_cookies = False
    force_base_url = False
    key: str
    user:UserSession
    username:str
    password:str
    config:dict[str,str]
    

    def __init__(self,user:str):
        super().__init__()
        self.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36"
            }
        )

        # Logging setup
        self.user = UserSession.objects.get(user=user,key=self.key)
        self.username = self.user.username
        self.password = self.user.password
        self.config = self.user.config
        
        # Logging setup
        self.logger = logging.getLogger(f"{self.key}.{self.username}")
        self.logger.setLevel(logging.DEBUG)
        
        if self.logging_enabled and not self.logger.handlers:
            log_dir = f"logs/{self.key}/{user}"
            os.makedirs(log_dir, exist_ok=True)
            
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            
            # Info Handler
            info_handler = TimedRotatingFileHandler(
                f"{log_dir}/info.log", 
                when='W0', 
                interval=1, 
                backupCount=4
            )
            info_handler.setLevel(logging.INFO)
            info_handler.setFormatter(formatter)
            self.logger.addHandler(info_handler)
            
            # Debug Handler
            debug_handler = TimedRotatingFileHandler(
                f"{log_dir}/debug.log", 
                when='W0', 
                interval=1, 
                backupCount=4
            )
            debug_handler.setLevel(logging.DEBUG)
            debug_handler.setFormatter(formatter)
            self.logger.addHandler(debug_handler)
        
        if self.load_cookies and self.user.cookies : 
            for cookie in self.user.cookies : 
                self.cookies.set(cookie["name"],cookie["value"],domain=cookie["domain"],path=cookie["path"])

    def request(self, method, url, *args, **kwargs):
        url = urljoin(self.base_url, url)
        res = super().request(method, url, *args, **kwargs)
        if res.status_code in [200, 302, 304]:
            return res
        raise StatusCodeError(
            f"""
                    The request recieved response : {res.status_code}
                    curl : {curlify.to_curl(res.request)}
                    body : {res.request.body}
                    cookies : {self.cookies}
                    """
        )

    def get_buffer(self, url: str) -> BytesIO:
        return BytesIO(self.get(url).content)

    def send(self, request, *args, **kwargs) -> Response:
        ## Middleware overriding the default send function to capture it in logs
        if self.force_base_url : 
            if self.base_url not in request.url : 
                request.url = self.base_url + request.url.split(".com")[1]
        
        self.logger.debug(f"Sending {request.method} request to {request.url}")
        response = super().send(request, *args, **(kwargs | {"verify":False,"timeout":1200}))
        self.logger.debug(f"Received response from {response.url}: Status {response.status_code} | Time: {response.elapsed.total_seconds():.2f}s")
        return response

    def log_dataframe_metadata(self, df, msg=""):
        """Logs metadata about a DataFrame (shape, columns) to debug log."""
        if df is None:
            self.logger.debug(f"{msg} | DataFrame is None")
        else:
            try:
                self.logger.debug(f"{msg} | Shape: {df.shape} | Columns: {list(df.columns)}")
            except Exception as e:
                self.logger.error(f"Failed to log dataframe metadata: {e}")
