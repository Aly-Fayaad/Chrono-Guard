"""Session-wide test configuration.

The test suite must never depend on the developer's `backend/.env` (which may
point at a production database). Force an isolated configuration *before* the
application packages are imported so `Settings` and the module-level database
engine pick it up.
"""

import os

os.environ["ENV"] = "dev"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
