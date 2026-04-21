"""경기도의료원 수원병원(GGSW) 크롤러

경기도의료원 통합 플랫폼(www.medical.or.kr)의 site_gb=SUWON 서브사이트.
공통 로직은 MedicalOrKrBaseCrawler 에 있음.
"""
from __future__ import annotations

from app.crawlers.medical_base import MedicalOrKrBaseCrawler


class GgswCrawler(MedicalOrKrBaseCrawler):
    hospital_code = "GGSW"
    hospital_name = "경기도의료원 수원병원"
    site_gb = "SUWON"
    site_path = "suwon"
