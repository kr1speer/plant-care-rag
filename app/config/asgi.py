"""Expose the ASGI application using environment-backed Django settings."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.config.settings")
application = get_asgi_application()
