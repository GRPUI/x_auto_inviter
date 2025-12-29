import asyncio
import random
from typing import List

from browserforge.fingerprints import Screen
from camoufox import AsyncCamoufox
from loguru import logger
from playwright.async_api import Page

from read_files import get_tokens_from_txt
from x_token_login import set_x_token_cookie


async def safe_click(page: Page, selector):
    try:
        await page.click(selector, timeout=500)
        return True
    except Exception as e:
        return False


async def get_x_link(
    post: str, tokens: List[str], quantity: int, comments: List[str]
):
    """
    Приглашает пользователей в комьюнити, пропуская уже приглашённых.
    Использует Redis лок для предотвращения одновременной обработки одного пользователя.
    """
    current_comments_quantity = 0
    async with AsyncCamoufox(
            headless=True,
            humanize=1,
            screen=Screen(min_width=1920, max_width=1920, min_height=1080, max_height=1080),
            window=(1920, 1080)
    ) as browser:
        while current_comments_quantity < quantity:
            token = random.choice(tokens)
            logger.debug("Browser instance created")
            page = await browser.new_page()
            logger.debug("Opening x homepage")
            await page.goto("https://x.com")
            logger.debug("Loading cookies")
            await set_x_token_cookie(page, token, domain="x.com")
            await page.goto(post)
            await page.wait_for_load_state("networkidle")
            username = await page.evaluate('''
                                () => {
                                    const el = document.querySelector('#react-root > div > div > div.css-175oi2r.r-1f2l425.r-13qz1uu.r-417010.r-18u37iz > header > div > div > div > div.css-175oi2r.r-184id4b > div > button > div.css-175oi2r.r-1wbh5a2.r-dnmrzs.r-1ny4l3l > div > div.css-175oi2r.r-1awozwy.r-18u37iz.r-1wbh5a2 > div > div > div > span');
                                    return el ? el.textContent : null;
                                }
                            ''')
            if not username:
                logger.error(f"Failed to retrieve username for token: {token}")
                await page.close()
                continue
            await page.mouse.wheel(0, 500)
            await page.wait_for_timeout(500)
            await page.mouse.wheel(0, -500)
            await page.wait_for_timeout(500)
            await page.keyboard.press("R")
            await page.wait_for_timeout(500)
            for i in range(11):
                logger.info(f"Attempt {i} to send a comment for token: {token}")
                try:
                    await page.click(
                        "div.r-1h8ys4a:nth-child(3) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2)",
                        click_count=3,
                    timeout=1000)
                except Exception as e:
                    pass
                await page.keyboard.press("Backspace")
                await page.keyboard.type(random.choice(comments))
                await page.wait_for_timeout(1000)
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(500)
                await safe_click(page, "div.r-slzeqm:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > button:nth-child(2)")
                await page.wait_for_timeout(5000)
                is_sent = True
                for _ in range(3):
                    result = await page.evaluate('''
                                    () => {
                                        const el = document.querySelector('div.r-1b43r93 > span:nth-child(1)');
                                        return el ? el.textContent : null;
                                    }
                                ''')
                    logger.debug(f"Sent result: {result}")
                    if result is not None and isinstance(result, str):
                        is_sent = False
                        break
                    else:
                        await page.wait_for_timeout(500)
                        logger.success("Successfully sent comment")
                        break
                if is_sent:
                    current_comments_quantity += 1
                    continue
                await page.click("div.r-1h8ys4a:nth-child(3) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2)", click_count=3)
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(1000)
                logger.info(f"Haven't sent the comment yet for attempt {i}")
            await page.close()

async def main_cli(
    tokens_file: str,
    comments_file: str,
    post_url: str,
    quantity: int
):

    try:
        tokens = get_tokens_from_txt(tokens_file)
        comments = get_tokens_from_txt(comments_file)
        total_tokens = len(tokens)

        logger.info(f"Loaded {total_tokens} tokens")

        await get_x_link(
            post=post_url,
            tokens=tokens,
            quantity=quantity,
            comments=comments,
        )
    except Exception as e:
        logger.error(f"Error processing tokens: {e}")


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
        "-p",
        "--post",
        required=True,
        help="Post URL.",
    )
    parser.add_argument(
        "-c",
        "--comments",
    default="texts.txt",
        help="Path to a text file with comments for the script.",
    )
    parser.add_argument(
        "-q",
        "--quantity",
        required=True,
        type=int,
        help="Quantity of comments.",
    )

    args = parser.parse_args()
    try:
        asyncio.run(
            main_cli(args.tokens, args.comments, args.post, args.quantity)
        )
        logger.info("Script completed successfully")
    except KeyboardInterrupt:
        logger.warning("Script interrupted by user")
    except Exception as e:
        logger.error(f"Script failed: {e}")
