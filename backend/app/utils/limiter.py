# backend/app/utils/limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

# WHY module-level singleton: both main.py (middleware registration) and
# routes.py (decorator) must reference the exact same Limiter instance.
# Creating it here avoids circular imports and ensures one shared counter store.
limiter = Limiter(key_func=get_remote_address)
