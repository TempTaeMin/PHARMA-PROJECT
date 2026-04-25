"""크롤러 팩토리

전용 httpx 크롤러:
  AMC, SNUH, CMCSEOUL, SEVERANCE, SMC,
  CMCEP, CMCYD, GANSEV, EUMCMK, EUMCSL,
  KUANAM, KUGURO, KUANSAN, KCCH, NCC,
  KUH, HYUMC, DUIH, SNUBH, KHU, KBSMC,
  CAU, CMCSV, SCHBC, AJOUMC, HALLYM, HALLYMKN, HALLYMHG,
  GIL, CMCIC, INHA, HYEMIN, GREEN, DBJE,
  NPH, VHS, KHNMC, KDH, SYMC, SMC2, BEDRO, SSHH,
  EULJINW, SGPAIK, SMGDB, CHAGN, SCHMC,
  NMC, HANIL, BESEOUL, SHH, DAEHAN, SRCH, HYJH, SERAN, BRMH,
  SUNGAE, HUIMYUNG, DONGSHIN, DRH,
  MJSM, CM, HONGIK, CGSS, GSS,
  SNMC, BUMIN, WOORIDUL, CHAMJE, ICHEON,
  ANSEONG, DAVOS, YONGIN, ASSM, MEDIFIELD, SNJA,
  SNMCC, CHABD, JESAENG, SNJUNG, GNHOSP, HYH, HALLYMDT, HYUGR,
  OSHANKOOK, JOUN, HDGH, DSWHOSP, GOODM, WILLS, WKGH,
  GGSW, PARK, PTSM, SWDS, HWAHONG, JISAM,
  SWOORI, METRO, WMCSB, CMCUJB, UPAIK, AYSAM, GGPC, UEMC,
  DAMC, KOSIN, DKUH, GNAH, DCMC, YUMC,
  KNUH, KNUHCG, JNUH, JNUHHS, UUH, DSMC,
  PNUH, PNUYH, PAIKBS,
  SCWH, CBNUH, CHNUH, YWMC,
  CUH, KYUH, JBUH,
  MIZMEDI, WKUH, GNUH2
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
from app.crawlers.hyemin_crawler import HyeminCrawler
from app.crawlers.green_crawler import GreenCrawler
from app.crawlers.dbje_crawler import DbjeCrawler
from app.crawlers.nph_crawler import NphCrawler
from app.crawlers.vhs_crawler import VhsCrawler
from app.crawlers.khnmc_crawler import KhnmcCrawler
from app.crawlers.kdh_crawler import KdhCrawler
from app.crawlers.symc_crawler import SymcCrawler
from app.crawlers.smc2_crawler import Smc2Crawler
from app.crawlers.bedro_crawler import BedroCrawler
from app.crawlers.sshh_crawler import SshhCrawler
from app.crawlers.eulji_nowon_crawler import EuljiNowonCrawler
from app.crawlers.sgpaik_crawler import SgpaikCrawler
from app.crawlers.smgdb_crawler import SmgdbCrawler
from app.crawlers.chagn_crawler import ChagnCrawler
from app.crawlers.schmc_seoul_crawler import SchmcSeoulCrawler
from app.crawlers.nmc_crawler import NmcCrawler
from app.crawlers.hanil_crawler import HanilCrawler
from app.crawlers.beseoul_crawler import BeseoulCrawler
from app.crawlers.shh_crawler import ShhCrawler
from app.crawlers.daehan_crawler import DaehanCrawler
from app.crawlers.srch_crawler import SrchCrawler
from app.crawlers.hyjh_crawler import HyjhCrawler
from app.crawlers.seran_crawler import SeranCrawler
from app.crawlers.brmh_crawler import BrmhCrawler
from app.crawlers.sungae_crawler import SungaeCrawler
from app.crawlers.huimyung_crawler import HuimyungCrawler
from app.crawlers.dongshin_crawler import DongshinCrawler
from app.crawlers.hallymkn_crawler import HallymknCrawler
from app.crawlers.hallymhg_crawler import HallymhgCrawler
from app.crawlers.drh_crawler import DrhCrawler
from app.crawlers.mjsm_crawler import MjsmCrawler
from app.crawlers.cm_crawler import CmCrawler
from app.crawlers.hongik_crawler import HongikCrawler
from app.crawlers.cgss_crawler import CgssCrawler
from app.crawlers.gss_crawler import GssCrawler
from app.crawlers.snmc_crawler import SnmcCrawler
from app.crawlers.bumin_crawler import BuminCrawler
from app.crawlers.wooridul_crawler import WooridulCrawler
from app.crawlers.chamje_crawler import ChamjeCrawler
from app.crawlers.icheon_crawler import IcheonCrawler
from app.crawlers.anseong_crawler import AnseongCrawler
from app.crawlers.davos_crawler import DavosCrawler
from app.crawlers.yongin_crawler import YonginCrawler
from app.crawlers.assm_crawler import AssmCrawler
from app.crawlers.medifield_crawler import MedifieldCrawler
from app.crawlers.snja_crawler import SnjaCrawler
from app.crawlers.snmcc_crawler import SnmccCrawler
from app.crawlers.chabd_crawler import ChabdCrawler
from app.crawlers.jesaeng_crawler import JesaengCrawler
from app.crawlers.snjung_crawler import SnjungCrawler
from app.crawlers.gnhosp_crawler import GnhospCrawler
from app.crawlers.hyh_crawler import HyhCrawler
from app.crawlers.hallymdt_crawler import HallymdtCrawler
from app.crawlers.hyugr_crawler import HyugrCrawler
from app.crawlers.oshankook_crawler import OshankookCrawler
from app.crawlers.joun_crawler import JounCrawler
from app.crawlers.hdgh_crawler import HdghCrawler
from app.crawlers.dswhosp_crawler import DswhospCrawler
from app.crawlers.goodm_crawler import GoodmCrawler
from app.crawlers.wills_crawler import WillsCrawler
from app.crawlers.wkgh_crawler import WkghCrawler
from app.crawlers.ggsw_crawler import GgswCrawler
from app.crawlers.park_crawler import ParkCrawler
from app.crawlers.ptsm_crawler import PtsmCrawler
from app.crawlers.swds_crawler import SwdsCrawler
from app.crawlers.hwahong_crawler import HwahongCrawler
from app.crawlers.jisam_crawler import JisamCrawler
from app.crawlers.swoori_crawler import SwooriCrawler
from app.crawlers.metro_crawler import MetroCrawler
from app.crawlers.wmcsb_crawler import WmcsbCrawler
from app.crawlers.cmcujb_crawler import CmcujbCrawler
from app.crawlers.upaik_crawler import UpaikCrawler
from app.crawlers.aysam_crawler import AysamCrawler
from app.crawlers.ggpc_crawler import GgpcCrawler
from app.crawlers.uemc_crawler import UemcCrawler
from app.crawlers.caugm_crawler import CaugmCrawler
from app.crawlers.gmsa_crawler import GmsaCrawler
from app.crawlers.cmcbc_crawler import CmcbcCrawler
from app.crawlers.myongji_crawler import MyongjiCrawler
from app.crawlers.nhimc_crawler import NhimcCrawler
from app.crawlers.chais_crawler import ChaisCrawler
from app.crawlers.ispaik_crawler import IspaikCrawler
from app.crawlers.sarang_crawler import SarangCrawler
from app.crawlers.danwon_crawler import DanwonCrawler
from app.crawlers.bcwoori_crawler import BcwooriCrawler
from app.crawlers.handoh_crawler import HandohCrawler
from app.crawlers.jain_crawler import JainCrawler
from app.crawlers.bcsejong_crawler import BcsejongCrawler
from app.crawlers.hsyuil_crawler import HsyuilCrawler
from app.crawlers.scsuh_crawler import ScsuhCrawler
from app.crawlers.damc_crawler import DamcCrawler
from app.crawlers.kosin_crawler import KosinCrawler
from app.crawlers.dkuh_crawler import DkuhCrawler
from app.crawlers.gnah_crawler import GnahCrawler
from app.crawlers.dcmc_crawler import DcmcCrawler
from app.crawlers.yumc_crawler import YumcCrawler
from app.crawlers.knuh_crawler import KnuhCrawler, KnuhcgCrawler
from app.crawlers.jnuh_crawler import JnuhCrawler, JnuhhsCrawler
from app.crawlers.uuh_crawler import UuhCrawler
from app.crawlers.dsmc_crawler import DsmcCrawler
from app.crawlers.pnuh_crawler import PnuhCrawler, PnuyhCrawler
from app.crawlers.paikbs_crawler import PaikbsCrawler
from app.crawlers.scwh_crawler import ScwhCrawler
from app.crawlers.cbnuh_crawler import CbnuhCrawler
from app.crawlers.chnuh_crawler import ChnuhCrawler
from app.crawlers.ywmc_crawler import YwmcCrawler
from app.crawlers.cuh_crawler import CuhCrawler
from app.crawlers.kyuh_crawler import KyuhCrawler
from app.crawlers.jbuh_crawler import JbuhCrawler
from app.crawlers.mizmedi_crawler import MizmediCrawler
from app.crawlers.wkuh_crawler import WkuhCrawler
from app.crawlers.gnuh2_crawler import Gnuh2Crawler

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
    "HYEMIN": (HyeminCrawler, "혜민병원"),
    "GREEN": (GreenCrawler, "녹색병원"),
    "DBJE": (DbjeCrawler, "동부제일병원"),
    "NPH": (NphCrawler, "경찰병원"),
    "VHS": (VhsCrawler, "중앙보훈병원"),
    "KHNMC": (KhnmcCrawler, "강동경희대학교병원"),
    "KDH": (KdhCrawler, "강동성심병원"),
    "SYMC": (SymcCrawler, "삼육서울병원"),
    "SMC2": (Smc2Crawler, "서울의료원"),
    "BEDRO": (BedroCrawler, "강남베드로병원"),
    "SSHH": (SshhCrawler, "서울성심병원"),
    "EULJINW": (EuljiNowonCrawler, "노원을지대학교병원"),
    "SGPAIK": (SgpaikCrawler, "인제대학교 상계백병원"),
    "SMGDB": (SmgdbCrawler, "서울특별시 동부병원"),
    "CHAGN": (ChagnCrawler, "강남차병원"),
    "SCHMC": (SchmcSeoulCrawler, "순천향대학교서울병원"),
    "NMC": (NmcCrawler, "국립중앙의료원"),
    "HANIL": (HanilCrawler, "한일병원"),
    "BESEOUL": (BeseoulCrawler, "베스티안서울병원"),
    "SHH": (ShhCrawler, "서울현대병원"),
    "DAEHAN": (DaehanCrawler, "대한병원"),
    "SRCH": (SrchCrawler, "서울적십자병원"),
    "HYJH": (HyjhCrawler, "에이치플러스 양지병원"),
    "SERAN": (SeranCrawler, "세란병원"),
    "BRMH": (BrmhCrawler, "서울특별시 보라매병원"),
    "SUNGAE": (SungaeCrawler, "성애병원"),
    "HUIMYUNG": (HuimyungCrawler, "희명병원"),
    "DONGSHIN": (DongshinCrawler, "동신병원"),
    "HALLYMKN": (HallymknCrawler, "한림대학교강남성심병원"),
    "HALLYMHG": (HallymhgCrawler, "한림대학교한강성심병원"),
    "DRH": (DrhCrawler, "대림성모병원"),
    "MJSM": (MjsmCrawler, "명지성모병원"),
    "CM": (CmCrawler, "CM병원"),
    "HONGIK": (HongikCrawler, "홍익병원"),
    "CGSS": (CgssCrawler, "청구성심병원"),
    "GSS": (GssCrawler, "구로성심병원"),
    "SNMC": (SnmcCrawler, "서울특별시 서남병원"),
    "BUMIN": (BuminCrawler, "서울부민병원"),
    "WOORIDUL": (WooridulCrawler, "청담 우리들병원"),
    "CHAMJE": (ChamjeCrawler, "참조은병원"),
    "ICHEON": (IcheonCrawler, "경기도의료원 이천병원"),
    "ANSEONG": (AnseongCrawler, "경기도의료원 안성병원"),
    "DAVOS": (DavosCrawler, "다보스병원"),
    "YONGIN": (YonginCrawler, "용인세브란스병원"),
    "ASSM": (AssmCrawler, "안성성모병원"),
    "MEDIFIELD": (MedifieldCrawler, "메디필드한강병원"),
    "SNJA": (SnjaCrawler, "성남중앙병원"),
    "SNMCC": (SnmccCrawler, "성남시의료원"),
    "CHABD": (ChabdCrawler, "분당차병원"),
    "JESAENG": (JesaengCrawler, "분당제생병원"),
    "SNJUNG": (SnjungCrawler, "성남정병원"),
    "GNHOSP": (GnhospCrawler, "강남병원"),
    "HYH": (HyhCrawler, "남양주한양병원"),
    "HALLYMDT": (HallymdtCrawler, "한림대학교동탄성심병원"),
    "HYUGR": (HyugrCrawler, "한양대학교구리병원"),
    "OSHANKOOK": (OshankookCrawler, "오산한국병원"),
    "JOUN": (JounCrawler, "조은오산병원"),
    "HDGH": (HdghCrawler, "현대병원"),
    "DSWHOSP": (DswhospCrawler, "동수원병원"),
    "GOODM": (GoodmCrawler, "굿모닝병원"),
    "WILLS": (WillsCrawler, "윌스기념병원"),
    "WKGH": (WkghCrawler, "원광종합병원"),
    "GGSW": (GgswCrawler, "경기도의료원 수원병원"),
    "PARK": (ParkCrawler, "PMC박병원"),
    "PTSM": (PtsmCrawler, "평택성모병원"),
    "SWDS": (SwdsCrawler, "수원덕산병원"),
    "HWAHONG": (HwahongCrawler, "화홍병원"),
    "JISAM": (JisamCrawler, "효산의료재단 지샘병원"),
    "SWOORI": (SwooriCrawler, "포천우리병원"),
    "METRO": (MetroCrawler, "메트로병원"),
    "WMCSB": (WmcsbCrawler, "원광대학교산본병원"),
    "CMCUJB": (CmcujbCrawler, "의정부성모병원"),
    "UPAIK": (UpaikCrawler, "의정부백병원"),
    "AYSAM": (AysamCrawler, "안양샘병원"),
    "GGPC": (GgpcCrawler, "경기도의료원 포천병원"),
    "UEMC": (UemcCrawler, "의정부을지대학교병원"),
    "CAUGM": (CaugmCrawler, "중앙대학교광명병원"),
    "GMSA": (GmsaCrawler, "광명성애병원"),
    "CMCBC": (CmcbcCrawler, "부천성모병원"),
    "MYONGJI": (MyongjiCrawler, "명지병원"),
    "NHIMC": (NhimcCrawler, "국민건강보험공단 일산병원"),
    "CHAIS": (ChaisCrawler, "일산차병원"),
    "ISPAIK": (IspaikCrawler, "인제대학교 일산백병원"),
    "SARANG": (SarangCrawler, "사랑의병원"),
    "DANWON": (DanwonCrawler, "단원병원"),
    "BCWOORI": (BcwooriCrawler, "부천우리병원"),
    "HANDOH": (HandohCrawler, "한도병원"),
    "JAIN": (JainCrawler, "더자인병원"),
    "BCSEJONG": (BcsejongCrawler, "부천세종병원"),
    "HSYUIL": (HsyuilCrawler, "화성유일병원"),
    "SCSUH": (ScsuhCrawler, "신천연합병원"),
    "DAMC": (DamcCrawler, "동아대학교병원"),
    "KOSIN": (KosinCrawler, "고신대학교복음병원"),
    "DKUH": (DkuhCrawler, "단국대학교의과대학부속병원"),
    "GNAH": (GnahCrawler, "강릉아산병원"),
    "DCMC": (DcmcCrawler, "대구가톨릭대학교병원"),
    "YUMC": (YumcCrawler, "영남대학교병원"),
    "KNUH": (KnuhCrawler, "경북대학교병원"),
    "KNUHCG": (KnuhcgCrawler, "칠곡경북대학교병원"),
    "JNUH": (JnuhCrawler, "전남대학교병원"),
    "JNUHHS": (JnuhhsCrawler, "화순전남대학교병원"),
    "UUH": (UuhCrawler, "울산대학교병원"),
    "DSMC": (DsmcCrawler, "계명대학교동산병원"),
    "PNUH": (PnuhCrawler, "부산대학교병원"),
    "PNUYH": (PnuyhCrawler, "양산부산대학교병원"),
    "PAIKBS": (PaikbsCrawler, "인제대학교 부산백병원"),
    "SCWH": (ScwhCrawler, "삼성창원병원"),
    "CBNUH": (CbnuhCrawler, "충북대학교병원"),
    "CHNUH": (ChnuhCrawler, "충남대학교병원"),
    "YWMC": (YwmcCrawler, "원주세브란스기독병원"),
    "CUH": (CuhCrawler, "조선대학교병원"),
    "KYUH": (KyuhCrawler, "건양대학교병원"),
    "JBUH": (JbuhCrawler, "전북대학교병원"),
    "MIZMEDI": (MizmediCrawler, "미즈메디병원"),
    "WKUH": (WkuhCrawler, "원광대학교병원"),
    "GNUH2": (Gnuh2Crawler, "경상국립대학교병원"),
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
    "HYEMIN": "서울", "GREEN": "서울", "DBJE": "서울", "NPH": "서울",
    "VHS": "서울", "KHNMC": "서울", "KDH": "서울", "SYMC": "서울",
    "SMC2": "서울", "BEDRO": "서울", "SSHH": "서울", "EULJINW": "서울",
    "SGPAIK": "서울", "SMGDB": "서울", "CHAGN": "서울",
    "SCHMC": "서울", "NMC": "서울", "HANIL": "서울",
    "BESEOUL": "서울", "SHH": "서울",
    "DAEHAN": "서울", "SRCH": "서울", "HYJH": "서울",
    "SERAN": "서울", "BRMH": "서울",
    "SUNGAE": "서울", "HUIMYUNG": "서울", "DONGSHIN": "서울",
    "HALLYMKN": "서울", "HALLYMHG": "서울", "DRH": "서울",
    "MJSM": "서울", "CM": "서울", "HONGIK": "서울",
    "CGSS": "서울", "GSS": "서울",
    "SNMC": "서울", "BUMIN": "서울", "WOORIDUL": "서울",
    "CHAMJE": "경기", "ICHEON": "경기",
    "ANSEONG": "경기", "DAVOS": "경기", "YONGIN": "경기",
    "ASSM": "경기", "MEDIFIELD": "경기", "SNJA": "경기",
    "SNMCC": "경기", "CHABD": "경기", "JESAENG": "경기", "SNJUNG": "경기",
    "GNHOSP": "경기", "HYH": "경기", "HALLYMDT": "경기", "HYUGR": "경기",
    "OSHANKOOK": "경기", "JOUN": "경기", "HDGH": "경기",
    "DSWHOSP": "경기", "GOODM": "경기", "WILLS": "경기", "WKGH": "경기",
    "GGSW": "경기", "PARK": "경기", "PTSM": "경기", "SWDS": "경기",
    "HWAHONG": "경기", "JISAM": "경기",
    "SWOORI": "경기", "METRO": "경기", "WMCSB": "경기",
    "CMCUJB": "경기", "UPAIK": "경기", "AYSAM": "경기",
    "GGPC": "경기", "UEMC": "경기",
    "CAUGM": "경기", "GMSA": "경기", "CMCBC": "경기",
    "MYONGJI": "경기", "NHIMC": "경기", "CHAIS": "경기", "ISPAIK": "경기",
    "SARANG": "경기", "DANWON": "경기", "BCWOORI": "경기", "HANDOH": "경기",
    "JAIN": "경기", "BCSEJONG": "경기", "HSYUIL": "경기", "SCSUH": "인천",
    "DAMC": "부산", "KOSIN": "부산",
    "DKUH": "충남", "GNAH": "강원",
    "DCMC": "대구", "YUMC": "대구",
    "KNUH": "대구", "KNUHCG": "대구",
    "JNUH": "광주", "JNUHHS": "전남",
    "UUH": "울산", "DSMC": "대구",
    "PNUH": "부산", "PNUYH": "부산", "PAIKBS": "부산",
    "SCWH": "경남", "CBNUH": "충북", "CHNUH": "대전", "YWMC": "강원",
    "CUH": "광주", "KYUH": "대전", "JBUH": "전북",
    "MIZMEDI": "서울", "WKUH": "전북", "GNUH2": "경남",
}


# 같은 재단/네트워크 그룹 — 의사 이직 매칭 시 같은 그룹이면 강한 시그널.
# 단일 병원만 있는 재단은 그룹 등록 안 함 (자기 자신과만 매칭).
_HOSPITAL_GROUPS: dict[str, list[str]] = {
    "KU":        ["KUANAM", "KUGURO", "KUANSAN"],
    "CMC":       ["CMCSEOUL", "CMCEP", "CMCYD", "CMCSV", "CMCIC", "CMCBC", "CMCUJB"],
    "HALLYM":    ["HALLYM", "HALLYMKN", "HALLYMHG", "HALLYMDT"],
    "EUMC":      ["EUMCMK", "EUMCSL"],
    "HYUMC":     ["HYUMC", "HYUGR"],
    "PAIK":      ["SGPAIK", "ISPAIK", "UPAIK", "PAIKBS"],
    "SCH":       ["SCHBC", "SCHMC"],
    "SAMSUNG":   ["SMC", "KBSMC", "SCWH"],
    "ASAN":      ["AMC", "GNAH"],
    "SEVERANCE": ["SEVERANCE", "GANSEV", "YONGIN", "YWMC"],
    "CHA":       ["CHAGN", "CHABD", "CHAIS"],
    "CAU":       ["CAU", "CAUGM"],
    "JNUH":      ["JNUH", "JNUHHS"],
    "KNUH":      ["KNUH", "KNUHCG"],
    "PNUH":      ["PNUH", "PNUYH"],
    "WKUH":      ["WKUH", "WMCSB"],
}

# 역방향 인덱스: 병원코드 → 그룹키
_CODE_TO_GROUP: dict[str, str] = {
    code: group_key
    for group_key, codes in _HOSPITAL_GROUPS.items()
    for code in codes
}


def get_hospital_group(hospital_code: str | None) -> str | None:
    """같은 재단 그룹 키 반환. 그룹 미등록이면 None."""
    if not hospital_code:
        return None
    return _CODE_TO_GROUP.get(hospital_code.upper())


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
