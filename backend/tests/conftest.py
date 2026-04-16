import os
import pytest
from fastapi.testclient import TestClient

os.environ["OPENAI_API_KEY"] = "mock_key"
