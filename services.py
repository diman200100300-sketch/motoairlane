import asyncio
import logging
import os
import aiohttp
import yt_dlp
from aiohttp import web

logger = logging.getLogger(__name__)

async def get_tiktok_direct_url(video_url: str) -> str:
    """Багатоступеневий метод отримання прямого посилання на відео без водяного знака"""
    # Етап 0: Розгортання коротких посилань vm.tiktok.com / v.tiktok.com
    if "tiktok.com" in video_url:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7'
                }
                async with session.get(video_url, allow_redirects=True, timeout=10, headers=headers) as resp:
                    video_url = str(resp.url)
                    logger.info(f"Розгорнуте фінальне посилання TikTok: {video_url}")
        except Exception as e:
            logger.error(f"Помилка редіректу короткого посилання: {e}")

    # Етап 1: TikWM API
    api_url = f"https://www.tikwm.com/api/?url={video_url}&hd=1"
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.tikwm.com/'
            }
            async with session.get(api_url, timeout=8, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        info = data.get("data", {})
                        direct = info.get("hdplay") or info.get("play")
                        if direct:
                            return direct
    except Exception as e:
        logger.error(f"Етап 1 (TikWM) помилка: {e}")

    # Етап 2: Cobalt API
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"url": video_url, "vQuality": "720"}
            headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            async with session.post("https://co.wuk.sh/api/json", json=payload, headers=headers, timeout=8) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    if res.get("status") in ["redirect", "stream"]:
                        return res.get("url")
    except Exception as e:
        logger.error(f"Етап 2 (Cobalt) помилка: {e}")

    # Етап 3: yt-dlp
    def extract_ytdlp():
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 15,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                return info.get('url')
            except Exception as e:
                logger.error(f"Етап 3 (yt-dlp) внутрішня помилка: {e}")
                return None

    try:
        loop = asyncio.get_running_loop()
        ytdlp_res = await loop.run_in_executor(None, extract_ytdlp)
        if ytdlp_res:
            return ytdlp_res
    except Exception as e:
        logger.error(f"Executor yt-dlp помилка: {e}")

    return None

async def handle_web_ping(request):
    return web.Response(text="ToolBox AI Bot is fully active and running!")

async def web_server_runner():
    try:
        app = web.Application()
        app.router.add_get("/", handle_web_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Вебсервер для Render успішно запущено на порту {port}")
    except Exception as e:
        logger.error(f"Помилка запуску вебсервера: {e}")
