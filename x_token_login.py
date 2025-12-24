from datetime import datetime, timedelta

from loguru import logger


async def set_x_token_cookie(
    page,
    token: str,
    domain: str = "x.com",
    expiration_days: int = 365,
    reload_timeout: int = 1000,
    wait_until: str = "domcontentloaded"
) -> bool:
    """
    Устанавливает cookie аутентификации X для существующей страницы.

    Args:
        page: Объект страницы Playwright
        token: Токен аутентификации
        domain: Домен для cookie (по умолчанию x.com)
        expiration_days: Количество дней до истечения cookie
        reload_timeout: Таймаут перезагрузки в миллисекундах
        wait_until: Условие ожидания при перезагрузке

    Returns:
        True если успешно, иначе False

    Raises:
        ValueError: Если токен невалиден
    """
    if not token or len(token) < 20:
        raise ValueError("Токен невалиден")
    
    clean_token = token.strip().strip('"\'')
    
    expiration_date = datetime.utcnow() + timedelta(days=expiration_days)
    expires_timestamp = int(expiration_date.timestamp())
    
    await page.context.add_cookies([
        {
            "name": "auth_token",
            "value": clean_token,
            "domain": domain,
            "path": "/",
            "expires": expires_timestamp,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax"
        }
    ])
    
    logger.info(f"✓ Cookie установлена успешно для домена {domain}")
    
    try:
        await page.reload(wait_until=wait_until, timeout=reload_timeout)
        logger.debug(f"✓ Страница перезагружена")
    except Exception as reload_error:
        logger.warning(f"⚠ Перезагрузка страницы заняла слишком много времени")
    
    return True
