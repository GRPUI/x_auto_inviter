import asyncio
from asyncio import gather
from datetime import datetime, UTC
from typing import List

from camoufox import AsyncCamoufox
from loguru import logger
from playwright.async_api import Page

from x_token_login import set_x_token_cookie
from read_files import get_tokens_from_txt, get_users_from_txt
from task_locking.in_redis import DistributedLock, _redis_client


async def safe_click(page: Page, selector):
    try:
        await page.click(selector, timeout=4000)
        return True
    except Exception as e:
        return False


async def get_x_link(
    community: str, token: str, joined_users_key: str
):
    """
    Приглашает пользователей в комьюнити, пропуская уже приглашённых.
    Использует Redis лок для предотвращения одновременной обработки одного пользователя.
    """
    async with AsyncCamoufox(headless=True, humanize=1) as browser:

        logger.debug("Browser instance created")
        page = await browser.new_page()
        logger.debug("Opening x homepage")
        await page.goto("https://x.com")
        logger.debug("Loading cookies")
        await set_x_token_cookie(page, token, domain="x.com")
        await page.goto(community)
        username = await page.evaluate('''
                            () => {
                                const el = document.querySelector('#react-root > div > div > div.css-175oi2r.r-1f2l425.r-13qz1uu.r-417010.r-18u37iz > header > div > div > div > div.css-175oi2r.r-184id4b > div > button > div.css-175oi2r.r-1wbh5a2.r-dnmrzs.r-1ny4l3l > div > div.css-175oi2r.r-1awozwy.r-18u37iz.r-1wbh5a2 > div > div > div > span');
                                return el ? el.textContent : null;
                            }
                        ''')
        if not username:
            return
        await safe_click(page, "button.r-1mnahxq > div:nth-child(1) > span:nth-child(1) > span:nth-child(1)")
        await page.mouse.wheel(0, 1000)
        await safe_click(
            page,
            "#react-root > div > div > div.css-175oi2r.r-1f2l425.r-13qz1uu.r-417010.r-18u37iz > main > div > div > div > div.css-175oi2r.r-kemksi.r-1kqtdi0.r-1ua6aaf.r-th6na.r-1phboty.r-16y2uox.r-184en5c.r-1abdc3e.r-1lg4w6u.r-f8sm7e.r-13qz1uu.r-1ye8kvj > div > div.css-175oi2r.r-f8sm7e.r-13qz1uu.r-1ye8kvj > div > div:nth-child(1) > div:nth-child(2) > div.css-175oi2r.r-17s6mgv.r-kzbkwu.r-3pj75a.r-ttdzmv.r-136ojw6 > div.css-175oi2r.r-18u37iz.r-d21r1u.r-1wtj0ep > div > div > div.css-175oi2r > button"
        )

        await safe_click(page, ".r-ne48ov > div:nth-child(1) > div:nth-child(3) > button:nth-child(1) > div:nth-child(1)")
        await page.keyboard.press("Escape")
        try:

            if username:
                if len(username) < 3:
                    logger.warning(f"Username '{username}' is too short. Seems like it's not real username.")
                    return
                lock = DistributedLock(
                    key=f"user_invite:{username}",
                    ttl=60,
                    skip_if_locked=True,  # Пропускаем если уже кто-то приглашает этого пользователя
                )
                redis = lock.redis
                await redis.sadd(joined_users_key, username.replace("@", ""))
            else:
                logger.warning(
                    f"Failed to retrieve username"
                )
        except Exception as e:
            logger.error(f"Failed to retrieve username: {e}")


async def add_to_mod(
    community: str, token: str, users_to_add: List[str]
):
    """
    Приглашает пользователей в комьюнити, пропуская уже приглашённых.
    Использует Redis лок для предотвращения одновременной обработки одного пользователя.
    """
    async with (AsyncCamoufox(headless=True, humanize=1) as browser):

        logger.debug("Browser instance created")
        page = await browser.new_page()
        logger.debug("Opening x homepage")
        await page.goto("https://x.com")
        logger.debug("Loading cookies")
        await set_x_token_cookie(page, token, domain="x.com")
        await page.goto(community + "members" if community.endswith("/") else community + "/members")
        await page.wait_for_load_state("networkidle")
        for user in users_to_add:
            await safe_click(page, "div.r-5oul0u:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2)")
            await page.click(
                "div.r-5oul0u:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2)",
                click_count=2)
            for letter in user:
                await page.type("div.r-5oul0u:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > input:nth-child(1)", text=letter)
            for _ in range(5):
                await safe_click(page, "div.r-1h0z5md:nth-child(2) > button:nth-child(1) > div:nth-child(1) > div:nth-child(1) > svg:nth-child(2)")
                text_on_button = await page.evaluate('''
                    () => {
                        const el = document.querySelector('.r-j2cz3j > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > span:nth-child(1)');
                        return el ? el.textContent : null;
                    }
                ''')
                await page.wait_for_timeout(100)
                if text_on_button == "Add to mod team":
                    await safe_click(page, ".r-j2cz3j > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1)")
                    await safe_click(page, "button.r-6gpygo:nth-child(1)")
                    break
                elif text_on_button is None:
                    button_result = await safe_click(page, "button.r-6gpygo:nth-child(1)")
                    if button_result:
                        break
                elif text_on_button == 'Remove from mod team':
                    break
            await page.keyboard.press("Escape")
            await safe_click(page, "div.r-5oul0u:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2)")
            await safe_click(page, "button.r-1yadl64")

async def worker(
    worker_id: int,
    token_queue: asyncio.Queue,
    community: str,
    joined_users_key: str,
):
    """Воркер, который обрабатывает токены из очереди"""
    while True:
        try:
            index, token = await token_queue.get()
            if token is None:  # Сигнал завершения
                token_queue.task_done()
                break

            logger.info(f"[Worker {worker_id}] Starting invites for token {index}")
            try:
                await get_x_link(
                    community=community,
                    token=token,
                    joined_users_key=joined_users_key,
                )
                logger.info(f"[Worker {worker_id}] Completed token {index}")
            except Exception as e:
                logger.error(
                    f"[Worker {worker_id}] Error processing token {index}: {e}"
                )
            finally:
                token_queue.task_done()
        except Exception as e:
            logger.error(f"[Worker {worker_id}] Unexpected error: {e}")
            token_queue.task_done()


async def main_cli(
    tokens_file: str,
    workers: int,
    admin_token: str ,
    community: str = "https://x.com/i/communities/1996945882479026553/",
    redis_url: str = "redis://localhost:6379"
):
    # Инициализируем Redis
    try:
        await DistributedLock.init_redis(redis_url=redis_url)
        logger.info(f"Connected to Redis at {redis_url}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    try:
        tokens = get_tokens_from_txt(tokens_file)
        total_tokens = len(tokens)

        logger.info(f"Loaded {total_tokens} tokens")
        logger.info(f"Starting {workers} workers")

        # Ключ для хранения приглашённых пользователей в Redis
        joined_users_key = f"joined_users:{community}:{datetime.timestamp(datetime.now(UTC))}"

        # Создаем очередь токенов
        token_queue = asyncio.Queue()
        for index, token in enumerate(tokens, start=1):
            await token_queue.put((index, token))

        # Добавляем сигналы завершения для каждого воркера
        for _ in range(workers):
            await token_queue.put((None, None))

        # Создаем воркеры
        worker_tasks = [
            worker(i, token_queue, community, joined_users_key)
            for i in range(workers)
        ]

        # Запускаем воркеры и ждем завершения очереди
        await asyncio.gather(*worker_tasks)
        logger.info("All workers completed")

        # Выводим статистику
        redis = _redis_client.get()
        if redis:
            get_users = await redis.smembers(joined_users_key)
            await add_to_mod(community, admin_token, list(get_users))
            joined_count = await redis.scard(joined_users_key)
            logger.info(f"Total users joined: {joined_count}/{len(tokens)}")

    finally:
        # Закрываем Redis соединение
        await DistributedLock.close_redis()
        logger.info("Redis connection closed")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Invite users to an X community using a list of tokens and usernames."
    )
    parser.add_argument(
        "-t",
        "--tokens",
        required=True,
        help="Path to a text file with tokens (one per line).",
    )
    parser.add_argument(
        "-a",
        "--admin-token",
        required=True,
        help="Admin token for setting up the browser and inviting users."
    )
    parser.add_argument(
        "-c",
        "--community",
        default="https://x.com/i/communities/1996945882479026553/",
        help="Community URL.",
    )
    parser.add_argument(
        "-w", "--workers", default=3, type=int, help="Number of parallel workers."
    )
    parser.add_argument(
        "-r",
        "--redis",
        default="redis://localhost:6379",
        help="Redis URL (default: redis://localhost:6379).",
    )
    args = parser.parse_args()
    try:
        asyncio.run(
            main_cli(args.tokens, args.workers, args.admin_token, args.community, args.redis)
        )
        logger.info("Script completed successfully")
    except KeyboardInterrupt:
        logger.warning("Script interrupted by user")
    except Exception as e:
        logger.error(f"Script failed: {e}")
