import asyncio
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
    users_to_invite: List[str], community: str, token: str, invited_users_key: str
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
        await safe_click(page, "button.r-1mnahxq > div:nth-child(1)") # пробуем нажать "Got it" после добавления в модераторы
        await page.mouse.wheel(0, 1000)
        await page.click(
            "button.r-1wron08:nth-child(2) > div:nth-child(1) > svg:nth-child(1)"
        )
        await page.click(
            "#layers > div.css-175oi2r.r-zchlnj.r-1d2f490.r-u8s1d.r-ipm5af.r-1p0dtai.r-105ug2t > div > div > div > div.css-175oi2r.r-1ny4l3l > div > div.css-175oi2r.r-j2cz3j.r-kemksi.r-1q9bdsx.r-qo02w8.r-1udh08x.r-u8s1d > div > div > div > a > div.css-175oi2r.r-16y2uox.r-1wbh5a2 > div > span"
        )

        for user in users_to_invite:
            # Используем Redis лок для предотвращения одновременной обработки одного пользователя
            lock = DistributedLock(
                key=f"user_invite:{user}",
                ttl=60,
                skip_if_locked=True,  # Пропускаем если уже кто-то приглашает этого пользователя
            )

            async with lock:
                if not lock.acquired:
                    logger.debug(
                        f"User {user} is being invited by another worker, skipping"
                    )
                    continue

                # Проверяем, был ли уже приглашён этот пользователь
                redis = lock.redis
                if await redis.sismember(invited_users_key, user):
                    logger.debug(f"User {user} already invited, skipping")
                    continue

                try:
                    await page.type(
                        ".r-vhj8yc > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > input:nth-child(1)",
                        user,
                    )
                    button_one, button_two = await asyncio.gather(
                        safe_click(
                            page,
                            "#typeaheadDropdown-3 > div:nth-child(2) > div:nth-child(1) > button:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > button:nth-child(2) > div:nth-child(1) > span:nth-child(1) > span:nth-child(1)",
                        ),
                        safe_click(
                            page, "button.r-15ysp7h:nth-child(2) > div:nth-child(1)"
                        ),
                    )
                    if button_one or button_two:
                        logger.success(f"Successfully invited user: {user}")
                        await redis.sadd(invited_users_key, user)
                    else:
                        logger.warning(
                            f"Failed to invite user: {user}. Seems like, their privacy settings strictly prohibit inviting."
                        )

                    await safe_click(
                        page, ".r-54znze > g:nth-child(1) > path:nth-child(1)"
                    )
                except Exception as e:
                    logger.error(f"Failed to invite user {user}: {e}")


async def worker(
    worker_id: int,
    token_queue: asyncio.Queue,
    users_to_invite: List[str],
    community: str,
    invited_users_key: str,
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
                    users_to_invite=users_to_invite,
                    community=community,
                    token=token,
                    invited_users_key=invited_users_key,
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
    users_file: str,
    workers: int,
    community: str = "https://x.com/i/communities/1996945882479026553/",
    redis_url: str = "redis://localhost:6379",
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
        users_to_invite = get_users_from_txt(users_file)
        total_tokens = len(tokens)

        logger.info(f"Loaded {total_tokens} tokens and {len(users_to_invite)} users")
        logger.info(f"Starting {workers} workers")

        # Ключ для хранения приглашённых пользователей в Redis
        invited_users_key = f"invited_users:{community}"

        # Создаем очередь токенов
        token_queue = asyncio.Queue()
        for index, token in enumerate(tokens, start=1):
            await token_queue.put((index, token))

        # Добавляем сигналы завершения для каждого воркера
        for _ in range(workers):
            await token_queue.put((None, None))

        # Создаем воркеры
        worker_tasks = [
            worker(i, token_queue, users_to_invite, community, invited_users_key)
            for i in range(workers)
        ]

        # Запускаем воркеры и ждем завершения очереди
        await asyncio.gather(*worker_tasks)
        logger.info("All workers completed")

        # Выводим статистику
        redis = _redis_client.get()
        if redis:
            invited_count = await redis.scard(invited_users_key)
            logger.info(f"Total users invited: {invited_count}/{len(users_to_invite)}")

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
        "-u",
        "--users",
        required=True,
        help="Path to a text file with usernames (one per line).",
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
            main_cli(args.tokens, args.users, args.workers, args.community, args.redis)
        )
        logger.info("Script completed successfully")
    except KeyboardInterrupt:
        logger.warning("Script interrupted by user")
    except Exception as e:
        logger.error(f"Script failed: {e}")
