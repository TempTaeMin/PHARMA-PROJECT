"""서울성모병원 크롤러 (CmcBaseCrawler 사용)"""
from app.crawlers.cmc_base import CmcBaseCrawler


class CmcseoulCrawler(CmcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://www.cmcseoul.or.kr",
            inst_no="2",
            hospital_code="CMCSEOUL",
            hospital_name="서울성모병원",
        )
