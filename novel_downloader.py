import click
import re

from playwright._impl._errors import TimeoutError
from playwright.sync_api import sync_playwright, Locator, expect as ep
from pathlib import Path

_SOURCE_URL = "https://www.bbiquge.org/"
_OUTPUT_DIR = "./novels"


class NovelDownloader:

    def __init__(self, headless: bool, output_dir: Path, source_url: str):
        self.browser = sync_playwright().start().chromium.launch(headless=headless)
        self.context = self.browser.new_context(accept_downloads=True, bypass_csp=True, ignore_https_errors=True)
        self.output_dir = output_dir
        self.source_url = source_url
        ep.set_options(30_000)

    def __del__(self):
        for context in self.browser.contexts:
            context.close()
        self.browser.close()

    def get_page(self):
        return self.context.new_page()

    def search_novel(self, novel_name: str) -> dict:
        result = dict()
        is_went_error = False
        page = self.get_page()
        try:
            page.goto(self.source_url)
        except TimeoutError:
            is_went_error = True
            result["code"] = "失败"
            result["payload"] = {"message": "访问网站超时"}
        if not is_went_error:
            search_input_locator = page.locator("//form/input[@name='searchkey']")
            search_submit_button_locator = page.locator("//form/button[@type='submit']")
            try:
                ep(search_input_locator).to_be_visible()
                ep(search_submit_button_locator).to_be_visible()
            except AssertionError:
                is_went_error = True
                result["code"] = "失败"
                result["payload"] = {"message": "未找到主页中的搜索栏"}
            if not is_went_error:
                search_input_locator.fill(novel_name)
                with page.expect_popup() as search_popup_page_info:
                    search_submit_button_locator.click()
                search_popup_page = search_popup_page_info.value
                novel_info_locator = search_popup_page.locator("#info")
                try:
                    ep(novel_info_locator).to_be_visible()
                except AssertionError:
                    is_went_error = True
                    result["code"] = "失败"
                    novel_list_locator = search_popup_page.locator("//div[@id='main']/div[@class='novelslistss']")
                    try:
                        ep(novel_list_locator).to_be_visible()
                        result["payload"] = {"message": "找到多部小说，需明确小说名称"}
                    except AssertionError:
                        result["payload"] = {"message": "未找到小说"}
                if not is_went_error:
                    novel_info = dict()
                    novel_info["name"] = novel_info_locator.locator("h1").inner_text().strip()
                    novel_info["link"] = search_popup_page.url
                    for novel_info_item in novel_info_locator.locator("p").all():
                        item_text = novel_info_item.inner_text().strip()
                        if item_text.startswith("作者"):
                            novel_info["author"] = item_text[item_text.find("：") + 1:]
                        if item_text.startswith("最新"):
                            novel_info["latest_chapter"] = item_text[item_text.find("：") + 1:]
                        if item_text.startswith("更新时间"):
                            matched = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}).*共(\d+万)字", item_text)
                            if matched:
                                novel_info["latest_updated_time"] = matched.group(1)
                                novel_info["word_count"] = matched.group(2)
                    chapter_links = list()
                    for chapter_link_locator in search_popup_page.locator("//div[@id='list']/dl/center/following"
                                                                          "-sibling::dd/a").all():
                        chapter_links.append(chapter_link_locator.get_attribute("href"))
                    novel_info["chapter_links"] = chapter_links
                    novel_info["chapter_count"] = len(chapter_links)
                    result["code"] = "成功"
                    result["payload"] = novel_info
        return result

    def download_novel(self, novel_name: str, thread_number: int):
        is_went_error = False
        search_result = self.search_novel(novel_name)
        if search_result["code"] == "成功":
            novel_info = dict(search_result["payload"])
            filename = f"{novel_info['name']}_{novel_info['author']}.txt"
            chapter_links = list(novel_info["chapter_links"])
            
        else:
            return search_result

@click.command()
@click.argument("novel_name", type=str)
@click.option("--headless", default=False, is_flag=True, help="是否显示浏览器")
@click.option("-o", "--output_dir", default=_OUTPUT_DIR, help="输出目录")
def cmd(novel_name, headless, output_dir):
    output_dir = Path(output_dir)
    if not output_dir.exists():
        output_dir.mkdir(exist_ok=True, parents=True)
    downloader = NovelDownloader(headless, output_dir, _SOURCE_URL)
    downloader.search_novel(novel_name)


if __name__ == '__main__':
    # cmd()
    downloader = NovelDownloader(False, Path("./novels"), _SOURCE_URL)
    print(downloader.search_novel("亏成首富"))
