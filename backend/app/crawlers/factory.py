"""크롤러 팩토리

- AMC: 전용 httpx 크롤러 (빠르고 안정적)
- 그 외: Playwright 범용 크롤러
"""
from app.crawlers.playwright_engine import PlaywrightCrawler, HOSPITAL_CONFIGS
from app.crawlers.asan_crawler import AsanCrawler
from app.crawlers.snuh_crawler import SnuhCrawler
from app.crawlers.cmcseoul_crawler import CmcseoulCrawler


def get_crawler(hospital_code: str):
    """병원 코드에 해당하는 크롤러 반환"""
    code = hospital_code.upper()

    if code == "AMC":
        return AsanCrawler()
    if code == "SNUH":
        return SnuhCrawler()
    if code == "CMCSEOUL":
        return CmcseoulCrawler()

    config = HOSPITAL_CONFIGS.get(code)
    if not config:
        raise ValueError(
            f"지원하지 않는 병원 코드: {hospital_code}. "
            f"지원 병원: ['AMC', 'SNUH'] + {list(HOSPITAL_CONFIGS.keys())}"
        )
    return PlaywrightCrawler(config)


def list_supported_hospitals() -> list[dict]:
    """지원하는 병원 목록 반환"""
    hospitals = [
        {"code": "AMC", "name": "서울아산병원"},
        {"code": "SNUH", "name": "서울대학교병원"},
        {"code": "CMCSEOUL", "name": "서울성모병원"},
    ]
    for cfg in HOSPITAL_CONFIGS.values():
        if cfg.code != "AMC":
            hospitals.append({"code": cfg.code, "name": cfg.name})
    return hospitals
