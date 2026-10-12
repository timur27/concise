# Kept so existing `python widget/server.py ...` commands keep working; the server lives in plainly_server/.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plainly_server.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
