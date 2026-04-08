"""크롤러 팩토리

전용 httpx 크롤러:
  AMC, SNUH, CMCSEOUL, SEVERANCE, SMC,
  CMCEP, CMCYD, GANSEV, EUMCMK, EUMCSL,
  KUANAM, KUGURO, KUANSAN, KCCH, NCC,
  KUH, HYUMC, DUIH, SNUBH, KHU, KBSMC,
  CAU, CMCSV, SCHBC, AJOUMC, HALLYM,
  GIL, CMCIC, INHA
그 외: Playwright 범용 크롤러
"""
from app.crawlers.playwright_engine import PlaywrightCrawler, HOSPITAL_CONFIGS
from app.crawlers.asan_crawler import AsanCrawler
from app.crawlers.snuh_crawler import SnuhCrawler
from app.crawlers.cmcseoul_crawler import CmcseoulCrawler
from app.crawlers.severance_crawler import SeveranceCrawler
from app.crawlers.samsung_crawler import SamsungCrawler
from app.crawlers.cmcep_crawler import CmcepCrawler
from app.crawlers.cmcyouido_crawler import CmcyouidoCrawler
from app.crawlers.gangnam_sev_crawler import GangnamSevCrawler
from app.crawlers.eumc_mokdong_crawler import EumcMokdongCrawler
from app.crawlers.eumc_seoul_crawler import EumcSeoulCrawler
from app.crawlers.kumc_anam_crawler import KumcAnamCrawler
from app.crawlers.kumc_guro_crawler import KumcGuroCrawler
from app.crawlers.kumc_ansan_crawler import KumcAnsanCrawler
from app.crawlers.kcch_crawler import KcchCrawler
from app.crawlers.ncc_crawler import NccCrawler
from app.crawlers.kuh_crawler import KuhCrawler
from app.crawlers.hyumc_crawler import HyumcCrawler
from app.crawlers.duih_crawler import DuihCrawler
from app.crawlers.snubh_crawler import SnubhCrawler
from app.crawlers.khu_crawler import KhuCrawler
from app.crawlers.kbsmc_crawler import KbsmcCrawler
from app.crawlers.cau_crawler import CauCrawler
from app.crawlers.cmcvincent_crawler import CmcvincentCrawler
from app.crawlers.schbc_crawler import SchbcCrawler
from app.crawlers.ajoumc_crawler import AjoumcCrawler
from app.crawlers.hallym_crawler import HallymCrawler
from app.crawlers.gil_crawler import GilCrawler
from app.crawlers.cmcincheon_crawler import CmcincheonCrawler
from app.crawlers.inha_crawler import InhaCrawler

# 병원 코드 → (크롤러 클래스, 병원 이름)
_DEDICATED_CRAWLERS = {
    "AMC": (AsanCrawler, "서울아산병원"),
    "SNUH": (SnuhCrawler, "서울대학교병원"),
    "CMCSEOUL": (CmcseoulCrawler, "서울성모병원"),
    "SEVERANCE": (SeveranceCrawler, "세브란스병원"),
    "SMC": (SamsungCrawler, "삼성서울병원"),
    "CMCEP": (CmcepCrawler, "은평성모병원"),
    "CMCYD": (CmcyouidoCrawler, "여의도성모병원"),
    "GANSEV": (GangnamSevCrawler, "강남세브란스병원"),
    "EUMCMK": (EumcMokdongCrawler, "이대목동병원"),
    "EUMCSL": (EumcSeoulCrawler, "이대서울병원"),
    "KUANAM": (KumcAnamCrawler, "고대안암병원"),
    "KUGURO": (KumcGuroCrawler, "고대구로병원"),
    "KUANSAN": (KumcAnsanCrawler, "고대안산병원"),
    "KCCH": (KcchCrawler, "한국원자력의학원"),
    "NCC": (NccCrawler, "국립암센터"),
    "KUH": (KuhCrawler, "건국대학교병원"),
    "HYUMC": (HyumcCrawler, "한양대병원"),
    "DUIH": (DuihCrawler, "동국대학교일산병원"),
    "SNUBH": (SnubhCrawler, "분당서울대병원"),
    "KHU": (KhuCrawler, "경희대병원"),
    "KBSMC": (KbsmcCrawler, "강북삼성병원"),
    "CAU": (CauCrawler, "중앙대병원"),
    "CMCSV": (CmcvincentCrawler, "성빈센트병원"),
    "SCHBC": (SchbcCrawler, "부천순천향병원"),
    "AJOUMC": (AjoumcCrawler, "아주대병원"),
    "HALLYM": (HallymCrawler, "한림성심병원"),
    "GIL": (GilCrawler, "길병원"),
    "CMCIC": (CmcincheonCrawler, "인천성모병원"),
    "INHA": (InhaCrawler, "인하대병원"),
}


def get_crawler(hospital_code: str):
    """병원 코드에 해당하는 크롤러 반환"""
    code = hospital_code.upper()

    entry = _DEDICATED_CRAWLERS.get(code)
    if entry:
        return entry[0]()

    config = HOSPITAL_CONFIGS.get(code)
    if not config:
        raise ValueError(
            f"지원하지 않는 병원 코드: {hospital_code}. "
            f"지원 병원: {list(_DEDICATED_CRAWLERS.keys())} + {list(HOSPITAL_CONFIGS.keys())}"
        )
    return PlaywrightCrawler(config)


# 병원 코드 → 지역
_HOSPITAL_REGION = {
    "AMC": "서울", "SNUH": "서울", "SMC": "서울", "SEVERANCE": "서울",
    "CMCSEOUL": "서울", "CMCEP": "서울", "CMCYD": "서울", "GANSEV": "서울",
    "EUMCMK": "서울", "EUMCSL": "서울", "KUANAM": "서울", "KUGURO": "서울",
    "KCCH": "서울", "KUH": "서울", "HYUMC": "서울", "KHU": "서울",
    "KBSMC": "서울", "CAU": "서울",
    "KUANSAN": "경기", "NCC": "경기", "DUIH": "경기", "SNUBH": "경기",
    "CMCSV": "경기", "SCHBC": "경기", "AJOUMC": "경기", "HALLYM": "경기",
    "GIL": "인천", "CMCIC": "인천", "INHA": "인천",
}


def list_supported_hospitals() -> list[dict]:
    """지원하는 병원 목록 반환 (지역 정보 포함)"""
    hospitals = [
        {"code": code, "name": name, "region": _HOSPITAL_REGION.get(code, "")}
        for code, (_, name) in _DEDICATED_CRAWLERS.items()
    ]
    dedicated = {h["code"] for h in hospitals}
    for cfg in HOSPITAL_CONFIGS.values():
        if cfg.code not in dedicated:
            hospitals.append({"code": cfg.code, "name": cfg.name, "region": _HOSPITAL_REGION.get(cfg.code, "")})
    return hospitals
