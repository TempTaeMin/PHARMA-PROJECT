"""이대목동병원 크롤러 - EUMC 계열 HTML+JS 파싱"""
from app.crawlers.eumc_crawler import EumcBaseCrawler


class EumcMokdongCrawler(EumcBaseCrawler):
    def __init__(self):
        super().__init__(
            base_url="https://mokdong.eumc.ac.kr",
            hospital_code="EUMCMK",
            hospital_name="이대목동병원",
        )
