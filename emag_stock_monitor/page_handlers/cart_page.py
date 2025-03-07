"""处理购物车页"""

from typing import Literal, Optional

from playwright.async_api import BrowserContext, Page
from scraper_utils.exceptions.browser_exception import PlaywrightError
from scraper_utils.utils.browser_util import wait_for_selector
from scraper_utils.utils.emag_util import parse_pnk
from scraper_utils.constants.time_constant import MS1000

from emag_stock_monitor.logger import logger
from emag_stock_monitor.models import CartProduct, CartProducts
from emag_stock_monitor.urls import CART_PAGE_URL


async def goto_cart_page(
    context: BrowserContext,
    wait_until: Literal['commit', 'domcontentloaded', 'load', 'networkidle'] = 'load',
    timeout: Optional[int] = None,
) -> Page:
    """打开购物车页面"""
    # WARNING 为什么用 networkidle 打开购物车页时，产品加载出来后仍然要等待一段时间？
    logger.info(f'打开购物车页')
    page = await context.new_page()
    await page.goto(CART_PAGE_URL, wait_until=wait_until, timeout=timeout)
    return page


async def wait_page_load(page: Page, timeout: int = 30 * MS1000) -> bool:
    """等待页面加载完成（检测页面是否有商品）"""
    logger.info('等待购物车页面加载...')
    return await wait_for_selector(
        # page=page, selector='xpath=//div[starts-with(@class,"vendors-item")]', timeout=timeout
        page=page,
        selector='xpath=//input[@max]',
        timeout=timeout,
    )


async def parse_cart(page: Page) -> CartProducts:
    """统计购物车页面的所有产品的库存（最大可加购数）"""
    logger.info('解析购物车')
    result = CartProducts()

    single_item_count = await page.locator('xpath=//div[@class="main-product-title-container"]/a').count()
    bundle_item_count = await page.locator(
        (
            'xpath=//div[@class="line-item bundle-main d-flex "]'
            '//div[@class="bundle-item-title fw-semibold"]/a'
        )
    ).count()
    logger.debug(f'找到 {single_item_count} 个单项商品，{bundle_item_count} 个捆绑商品')

    # 解析单项商品
    for i in range(single_item_count):
        logger.debug(f'解析单项商品 {i}')
        i_url_a = page.locator(f'xpath=(//div[@class="main-product-title-container"]/a)[{i+1}]')
        i_qty_input = page.locator(
            (
                f'xpath=(//div[@class="main-product-title-container"]'
                f'/ancestor::div[@class="line-item-details"]//input[@max])[{i+1}]'
            )
        )
        i_pnk: str = parse_pnk(await i_url_a.get_attribute('href', timeout=MS1000))  # type: ignore
        i_qty: int = int(await i_qty_input.get_attribute('max', timeout=MS1000))  # type: ignore
        logger.debug(f'解析到商品 "{i_pnk}" "{i_qty}"')
        result.add(CartProduct(i_pnk, i_qty))

    # 解析捆绑商品
    for i in range(bundle_item_count):
        logger.debug(f'解析捆绑商品 {i}')
        i_url_a = page.locator(
            (
                f'xpath=(//div[@class="line-item bundle-main d-flex "]'
                f'//div[@class="bundle-item-title fw-semibold"]/a)[{i+1}]'
            )
        )
        i_qty_input = page.locator(
            (
                f'xpath=(//div[@class="line-item bundle-main d-flex "]/ancestor::'
                f'div[@class="cart-widget cart-line"]//input[@max])[{i+1}]'
            )
        )
        i_pnk: str = parse_pnk(await i_url_a.get_attribute('href', timeout=MS1000))  # type: ignore
        try:
            # NOTICE 有的捆绑产品会提示 Acest pachet de produse nu mai este disponibil 此产品捆绑销售不再提供，此时是找不到 qty 的
            i_qty: int = int(await i_qty_input.get_attribute('max', timeout=MS1000))  # type: ignore
        except PlaywrightError as pe:
            logger.warning(f'定位不到第 {i+1} 个捆绑商品的 qty，可能是不再可售\n{pe}')
            i_qty = 0
        logger.debug(f'解析到商品 "{i_pnk}" "{i_qty}"')
        result.add(CartProduct(i_pnk, i_qty))

    return result


async def clear_cart(page: Page) -> None:
    """清空购物车"""
    logger.info('清空购物车')

    # TODO 是否需要判断清空完成？
    single_item_sterge_count = await page.locator(
        (
            'xpath=//div[@class="main-product-title-container"]/ancestor::'
            'div[@class="line-item-details"]'
            '//button[contains(@class, "btn-remove-product")]'
        )
        # (
        #     'xpath=//div[@class="line-item line-item-footer d-none d-md-block"]'
        #     '/div[@class="mb-1"]'
        #     '/button[contains(@class, "btn-remove-product")]'
        # )
    ).count()
    bundle_item_sterge_count = await page.locator(
        (
            'xpath=//div[@class="line-item bundle-main d-flex "]/ancestor::'
            'div[@class="cart-widget cart-line"]'
            '//button[contains(@class, "btn-remove-product")]'
        )
    ).count()
    logger.debug(
        f'找到 {single_item_sterge_count} 个单项商品 Sterge，{bundle_item_sterge_count} 个捆绑商品 Sterge'
    )

    # 解析单项商品
    while single_item_sterge_count > 0:
        logger.debug(f'尝试 Sterge 第 {single_item_sterge_count} 个单项商品')
        try:
            await page.locator(
                (
                    f'xpath=(//div[@class="line-item line-item-footer d-none d-md-block"]'
                    f'/div[@class="mb-1"]'
                    f'/button[contains(@class, "btn-remove-product")])[{single_item_sterge_count}]'
                )
            ).click(timeout=MS1000)
        except PlaywrightError as pe:
            logger.error(pe)
        else:
            logger.success(f'第 {single_item_sterge_count} 个单项商品 Sterge 成功')
            single_item_sterge_count -= 1

    # 解析捆绑商品
    while bundle_item_sterge_count > 0:
        logger.debug(f'尝试 Sterge 第 {bundle_item_sterge_count} 个捆绑商品')
        try:
            await page.locator(
                (
                    f'xpath=(//div[@class="line-item bundle-main d-flex "]/ancestor::'
                    f'div[@class="cart-widget cart-line"]'
                    f'//button[contains(@class, "btn-remove-product")])[{bundle_item_sterge_count}]'
                )
            ).click(timeout=MS1000)
        except PlaywrightError as pe:
            logger.error(pe)
        else:
            logger.success(f'第 {bundle_item_sterge_count} 个捆绑商品 Sterge 成功')
            bundle_item_sterge_count -= 1


async def handle_cart(context: BrowserContext) -> CartProducts:
    """处理购物车

    ---

    * 打开购物车页面
    * 等待页面加载
    * 解析购物车数据
    * 清空购物车
    """

    page = await goto_cart_page(context, wait_until='networkidle')
    if not await wait_page_load(page):
        logger.error('等待购物车页面加载失败')
        raise RuntimeError

    result = await parse_cart(page)
    await clear_cart(page)
    await page.close()

    return result
