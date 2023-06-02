import httpx
import asyncio
import re
from PIL import Image
import io
import typing

from wombo.urls import urls, auth_key_headers, headers_gen, check_headers
from wombo.models import CreateTask, CheckTask


class AsyncDream:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient()

    async def _get_js_filename(self) -> str:
        ''' Get name JS file, from extract Google Key '''

        response = await self.client.get(urls['js_filename'])
        js_filename = re.findall(r'_app-(\w+)', response.text)
		
        return js_filename[0]
    
    async def _get_google_key(self) -> str:
        ''' Get Google Key from JS file '''
        js_filename = await self._get_js_filename()
		
        url = f"https://dream.ai/_next/static/chunks/pages/_app-{js_filename}.js"
        response = await self.client.get(url)

        key = re.findall(r'"(AI\w+)"', response.text)
        return key[0]
    
    async def _get_auth_key(self) -> str:
        ''' Get Auth Key from JS file '''
        params = {'key': await self._get_google_key()}
        json_data = {'returnSecureToken': True}

        response = await self.client.post(urls["auth_key"],
				headers=auth_key_headers,
				params=params,
				json=json_data,
				timeout=20
			)
        
        result = response.json()
        return result['idToken']
    
    
    # ============================================================================================= # 
    async def create_task(self, text: str, style: int = 84) -> CreateTask:
        ''' We set the task to generate an image and use a certain TASK_ID, which we will track'''
        draw_url = "https://paint.api.wombo.ai/api/v2/tasks"
        auth_key = await self._get_auth_key()
        data = '{"is_premium":false,"input_spec":{"prompt":"%s","style":%d,"display_freq":10}}' % (text[:200], style)

        response = await self.client.post(draw_url,
				headers=headers_gen(auth_key),
				data=data.encode(),
				timeout=20
			)
        result = response.json()
        result = CreateTask.parse_obj(result)
        return result
    
    async def check_task(self, task_id: str, only_bool: bool=True) -> typing.Union[CheckTask, bool]:
        ''' Checks if the image has already been generated by task_id '''
        img_check_url = f"https://paint.api.wombo.ai/api/v2/tasks/{task_id}"

        response = await self.client.get(img_check_url, headers=check_headers, timeout=10)
        result = response.json()

        result = CheckTask.parse_obj(result)
        if only_bool:
            if result.photo_url_list:
                return True
            else:
                return False
        return result
    
    async def generate(self, text: str, style: int = 84, gif: bool = False):
        """Generate image"""
        task = await self.create_task(text=text, style=style)
        await asyncio.sleep(2)
        for _ in range(10):
            task = await self.check_task(task_id=task.id, only_bool=False)
            if task.photo_url_list and task.state != "generating":
                if gif:
                    res = await self.gif(task.photo_url_list)
                else:
                    res = task
                break
            await asyncio.sleep(2)
        return res

    # ============================================================================================= # 
    def gif_creating(self, frames: list, duration: int = 400) -> io.BytesIO:
        result = io.BytesIO()
        frames[0].save(
            result,
            save_all=True,
            append_images=frames[1:],  # Срез который игнорирует первый кадр.
            format='GIF',
            duration=duration, 
            loop=1
        )
        return result
    
    async def gif(self, url_list: list, thread: bool = True) -> io.BytesIO:
        """ Creating a streaming object with gif """
        tasks = [self.client.get(url) for url in url_list]
        res = await asyncio.gather(*tasks)
        frames= [Image.open(io.BytesIO(url.content)) for url in res]
        if thread:
            result = await asyncio.to_thread(self.gif_creating, (frames))
        else:
            result = self.gif_creating(frames)
        return result



    
async def main():
    dream = AsyncDream()
    task = await dream.generate("Anime waifu in bikini")
    print(task)
    # frames = await dream.get_stage_task(task)


if __name__ == "__main__":  
    asyncio.run(main())

	    