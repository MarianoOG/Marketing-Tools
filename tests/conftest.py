"""Point the backend at a throwaway data folder before anything imports it."""

import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="marketing-tools-test-")
