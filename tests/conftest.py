"""Test session setup.

The network engine fixes its storage root when it is first imported. Without a models root in the
environment the tests give it a throwaway one, so a test run never writes into the installed package or
into a real models root it was not pointed at.
"""

from __future__ import annotations

import os
import tempfile

if not os.environ.get("CONECTOMA_MODELS_ROOT"):
    os.environ["CONECTOMA_MODELS_ROOT"] = tempfile.mkdtemp(prefix="conectoma-models-")
