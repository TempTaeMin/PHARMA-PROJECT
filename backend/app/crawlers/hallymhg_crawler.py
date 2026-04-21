"""한림대학교 한강성심병원 (HALLYMHG) 크롤러

한림대 공용 베이스 클래스(`hallym_base.HallymBaseCrawler`)를 상속.
도메인: https://hangang.hallym.or.kr (영등포 소재, 화상 특화)
external_id: HALLYMHG-{Doctor_Id}
"""
from app.crawlers.hallym_base import HallymBaseCrawler


class HallymhgCrawler(HallymBaseCrawler):
    def __init__(self):
        super().__init__(
            hospital_code="HALLYMHG",
            hospital_name="한림대학교한강성심병원",
            base_url="https://hangang.hallym.or.kr",
        )
