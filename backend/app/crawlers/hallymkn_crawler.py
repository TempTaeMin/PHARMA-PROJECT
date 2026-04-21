"""한림대학교 강남성심병원 (HALLYMKN) 크롤러

한림대 공용 베이스 클래스(`hallym_base.HallymBaseCrawler`)를 상속.
도메인: https://kangnam.hallym.or.kr (영등포 소재)
external_id: HALLYMKN-{Doctor_Id}
"""
from app.crawlers.hallym_base import HallymBaseCrawler


class HallymknCrawler(HallymBaseCrawler):
    def __init__(self):
        super().__init__(
            hospital_code="HALLYMKN",
            hospital_name="한림대학교강남성심병원",
            base_url="https://kangnam.hallym.or.kr",
        )
