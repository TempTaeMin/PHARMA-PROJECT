"""경기도의료원 안성병원(ANSEONG) 크롤러

경기도의료원 통합 플랫폼(www.medical.or.kr)의 site_gb=ANSUNG 서브사이트.
※ medical.or.kr 내부 키는 "ANSUNG"(구식 표기) 이며, 우리 시스템 코드는 "ANSEONG".
공통 로직은 MedicalOrKrBaseCrawler 에 있음.
"""
from __future__ import annotations

from app.crawlers.medical_base import MedicalOrKrBaseCrawler


class AnseongCrawler(MedicalOrKrBaseCrawler):
    hospital_code = "ANSEONG"
    hospital_name = "경기도의료원 안성병원"
    site_gb = "ANSUNG"
    site_path = "ansung"
