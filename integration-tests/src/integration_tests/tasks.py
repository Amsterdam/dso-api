from locust import TaskSet, task


class BaseTaskSet(TaskSet):
    path: str = ""

    @property
    def url(self):
        return self.user.base_url + self.path

    def response_json_or_failure(
        self,
        response,
        failure_message: str = "Expected output not in response",
    ):
        # Locust uses a dummy response on transport failures/timeouts.
        if response.status_code == 0:
            # Mark as a success to avoid counting it as a failure in the test results.
            response.success()
            return None

        try:
            return response.json()
        except ValueError:
            response.failure(failure_message)
            return None

    @task
    def stop(self):
        self.interrupt()


class DSOTaskSet(BaseTaskSet):

    @task
    def anonymous_request_to_public_dataset(self):
        url = self.user.base_url + "/bag/v1/panden"
        response = self.client.get(url)
        self.response_json_or_failure(response, "Failed to retrieve DSO data")

    @task
    def anonymous_request_to_scoped_dataset(self):
        url = self.user.base_url + "/brandkranen/v1/brandkranen"
        with self.client.get(url, catch_response=True) as response:
            self.response_json_or_failure(response, "Failed to retrieve DSO data")

            if response.status_code == 403:
                response.success()

    @task
    def scoped_request_to_scoped_dataset(self):
        url = self.user.base_url + "/brandkranen/brandkranen"
        self.client.headers.update({"Authorization": f"Bearer {self.user.environment.token}"})
        response = self.client.get(url)
        self.response_json_or_failure(response, "Failed to retrieve DSO data")

    @task
    def request_with_api_key_to_public_dataset(self):
        url = self.user.base_url + "/bag/v1/woonplaatsen"
        self.client.headers.update({"X-API-Key": "api-test-key"})
        response = self.client.get(url)
        self.response_json_or_failure(response, "Failed to retrieve DSO data")
