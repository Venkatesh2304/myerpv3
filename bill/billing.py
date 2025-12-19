from report.models import BeatReport
from django.db import close_old_connections,connections
from report.models import SalesRegisterReport
from report.models import EmptyArgs
import datetime
import os
from collections import defaultdict
import threading
import time
import traceback 
from PyPDF2 import PdfMerger
from django.http import JsonResponse
import pandas as pd
from enum import Enum, IntEnum

from custom.classes import Billing, Einvoice
from django.db.models import F,F
from rest_framework.decorators import api_view
import hashlib
from django.http import JsonResponse
from . import models
import report.models as report_models
import erp.models as erp_models

#TODO : ENUMS   
class BillingStatus(IntEnum) :
    NotStarted = 0
    Success = 1
    Started = 2
    Failed = 3
