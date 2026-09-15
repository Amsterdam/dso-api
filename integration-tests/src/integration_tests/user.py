import uuid

from locust import HttpUser

from integration_tests import settings
from integration_tests.tasks import DSOTaskSet


class DSOUser(HttpUser):
    host: str = settings.DATAPUNT_API_URL
    base_path: str = "/v1"
    base_url: str = f"{host}{base_path}"

    tasks = {DSOTaskSet}

    def on_start(self):
        self.client.headers = {
            "X-User": "DSO API Integration Tests",
            "X-Correlation-ID": str(uuid.uuid4()),
            "X-Task-Description": "Integration Tests",
            "Content-Type": "application/json",
            #"Authorization": f"Bearer {self.environment.token}",
        }
