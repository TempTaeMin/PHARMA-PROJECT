"""의정부성모병원 크롤러 - CMC 계열 JSON API"""
from app.crawlers.cmc_base import CmcBaseCrawler


class CmcujbCrawler(CmcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://www.cmcujb.or.kr",
            inst_no="4",
            hospital_code="CMCUJB",
            hospital_name="의정부성모병원",
        )
