import concurrent.futures
import re
from pathlib import Path

import numpy
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

    def search_novel(self, novel_name: str) -> dict:
        """
        在搜索页面搜索小说，返回搜索结果
        :param novel_name: 目标小说名称
        :return:
        1. 成功返回示例：
            {
                "code": "成功",
                "payload":
                    {
                        "name": "novel_name",
                        "link": "novel_website_link",
                        "author": "author",
                        "word_count": "1230万",
                        "latest_chapter": "第123章"
                        "latest_updated_time": "2023-09-23 12:30",
                    }
            }
        2. 失败返回示例：
            {
                "code": "失败",
                "payload":
                    {
                        "message": "error_message"
                    }
            }
        """
        result = dict()
        error_payload = dict()
        normal_payload = dict()
        is_went_wrong = False
        page = self.get_page()
        try:
            page.goto(self.source_url)
        except TimeoutError:
            is_went_wrong = True
            error_payload["message"] = "访问网站超时"
        if not is_went_wrong:
            search_input_locator = page.locator("//form/input[@name='searchkey']")
            search_submit_button_locator = page.locator("//form/button[@type='submit']")
            try:
                ep(search_input_locator).to_be_visible()
                ep(search_submit_button_locator).to_be_visible()
            except AssertionError:
                is_went_wrong = True
                error_payload["message"] = "未找到页面中的搜索栏"
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
                    novel_list_locator = search_popup_page.locator("//div[@id='main']/div[@class='novelslistss']")
                    try:
                        ep(novel_list_locator).to_be_visible()
                        error_payload["message"] = "找到多部小说，需明确小说名称"
                    except AssertionError:
                        error_payload["message"] = "未找到小说信息"
                if not is_went_wrong:
                    normal_payload["name"] = novel_info_locator.locator("h1").inner_text().strip()
                    normal_payload["link"] = search_popup_page.url
                    for novel_info_item in novel_info_locator.locator("p").all():
                        item_text = novel_info_item.inner_text().strip()
                        if item_text.startswith("作者"):
                            normal_payload["author"] = item_text[item_text.find("：") + 1:]
                        if item_text.startswith("最新"):
                            normal_payload["latest_chapter"] = item_text[item_text.find("：") + 1:]
                        if item_text.startswith("更新时间"):
                            matched = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}).*共(\d+万)字", item_text)
                            if matched:
                                normal_payload["latest_updated_time"] = matched.group(1)
                                normal_payload["word_count"] = matched.group(2)
                    chapter_links = list()
                    for chapter_link_locator in search_popup_page.locator("//div[@id='list']/dl/center/following"
                                                                          "-sibling::dd/a").all():
                        chapter_links.append(page.url + chapter_link_locator.get_attribute("href"))
                    normal_payload["chapter_links"] = chapter_links
                    normal_payload["chapter_count"] = len(chapter_links)
        if is_went_wrong:
            result["code"] = "失败"
            result["payload"] = error_payload
        else:
            result["code"] = "成功"
            result["payload"] = normal_payload
        return result

    def download_novel(self, novel_name: str, thread_number: int) -> dict:
        search_result = self.search_novel(novel_name)
        search_result_code = search_result["code"]
        if search_result_code == "成功":
            novel_info = dict(search_result["payload"])
            chapter_links = list(novel_info["chapter_links"])
            chapter_links_segments = [x.tolist() for x in numpy.array_split(chapter_links, thread_number)]
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=thread_number)
            chapter_download_result = list()
            for segment in chapter_links_segments:
                chapter_download_result.append(
                    executor.submit(self._download_chapters, self.get_page(), novel_name, segment))
        else:
            return search_result

    def _download_chapters(self, page: Page, novel_name: str, chapter_links: list) -> dict:
        """
        按章节下载小说
        :param page: 浏览器页面对象
        :param novel_name: 小说名称
        :param chapter_links: 章节链接列表
        :return:
        """
        current_chapter_index = 1
        useless_str = f"笔趣阁 www.bbiquge.org，最快更新{novel_name} ！"
        start_chapter_link = str(chapter_links[0])
        start_chapter_number = int(start_chapter_link[start_chapter_link.rfind("/") + 1:start_chapter_link.rfind(".")])
        file_name = f"{novel_name}_{start_chapter_number}.txt"
        file_path = _OUTPUT_DIR + "_" + file_name
        f_handler = open(file_path, "w", encoding="utf-8")
        is_went_wrong = False
        for chapter_link in chapter_links:
            page.goto(chapter_link)
            chapter_title_locator = page.locator("//div[@class='bookname']/h1")
            chapter_content_locator = page.locator("//div[@id='content']")
            try:
                ep(chapter_title_locator).to_be_visible()
                ep(chapter_content_locator).to_be_visible()
            except AssertionError:
                is_went_wrong = True
            if not is_went_wrong:
                chapter_title = chapter_title_locator.inner_text().strip()
                chapter_content = chapter_content_locator.inner_text().replace("\xa0", "").replace("\n\n",
                                                                                                   "\n").replace(
                    useless_str, "").strip()
                if len(chapter_title) * len(chapter_content) > 0:
                    f_handler.write(chapter_title)
                    f_handler.write(chapter_content)
                    f_handler.write('\n\n' + '-' * 10 + '\n\n')
                    current_chapter_index += 1
                    print(f"{chapter_title}已下载完成！")
                    if current_chapter_index % 10 == 0:
                        f_handler.flush()
                else:
                    is_went_wrong = True
            if is_went_wrong:
                break
        f_handler.close()
        if is_went_wrong:
            return {"code": "失败", "payload": {"message": "下载失败"}}
        else:
            return {"code": "成功", "payload": {"file_path": file_path, "start_chapter_number": start_chapter_number}}

if __name__ == '__main__':
    downloader = NovelDownloader(headless=False, output_dir=Path(_OUTPUT_DIR), source_url=_SOURCE_URL)
    print(downloader.search_novel("亏成首富"))
