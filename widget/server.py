# Kept so existing `python widget/server.py ...` commands keep working; the server lives in concise_server/.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from concise_server.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
