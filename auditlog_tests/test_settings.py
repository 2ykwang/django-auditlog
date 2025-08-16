"""
Settings file for the Auditlog test suite.
"""

import os

DEBUG = True

SECRET_KEY = "test"

# Get test type from environment variable
TEST_TYPE = os.getenv("AUDITLOG_TEST_TYPE", "sqlite")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.messages",
    "django.contrib.sessions",
    "django.contrib.admin",
    "django.contrib.staticfiles",
    "auditlog",
    "test_app",
]

# Add postgres contrib only when using PostgreSQL
if TEST_TYPE == "postgres":
    INSTALLED_APPS.insert(-2, "django.contrib.postgres")

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
]

# Database configuration based on test type
if TEST_TYPE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv(
                "TEST_DB_NAME", "auditlog" + os.environ.get("TOX_PARALLEL_ENV", "")
            ),
            "USER": os.getenv("TEST_DB_USER", "postgres"),
            "PASSWORD": os.getenv("TEST_DB_PASS", ""),
            "HOST": os.getenv("TEST_DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("TEST_DB_PORT", "5432"),
        }
    }
elif TEST_TYPE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv(
                "TEST_DB_NAME", "auditlog_test" + os.environ.get("TOX_PARALLEL_ENV", "")
            ),
            "USER": os.getenv("TEST_DB_USER", "mysqluser"),
            "PASSWORD": os.getenv("TEST_DB_PASS", "mysqlpass"),
            "HOST": os.getenv("TEST_DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("TEST_DB_PORT", "3306"),
            "OPTIONS": {
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:  # Default to SQLite
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(os.path.dirname(__file__), "auditlog_test.db"),
        }
    }

TEMPLATES = [
    {
        "APP_DIRS": True,
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    },
]

STATIC_URL = "/static/"

ROOT_URLCONF = "test_app.urls"

USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
