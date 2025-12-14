from myerpv2 import settings
from sqlalchemy import create_engine
from django.db import connection


engine = create_engine(
    f"postgresql+psycopg2://{settings.DATABASES['default']['USER']}:{settings.DATABASES['default']['PASSWORD']}@"
    f"{settings.DATABASES['default']['HOST']}:{settings.DATABASES['default']['PORT']}/"
    f"{settings.DATABASES['default']['NAME']}"
, echo = False)


# def get_django_connection():
#     return connection.connection

# engine = create_engine(
#     "postgresql+psycopg2://",  # DSN ignored because creator= overrides it
#     creator=get_django_connection,
#     poolclass=None,
# )