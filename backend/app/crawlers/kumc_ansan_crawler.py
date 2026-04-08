"""고대안산병원 크롤러 - KUMC 계열 JSON API"""
from app.crawlers.kumc_base import KumcBaseCrawler


class KumcAnsanCrawler(KumcBaseCrawler):
    def __init__(self):
        super().__init__(
            hp_cd="AS",
            inst_no=3,
            hospital_code="KUANSAN",
            hospital_name="고대안산병원",
        )
