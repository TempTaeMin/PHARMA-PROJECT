"""경기도의료원 이천병원(ICHEON) 크롤러

경기도의료원 통합 플랫폼(www.medical.or.kr)의 site_gb=ICHEON 서브사이트.
공통 로직은 MedicalOrKrBaseCrawler 에 있음. 이 파일은 사이트 식별자만 지정한다.
"""
from __future__ import annotations

from app.crawlers.medical_base import MedicalOrKrBaseCrawler


class IcheonCrawler(MedicalOrKrBaseCrawler):
    hospital_code = "ICHEON"
    hospital_name = "경기도의료원 이천병원"
    site_gb = "ICHEON"
    site_path = "icheon"
