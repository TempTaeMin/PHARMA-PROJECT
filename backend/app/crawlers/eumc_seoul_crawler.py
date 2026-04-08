"""이대서울병원 크롤러 - EUMC 계열 HTML+JS 파싱"""
from app.crawlers.eumc_crawler import EumcBaseCrawler


class EumcSeoulCrawler(EumcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://seoul.eumc.ac.kr",
            hospital_code="EUMCSL",
            hospital_name="이대서울병원",
        )
