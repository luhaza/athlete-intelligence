"""Load environment variables from a .env file at startup.

Import this module (or call :func:`load_env`) before constructing any
client or database engine so that variables defined in ``.env`` are
available via ``os.environ``.
"""

from dotenv import load_dotenv

load_dotenv()
