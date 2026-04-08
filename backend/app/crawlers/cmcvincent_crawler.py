"""성빈센트병원 크롤러 - CMC 계열 JSON API"""
from app.crawlers.cmc_base import CmcBaseCrawler


class CmcvincentCrawler(CmcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://www.cmcvincent.or.kr",
            inst_no="6",
            hospital_code="CMCSV",
            hospital_name="성빈센트병원",
        )
