"""부천성모병원 크롤러 - CMC 계열 JSON API"""
from app.crawlers.cmc_base import CmcBaseCrawler


class CmcbcCrawler(CmcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://www.cmcbucheon.or.kr",
            inst_no="5",
            hospital_code="CMCBC",
            hospital_name="부천성모병원",
        )
