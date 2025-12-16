import multiprocessing

# Network
bind = "0.0.0.0:5000"

# Workers
workers = 2
worker_class = "gthread"
threads = 4

# App loading
preload_app = False

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
capture_output = True

# Set your Django WSGI module here if desired, e.g.:
wsgi_app = "myerpv2.wsgi:application"
