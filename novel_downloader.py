import random
import re
import time
from pathlib import Path

import click
from playwright.sync_api import sync_playwright, expect as ep
from playwright.sync_api._generated import Page

_SOURCE_URL = "https://www.bbiquge.org/"
_OUTPUT_DIR = "./novels"


class NovelDownloader:

    def __init__(self, headless: bool, output_dir: Path, source_url: str):
        """
        初始化浏览器、输出文档等信息
        :param headless: 启用无头模式
        :param output_dir: 输出文档目录
        :param source_url: 小说网站源地址
        """
        self.browser = sync_playwright().start().chromium.launch(headless=headless)
        self.context = self.browser.new_context(accept_downloads=True, bypass_csp=True, ignore_https_errors=True)
        self.output_dir = output_dir
        self.source_url = source_url
        ep.set_options(30_000)

    def __del__(self):
        """
        关闭浏览器等，释放资源
        """""
        for context in self.browser.contexts:
            context.close()
        self.browser.close()

    def get_page(self) -> Page:
        """
        生成一个新的浏览器页面对象
        """
        return self.context.new_page()

    def download_novel(self, **kwargs) -> dict:
        """
        下载小说
        :param kwargs: 小说名称或链接
        :return:
        """
        result = dict()
        if "name" in kwargs:
            search_result = self._search_novel(kwargs["name"])
        else:
            search_result = self._get_novel_info(kwargs["url"])
        if search_result["code"]:
            file_path = f"{_OUTPUT_DIR}/{search_result['name']}_{search_result['author']}.txt"
            file_handler = open(file_path, "a+", encoding="utf-8")
            current_chapter_index = 1
            useless_str = f"笔趣阁 www.bbiquge.org，最快更新{search_result['name']} ！"
            is_went_wrong = False
            page = self.get_page()
            chapter_links = search_result["chapter_links"]
            for chapter_link in chapter_links:
                page.goto(chapter_link)
                chapter_title_locator = page.locator("//div[@class='bookname']/h1")
                chapter_content_locator = page.locator("//div[@id='content']")
                try:
                    ep(chapter_title_locator).to_be_visible()
                    ep(chapter_content_locator).to_be_visible()
                except AssertionError:
                    is_went_wrong = True
                    result["code"] = False
                    result["message"] = f"未找到章节信息：{chapter_link}"
                if not is_went_wrong:
                    chapter_title = chapter_title_locator.inner_text().strip()
                    chapter_content = chapter_content_locator.inner_text().replace(
                        "\xa0", "").replace("\n\n", "\n").replace(useless_str, "").strip()
                    if len(chapter_title) * len(chapter_content) > 0:
                        file_handler.write(chapter_title)
                        file_handler.write('\n')
                        file_handler.write(chapter_content)
                        file_handler.write('\n\n' + '-' * 10 + '\n\n')
                        current_chapter_index += 1
                        print(f"{chapter_title} 已下载完成！")
                        if current_chapter_index % 10 == 0:
                            file_handler.flush()
                    else:
                        is_went_wrong = True
                        result["code"] = False
                        result["message"] = f"章节内容为空：{chapter_title}"
                if is_went_wrong:
                    break
                # time.sleep(random.randint(0, 1))
            file_handler.close()
            if not is_went_wrong:
                result["code"] = True
                result["file_path"] = file_path
                result["link"] = search_result["link"]
                result["chapter_count"] = search_result["chapter_count"]
                result["word_count"] = search_result["word_count"]
                result["latest_chapter"] = search_result["latest_chapter"]
            return result
        else:
            return search_result

    def _search_novel(self, novel_name: str) -> dict:
        """
        搜索小说，返回搜索结果
        :param novel_name:  小说名称
        :return:
        1. 成功返回示例：
            {
                "code": True,
                "name": novel_name,
                "link": novel_link,
                "author": author,
                "chapter_count": 123,
                "chapter_links": [http://XXXX1, http://XXXX2]
                "word_count": 1234万,
                "latest_chapter": 第一章,
                "latest_updated_time": 2023-09-23 12:30
            }
        2. 失败返回示例：
          {
                "code": False,
                "message": "error_message"
            }
        """
        result = dict()
        is_went_wrong = False
        page = self.get_page()
        try:
            page.goto(self.source_url)
        except TimeoutError:
            is_went_wrong = True
            result["code"] = False
            result["message"] = "访问网站超时"
        if not is_went_wrong:
            search_input_locator = page.locator("//form/input[@name='searchkey']")
            search_submit_button_locator = page.locator("//form/button[@type='submit']")
            try:
                ep(search_input_locator).to_be_visible()
                ep(search_submit_button_locator).to_be_visible()
            except AssertionError:
                is_went_wrong = True
                result["code"] = False
                result["message"] = "未找到页面中的搜索栏"
            if not is_went_wrong:
                search_input_locator.fill(novel_name)
                with page.expect_popup() as search_popup_info:
                    search_submit_button_locator.click()
                search_popup_page = search_popup_info.value
                novel_info_locator = search_popup_page.locator("#info")
                try:
                    ep(novel_info_locator).to_be_visible()
                except AssertionError:
                    is_went_wrong = True
                    result["code"] = False
                    novel_list_locator = search_popup_page.locator("//div[@id='main']/div[@class='novelslistss']")
                    try:
                        ep(novel_list_locator).to_be_visible()
                        result["message"] = "找到多部小说，需明确小说名称"
                    except AssertionError:
                        result["message"] = "未找到小说信息"
                if not is_went_wrong:
                    result["name"] = novel_info_locator.locator("h1").inner_text().strip()
                    result["link"] = search_popup_page.url
                    for novel_info_item in novel_info_locator.locator("p").all():
                        item_text = novel_info_item.inner_text().strip()
                        if item_text.startswith("作者"):
                            result["author"] = item_text[item_text.find("：") + 1:]
                        if item_text.startswith("最新"):
                            result["latest_chapter"] = item_text[item_text.find("：") + 1:]
                        if item_text.startswith("更新时间"):
                            matched = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}).*共(\d+万)字", item_text)
                            if matched:
                                result["latest_updated_time"] = matched.group(1)
                                result["word_count"] = matched.group(2)
                    chapter_links = list()
                    for chapter_link_locator in search_popup_page.locator(
                            "//div[@id='list']/dl/center/following-sibling::dd/a").all():
                        chapter_links.append(search_popup_page.url + chapter_link_locator.get_attribute("href"))
                    result["chapter_links"] = chapter_links
                    result["chapter_count"] = len(chapter_links)
                    result["code"] = True
                search_popup_page.close()
        page.close()
        return result

    def _get_novel_info(self, novel_url: str) -> dict:
        search_popup_page = self.get_page()
        is_went_wrong = False
        result = dict()
        try:
            search_popup_page.goto(novel_url)
        except TimeoutError:
            is_went_wrong = True
            result["code"] = False
            result["message"] = "访问网站超时"
        if not is_went_wrong:
            novel_info_locator = search_popup_page.locator("#info")
            try:
                ep(novel_info_locator).to_be_visible()
            except AssertionError:
                is_went_wrong = True
                result["code"] = False
                result["message"] = "未找到小说信息"
            if not is_went_wrong:
                result["name"] = novel_info_locator.locator("h1").inner_text().strip()
                result["link"] = search_popup_page.url
                for novel_info_item in novel_info_locator.locator("p").all():
                    item_text = novel_info_item.inner_text().strip()
                    if item_text.startswith("作者"):
                        result["author"] = item_text[item_text.find("：") + 1:]
                    if item_text.startswith("最新"):
                        result["latest_chapter"] = item_text[item_text.find("：") + 1:]
                    if item_text.startswith("更新时间"):
                        matched = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}).*共(\d+万)字", item_text)
                        if matched:
                            result["latest_updated_time"] = matched.group(1)
                            result["word_count"] = matched.group(2)
                chapter_links = list()
                for chapter_link_locator in search_popup_page.locator(
                        "//div[@id='list']/dl/center/following-sibling::dd/a").all():
                    chapter_links.append(search_popup_page.url + chapter_link_locator.get_attribute("href"))
                result["chapter_links"] = chapter_links
                result["chapter_count"] = len(chapter_links)
                result["code"] = True
            search_popup_page.close()
        return result


@click.command()
@click.option("-n", "--name", type=str, help="小说名称")
@click.option("-u", "--url", type=str, help="小说链接")
@click.option("--headless", default=False, is_flag=True, help="是否显示浏览器")
@click.option("-o", "--output_dir", default=_OUTPUT_DIR, help="输出目录")
def cmd(name, url, headless, output_dir):
    output_dir = Path(output_dir)
    if not output_dir.exists():
        output_dir.mkdir(exist_ok=True, parents=True)
    downloader = NovelDownloader(headless, output_dir, _SOURCE_URL)
    if name is not None:
        downloader.download_novel(name=name)
    if url is not None:
        downloader.download_novel(url=url)


if __name__ == '__main__':
    cmd()
