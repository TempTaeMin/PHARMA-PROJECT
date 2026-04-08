"""여의도성모병원 크롤러 - CMC 계열 JSON API"""
from app.crawlers.cmc_base import CmcBaseCrawler


class CmcyouidoCrawler(CmcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://www.cmcsungmo.or.kr",
            inst_no="3",
            hospital_code="CMCYD",
            hospital_name="여의도성모병원",
        )
