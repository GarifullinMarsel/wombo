from time import sleep
from typing import Union

import re
import io

import httpx
from PIL import Image

from wombo.base_models.styles import Style
from wombo.urls import urls, headers_gen, check_headers, auth_key_headers
from wombo.models import CreateTask, CheckTask
from wombo.base_models import BaseDream


class Dream(BaseDream):
    def __init__(self, max_requests_per_token: int = 2, out_msg: str = "") -> None:
        self.client = httpx.Client()
        self.max_requests_per_token = max_requests_per_token
        self.out_msg = out_msg

    def _get_js_filename(self) -> str:
        """
        Gets the name of the JS file from which we extract the Google Key
        """
        response = self.client.get(urls["js_filename"])
        js_filename = re.findall(r"_app-(\w+)", response.text)

        return js_filename[0]

    def _get_google_key(self) -> str:
        """
        Getting Google Key from JS file
        """
        js_filename = self._get_js_filename()

        url = f"https://dream.ai/_next/static/chunks/pages/_app-{js_filename}.js"
        response = self.client.get(url)

        key = re.findall(r'"(AI\w+)"', response.text)
        return key[0]

    def _get_auth_key(self) -> str:
        """
        Get Auth Key from JS file
        """
        if self._counter_calls_auth < self.max_requests_per_token and self._auth_token:
            self._counter_calls_auth += 1
            return self._auth_token

        params = {"key": self._get_google_key()}
        json_data = {"returnSecureToken": True}

        response = self.client.post(
            urls["auth_key"],
            headers=auth_key_headers,
            params=params,
            json=json_data,
            timeout=20,
        )

        result = response.json()
        self._auth_token = result["idToken"]
        self._counter_calls_auth = 0
        return self._auth_token

    # ============================================================================================= #
    def create_task(self, text: str, style: Style) -> CreateTask:
        """
        We set the task to generate an image and use a certain TASK_ID, which we will track
        """
        draw_url = "https://paint.api.wombo.ai/api/v2/tasks"
        auth_key = self._get_auth_key()
        data = (
                '{"is_premium":false,"input_spec":{"prompt":"%s","style":%d,"display_freq":10}}'
                % (text[:200], style.value)
        )

        response = self.client.post(
            url=draw_url, headers=headers_gen(auth_key), data=data, timeout=20
        )
        result_row = response.json()
        result = CreateTask.parse_obj(result_row)
        return result

    def check_task(self, task_id: str, only_bool: bool = False) -> Union[CheckTask, bool]:
        """
        Checks if the image has already been generated by task_id
        """
        img_check_url = f"https://paint.api.wombo.ai/api/v2/tasks/{task_id}"

        response = self.client.get(img_check_url, headers=check_headers, timeout=10)
        result = CheckTask.parse_obj(response.json())
        return bool(result.photo_url_list) if only_bool else result

    def _generate_model_image(
            self,
            text: str,
            style: Style = Style.buliojourney_v2,
            timeout: int = 60,
            check_for: int = 3
    ) -> CheckTask:
        """
        Generate image
        """
        task = self.create_task(text=text, style=style)

        while timeout > 0:
            sleep(check_for)
            timeout -= check_for
            check_task = self.check_task(task.id)

            if check_task.photo_url_list and check_task.state != "generating":
                return check_task
        else:
            TimeoutError(self.out_msg)

    def generate_image(
            self,
            text: str,
            style: Style = Style.buliojourney_v2,
            timeout: int = 60,
            check_for: int = 3
    ) -> io.BytesIO:
        """
        Generate image
        """
        image_url = (self._generate_model_image(
            text, style, timeout, check_for
        )).photo_url_list[-1]

        image = self.client.get(image_url)
        bytes_stream = io.BytesIO()
        bytes_stream.write(image.read())
        return bytes_stream

    def generate_gif(
            self,
            text: str,
            style: Style,
            timeout: int,
            check_for: int
    ) -> io.BytesIO:
        """
        Generate gif
        """
        urls_images = self._generate_model_image(
            text,
            style,
            timeout,
            check_for
        )
        return self.gif(urls_images.photo_url_list)

    def gif(self, url_list: list) -> io.BytesIO:
        """
        Creating a streaming object with gif
        """
        urls = [self.client.get(url) for url in url_list]
        frames = [Image.open(io.BytesIO(url.content)) for url in urls]
        return self.save_frames_as_gif(frames)
