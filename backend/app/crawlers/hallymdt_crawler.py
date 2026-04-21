"""한림대학교 동탄성심병원 (HALLYMDT) 크롤러

한림대 공용 베이스 클래스(`hallym_base.HallymBaseCrawler`)를 상속.
도메인: https://dongtan.hallym.or.kr (경기 화성시 동탄)
external_id: HALLYMDT-{Doctor_Id}
"""
from app.crawlers.hallym_base import HallymBaseCrawler


class HallymdtCrawler(HallymBaseCrawler):
    def __init__(self):
        super().__init__(
            hospital_code="HALLYMDT",
            hospital_name="한림대학교동탄성심병원",
            base_url="https://dongtan.hallym.or.kr",
        )
