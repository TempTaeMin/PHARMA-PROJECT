"""은평성모병원 크롤러 - CMC 계열 JSON API"""
from app.crawlers.cmc_base import CmcBaseCrawler


class CmcepCrawler(CmcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://www.cmcep.or.kr",
            inst_no="9",
            hospital_code="CMCEP",
            hospital_name="은평성모병원",
        )
