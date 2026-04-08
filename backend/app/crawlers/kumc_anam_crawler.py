"""고대안암병원 크롤러 - KUMC 계열 JSON API"""
from app.crawlers.kumc_base import KumcBaseCrawler


class KumcAnamCrawler(KumcBaseCrawler):
    def __init__(self):
        super().__init__(
            hp_cd="AA",
            inst_no=1,
            hospital_code="KUANAM",
            hospital_name="고대안암병원",
        )
