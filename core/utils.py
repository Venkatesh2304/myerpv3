import os
from django.conf import settings
from urllib.parse import urljoin

def get_media_url(path):
    relative_path = os.path.relpath(path, settings.MEDIA_ROOT)
    media_url = urljoin(settings.MEDIA_URL, relative_path.replace(os.sep, '/'))
    return media_url
