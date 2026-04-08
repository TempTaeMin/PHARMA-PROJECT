"""고대구로병원 크롤러 - KUMC 계열 JSON API"""
from app.crawlers.kumc_base import KumcBaseCrawler


class KumcGuroCrawler(KumcBaseCrawler):
    def __init__(self):
        super().__init__(
            hp_cd="GR",
            inst_no=2,
            hospital_code="KUGURO",
            hospital_name="고대구로병원",
        )
