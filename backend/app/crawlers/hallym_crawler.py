"""한림대학교 성심병원 (HALLYM) 크롤러

한림대 공용 베이스 클래스(`hallym_base.HallymBaseCrawler`)를 상속.
도메인: https://hallym.hallym.or.kr
external_id: HALLYM-{Doctor_Id}
"""
from app.crawlers.hallym_base import HallymBaseCrawler


_FALLBACK_DEPTS = [
    ("12105107", "내과", "OS"),
    ("12105102", "호흡기-알레르기내과", "OS"),
    ("12105113", "소화기내과", "OS"),
    ("12105105", "신경과", "OS"),
    ("12105108", "정신건강의학과", "OS"),
    ("12105101", "일반외과", "OS"),
    ("12105103", "흉부외과", "OS"),
    ("12105109", "신경외과", "OS"),
    ("12105106", "정형외과", "OS"),
    ("12105114", "성형외과", "OS"),
    ("12105117", "소아청소년과", "OS"),
    ("12105118", "산부인과", "OS"),
    ("12105119", "안과", "OS"),
    ("12105120", "이비인후과", "OS"),
    ("12105121", "비뇨기과", "OS"),
    ("12105122", "재활의학과", "OS"),
    ("12105124", "가정의학과", "OS"),
    ("12105135", "피부과", "OS"),
    ("12105127", "마취통증의학과", "OS"),
    ("12105123", "방사선종양학과", "OS"),
    ("12105130", "응급의학과", "OS"),
    ("12105110", "소아외과", "OS"),
    ("12105115", "치과", "OS"),
    ("12105128", "진단방사선과", "OS"),
    ("12105132", "영상의학과", "OS"),
]


class HallymCrawler(HallymBaseCrawler):
    def __init__(self):
        super().__init__(
            hospital_code="HALLYM",
            hospital_name="한림성심병원",
            base_url="https://hallym.hallym.or.kr",
            fallback_depts=_FALLBACK_DEPTS,
        )
