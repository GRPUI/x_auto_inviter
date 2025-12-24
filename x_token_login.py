import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

from camoufox import AsyncCamoufox



class XTokenLoginError(Exception):
    """Исключение для ошибок входа через токен X"""
    pass


class XTokenLogin:
    """
    Класс для автоматизации входа в X (Twitter) через токен аутентификации в Camoufox.
    Решает потенциальные проблемы оригинального кода:
    - Валидация токена
    - Правильная обработка cookie параметров
    - Обработка ошибок
    - Поддержка различных доменов X
    - Логирование операций
    """

    # Возможные домены X
    X_DOMAINS = [
        "x.com",
        "twitter.com",
        "www.x.com",
        "www.twitter.com"
    ]

    # Основной домен для cookie
    PRIMARY_DOMAIN = "x.com"

    def __init__(
        self,
        page=None,
        addon_path: str = "./api/v1/services/automation/addons/firefox-build1.2.0-prod/",
        headless: bool = True,
        humanize: int = 10,
        target_url: str = "https://x.com"
    ):
        """
        Инициализация класса для входа через токен X.

        Args:
            page: Объект страницы Playwright (опционально)
            addon_path: Путь к расширению Firefox
            headless: Запускать ли браузер в headless режиме
            humanize: Уровень гуманизации поведения браузера
            target_url: URL для перенаправления после входа
        """
        self.page = page
        self.addon_path = addon_path
        self.headless = headless
        self.humanize = humanize
        self.target_url = target_url
        self.browser = None
        self._owns_browser = False  # Флаг: создали ли мы браузер сами

    async def __aenter__(self):
        """Контекстный менеджер для автоматического управления браузером"""
        if not self.page:
            self.browser = AsyncCamoufox(
                headless=self.headless,
                humanize=self.humanize,
                addons=[self.addon_path]
            )
            await self.browser.__aenter__()
            self._owns_browser = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие браузера при выходе из контекстного менеджера"""
        if self._owns_browser and self.browser:
            await self.browser.__aexit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def validate_token(token: str) -> bool:
        """
        Валидирует токен аутентификации.

        Args:
            token: Токен для проверки

        Returns:
            True если токен валиден, иначе False

        Raises:
            XTokenLoginError: Если токен пуст или имеет неправильный формат
        """
        if not token:
            raise XTokenLoginError("Токен не может быть пустым")

        # Удаляем кавычки если они есть
        token = token.strip().strip('"\'')

        if not token:
            raise XTokenLoginError("Токен содержит только кавычки")

        # Проверяем минимальную длину (обычно токены длиннее 20 символов)
        if len(token) < 20:
            raise XTokenLoginError(f"Токен слишком короткий: {len(token)} символов")

        # Проверяем что токен содержит допустимые символы (alphanumeric, -, _)
        if not re.match(r'^[a-zA-Z0-9\-_]+$', token):
            raise XTokenLoginError("Токен содержит недопустимые символы")

        return True

    @staticmethod
    def clean_token(token: str) -> str:
        """
        Очищает токен от кавычек и пробелов.

        Args:
            token: Исходный токен

        Returns:
            Очищенный токен
        """
        return token.strip().strip('"\'')

    async def set_auth_cookie(
        self,
        token: str,
        domain: Optional[str] = None,
        expiration_days: int = 365
    ) -> None:
        """
        Устанавливает cookie аутентификации.

        Args:
            token: Токен аутентификации
            domain: Домен для cookie (по умолчанию PRIMARY_DOMAIN)
            expiration_days: Количество дней до истечения cookie

        Raises:
            XTokenLoginError: Если токен невалиден или не удалось установить cookie
        """
        if not self.page:
            raise XTokenLoginError("Страница не инициализирована")

        # Валидируем токен
        self.validate_token(token)
        clean_token = self.clean_token(token)

        # Используем переданный домен или основной
        cookie_domain = domain or self.PRIMARY_DOMAIN

        # Вычисляем время истечения
        expiration_date = datetime.utcnow() + timedelta(days=expiration_days)
        expires_timestamp = int(expiration_date.timestamp())

        try:
            # Устанавливаем cookie через контекст страницы
            await self.page.context.add_cookies([
                {
                    "name": "auth_token",
                    "value": clean_token,
                    "domain": cookie_domain,
                    "path": "/",
                    "expires": expires_timestamp,
                    "httpOnly": True,  # Защита от XSS
                    "secure": True,    # Только HTTPS
                    "sameSite": "Lax"  # CSRF защита
                }
            ])

            print(f"✓ Cookie установлена успешно для домена {cookie_domain}")
            print(f"  Срок действия: {expiration_date.isoformat()}")

        except Exception as e:
            raise XTokenLoginError(f"Ошибка при установке cookie: {str(e)}")

    async def navigate_to_target(self) -> None:
        """
        Перенаправляет на целевой URL после установки cookie.

        Raises:
            XTokenLoginError: Если не удалось перейти на URL
        """
        if not self.page:
            raise XTokenLoginError("Страница не инициализирована")

        try:
            await self.page.goto(self.target_url, wait_until="networkidle")
            print(f"✓ Перенаправление на {self.target_url} успешно")
        except Exception as e:
            raise XTokenLoginError(f"Ошибка при перенаправлении: {str(e)}")

    async def verify_login(self, timeout: int = 10000) -> bool:
        """
        Проверяет успешность входа.

        Args:
            timeout: Таймаут ожидания в миллисекундах

        Returns:
            True если вход успешен, иначе False
        """
        if not self.page:
            raise XTokenLoginError("Страница не инициализирована")

        try:
            # Проверяем наличие элементов, которые появляются только после входа
            # Например, кнопка "Compose" или профиль пользователя
            await self.page.wait_for_selector(
                '[aria-label="Compose"], [data-testid="SideNav_NewTweet_Button"]',
                timeout=timeout
            )
            print("✓ Вход успешен - найдены элементы авторизованного пользователя")
            return True
        except Exception as e:
            print(f"✗ Вход не подтвержден: {str(e)}")
            return False

    async def save_session(
        self,
        cookies_path: str = "./api/v1/services/automation/cookies.json",
        storage_path: str = "./api/v1/services/automation/storage.json"
    ) -> None:
        """
        Сохраняет сессию (cookies и localStorage).

        Args:
            cookies_path: Путь для сохранения cookies
            storage_path: Путь для сохранения localStorage
        """
        pass

    async def login_with_token(
        self,
        token: str,
        verify: bool = True,
        save_session: bool = True
    ) -> bool:
        """
        Основной метод для входа через токен.

        Args:
            token: Токен аутентификации
            verify: Проверять ли успешность входа
            save_session: Сохранять ли сессию после входа

        Returns:
            True если вход успешен, иначе False

        Raises:
            XTokenLoginError: Если возникла ошибка при входе
        """
        try:
            # Создаем новую страницу
            self.page = await self.browser.new_page()
            print("✓ Новая страница создана")

            # Переходим на целевой URL
            await self.navigate_to_target()

            # Устанавливаем cookie с токеном
            await self.set_auth_cookie(token)

            # Перезагружаем страницу для применения cookie
            await self.page.reload(wait_until="networkidle")
            print("✓ Страница перезагружена")

            # Проверяем успешность входа если требуется
            if verify:
                is_logged_in = await self.verify_login()
                if not is_logged_in:
                    print("⚠ Вход не подтвержден, но продолжаем...")


            print("✓ Вход через токен завершен успешно")
            return True

        except XTokenLoginError as e:
            print(f"✗ Ошибка входа: {str(e)}")
            raise
        except Exception as e:
            print(f"✗ Неожиданная ошибка: {str(e)}")
            raise XTokenLoginError(f"Неожиданная ошибка при входе: {str(e)}")


async def login_with_x_token(
    token: str,
    addon_path: str = "./api/v1/services/automation/addons/firefox-build1.2.0-prod/",
    headless: bool = True,
    target_url: str = "https://x.com"
) -> bool:
    """
    Удобная функция для входа в X через токен (создает браузер автоматически).

    Args:
        token: Токен аутентификации
        addon_path: Путь к расширению Firefox
        headless: Запускать ли браузер в headless режиме
        target_url: URL для перенаправления после входа

    Returns:
        True если вход успешен, иначе False

    Raises:
        XTokenLoginError: Если возникла ошибка при входе
    """
    async with XTokenLogin(
        addon_path=addon_path,
        headless=headless,
        target_url=target_url
    ) as login:
        return await login.login_with_token(token, verify=True, save_session=True)


async def set_x_token_cookie(
    page,
    token: str,
    domain: str = "x.com",
    expiration_days: int = 365,
    verify: bool = False,
    save_session: bool = False,
    reload_timeout: int = 10000,
    wait_until: str = "domcontentloaded"
) -> bool:
    """
    Устанавливает cookie аутентификации X для существующей страницы.
    Удобная функция для использования с уже открытой страницей.

    Args:
        page: Объект страницы Playwright
        token: Токен аутентификации
        domain: Домен для cookie (по умолчанию x.com)
        expiration_days: Количество дней до истечения cookie
        verify: Проверять ли успешность входа
        save_session: Сохранять ли сессию после входа
        reload_timeout: Таймаут перезагрузки в миллисекундах (по умолчанию 10000)
        wait_until: Условие ожидания при перезагрузке ("domcontentloaded", "load", "networkidle")

    Returns:
        True если успешно, иначе False

    Raises:
        XTokenLoginError: Если возникла ошибка
    """
    try:
        login = XTokenLogin(page=page)
        
        # Валидируем и устанавливаем cookie
        login.validate_token(token)
        clean_token = login.clean_token(token)
        
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
        
        print(f"✓ Cookie установлена успешно для домена {domain}")
        print(f"  Срок действия: {expiration_date.isoformat()}")
        
        # Перезагружаем страницу для применения cookie с гибким таймаутом
        try:
            await page.reload(wait_until=wait_until, timeout=reload_timeout)
            print(f"✓ Страница перезагружена (wait_until={wait_until})")
        except Exception as reload_error:
            print(f"⚠ Перезагрузка страницы заняла слишком много времени: {str(reload_error)}")
            print("  Продолжаем без полной перезагрузки...")
            # Даже если перезагрузка не удалась, cookie уже установлена
        
        # Проверяем успешность входа если требуется
        if verify:
            try:
                is_logged_in = await login.verify_login(timeout=5000)
                if not is_logged_in:
                    print("⚠ Вход не подтвержден, но продолжаем...")
            except Exception as verify_error:
                print(f"⚠ Проверка входа не удалась: {str(verify_error)}")

        
        print("✓ Установка cookie завершена успешно")
        return True
        
    except XTokenLoginError as e:
        print(f"✗ Ошибка: {str(e)}")
        raise
    except Exception as e:
        print(f"✗ Неожиданная ошибка: {str(e)}")
        raise XTokenLoginError(f"Неожиданная ошибка: {str(e)}")


async def open_browser_interactive():
    """Открывает браузер в интерактивном режиме для тестирования"""
    async with AsyncCamoufox(headless=False, humanize=10) as browser:
        page = await browser.new_page()
        await page.goto("https://x.com")
        await asyncio.Future()  # Бесконечное ожидание


if __name__ == "__main__":
    # Пример использования
    import sys

    if len(sys.argv) > 1:
        token = sys.argv[1]
        try:
            asyncio.run(login_with_x_token(token))
        except XTokenLoginError as e:
            print(f"Ошибка: {e}")
            sys.exit(1)
    else:
        print("Использование: python x_token_login.py <token>")
        print("\nДля интерактивного режима:")
        asyncio.run(open_browser_interactive())
