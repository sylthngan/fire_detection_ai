
import requests


class DetectionAPIClient:
    def __init__(
        self,
        base_url="http://127.0.0.1:8000",
        timeout=2
    ):
        self.endpoint = (
            base_url.rstrip("/") + "/api/detections"
        )
        self.timeout = timeout

    def send_detection(self, detection):
        payload = detection.to_dict()

        # image_path hiện là đường dẫn file cục bộ.
        # Không gửi trường này nếu Backend chưa hỗ trợ.
        payload.pop("image_path", None)

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout
            )

            response.raise_for_status()

            print(
                f"[API] Detection sent: "
                f"{response.status_code}"
            )

            return True

        except requests.RequestException as error:
            print(f"[API] Send failed: {error}")
            return False
