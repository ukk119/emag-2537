"""处理产品列表页"""

from random import randint
from time import perf_counter

from playwright.async_api import Page
from scraper_utils.constants.time_constant import MS1000
from scraper_utils.exceptions.browser_exception import PlaywrightError
from scraper_utils.utils.emag_util import parse_pnk

from emag_stock_monitor.logger import logger
from emag_stock_monitor.models import CartProducts
from emag_stock_monitor.page_handlers.cart_page import handle_cart


async def wait_page_load(page: Page, expect_count: int = 60, timeout: float = 10) -> bool:
    """等待页面加载完成（等待加载出足够数量的产品卡片）"""
    logger.info(f'等待页面 "{page.url}" 加载...')
    start_time = perf_counter()

    while True:
        # 超时退出
        if perf_counter() - start_time > timeout:
            logger.warning(f'等待页面 "{page.url}" 加载超时')
            return False

        # 统计产品卡片数量
        card_item_without_promovat_divs = page.locator(
            (
                'xpath='
                '//div[starts-with(@class, "card-item")]'
                '[not(.//div[starts-with(@class, "card-v2-badge-cmp-holder")]/span[starts-with(@class, "card-v2-badge-cmp")])]'
            ),
        )
        card_item_without_promovat_div_count = await card_item_without_promovat_divs.count()
        logger.debug(f'找到 {card_item_without_promovat_div_count} 个 card_item_without_promovat_div')
        if card_item_without_promovat_div_count >= expect_count:
            logger.debug(
                f'等待页面 "{page.url}" 加载成功，检测到 {card_item_without_promovat_div_count} 个商品'
            )
            return True

        # 模拟鼠标滑动
        await page.mouse.wheel(delta_x=0, delta_y=randint(200, 1000))
        await page.wait_for_timeout(randint(0, 500))


async def add_to_cart(page: Page, close_dialog_retry_count: int = 5) -> CartProducts:
    """加购页面上的产品"""
    # NOTICE 购物车一次最多放 50 种产品
    # TODO 要不要主动检测购物车种类加购上限？
    # TODO 要不改成加购前判断是否有弹窗，而不是现在的每次加购后等待弹窗？

    """
    记录加购成功的次数，每当计数达到上限就打开购物车页面统计各产品的最大加购数量，
    并在统计完成后清空购物车，然后继续加购
    """

    # BUG

    result = CartProducts()

    # 去除 Promovat、有加购按钮的 card-item
    add_cart_able_card_item_without_promovat_divs = page.locator(
        '//div[starts-with(@class, "card-item")]'
        '[not(.//div[starts-with(@class, "card-v2-badge-cmp-holder")]/span[starts-with(@class, "card-v2-badge-cmp")])'
        ' and .//form/button]'
    )
    # 产品 pnk 列表
    pnks: list[str] = [
        parse_pnk(await div.get_attribute('data-url', timeout=MS1000))  # type: ignore
        for div in await add_cart_able_card_item_without_promovat_divs.all()
    ]
    # 去除 Promovat 的加购按钮
    add_cart_buttons = page.locator(
        (
            'xpath='
            '//div[starts-with(@class, "card-item")]'
            '[not(.//div[starts-with(@class, "card-v2-badge-cmp-holder")]/span[starts-with(@class, "card-v2-badge-cmp")])]'
            '//form/button'
        ),
    )
    # 统计页面上的加购按钮总数
    add_cart_button_count = await add_cart_buttons.count()

    if add_cart_button_count != len(pnks):
        logger.error(f'解析到的 pnk 总数 {len(pnks)} 与加购按钮总数 {add_cart_button_count} 不同')

    added_count = 0
    while added_count < add_cart_button_count:
        # 加购达到一定数量就打开购物车页面，统计已加购的产品
        if added_count > 0 and added_count % 40 == 0:
            result += await handle_cart(page.context)

        ##### 点击加购按钮，等待弹窗出现，点击关闭弹窗 #####
        try:
            # 点击加购按钮
            await page.locator(
                'xpath='
                '(//div[starts-with(@class, "card-item")]'
                '[not(.//div[starts-with(@class, "card-v2-badge-cmp-holder")]/span[starts-with(@class, "card-v2-badge-cmp")])]'
                f'//form/button)[{added_count+1}]'
            ).click(timeout=MS1000)

        # 如果点击加购失败了就重试
        except PlaywrightError as pe_add_cart:
            logger.error(f'尝试点击加购按钮失败\n{pe_add_cart}')

        # 如果点击加购成功了就等待关闭加购弹窗
        else:
            added_count += 1
            logger.debug(f'加购成功，当前成功加购至第 {added_count} 个')

            # 点击关闭弹窗（失败时有重试次数）
            for _ in range(close_dialog_retry_count):
                try:
                    await page.locator('xpath=//button[@class="close gtm_6046yfqs"]').click()
                except PlaywrightError as pe_close_dialog:
                    logger.error(f'尝试关闭加购弹窗失败\n{pe_close_dialog}')
                else:
                    break

    # 当整个页面的加购完成就打开购物车页面，统计已加购产品
    result += await handle_cart(page.context)

    await page.close()

    return result
