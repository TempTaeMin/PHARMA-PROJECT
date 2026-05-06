# 서울/경기 크롤러 1차 검증 결과

- 검증 일시: 2026-05-04 22:16:20
- 대상 지역: 강원, 경기, 경남, 광주, 대구, 대전, 부산, 서울, 울산, 인천, 전남, 전북, 충남, 충북
- 전체: **145**개 / 총 소요: 876.7s
- ✅ OK **25** / ⚠️ WARN **117** / ❌ FAIL **3**
- 수집된 의사 총합: 17,589명
- 평균 실행시간: 24.1s / 평균 스케줄 미보유 비율: 17.5%

## 전체 결과표

| 코드 | 병원명 | 지역 | 판정 | 의사 | 진료과 | 빈스케줄% | 시간(s) | 주요 이슈 |
|------|--------|------|------|------|--------|-----------|---------|-----------|
| AMC | 서울아산병원 | 서울 | ❌ FAIL | 0 | 0 | 0% | 180.0 | C1:Timeout after 180.0s |
| DCMC | 대구가톨릭대학교병원 | 대구 | ❌ FAIL | 0 | 0 | 0% | 180.0 | C1:Timeout after 180.0s |
| HYUMC | 한양대병원 | 서울 | ❌ FAIL | 0 | 0 | 0% | 180.0 | C1:Timeout after 180.0s |
| AJOUMC | 아주대병원 | 경기 | ⚠️ WARN | 357 | 42 | 33% | 63.0 | C11:일정 없음 안내 누락 117명 |
| AYSAM | 안양샘병원 | 경기 | ⚠️ WARN | 65 | 28 | 2% | 4.9 | C11:일정 없음 안내 누락 1명 |
| BCSEJONG | 부천세종병원 | 경기 | ⚠️ WARN | 86 | 27 | 30% | 37.3 | C11:일정 없음 안내 누락 26명 |
| BCWOORI | 부천우리병원 | 경기 | ⚠️ WARN | 22 | 13 | 36% | 0.7 | C11:일정 없음 안내 누락 8명 |
| BEDRO | 강남베드로병원 | 서울 | ⚠️ WARN | 36 | 17 | 11% | 0.8 | C11:일정 없음 안내 누락 4명 |
| BESEOUL | 베스티안서울병원 | 서울 | ⚠️ WARN | 8 | 4 | 38% | 1.4 | C11:일정 없음 안내 누락 3명 |
| BRMH | 서울특별시 보라매병원 | 서울 | ⚠️ WARN | 176 | 29 | 24% | 10.1 | C11:일정 없음 안내 누락 43명 |
| BUMIN | 서울부민병원 | 서울 | ⚠️ WARN | 55 | 23 | 40% | 2.8 | C11:일정 없음 안내 누락 22명 |
| CAU | 중앙대병원 | 서울 | ⚠️ WARN | 247 | 36 | 41% | 52.5 | C11:일정 없음 안내 누락 102명 |
| CAUGM | 중앙대학교광명병원 | 경기 | ⚠️ WARN | 228 | 40 | 42% | 92.0 | C11:일정 없음 안내 누락 96명 |
| CBNUH | 충북대학교병원 | 충북 | ⚠️ WARN | 192 | 46 | 28% | 5.0 | C10:공휴일에 열린 날짜별 일정 259건; C11:일정 없음 안내 누락 52명 |
| CGSS | 청구성심병원 | 서울 | ⚠️ WARN | 23 | 13 | 39% | 7.2 | C11:일정 없음 안내 누락 9명 |
| CHABD | 분당차병원 | 경기 | ⚠️ WARN | 171 | 28 | 16% | 71.5 | C11:일정 없음 안내 누락 28명 |
| CHAGN | 강남차병원 | 서울 | ⚠️ WARN | 113 | 17 | 33% | 15.6 | C11:일정 없음 안내 누락 37명 |
| CHAIS | 일산차병원 | 경기 | ⚠️ WARN | 190 | 39 | 35% | 38.5 | C11:일정 없음 안내 누락 66명 |
| CHAMJE | 참조은병원 | 경기 | ⚠️ WARN | 70 | 22 | 6% | 17.5 | C11:일정 없음 안내 누락 4명 |
| CHNUH | 충남대학교병원 | 대전 | ⚠️ WARN | 259 | 34 | 9% | 8.1 | C8:격주 근무인데 notes 미반영 4명; C10:공휴일에 열린 날짜별 일정 538건; C11:일정 ... |
| CM | CM병원 | 서울 | ⚠️ WARN | 25 | 17 | 24% | 1.2 | C11:일정 없음 안내 누락 6명 |
| CMCBC | 부천성모병원 | 경기 | ⚠️ WARN | 0 | 0 | 0% | 0.1 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| CMCEP | 은평성모병원 | 서울 | ⚠️ WARN | 0 | 0 | 0% | 0.1 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| CMCIC | 인천성모병원 | 인천 | ⚠️ WARN | 263 | 38 | 36% | 40.1 | C11:일정 없음 안내 누락 95명 |
| CMCSEOUL | 서울성모병원 | 서울 | ⚠️ WARN | 0 | 0 | 0% | 0.1 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| CMCSV | 성빈센트병원 | 경기 | ⚠️ WARN | 0 | 0 | 0% | 0.8 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| CMCUJB | 의정부성모병원 | 경기 | ⚠️ WARN | 0 | 0 | 0% | 0.1 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| CMCYD | 여의도성모병원 | 서울 | ⚠️ WARN | 0 | 0 | 0% | 0.1 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| CUH | 조선대학교병원 | 광주 | ⚠️ WARN | 178 | 32 | 24% | 3.9 | C11:일정 없음 안내 누락 36명 |
| DAEHAN | 대한병원 | 서울 | ⚠️ WARN | 12 | 8 | 17% | 0.2 | C11:일정 없음 안내 누락 2명 |
| DAMC | 동아대학교병원 | 부산 | ⚠️ WARN | 138 | 35 | 24% | 11.4 | C10:공휴일에 열린 날짜별 일정 250건; C11:일정 없음 안내 누락 33명 |
| DANWON | 단원병원 | 경기 | ⚠️ WARN | 58 | 25 | 3% | 1.7 | C11:일정 없음 안내 누락 2명 |
| DKUH | 단국대학교의과대학부속병원 | 충남 | ⚠️ WARN | 209 | 34 | 12% | 12.3 | C10:공휴일에 열린 날짜별 일정 683건; C11:일정 없음 안내 누락 23명 |
| DRH | 대림성모병원 | 서울 | ⚠️ WARN | 39 | 17 | 26% | 19.7 | C11:일정 없음 안내 누락 10명 |
| DSMC | 계명대학교동산병원 | 대구 | ⚠️ WARN | 266 | 42 | 3% | 36.3 | C10:공휴일에 열린 날짜별 일정 755건; C11:일정 없음 안내 누락 8명 |
| DSWHOSP | 동수원병원 | 경기 | ⚠️ WARN | 0 | 0 | 0% | 7.6 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| DUIH | 동국대학교일산병원 | 경기 | ⚠️ WARN | 105 | 28 | 4% | 0.5 | C11:일정 없음 안내 누락 4명 |
| EULJINW | 노원을지대학교병원 | 서울 | ⚠️ WARN | 134 | 32 | 14% | 4.4 | C11:일정 없음 안내 누락 19명 |
| EUMCMK | 이대목동병원 | 서울 | ⚠️ WARN | 186 | 34 | 6% | 154.3 | C11:일정 없음 안내 누락 12명 |
| EUMCSL | 이대서울병원 | 서울 | ⚠️ WARN | 180 | 29 | 3% | 166.2 | C11:일정 없음 안내 누락 5명 |
| GANSEV | 강남세브란스병원 | 서울 | ⚠️ WARN | 0 | 0 | 0% | 21.1 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| GIL | 길병원 | 인천 | ⚠️ WARN | 300 | 35 | 35% | 7.5 | C11:일정 없음 안내 누락 104명 |
| GMSA | 광명성애병원 | 경기 | ⚠️ WARN | 73 | 28 | 14% | 5.1 | C11:일정 없음 안내 누락 10명 |
| GNAH | 강릉아산병원 | 강원 | ⚠️ WARN | 148 | 33 | 27% | 15.2 | C11:일정 없음 안내 누락 40명 |
| GNHOSP | 강남병원 | 경기 | ⚠️ WARN | 47 | 20 | 4% | 5.0 | C11:일정 없음 안내 누락 2명 |
| GNUH2 | 경상국립대학교병원 | 경남 | ⚠️ WARN | 188 | 46 | 20% | 59.4 | C11:일정 없음 안내 누락 37명 |
| GOODM | 굿모닝병원 | 경기 | ⚠️ WARN | 76 | 29 | 37% | 7.0 | C11:일정 없음 안내 누락 28명 |
| GSS | 구로성심병원 | 서울 | ⚠️ WARN | 35 | 20 | 49% | 2.1 | C11:일정 없음 안내 누락 17명 |
| HANIL | 한일병원 | 서울 | ⚠️ WARN | 92 | 29 | 42% | 1.0 | C11:일정 없음 안내 누락 39명 |
| HSYUIL | 화성유일병원 | 경기 | ⚠️ WARN | 5 | 0 | 100% | 0.8 | C3:진료과 0개; C6:스케줄 없는 의사 100% (5/5); C11:일정 없음 안내 누락 5명 |
| HWAHONG | 화홍병원 | 경기 | ⚠️ WARN | 66 | 24 | 41% | 2.6 | C11:일정 없음 안내 누락 27명 |
| HYEMIN | 혜민병원 | 서울 | ⚠️ WARN | 43 | 22 | 19% | 0.6 | C11:일정 없음 안내 누락 8명 |
| HYH | 남양주한양병원 | 경기 | ⚠️ WARN | 35 | 20 | 37% | 7.1 | C11:일정 없음 안내 누락 13명 |
| HYJH | 에이치플러스 양지병원 | 서울 | ⚠️ WARN | 69 | 22 | 30% | 2.5 | C11:일정 없음 안내 누락 3명 |
| HYUGR | 한양대학교구리병원 | 경기 | ⚠️ WARN | 81 | 20 | 43% | 176.5 | C10:공휴일에 열린 날짜별 일정 117건; C11:일정 없음 안내 누락 35명 |
| INHA | 인하대병원 | 인천 | ⚠️ WARN | 270 | 35 | 33% | 16.5 | C11:일정 없음 안내 누락 90명 |
| ISPAIK | 인제대학교 일산백병원 | 경기 | ⚠️ WARN | 317 | 70 | 18% | 2.2 | C11:일정 없음 안내 누락 57명 |
| JAIN | 더자인병원 | 경기 | ⚠️ WARN | 32 | 15 | 25% | 0.6 | C11:일정 없음 안내 누락 8명 |
| JBUH | 전북대학교병원 | 전북 | ⚠️ WARN | 241 | 42 | 24% | 19.0 | C11:일정 없음 안내 누락 55명 |
| JESAENG | 분당제생병원 | 경기 | ⚠️ WARN | 123 | 32 | 28% | 10.5 | C11:일정 없음 안내 누락 34명 |
| JISAM | 효산의료재단 지샘병원 | 경기 | ⚠️ WARN | 89 | 35 | 8% | 23.5 | C10:공휴일에 열린 날짜별 일정 251건; C11:일정 없음 안내 누락 7명 |
| JNUH | 전남대학교병원 | 광주 | ⚠️ WARN | 258 | 41 | 39% | 7.0 | C11:일정 없음 안내 누락 100명 |
| JNUHHS | 화순전남대학교병원 | 전남 | ⚠️ WARN | 148 | 35 | 30% | 7.1 | C11:일정 없음 안내 누락 45명 |
| JOUN | 조은오산병원 | 경기 | ⚠️ WARN | 42 | 16 | 7% | 8.2 | C11:일정 없음 안내 누락 3명 |
| KBSMC | 강북삼성병원 | 서울 | ⚠️ WARN | 413 | 37 | 42% | 52.0 | C10:공휴일에 열린 날짜별 일정 212건; C11:일정 없음 안내 누락 172명 |
| KCCH | 한국원자력의학원 | 서울 | ⚠️ WARN | 100 | 29 | 25% | 60.4 | C11:일정 없음 안내 누락 25명 |
| KDH | 강동성심병원 | 서울 | ⚠️ WARN | 140 | 30 | 26% | 7.7 | C11:일정 없음 안내 누락 36명 |
| KHNMC | 강동경희대학교병원 | 서울 | ⚠️ WARN | 194 | 31 | 30% | 6.5 | C11:일정 없음 안내 누락 59명 |
| KHU | 경희대병원 | 서울 | ⚠️ WARN | 211 | 38 | 20% | 50.1 | C11:일정 없음 안내 누락 41명 |
| KNUH | 경북대학교병원 | 대구 | ⚠️ WARN | 231 | 41 | 0% | 8.5 | C10:공휴일에 열린 날짜별 일정 517건 |
| KNUHCG | 칠곡경북대학교병원 | 대구 | ⚠️ WARN | 197 | 51 | 0% | 13.2 | C10:공휴일에 열린 날짜별 일정 455건 |
| KOSIN | 고신대학교복음병원 | 부산 | ⚠️ WARN | 194 | 41 | 24% | 0.8 | C11:일정 없음 안내 누락 46명 |
| KUANAM | 고대안암병원 | 서울 | ⚠️ WARN | 182 | 32 | 12% | 92.2 | C10:공휴일에 열린 날짜별 일정 1건; C11:일정 없음 안내 누락 22명 |
| KUANSAN | 고대안산병원 | 경기 | ⚠️ WARN | 128 | 25 | 16% | 25.5 | C10:공휴일에 열린 날짜별 일정 4건; C11:일정 없음 안내 누락 20명 |
| KUGURO | 고대구로병원 | 서울 | ⚠️ WARN | 163 | 34 | 15% | 91.9 | C10:공휴일에 열린 날짜별 일정 7건; C11:일정 없음 안내 누락 25명 |
| KUH | 건국대학교병원 | 서울 | ⚠️ WARN | 252 | 34 | 30% | 125.4 | C10:공휴일에 열린 날짜별 일정 9건; C11:일정 없음 안내 누락 76명 |
| KYUH | 건양대학교병원 | 대전 | ⚠️ WARN | 170 | 34 | 34% | 70.9 | C10:공휴일에 열린 날짜별 일정 287건; C11:일정 없음 안내 누락 49명 |
| MEDIFIELD | 메디필드한강병원 | 경기 | ⚠️ WARN | 1 | 1 | 0% | 0.0 | C2:의사 수 부족 (1명) |
| METRO | 메트로병원 | 경기 | ⚠️ WARN | 0 | 0 | 0% | 1.1 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| MIZMEDI | 미즈메디병원 | 서울 | ⚠️ WARN | 78 | 14 | 42% | 36.6 | C11:일정 없음 안내 누락 7명 |
| MYONGJI | 명지병원 | 경기 | ⚠️ WARN | 160 | 34 | 31% | 17.4 | C11:일정 없음 안내 누락 49명 |
| NHIMC | 국민건강보험공단 일산병원 | 경기 | ⚠️ WARN | 252 | 37 | 50% | 51.1 | C10:공휴일에 열린 날짜별 일정 21건; C11:일정 없음 안내 누락 125명 |
| NPH | 경찰병원 | 서울 | ⚠️ WARN | 67 | 29 | 13% | 1.4 | C11:일정 없음 안내 누락 9명 |
| OSHANKOOK | 오산한국병원 | 경기 | ⚠️ WARN | 51 | 23 | 16% | 5.4 | C11:일정 없음 안내 누락 8명 |
| PAIKBS | 인제대학교 부산백병원 | 부산 | ⚠️ WARN | 361 | 75 | 11% | 2.6 | C11:일정 없음 안내 누락 39명 |
| PNUH | 부산대학교병원 | 부산 | ⚠️ WARN | 429 | 51 | 27% | 20.9 | C11:일정 없음 안내 누락 115명 |
| PNUYH | 양산부산대학교병원 | 부산 | ⚠️ WARN | 231 | 29 | 29% | 6.0 | C11:일정 없음 안내 누락 68명 |
| PTSM | 평택성모병원 | 경기 | ⚠️ WARN | 69 | 23 | 42% | 13.2 | C11:일정 없음 안내 누락 29명 |
| SARANG | 사랑의병원 | 경기 | ⚠️ WARN | 41 | 12 | 29% | 0.7 | C11:일정 없음 안내 누락 12명 |
| SCHBC | 부천순천향병원 | 경기 | ⚠️ WARN | 240 | 37 | 30% | 145.6 | C10:공휴일에 열린 날짜별 일정 89건; C11:일정 없음 안내 누락 73명 |
| SCHMC | 순천향대학교서울병원 | 서울 | ⚠️ WARN | 247 | 36 | 33% | 148.3 | C10:공휴일에 열린 날짜별 일정 137건; C11:일정 없음 안내 누락 81명 |
| SCSUH | 신천연합병원 | 인천 | ⚠️ WARN | 16 | 12 | 6% | 6.7 | C10:공휴일에 열린 날짜별 일정 37건; C11:일정 없음 안내 누락 1명 |
| SCWH | 삼성창원병원 | 경남 | ⚠️ WARN | 176 | 34 | 32% | 12.1 | C10:공휴일에 열린 날짜별 일정 89건; C11:일정 없음 안내 누락 56명 |
| SGPAIK | 인제대학교 상계백병원 | 서울 | ⚠️ WARN | 237 | 67 | 18% | 2.0 | C11:일정 없음 안내 누락 43명 |
| SHH | 서울현대병원 | 서울 | ⚠️ WARN | 22 | 13 | 18% | 0.2 | C11:일정 없음 안내 누락 4명 |
| SMC | 삼성서울병원 | 서울 | ⚠️ WARN | 729 | 57 | 40% | 43.7 | C11:일정 없음 안내 누락 293명 |
| SMC2 | 서울의료원 | 서울 | ⚠️ WARN | 160 | 37 | 27% | 4.1 | C11:일정 없음 안내 누락 43명 |
| SMGDB | 서울특별시 동부병원 | 서울 | ⚠️ WARN | 28 | 16 | 11% | 0.2 | C11:일정 없음 안내 누락 3명 |
| SNJA | 성남중앙병원 | 경기 | ⚠️ WARN | 0 | 0 | 0% | 0.0 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| SNMC | 서울특별시 서남병원 | 서울 | ⚠️ WARN | 39 | 22 | 10% | 4.6 | C11:일정 없음 안내 누락 4명 |
| SNMCC | 성남시의료원 | 경기 | ⚠️ WARN | 0 | 0 | 0% | 15.3 | C2:의사 수 부족 (0명); C3:진료과 0개 |
| SNUBH | 분당서울대병원 | 경기 | ⚠️ WARN | 395 | 30 | 2% | 9.3 | C11:일정 없음 안내 누락 4명 |
| SNUH | 서울대학교병원 | 서울 | ⚠️ WARN | 482 | 91 | 2% | 2.0 | C11:일정 없음 안내 누락 7명 |
| SRCH | 서울적십자병원 | 서울 | ⚠️ WARN | 41 | 24 | 5% | 8.2 | C11:일정 없음 안내 누락 2명 |
| SSHH | 서울성심병원 | 서울 | ⚠️ WARN | 29 | 12 | 7% | 0.2 | C11:일정 없음 안내 누락 2명 |
| SUNGAE | 성애병원 | 서울 | ⚠️ WARN | 59 | 26 | 10% | 5.2 | C11:일정 없음 안내 누락 6명 |
| SWDS | 수원덕산병원 | 경기 | ⚠️ WARN | 52 | 29 | 40% | 2.0 | C11:일정 없음 안내 누락 21명 |
| SWOORI | 포천우리병원 | 경기 | ⚠️ WARN | 63 | 26 | 0% | 0.2 | C11:일정 없음 안내 누락 63명 |
| SYMC | 삼육서울병원 | 서울 | ⚠️ WARN | 89 | 30 | 18% | 0.5 | C11:일정 없음 안내 누락 16명 |
| UEMC | 의정부을지대학교병원 | 경기 | ⚠️ WARN | 173 | 39 | 9% | 3.7 | C11:일정 없음 안내 누락 15명 |
| UPAIK | 의정부백병원 | 경기 | ⚠️ WARN | 21 | 14 | 29% | 0.8 | C11:일정 없음 안내 누락 6명 |
| UUH | 울산대학교병원 | 울산 | ⚠️ WARN | 260 | 36 | 33% | 71.9 | C10:공휴일에 열린 날짜별 일정 362건; C11:일정 없음 안내 누락 59명 |
| VHS | 중앙보훈병원 | 서울 | ⚠️ WARN | 169 | 36 | 14% | 3.0 | C11:일정 없음 안내 누락 24명 |
| WILLS | 윌스기념병원 | 경기 | ⚠️ WARN | 92 | 23 | 24% | 28.6 | C11:일정 없음 안내 누락 22명 |
| WKGH | 원광종합병원 | 경기 | ⚠️ WARN | 15 | 12 | 0% | 0.1 | C11:일정 없음 안내 누락 15명 |
| WKUH | 원광대학교병원 | 전북 | ⚠️ WARN | 158 | 38 | 31% | 17.4 | C10:공휴일에 열린 날짜별 일정 241건; C11:일정 없음 안내 누락 49명 |
| WMCSB | 원광대학교산본병원 | 경기 | ⚠️ WARN | 45 | 21 | 40% | 3.3 | C11:일정 없음 안내 누락 18명 |
| WOORIDUL | 청담 우리들병원 | 서울 | ⚠️ WARN | 28 | 9 | 46% | 18.0 | C11:일정 없음 안내 누락 13명 |
| YUMC | 영남대학교병원 | 대구 | ⚠️ WARN | 192 | 39 | 25% | 2.8 | C11:일정 없음 안내 누락 39명 |
| YWMC | 원주세브란스기독병원 | 강원 | ⚠️ WARN | 192 | 40 | 15% | 8.7 | C10:공휴일에 열린 날짜별 일정 350건; C11:일정 없음 안내 누락 28명 |
| ANSEONG | 경기도의료원 안성병원 | 경기 | ✅ OK | 24 | 15 | 0% | 4.0 | - |
| ASSM | 안성성모병원 | 경기 | ✅ OK | 28 | 15 | 0% | 1.0 | - |
| DAVOS | 다보스병원 | 경기 | ✅ OK | 37 | 17 | 30% | 3.9 | - |
| DBJE | 동부제일병원 | 서울 | ✅ OK | 17 | 6 | 0% | 0.5 | - |
| DONGSHIN | 동신병원 | 서울 | ✅ OK | 15 | 4 | 0% | 0.4 | - |
| GGPC | 경기도의료원 포천병원 | 경기 | ✅ OK | 19 | 16 | 0% | 1.4 | - |
| GGSW | 경기도의료원 수원병원 | 경기 | ✅ OK | 37 | 18 | 0% | 2.0 | - |
| GREEN | 녹색병원 | 서울 | ✅ OK | 27 | 16 | 0% | 0.4 | - |
| HALLYM | 한림성심병원 | 경기 | ✅ OK | 211 | 34 | 0% | 92.4 | - |
| HALLYMDT | 한림대학교동탄성심병원 | 경기 | ✅ OK | 199 | 31 | 0% | 66.2 | - |
| HALLYMHG | 한림대학교한강성심병원 | 서울 | ✅ OK | 22 | 9 | 0% | 5.2 | - |
| HALLYMKN | 한림대학교강남성심병원 | 서울 | ✅ OK | 163 | 30 | 0% | 54.4 | - |
| HANDOH | 한도병원 | 경기 | ✅ OK | 59 | 23 | 0% | 2.5 | - |
| HDGH | 현대병원 | 경기 | ✅ OK | 84 | 29 | 0% | 5.9 | - |
| HONGIK | 홍익병원 | 서울 | ✅ OK | 50 | 20 | 0% | 0.5 | - |
| HUIMYUNG | 희명병원 | 서울 | ✅ OK | 25 | 14 | 0% | 0.3 | - |
| ICHEON | 경기도의료원 이천병원 | 경기 | ✅ OK | 38 | 16 | 0% | 2.7 | - |
| MJSM | 명지성모병원 | 서울 | ✅ OK | 35 | 14 | 0% | 0.9 | - |
| NCC | 국립암센터 | 경기 | ✅ OK | 90 | 12 | 0% | 40.8 | - |
| NMC | 국립중앙의료원 | 서울 | ✅ OK | 87 | 27 | 0% | 9.1 | - |
| PARK | PMC박병원 | 경기 | ✅ OK | 14 | 8 | 0% | 2.8 | - |
| SERAN | 세란병원 | 서울 | ✅ OK | 12 | 2 | 0% | 0.4 | - |
| SEVERANCE | 세브란스병원 | 서울 | ✅ OK | 395 | 40 | 0% | 7.4 | - |
| SNJUNG | 성남정병원 | 경기 | ✅ OK | 23 | 11 | 0% | 9.7 | - |
| YONGIN | 용인세브란스병원 | 경기 | ✅ OK | 245 | 47 | 0% | 5.2 | - |

## ❌ FAIL 상세

### 서울아산병원 (AMC) — 서울
- 원인: `Timeout after 180.0s`
- C1: Timeout after 180.0s

### 대구가톨릭대학교병원 (DCMC) — 대구
- 원인: `Timeout after 180.0s`
- C1: Timeout after 180.0s

### 한양대병원 (HYUMC) — 서울
- 원인: `Timeout after 180.0s`
- C1: Timeout after 180.0s

## ⚠️ WARN 상세

### 아주대병원 (AJOUMC) — 경기
- 의사 357명, 진료과 42개, 실행 63.0s
- C11: 일정 없음 안내 누락 117명
  - 샘플(최대 5개):
    - `{'doctor': '김규남', 'dept': '가정의학과', 'external_id': 'AJOUMC-297'}`
    - `{'doctor': '정수지', 'dept': '가정의학과', 'external_id': 'AJOUMC-708'}`
    - `{'doctor': '이석훈', 'dept': '가정의학과', 'external_id': 'AJOUMC-520'}`
    - `{'doctor': '김영롱', 'dept': '감염내과', 'external_id': 'AJOUMC-549'}`
    - `{'doctor': '유진세', 'dept': '급성기일반내과', 'external_id': 'AJOUMC-815'}`

### 안양샘병원 (AYSAM) — 경기
- 의사 65명, 진료과 28개, 실행 4.9s
- C11: 일정 없음 안내 누락 1명
  - 샘플(최대 5개):
    - `{'doctor': '이주영', 'dept': '감염내과', 'external_id': 'AYSAM-ifmedical-131'}`

### 부천세종병원 (BCSEJONG) — 경기
- 의사 86명, 진료과 27개, 실행 37.3s
- C11: 일정 없음 안내 누락 26명
  - 샘플(최대 5개):
    - `{'doctor': '이영비', 'dept': '가정의학과', 'external_id': 'BCSEJONG-2230000000-20110022'}`
    - `{'doctor': '민경범', 'dept': '마취통증의학과', 'external_id': 'BCSEJONG-2090000000-20240208'}`
    - `{'doctor': '박종광', 'dept': '마취통증의학과', 'external_id': 'BCSEJONG-2090000000-20240633'}`
    - `{'doctor': '윤태균', 'dept': '마취통증의학과', 'external_id': 'BCSEJONG-2090000000-20180052'}`
    - `{'doctor': '박재영', 'dept': '병리과', 'external_id': 'BCSEJONG-2210000000-20170645'}`

### 부천우리병원 (BCWOORI) — 경기
- 의사 22명, 진료과 13개, 실행 0.7s
- C11: 일정 없음 안내 누락 8명
  - 샘플(최대 5개):
    - `{'doctor': '황주철', 'dept': '내과', 'external_id': 'BCWOORI-70025cc45a'}`
    - `{'doctor': '이건우', 'dept': '내과', 'external_id': 'BCWOORI-682ca3fc1b'}`
    - `{'doctor': '이승철', 'dept': '응급실', 'external_id': 'BCWOORI-db74c545fa'}`
    - `{'doctor': '전진욱', 'dept': '응급실', 'external_id': 'BCWOORI-33aab556fc'}`
    - `{'doctor': '이태윤', 'dept': '영상의학과', 'external_id': 'BCWOORI-80b776e00c'}`

### 강남베드로병원 (BEDRO) — 서울
- 의사 36명, 진료과 17개, 실행 0.8s
- C11: 일정 없음 안내 누락 4명
  - 샘플(최대 5개):
    - `{'doctor': '김재웅', 'dept': '신경외과', 'external_id': 'BEDRO-1-5'}`
    - `{'doctor': '이종진', 'dept': '마취통증의학과', 'external_id': 'BEDRO-14-2'}`
    - `{'doctor': '지슬기', 'dept': '마취통증의학과', 'external_id': 'BEDRO-14-3'}`
    - `{'doctor': '박인경', 'dept': '마취통증의학과', 'external_id': 'BEDRO-14-4'}`

### 베스티안서울병원 (BESEOUL) — 서울
- 의사 8명, 진료과 4개, 실행 1.4s
- C11: 일정 없음 안내 누락 3명
  - 샘플(최대 5개):
    - `{'doctor': '조진경', 'dept': '소아화상', 'external_id': 'BESEOUL-child-72c54df6'}`
    - `{'doctor': '윤천재', 'dept': '화상외과', 'external_id': 'BESEOUL-adult-d9a05c96'}`
    - `{'doctor': '이종구', 'dept': '화상재건', 'external_id': 'BESEOUL-recon-95c31b17'}`

### 서울특별시 보라매병원 (BRMH) — 서울
- 의사 176명, 진료과 29개, 실행 10.1s
- C11: 일정 없음 안내 누락 43명
  - 샘플(최대 5개):
    - `{'doctor': '김대식', 'dept': '공공의학과', 'external_id': 'BRMH-216'}`
    - `{'doctor': '임상강사1', 'dept': '내분비대사내과', 'external_id': 'BRMH-252'}`
    - `{'doctor': '김재우', 'dept': '성형외과', 'external_id': 'BRMH-473'}`
    - `{'doctor': '최지은', 'dept': '소아청소년과', 'external_id': 'BRMH-367'}`
    - `{'doctor': '김혜진', 'dept': '소아청소년과', 'external_id': 'BRMH-504'}`

### 서울부민병원 (BUMIN) — 서울
- 의사 55명, 진료과 23개, 실행 2.8s
- C11: 일정 없음 안내 누락 22명
  - 샘플(최대 5개):
    - `{'doctor': '양희진', 'dept': '인공신장센터', 'external_id': 'BUMIN-4-198'}`
    - `{'doctor': '안현준', 'dept': '부민 라이프케어센터 서울', 'external_id': 'BUMIN-5-415'}`
    - `{'doctor': '김동훈', 'dept': '부민 라이프케어센터 서울', 'external_id': 'BUMIN-5-418'}`
    - `{'doctor': '김정현', 'dept': '부민 라이프케어센터 서울', 'external_id': 'BUMIN-5-420'}`
    - `{'doctor': '최욱열', 'dept': '부민 라이프케어센터 서울', 'external_id': 'BUMIN-5-454'}`

### 중앙대병원 (CAU) — 서울
- 의사 247명, 진료과 36개, 실행 52.5s
- C11: 일정 없음 안내 누락 102명
  - 샘플(최대 5개):
    - `{'doctor': '강신혁', 'dept': '성형외과', 'external_id': 'CAU-01361'}`
    - `{'doctor': '강정우', 'dept': '소아청소년과', 'external_id': 'CAU-01894'}`
    - `{'doctor': '강현', 'dept': '마취통증의학과', 'external_id': 'CAU-00864'}`
    - `{'doctor': '고미희', 'dept': '응급의학과', 'external_id': 'CAU-01820'}`
    - `{'doctor': '고재현', 'dept': '정형외과', 'external_id': 'CAU-01987'}`

### 중앙대학교광명병원 (CAUGM) — 경기
- 의사 228명, 진료과 40개, 실행 92.0s
- C11: 일정 없음 안내 누락 96명
  - 샘플(최대 5개):
    - `{'doctor': '강세진', 'dept': '마취통증의학과', 'external_id': 'CAUGM-85-1201-01806'}`
    - `{'doctor': '강수연', 'dept': '응급의학과', 'external_id': 'CAUGM-86-952-01528'}`
    - `{'doctor': '강지영', 'dept': '소하검진센터', 'external_id': 'CAUGM-118-1185-01776'}`
    - `{'doctor': '강흥식', 'dept': '영상의학과', 'external_id': 'CAUGM-114-1031-01602'}`
    - `{'doctor': '고은별', 'dept': '입원내과', 'external_id': 'CAUGM-88-1259-01905'}`

### 충북대학교병원 (CBNUH) — 충북
- 의사 192명, 진료과 46개, 실행 5.0s
- C10: 공휴일에 열린 날짜별 일정 259건
  - 샘플(최대 5개):
    - `{'doctor': '정혜원', 'dept': '감염내과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '정혜원', 'dept': '감염내과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김희성', 'dept': '감염내과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김희성', 'dept': '감염내과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '오태근', 'dept': '내분비내과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 52명
  - 샘플(최대 5개):
    - `{'doctor': '강민규', 'dept': '알레르기내과', 'external_id': 'CBNUH-34'}`
    - `{'doctor': '김희경', 'dept': '혈액종양내과', 'external_id': 'CBNUH-38'}`
    - `{'doctor': '신윤미', 'dept': '호흡기내과', 'external_id': 'CBNUH-46'}`
    - `{'doctor': '김상태', 'dept': '마취통증의학과', 'external_id': 'CBNUH-82'}`
    - `{'doctor': '배진호', 'dept': '마취통증의학과', 'external_id': 'CBNUH-83'}`

### 청구성심병원 (CGSS) — 서울
- 의사 23명, 진료과 13개, 실행 7.2s
- C11: 일정 없음 안내 누락 9명
  - 샘플(최대 5개):
    - `{'doctor': '백승원', 'dept': '응급의학과', 'external_id': 'CGSS-61'}`
    - `{'doctor': '문지형', 'dept': '응급의학과', 'external_id': 'CGSS-27184'}`
    - `{'doctor': '박도영', 'dept': '응급의학과', 'external_id': 'CGSS-45588'}`
    - `{'doctor': '유재영', 'dept': '응급의학과', 'external_id': 'CGSS-44174'}`
    - `{'doctor': '최희령', 'dept': '마취통증의학과', 'external_id': 'CGSS-66'}`

### 분당차병원 (CHABD) — 경기
- 의사 171명, 진료과 28개, 실행 71.5s
- C11: 일정 없음 안내 누락 28명
  - 샘플(최대 5개):
    - `{'doctor': '고광현', 'dept': '소화기내과', 'external_id': 'CHABD-Gastroenterology_AA11361'}`
    - `{'doctor': '권창일', 'dept': '소화기내과', 'external_id': 'CHABD-Gastroenterology_AA11681'}`
    - `{'doctor': '신석표', 'dept': '소화기내과', 'external_id': 'CHABD-Gastroenterology_AA13531'}`
    - `{'doctor': '성민제', 'dept': '소화기내과', 'external_id': 'CHABD-Gastroenterology_AA13231'}`
    - `{'doctor': '유지훈', 'dept': '소화기내과', 'external_id': 'CHABD-Gastroenterology_26022705'}`

### 강남차병원 (CHAGN) — 서울
- 의사 113명, 진료과 17개, 실행 15.6s
- C11: 일정 없음 안내 누락 37명
  - 샘플(최대 5개):
    - `{'doctor': '남수경', 'dept': '소아청소년과', 'external_id': 'CHAGN-pediatrics-p2445'}`
    - `{'doctor': '김호', 'dept': '소아청소년과', 'external_id': 'CHAGN-pediatrics-p2646'}`
    - `{'doctor': '방은치', 'dept': '마취통증의학과', 'external_id': 'CHAGN-list/anesthesia-p276'}`
    - `{'doctor': '김명옥', 'dept': '마취통증의학과', 'external_id': 'CHAGN-list/anesthesia-p2277'}`
    - `{'doctor': '강용인', 'dept': '마취통증의학과', 'external_id': 'CHAGN-list/anesthesia-p274'}`

### 일산차병원 (CHAIS) — 경기
- 의사 190명, 진료과 39개, 실행 38.5s
- C11: 일정 없음 안내 누락 66명
  - 샘플(최대 5개):
    - `{'doctor': '김지윤', 'dept': '소화기내과', 'external_id': 'CHAIS-department_gastroenterology-p2615'}`
    - `{'doctor': '이창진', 'dept': '소아청소년과', 'external_id': 'CHAIS-department_pediatrics-12341243'}`
    - `{'doctor': '이원석', 'dept': '소아청소년과', 'external_id': 'CHAIS-department_pediatrics-AG24121'}`
    - `{'doctor': '이근무', 'dept': '소아청소년과', 'external_id': 'CHAIS-department_pediatrics-IL0062'}`
    - `{'doctor': '이흔지', 'dept': '소아청소년과', 'external_id': 'CHAIS-department_pediatrics-20240229'}`

### 참조은병원 (CHAMJE) — 경기
- 의사 70명, 진료과 22개, 실행 17.5s
- C11: 일정 없음 안내 누락 4명
  - 샘플(최대 5개):
    - `{'doctor': '이태규', 'dept': '마취통증의학과', 'external_id': 'CHAMJE-74'}`
    - `{'doctor': '박슬기', 'dept': '마취통증의학과', 'external_id': 'CHAMJE-73'}`
    - `{'doctor': '정승환', 'dept': '마취통증의학과', 'external_id': 'CHAMJE-75'}`
    - `{'doctor': '오쌍용', 'dept': '소화기내과', 'external_id': 'CHAMJE-32'}`

### 충남대학교병원 (CHNUH) — 대전
- 의사 259명, 진료과 34개, 실행 8.1s
- C8: 격주 근무인데 notes 미반영 4명
  - 샘플(최대 5개):
    - `{'doctor': '안소영', 'dept': '재활의학과'}`
    - `{'doctor': '최자영', 'dept': '재활의학과'}`
    - `{'doctor': '김상범', 'dept': '정형외과'}`
    - `{'doctor': '윤자영', 'dept': '정형외과'}`
- C10: 공휴일에 열린 날짜별 일정 538건
  - 샘플(최대 5개):
    - `{'doctor': '김성수', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김성수', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김성수', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김성수', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김성수', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 17명
  - 샘플(최대 5개):
    - `{'doctor': '신용섭', 'dept': '마취통증의학과', 'external_id': 'CHNUH-DC00000065'}`
    - `{'doctor': '최아영', 'dept': '소아청소년과', 'external_id': 'CHNUH-H000164918'}`
    - `{'doctor': '김병찬', 'dept': '소아청소년과', 'external_id': 'CHNUH-H000170538'}`
    - `{'doctor': '오락균', 'dept': '외과', 'external_id': 'CHNUH-H000188504'}`
    - `{'doctor': '유인술', 'dept': '응급의학과', 'external_id': 'CHNUH-DC00000106'}`

### CM병원 (CM) — 서울
- 의사 25명, 진료과 17개, 실행 1.2s
- C11: 일정 없음 안내 누락 6명
  - 샘플(최대 5개):
    - `{'doctor': '유성열', 'dept': '마취통증의학과', 'external_id': 'CM-21'}`
    - `{'doctor': '최승연', 'dept': '마취통증의학과', 'external_id': 'CM-52'}`
    - `{'doctor': '김동오', 'dept': '영상의학과', 'external_id': 'CM-23'}`
    - `{'doctor': '황수연', 'dept': '영상의학과', 'external_id': 'CM-53'}`
    - `{'doctor': '양성은', 'dept': '진단검사의학과', 'external_id': 'CM-25'}`

### 부천성모병원 (CMCBC) — 경기
- 의사 0명, 진료과 0개, 실행 0.1s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 은평성모병원 (CMCEP) — 서울
- 의사 0명, 진료과 0개, 실행 0.1s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 인천성모병원 (CMCIC) — 인천
- 의사 263명, 진료과 38개, 실행 40.1s
- C11: 일정 없음 안내 누락 95명
  - 샘플(최대 5개):
    - `{'doctor': '강성희', 'dept': '마취통증의학과', 'external_id': 'CMCIC-54'}`
    - `{'doctor': '조은정', 'dept': '마취통증의학과', 'external_id': 'CMCIC-53'}`
    - `{'doctor': '장연', 'dept': '마취통증의학과', 'external_id': 'CMCIC-12'}`
    - `{'doctor': '이영준', 'dept': '마취통증의학과', 'external_id': 'CMCIC-56'}`
    - `{'doctor': '김달아', 'dept': '마취통증의학과', 'external_id': 'CMCIC-57'}`

### 서울성모병원 (CMCSEOUL) — 서울
- 의사 0명, 진료과 0개, 실행 0.1s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 성빈센트병원 (CMCSV) — 경기
- 의사 0명, 진료과 0개, 실행 0.8s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 의정부성모병원 (CMCUJB) — 경기
- 의사 0명, 진료과 0개, 실행 0.1s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 여의도성모병원 (CMCYD) — 서울
- 의사 0명, 진료과 0개, 실행 0.1s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 조선대학교병원 (CUH) — 광주
- 의사 178명, 진료과 32개, 실행 3.9s
- C11: 일정 없음 안내 누락 36명
  - 샘플(최대 5개):
    - `{'doctor': '강다영', 'dept': '신장내과', 'external_id': 'CUH-473-1024'}`
    - `{'doctor': '안태훈', 'dept': '마취통증의학과', 'external_id': 'CUH-130-106'}`
    - `{'doctor': '정기태', 'dept': '마취통증의학과', 'external_id': 'CUH-130-201'}`
    - `{'doctor': '김동준', 'dept': '마취통증의학과', 'external_id': 'CUH-130-719'}`
    - `{'doctor': '조수연', 'dept': '마취통증의학과', 'external_id': 'CUH-130-960'}`

### 대한병원 (DAEHAN) — 서울
- 의사 12명, 진료과 8개, 실행 0.2s
- C11: 일정 없음 안내 누락 2명
  - 샘플(최대 5개):
    - `{'doctor': '이가원', 'dept': '응급의학과', 'external_id': 'DAEHAN-doctor_13'}`
    - `{'doctor': '이승재', 'dept': '응급의학과', 'external_id': 'DAEHAN-doctor_14'}`

### 동아대학교병원 (DAMC) — 부산
- 의사 138명, 진료과 35개, 실행 11.4s
- C10: 공휴일에 열린 날짜별 일정 250건
  - 샘플(최대 5개):
    - `{'doctor': '박주성', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '박주성', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '박주성', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '한성호', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '한성호', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 33명
  - 샘플(최대 5개):
    - `{'doctor': '최소론', 'dept': '마취통증의학과', 'external_id': 'DAMC-08580'}`
    - `{'doctor': '정찬종', 'dept': '마취통증의학과', 'external_id': 'DAMC-91791'}`
    - `{'doctor': '이태영', 'dept': '마취통증의학과', 'external_id': 'DAMC-24253'}`
    - `{'doctor': '나서희', 'dept': '병리과', 'external_id': 'DAMC-93768'}`
    - `{'doctor': '노미숙', 'dept': '병리과', 'external_id': 'DAMC-96370'}`

### 단원병원 (DANWON) — 경기
- 의사 58명, 진료과 25개, 실행 1.7s
- C11: 일정 없음 안내 누락 2명
  - 샘플(최대 5개):
    - `{'doctor': '조성욱', 'dept': '응급의학과', 'external_id': 'DANWON-100111-5'}`
    - `{'doctor': '김지훈', 'dept': '응급의학과', 'external_id': 'DANWON-100111-6'}`

### 단국대학교의과대학부속병원 (DKUH) — 충남
- 의사 209명, 진료과 34개, 실행 12.3s
- C10: 공휴일에 열린 날짜별 일정 683건
  - 샘플(최대 5개):
    - `{'doctor': '송일한', 'dept': '소화기내과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '송일한', 'dept': '소화기내과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '송일한', 'dept': '소화기내과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김홍자', 'dept': '소화기내과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김홍자', 'dept': '소화기내과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 23명
  - 샘플(최대 5개):
    - `{'doctor': '신현덕', 'dept': '소화기내과', 'external_id': 'DKUH-436021'}`
    - `{'doctor': '전민호', 'dept': '소화기내과', 'external_id': 'DKUH-473797'}`
    - `{'doctor': '이응수', 'dept': '소화기내과', 'external_id': 'DKUH-486815'}`
    - `{'doctor': '이명용', 'dept': '심장혈관내과', 'external_id': 'DKUH-436120'}`
    - `{'doctor': '정현경', 'dept': '내분비대사내과', 'external_id': 'DKUH-436050'}`

### 대림성모병원 (DRH) — 서울
- 의사 39명, 진료과 17개, 실행 19.7s
- C11: 일정 없음 안내 누락 10명
  - 샘플(최대 5개):
    - `{'doctor': '이소민', 'dept': '영상의학과', 'external_id': 'DRH-1-86'}`
    - `{'doctor': '박지윤', 'dept': '영상의학과', 'external_id': 'DRH-1-117'}`
    - `{'doctor': '이유경', 'dept': '영상의학과', 'external_id': 'DRH-1-142'}`
    - `{'doctor': '김하정', 'dept': '영상의학과', 'external_id': 'DRH-1-155'}`
    - `{'doctor': '최혜경', 'dept': '영상의학과', 'external_id': 'DRH-1-169'}`

### 계명대학교동산병원 (DSMC) — 대구
- 의사 266명, 진료과 42개, 실행 36.3s
- C10: 공휴일에 열린 날짜별 일정 755건
  - 샘플(최대 5개):
    - `{'doctor': '김대현', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김대현', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '서영성', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '서영성', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '서영성', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 8명
  - 샘플(최대 5개):
    - `{'doctor': '김지민', 'dept': '류마티스내과', 'external_id': 'DSMC-202'}`
    - `{'doctor': '김창현', 'dept': '신경외과', 'external_id': 'DSMC-198'}`
    - `{'doctor': '김재범', 'dept': '심장혈관흉부외과', 'external_id': 'DSMC-419'}`
    - `{'doctor': '조순영', 'dept': '안과', 'external_id': 'DSMC-515'}`
    - `{'doctor': '방승필', 'dept': '안과', 'external_id': 'DSMC-610'}`

### 동수원병원 (DSWHOSP) — 경기
- 의사 0명, 진료과 0개, 실행 7.6s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 동국대학교일산병원 (DUIH) — 경기
- 의사 105명, 진료과 28개, 실행 0.5s
- C11: 일정 없음 안내 누락 4명
  - 샘플(최대 5개):
    - `{'doctor': '김남희', 'dept': '신경과', 'external_id': 'DUIH-050178'}`
    - `{'doctor': '김예니', 'dept': '정신건강의학과', 'external_id': 'DUIH-190841'}`
    - `{'doctor': '곽범석', 'dept': '외과', 'external_id': 'DUIH-060124'}`
    - `{'doctor': '도한호', 'dept': '양한방 통합 뇌손상 집중 치료센터', 'external_id': 'DUIH-100129'}`

### 노원을지대학교병원 (EULJINW) — 서울
- 의사 134명, 진료과 32개, 실행 4.4s
- C11: 일정 없음 안내 누락 19명
  - 샘플(최대 5개):
    - `{'doctor': '신정민', 'dept': '류마티스내과', 'external_id': 'EULJINW-ABBHAA-20230286'}`
    - `{'doctor': '장혜원', 'dept': '마취통증의학과', 'external_id': 'EULJINW-ABVAAA-20190266'}`
    - `{'doctor': '조혜연', 'dept': '마취통증의학과', 'external_id': 'EULJINW-ABVAAA-20231169'}`
    - `{'doctor': '강수정', 'dept': '마취통증의학과', 'external_id': 'EULJINW-ABVAAA-20260034'}`
    - `{'doctor': '오은혜', 'dept': '소아청소년과', 'external_id': 'EULJINW-ABCAAA-20240165'}`

### 이대목동병원 (EUMCMK) — 서울
- 의사 186명, 진료과 34개, 실행 154.3s
- C11: 일정 없음 안내 누락 12명
  - 샘플(최대 5개):
    - `{'doctor': '최용주', 'dept': '마취통증의학과/통증클리닉', 'external_id': 'EUMCMK-1011398'}`
    - `{'doctor': '강보경', 'dept': '마취통증의학과/통증클리닉', 'external_id': 'EUMCMK-1011367'}`
    - `{'doctor': '박은경', 'dept': '마취통증의학과/통증클리닉', 'external_id': 'EUMCMK-1002998'}`
    - `{'doctor': '유은영', 'dept': '마취통증의학과/통증클리닉', 'external_id': 'EUMCMK-1003744'}`
    - `{'doctor': '일반의', 'dept': '산부인과', 'external_id': 'EUMCMK-9002820'}`

### 이대서울병원 (EUMCSL) — 서울
- 의사 180명, 진료과 29개, 실행 166.2s
- C11: 일정 없음 안내 누락 5명
  - 샘플(최대 5개):
    - `{'doctor': '김우신', 'dept': '내과', 'external_id': 'EUMCSL-1004184'}`
    - `{'doctor': '유경하', 'dept': '소아청소년과', 'external_id': 'EUMCSL-1001176'}`
    - `{'doctor': '박지윤', 'dept': '소아청소년과', 'external_id': 'EUMCSL-1004506'}`
    - `{'doctor': '배현경', 'dept': '소아청소년과', 'external_id': 'EUMCSL-1005699'}`
    - `{'doctor': '현동호', 'dept': '영상의학과', 'external_id': 'EUMCSL-1024213'}`

### 강남세브란스병원 (GANSEV) — 서울
- 의사 0명, 진료과 0개, 실행 21.1s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 길병원 (GIL) — 인천
- 의사 300명, 진료과 35개, 실행 7.5s
- C11: 일정 없음 안내 누락 104명
  - 샘플(최대 5개):
    - `{'doctor': '이규래', 'dept': '가정의학과', 'external_id': 'GIL-3899645'}`
    - `{'doctor': '이경천', 'dept': '마취통증의학과', 'external_id': 'GIL-57068'}`
    - `{'doctor': '정월선', 'dept': '마취통증의학과', 'external_id': 'GIL-52272'}`
    - `{'doctor': '이동철', 'dept': '마취통증의학과', 'external_id': 'GIL-52784'}`
    - `{'doctor': '곽현정', 'dept': '마취통증의학과', 'external_id': 'GIL-52847'}`

### 광명성애병원 (GMSA) — 경기
- 의사 73명, 진료과 28개, 실행 5.1s
- C11: 일정 없음 안내 누락 10명
  - 샘플(최대 5개):
    - `{'doctor': '박노원', 'dept': '가정의학과', 'external_id': 'GMSA-SH1701-DT2558'}`
    - `{'doctor': '김경채', 'dept': '건강의학센터', 'external_id': 'GMSA-SH1702-DT3137'}`
    - `{'doctor': '최봉규', 'dept': '건강의학센터', 'external_id': 'GMSA-SH1702-DT3138'}`
    - `{'doctor': '홍연표', 'dept': '건강의학센터', 'external_id': 'GMSA-SH1702-DT3193'}`
    - `{'doctor': '한미경', 'dept': '건강의학센터', 'external_id': 'GMSA-SH1702-DT3136'}`

### 강릉아산병원 (GNAH) — 강원
- 의사 148명, 진료과 33개, 실행 15.2s
- C11: 일정 없음 안내 누락 40명
  - 샘플(최대 5개):
    - `{'doctor': '성규완', 'dept': '마취통증의학과', 'external_id': 'GNAH-138'}`
    - `{'doctor': '김성수', 'dept': '마취통증의학과', 'external_id': 'GNAH-137'}`
    - `{'doctor': '정화성', 'dept': '마취통증의학과', 'external_id': 'GNAH-140'}`
    - `{'doctor': '정의균', 'dept': '마취통증의학과', 'external_id': 'GNAH-141'}`
    - `{'doctor': '김진선', 'dept': '마취통증의학과', 'external_id': 'GNAH-142'}`

### 강남병원 (GNHOSP) — 경기
- 의사 47명, 진료과 20개, 실행 5.0s
- C11: 일정 없음 안내 누락 2명
  - 샘플(최대 5개):
    - `{'doctor': '이순호', 'dept': '응급의학과', 'external_id': 'GNHOSP-19_3350'}`
    - `{'doctor': '이미진', 'dept': '달빛어린이병원', 'external_id': 'GNHOSP-24_3219'}`

### 경상국립대학교병원 (GNUH2) — 경남
- 의사 188명, 진료과 46개, 실행 59.4s
- C11: 일정 없음 안내 누락 37명
  - 샘플(최대 5개):
    - `{'doctor': '조성희', 'dept': '정형외과', 'external_id': 'GNUH2-OS-119015'}`
    - `{'doctor': '김성재', 'dept': '안과', 'external_id': 'GNUH2-EY-23605'}`
    - `{'doctor': '하인봉', 'dept': '방사선종양학과', 'external_id': 'GNUH2-RO-117037'}`
    - `{'doctor': '정진희', 'dept': '응급의학과', 'external_id': 'GNUH2-EM-113106'}`
    - `{'doctor': '성애진', 'dept': '응급의학과', 'external_id': 'GNUH2-EM-120026'}`

### 굿모닝병원 (GOODM) — 경기
- 의사 76명, 진료과 29개, 실행 7.0s
- C11: 일정 없음 안내 누락 28명
  - 샘플(최대 5개):
    - `{'doctor': '이권일', 'dept': '응급의학과', 'external_id': 'GOODM-47'}`
    - `{'doctor': '김정훈', 'dept': '응급의학과', 'external_id': 'GOODM-45'}`
    - `{'doctor': '이선범', 'dept': '응급의학과', 'external_id': 'GOODM-46'}`
    - `{'doctor': '이현재', 'dept': '응급의학과', 'external_id': 'GOODM-220'}`
    - `{'doctor': '김동욱', 'dept': '응급의학과', 'external_id': 'GOODM-203'}`

### 구로성심병원 (GSS) — 서울
- 의사 35명, 진료과 20개, 실행 2.1s
- C11: 일정 없음 안내 누락 17명
  - 샘플(최대 5개):
    - `{'doctor': '강정호', 'dept': '영상의학과', 'external_id': 'GSS-ba9a1d3d41'}`
    - `{'doctor': '곽상훈', 'dept': '응급의학과', 'external_id': 'GSS-6ad62cedd3'}`
    - `{'doctor': '김명중', 'dept': '응급의학과', 'external_id': 'GSS-7fb2c0be0b'}`
    - `{'doctor': '김병성', 'dept': '직업환경의학과', 'external_id': 'GSS-d2348b59fb'}`
    - `{'doctor': '김윤기', 'dept': '가정의학과', 'external_id': 'GSS-50e23ffd79'}`

### 한일병원 (HANIL) — 서울
- 의사 92명, 진료과 29개, 실행 1.0s
- C11: 일정 없음 안내 누락 39명
  - 샘플(최대 5개):
    - `{'doctor': '강양자', 'dept': '마취통증의학과', 'external_id': 'HANIL-19610022'}`
    - `{'doctor': '정유성', 'dept': '마취통증의학과', 'external_id': 'HANIL-19510023'}`
    - `{'doctor': '유정영', 'dept': '마취통증의학과', 'external_id': 'HANIL-21610001'}`
    - `{'doctor': '박윤선', 'dept': '마취통증의학과', 'external_id': 'HANIL-25610015'}`
    - `{'doctor': '허지혜', 'dept': '영상의학과', 'external_id': 'HANIL-17610018'}`

### 화성유일병원 (HSYUIL) — 경기
- 의사 5명, 진료과 0개, 실행 0.8s
- C3: 진료과 0개
- C6: 스케줄 없는 의사 100% (5/5)
- C11: 일정 없음 안내 누락 5명
  - 샘플(최대 5개):
    - `{'doctor': '고은정', 'dept': '', 'external_id': 'HSYUIL-9bbb83170a'}`
    - `{'doctor': '박형도', 'dept': '', 'external_id': 'HSYUIL-8f6a71c7d1'}`
    - `{'doctor': '서민우', 'dept': '', 'external_id': 'HSYUIL-eaefd58429'}`
    - `{'doctor': '홍승수', 'dept': '', 'external_id': 'HSYUIL-e42db769b0'}`
    - `{'doctor': '최창식', 'dept': '', 'external_id': 'HSYUIL-e3c8645b36'}`

### 화홍병원 (HWAHONG) — 경기
- 의사 66명, 진료과 24개, 실행 2.6s
- C11: 일정 없음 안내 누락 27명
  - 샘플(최대 5개):
    - `{'doctor': '이세호', 'dept': '응급의학과', 'external_id': 'HWAHONG-188'}`
    - `{'doctor': '전세근', 'dept': '마취통증의학과', 'external_id': 'HWAHONG-273'}`
    - `{'doctor': '박경배', 'dept': '마취통증의학과', 'external_id': 'HWAHONG-184'}`
    - `{'doctor': '이해광', 'dept': '마취통증의학과', 'external_id': 'HWAHONG-279'}`
    - `{'doctor': '이세형', 'dept': '영상의학과', 'external_id': 'HWAHONG-274'}`

### 혜민병원 (HYEMIN) — 서울
- 의사 43명, 진료과 22개, 실행 0.6s
- C11: 일정 없음 안내 누락 8명
  - 샘플(최대 5개):
    - `{'doctor': '조해선', 'dept': '마취통증의학과', 'external_id': 'HYEMIN-6df072b212'}`
    - `{'doctor': '장석환', 'dept': '영상의학과', 'external_id': 'HYEMIN-6da1acb8eb'}`
    - `{'doctor': '오병연', 'dept': '응급의학과', 'external_id': 'HYEMIN-c213854432'}`
    - `{'doctor': '전진우', 'dept': '응급의학과', 'external_id': 'HYEMIN-33c0505ed6'}`
    - `{'doctor': '박지수', 'dept': '응급의학과', 'external_id': 'HYEMIN-97d8749040'}`

### 남양주한양병원 (HYH) — 경기
- 의사 35명, 진료과 20개, 실행 7.1s
- C11: 일정 없음 안내 누락 13명
  - 샘플(최대 5개):
    - `{'doctor': '·', 'dept': '비뇨기과', 'external_id': 'HYH-14_6'}`
    - `{'doctor': '·', 'dept': '흉부혈관외과', 'external_id': 'HYH-21_14'}`
    - `{'doctor': '황인순', 'dept': '마취통증의학과', 'external_id': 'HYH-25_18'}`
    - `{'doctor': '서관용', 'dept': '진단검사의학과', 'external_id': 'HYH-26_19'}`
    - `{'doctor': '안용식', 'dept': '영상의학과', 'external_id': 'HYH-27_20'}`

### 에이치플러스 양지병원 (HYJH) — 서울
- 의사 69명, 진료과 22개, 실행 2.5s
- C11: 일정 없음 안내 누락 3명
  - 샘플(최대 5개):
    - `{'doctor': '김형건', 'dept': '', 'external_id': 'HYJH-323'}`
    - `{'doctor': '오정진', 'dept': '', 'external_id': 'HYJH-343'}`
    - `{'doctor': '민선영', 'dept': '', 'external_id': 'HYJH-257'}`

### 한양대학교구리병원 (HYUGR) — 경기
- 의사 81명, 진료과 20개, 실행 176.5s
- C10: 공휴일에 열린 날짜별 일정 117건
  - 샘플(최대 5개):
    - `{'doctor': '김지은', 'dept': '감염내과', 'date': '2026-05-24', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김지은', 'dept': '감염내과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김지은', 'dept': '감염내과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김지은', 'dept': '감염내과', 'date': '2026-06-06', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '이창범', 'dept': '내분비대사내과', 'date': '2026-05-24', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 35명
  - 샘플(최대 5개):
    - `{'doctor': '염종훈', 'dept': '마취통증의학과', 'external_id': 'HYUGR-1956874-112110'}`
    - `{'doctor': '조상윤', 'dept': '마취통증의학과', 'external_id': 'HYUGR-1961611-112110'}`
    - `{'doctor': '심재항', 'dept': '마취통증의학과', 'external_id': 'HYUGR-2011277-112110'}`
    - `{'doctor': '오미경', 'dept': '마취통증의학과', 'external_id': 'HYUGR-2137498-112110'}`
    - `{'doctor': '박형준', 'dept': '마취통증의학과', 'external_id': 'HYUGR-2226234-112110'}`

### 인하대병원 (INHA) — 인천
- 의사 270명, 진료과 35개, 실행 16.5s
- C11: 일정 없음 안내 누락 90명
  - 샘플(최대 5개):
    - `{'doctor': '송장호', 'dept': '마취통증의학과', 'external_id': 'INHA-63446'}`
    - `{'doctor': '임현경', 'dept': '마취통증의학과', 'external_id': 'INHA-63417'}`
    - `{'doctor': '정종권', 'dept': '마취통증의학과', 'external_id': 'INHA-63391'}`
    - `{'doctor': '한정욱', 'dept': '마취통증의학과', 'external_id': 'INHA-63420'}`
    - `{'doctor': '김현주', 'dept': '마취통증의학과', 'external_id': 'INHA-63349'}`

### 인제대학교 일산백병원 (ISPAIK) — 경기
- 의사 317명, 진료과 70개, 실행 2.2s
- C11: 일정 없음 안내 누락 57명
  - 샘플(최대 5개):
    - `{'doctor': '손준혁', 'dept': '간·담도·췌장암센터', 'external_id': 'ISPAIK-2287'}`
    - `{'doctor': '김경우', 'dept': '마취통증의학과', 'external_id': 'ISPAIK-648'}`
    - `{'doctor': '김준현', 'dept': '마취통증의학과', 'external_id': 'ISPAIK-1231'}`
    - `{'doctor': '김수연', 'dept': '마취통증의학과', 'external_id': 'ISPAIK-1989'}`
    - `{'doctor': '김지연', 'dept': '마취통증의학과', 'external_id': 'ISPAIK-1230'}`

### 더자인병원 (JAIN) — 경기
- 의사 32명, 진료과 15개, 실행 0.6s
- C11: 일정 없음 안내 누락 8명
  - 샘플(최대 5개):
    - `{'doctor': '서재경', 'dept': '응급센터', 'external_id': 'JAIN-114'}`
    - `{'doctor': '윤형식', 'dept': '응급센터', 'external_id': 'JAIN-110'}`
    - `{'doctor': '이선근', 'dept': '응급센터', 'external_id': 'JAIN-146'}`
    - `{'doctor': '홍성민', 'dept': '응급센터', 'external_id': 'JAIN-57'}`
    - `{'doctor': '김성훈', 'dept': '마취통증의학과', 'external_id': 'JAIN-100'}`

### 전북대학교병원 (JBUH) — 전북
- 의사 241명, 진료과 42개, 실행 19.0s
- C11: 일정 없음 안내 누락 55명
  - 샘플(최대 5개):
    - `{'doctor': '김동찬', 'dept': '마취통증의학과', 'external_id': 'JBUH-AN-08105'}`
    - `{'doctor': '고성훈', 'dept': '마취통증의학과', 'external_id': 'JBUH-AN-92221'}`
    - `{'doctor': '김덕규', 'dept': '마취통증의학과', 'external_id': 'JBUH-AN-20322'}`
    - `{'doctor': '이주환', 'dept': '마취통증의학과', 'external_id': 'JBUH-AN-26805'}`
    - `{'doctor': '이준호', 'dept': '마취통증의학과', 'external_id': 'JBUH-AN-21759'}`

### 분당제생병원 (JESAENG) — 경기
- 의사 123명, 진료과 32개, 실행 10.5s
- C11: 일정 없음 안내 누락 34명
  - 샘플(최대 5개):
    - `{'doctor': '김가현', 'dept': '마취통증의학과', 'external_id': 'JESAENG-1007130'}`
    - `{'doctor': '박주훈', 'dept': '마취통증의학과', 'external_id': 'JESAENG-1006833'}`
    - `{'doctor': '정주영', 'dept': '마취통증의학과', 'external_id': 'JESAENG-1006838'}`
    - `{'doctor': '최미영', 'dept': '마취통증의학과', 'external_id': 'JESAENG-1006988'}`
    - `{'doctor': '최현규', 'dept': '마취통증의학과', 'external_id': 'JESAENG-1006821'}`

### 효산의료재단 지샘병원 (JISAM) — 경기
- 의사 89명, 진료과 35개, 실행 23.5s
- C10: 공휴일에 열린 날짜별 일정 251건
  - 샘플(최대 5개):
    - `{'doctor': '이정호', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '이정호', 'dept': '가정의학과', 'date': '2026-06-06', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '이정호', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '조영규', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '강의규', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 7명
  - 샘플(최대 5개):
    - `{'doctor': '길호영', 'dept': '마취통증의학과', 'external_id': 'JISAM-346'}`
    - `{'doctor': '박종혁', 'dept': '신경외과', 'external_id': 'JISAM-256'}`
    - `{'doctor': '전용식', 'dept': '영상의학과', 'external_id': 'JISAM-266'}`
    - `{'doctor': '류소영', 'dept': '치과', 'external_id': 'JISAM-348'}`
    - `{'doctor': '이지연', 'dept': '혈액종양내과', 'external_id': 'JISAM-301'}`

### 전남대학교병원 (JNUH) — 광주
- 의사 258명, 진료과 41개, 실행 7.0s
- C11: 일정 없음 안내 누락 100명
  - 샘플(최대 5개):
    - `{'doctor': '정해성', 'dept': '감염내과', 'external_id': 'JNUH-IMD-ID00035'}`
    - `{'doctor': '곽한덕', 'dept': '대장항문외과', 'external_id': 'JNUH-GSA-GE00083'}`
    - `{'doctor': '강지현', 'dept': '류마티스내과', 'external_id': 'JNUH-IMR-RH00025'}`
    - `{'doctor': '윤명하', 'dept': '마취통증의학과', 'external_id': 'JNUH-AN-AN00006'}`
    - `{'doctor': '곽상현', 'dept': '마취통증의학과', 'external_id': 'JNUH-AN-AN00009'}`

### 화순전남대학교병원 (JNUHHS) — 전남
- 의사 148명, 진료과 35개, 실행 7.1s
- C11: 일정 없음 안내 누락 45명
  - 샘플(최대 5개):
    - `{'doctor': '이아랑', 'dept': '감염내과', 'external_id': 'JNUHHS-IMD-ID00034'}`
    - `{'doctor': '김희경', 'dept': '내분비대사내과', 'external_id': 'JNUHHS-IME-ED00032'}`
    - `{'doctor': '윤지희', 'dept': '내분비대사내과', 'external_id': 'JNUHHS-IME-ED00036'}`
    - `{'doctor': '이자람', 'dept': '대장항문외과', 'external_id': 'JNUHHS-GSA-GE00095'}`
    - `{'doctor': '윤명하', 'dept': '마취통증의학과', 'external_id': 'JNUHHS-AN-AN00006'}`

### 조은오산병원 (JOUN) — 경기
- 의사 42명, 진료과 16개, 실행 8.2s
- C11: 일정 없음 안내 누락 3명
  - 샘플(최대 5개):
    - `{'doctor': '정대관', 'dept': '내과', 'external_id': 'JOUN-4_doctor233-33'}`
    - `{'doctor': '이재승', 'dept': '피부비뇨의학과', 'external_id': 'JOUN-7_doctor36'}`
    - `{'doctor': '배인근', 'dept': '직업환경의학과', 'external_id': 'JOUN-17_doctor21'}`

### 강북삼성병원 (KBSMC) — 서울
- 의사 413명, 진료과 37개, 실행 52.0s
- C10: 공휴일에 열린 날짜별 일정 212건
  - 샘플(최대 5개):
    - `{'doctor': '강재헌', 'dept': '가정의학과', 'date': '2026-06-06', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '강재헌', 'dept': '가정의학과', 'date': '2026-06-06', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '배예슬', 'dept': '가정의학과', 'date': '2026-06-06', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '배예슬', 'dept': '가정의학과', 'date': '2026-06-06', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '주은정', 'dept': '감염내과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 172명
  - 샘플(최대 5개):
    - `{'doctor': '김윤홍', 'dept': '마취통증의학과', 'external_id': 'KBSMC-33-5'}`
    - `{'doctor': '오은정', 'dept': '마취통증의학과', 'external_id': 'KBSMC-434-5'}`
    - `{'doctor': '전주현', 'dept': '마취통증의학과', 'external_id': 'KBSMC-425-5'}`
    - `{'doctor': '권도희', 'dept': '병리과', 'external_id': 'KBSMC-47-7'}`
    - `{'doctor': '김한나', 'dept': '병리과', 'external_id': 'KBSMC-59-7'}`

### 한국원자력의학원 (KCCH) — 서울
- 의사 100명, 진료과 29개, 실행 60.4s
- C11: 일정 없음 안내 누락 25명
  - 샘플(최대 5개):
    - `{'doctor': '이지희', 'dept': '마취통증의학과', 'external_id': 'KCCH-9'}`
    - `{'doctor': '이수남', 'dept': '마취통증의학과', 'external_id': 'KCCH-7'}`
    - `{'doctor': '이소영', 'dept': '마취통증의학과', 'external_id': 'KCCH-85'}`
    - `{'doctor': '이지연', 'dept': '마취통증의학과', 'external_id': 'KCCH-63'}`
    - `{'doctor': '이승숙', 'dept': '병리과', 'external_id': 'KCCH-105'}`

### 강동성심병원 (KDH) — 서울
- 의사 140명, 진료과 30개, 실행 7.7s
- C11: 일정 없음 안내 누락 36명
  - 샘플(최대 5개):
    - `{'doctor': '박수연', 'dept': '내분비내과', 'external_id': 'KDH-180525'}`
    - `{'doctor': '박다희', 'dept': '소화기내과', 'external_id': 'KDH-160119'}`
    - `{'doctor': '김유선', 'dept': '소화기내과', 'external_id': 'KDH-230175'}`
    - `{'doctor': '전희중', 'dept': '신장내과', 'external_id': 'KDH-150295'}`
    - `{'doctor': '김일석', 'dept': '마취통증의학과', 'external_id': 'KDH-50361'}`

### 강동경희대학교병원 (KHNMC) — 서울
- 의사 194명, 진료과 31개, 실행 6.5s
- C11: 일정 없음 안내 누락 59명
  - 샘플(최대 5개):
    - `{'doctor': '이봉재', 'dept': '마취통증의학과', 'external_id': 'KHNMC-000129-98'}`
    - `{'doctor': '강종만', 'dept': '마취통증의학과', 'external_id': 'KHNMC-000129-99'}`
    - `{'doctor': '허협', 'dept': '마취통증의학과', 'external_id': 'KHNMC-000129-4938'}`
    - `{'doctor': '강화자', 'dept': '마취통증의학과', 'external_id': 'KHNMC-000129-24000021'}`
    - `{'doctor': '권미영', 'dept': '마취통증의학과', 'external_id': 'KHNMC-000129-25000271'}`

### 경희대병원 (KHU) — 서울
- 의사 211명, 진료과 38개, 실행 50.1s
- C11: 일정 없음 안내 누락 41명
  - 샘플(최대 5개):
    - `{'doctor': '박성욱', 'dept': '마취통증의학과', 'external_id': 'KHU-4826'}`
    - `{'doctor': '김미경', 'dept': '마취통증의학과', 'external_id': 'KHU-7890'}`
    - `{'doctor': '최정현', 'dept': '마취통증의학과', 'external_id': 'KHU-6874'}`
    - `{'doctor': '유안희', 'dept': '마취통증의학과', 'external_id': 'KHU-6802'}`
    - `{'doctor': '이상호', 'dept': '마취통증의학과', 'external_id': 'KHU-6889'}`

### 경북대학교병원 (KNUH) — 대구
- 의사 231명, 진료과 41개, 실행 8.5s
- C10: 공휴일에 열린 날짜별 일정 517건
  - 샘플(최대 5개):
    - `{'doctor': '고혜진', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '고혜진', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '박지연', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '홍희은', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '홍희은', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`

### 칠곡경북대학교병원 (KNUHCG) — 대구
- 의사 197명, 진료과 51개, 실행 13.2s
- C10: 공휴일에 열린 날짜별 일정 455건
  - 샘플(최대 5개):
    - `{'doctor': '송지은', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '송지은', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '홍희은', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '어재은', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '강수정', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`

### 고신대학교복음병원 (KOSIN) — 부산
- 의사 194명, 진료과 41개, 실행 0.8s
- C11: 일정 없음 안내 누락 46명
  - 샘플(최대 5개):
    - `{'doctor': '김미향', 'dept': '진단검사의학과', 'external_id': 'KOSIN-165'}`
    - `{'doctor': '계여곤', 'dept': '응급의학과', 'external_id': 'KOSIN-140'}`
    - `{'doctor': '조영덕', 'dept': '영상의학과', 'external_id': 'KOSIN-126'}`
    - `{'doctor': '홍유라', 'dept': '소아청소년과', 'external_id': 'KOSIN-82'}`
    - `{'doctor': '이상신', 'dept': '정신건강의학과', 'external_id': 'KOSIN-153'}`

### 고대안암병원 (KUANAM) — 서울
- 의사 182명, 진료과 32개, 실행 92.2s
- C10: 공휴일에 열린 날짜별 일정 1건
  - 샘플(최대 5개):
    - `{'doctor': '강성구', 'dept': '비뇨의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 22명
  - 샘플(최대 5개):
    - `{'doctor': '성현영', 'dept': '마취통증의학과', 'external_id': 'KUANAM-16072'}`
    - `{'doctor': '신현주', 'dept': '마취통증의학과', 'external_id': 'KUANAM-08685'}`
    - `{'doctor': '신혜원', 'dept': '마취통증의학과', 'external_id': 'KUANAM-01498'}`
    - `{'doctor': '유해선', 'dept': '마취통증의학과', 'external_id': 'KUANAM-03204'}`
    - `{'doctor': '윤승주', 'dept': '마취통증의학과', 'external_id': 'KUANAM-07B04'}`

### 고대안산병원 (KUANSAN) — 경기
- 의사 128명, 진료과 25개, 실행 25.5s
- C10: 공휴일에 열린 날짜별 일정 4건
  - 샘플(최대 5개):
    - `{'doctor': '이혜윤', 'dept': '유방내분비외과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '박진희', 'dept': '혈액종양내과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '이병현', 'dept': '혈액종양내과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '이세련', 'dept': '혈액종양내과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 20명
  - 샘플(최대 5개):
    - `{'doctor': '김운영', 'dept': '마취통증의학과', 'external_id': 'KUANSAN-01315'}`
    - `{'doctor': '김재환', 'dept': '마취통증의학과', 'external_id': 'KUANSAN-97029'}`
    - `{'doctor': '신연식', 'dept': '마취통증의학과', 'external_id': 'KUANSAN-03095'}`
    - `{'doctor': '이윤숙', 'dept': '마취통증의학과', 'external_id': 'KUANSAN-01393'}`
    - `{'doctor': '주충희', 'dept': '마취통증의학과', 'external_id': 'KUANSAN-20G31'}`

### 고대구로병원 (KUGURO) — 서울
- 의사 163명, 진료과 34개, 실행 91.9s
- C10: 공휴일에 열린 날짜별 일정 7건
  - 샘플(최대 5개):
    - `{'doctor': '신주희', 'dept': '치과보존과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '신주희', 'dept': '치과보존과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '권택현', 'dept': '신경외과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '권택현', 'dept': '신경외과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '신정호', 'dept': '산부인과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 25명
  - 샘플(최대 5개):
    - `{'doctor': '조민정', 'dept': '응급중환자외상외과', 'external_id': 'KUGURO-23467'}`
    - `{'doctor': '공명훈', 'dept': '마취통증의학과', 'external_id': 'KUGURO-91009'}`
    - `{'doctor': '김영성', 'dept': '마취통증의학과', 'external_id': 'KUGURO-09394'}`
    - `{'doctor': '김혜빈', 'dept': '마취통증의학과', 'external_id': 'KUGURO-22544'}`
    - `{'doctor': '김희주', 'dept': '마취통증의학과', 'external_id': 'KUGURO-00486'}`

### 건국대학교병원 (KUH) — 서울
- 의사 252명, 진료과 34개, 실행 125.4s
- C10: 공휴일에 열린 날짜별 일정 9건
  - 샘플(최대 5개):
    - `{'doctor': '박상오', 'dept': '응급의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '박상오', 'dept': '응급의학과', 'date': '2026-05-24', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '박상오', 'dept': '응급의학과', 'date': '2026-05-24', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '홍대영', 'dept': '응급의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '홍대영', 'dept': '응급의학과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 76명
  - 샘플(최대 5개):
    - `{'doctor': '최효선', 'dept': '건강의학과', 'external_id': 'KUH-20100154'}`
    - `{'doctor': '박소연', 'dept': '건강의학과', 'external_id': 'KUH-20150598'}`
    - `{'doctor': '한혜진', 'dept': '건강의학과', 'external_id': 'KUH-20120277'}`
    - `{'doctor': '홍미진', 'dept': '건강의학과', 'external_id': 'KUH-20070066'}`
    - `{'doctor': '김소이', 'dept': '건강의학과', 'external_id': 'KUH-20100158'}`

### 건양대학교병원 (KYUH) — 대전
- 의사 170명, 진료과 34개, 실행 70.9s
- C10: 공휴일에 열린 날짜별 일정 287건
  - 샘플(최대 5개):
    - `{'doctor': '강영우', 'dept': '소화기내과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '강영우', 'dept': '소화기내과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '강영우', 'dept': '소화기내과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '최용우', 'dept': '소화기내과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '최용우', 'dept': '소화기내과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 49명
  - 샘플(최대 5개):
    - `{'doctor': '김창화', 'dept': '소화기내과', 'external_id': 'KYUH-GAS-C7725F48BA21A1CF5D625AFA81C8C57E'}`
    - `{'doctor': '김용준', 'dept': '소화기내과', 'external_id': 'KYUH-GAS-1774BBE08861259E6693F5416EA02641'}`
    - `{'doctor': '김준영', 'dept': '소화기내과', 'external_id': 'KYUH-GAS-A61BAECF2355D63949B5A2A034547CC5'}`
    - `{'doctor': '신유진', 'dept': '신장내과', 'external_id': 'KYUH-NEP-B40B09D8808A4270513CA8FCDD59B697'}`
    - `{'doctor': '장민정', 'dept': '소아청소년과', 'external_id': 'KYUH-PED-AFE9F469A6F5FBC86BED379D4EBBFC71'}`

### 메디필드한강병원 (MEDIFIELD) — 경기
- 의사 1명, 진료과 1개, 실행 0.0s
- C2: 의사 수 부족 (1명)

### 메트로병원 (METRO) — 경기
- 의사 0명, 진료과 0개, 실행 1.1s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 미즈메디병원 (MIZMEDI) — 서울
- 의사 78명, 진료과 14개, 실행 36.6s
- C11: 일정 없음 안내 누락 7명
  - 샘플(최대 5개):
    - `{'doctor': '서보름', 'dept': '진단검사의학과', 'external_id': 'MIZMEDI-204'}`
    - `{'doctor': '신형옥', 'dept': '영상의학과', 'external_id': 'MIZMEDI-207'}`
    - `{'doctor': '국가건강검진', 'dept': '', 'external_id': 'MIZMEDI-178'}`
    - `{'doctor': '배우리', 'dept': '가정의학과', 'external_id': 'MIZMEDI-231'}`
    - `{'doctor': '윤인경', 'dept': '영상의학과', 'external_id': 'MIZMEDI-722'}`

### 명지병원 (MYONGJI) — 경기
- 의사 160명, 진료과 34개, 실행 17.4s
- C11: 일정 없음 안내 누락 49명
  - 샘플(최대 5개):
    - `{'doctor': '박준리', 'dept': '가정의학과', 'external_id': 'MYONGJI-3-FM014'}`
    - `{'doctor': '박희열', 'dept': '가정의학과', 'external_id': 'MYONGJI-4-FM019'}`
    - `{'doctor': '안지연', 'dept': '내분비내과', 'external_id': 'MYONGJI-12-EN009'}`
    - `{'doctor': '민진혜', 'dept': '마취통증의학과', 'external_id': 'MYONGJI-143-AN002'}`
    - `{'doctor': '이용경', 'dept': '마취통증의학과', 'external_id': 'MYONGJI-15-AN008'}`

### 국민건강보험공단 일산병원 (NHIMC) — 경기
- 의사 252명, 진료과 37개, 실행 51.1s
- C10: 공휴일에 열린 날짜별 일정 21건
  - 샘플(최대 5개):
    - `{'doctor': '김영식', 'dept': '비뇨의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '마감'}`
    - `{'doctor': '김영식', 'dept': '비뇨의학과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '마감'}`
    - `{'doctor': '최종원', 'dept': '소화기내과', 'date': '2026-06-03', 'slot': 'morning', 'status': '마감'}`
    - `{'doctor': '최윤이', 'dept': '소화기내과', 'date': '2026-06-03', 'slot': 'morning', 'status': '마감'}`
    - `{'doctor': '이지은', 'dept': '신경과', 'date': '2026-06-03', 'slot': 'morning', 'status': '마감'}`
- C11: 일정 없음 안내 누락 125명
  - 샘플(최대 5개):
    - `{'doctor': '송선옥', 'dept': '내분비내과', 'external_id': 'NHIMC-4-171'}`
    - `{'doctor': '안은경', 'dept': '마취통증의학과', 'external_id': 'NHIMC-17-113'}`
    - `{'doctor': '강상화', 'dept': '마취통증의학과', 'external_id': 'NHIMC-17-5'}`
    - `{'doctor': '조정구', 'dept': '마취통증의학과', 'external_id': 'NHIMC-17-114'}`
    - `{'doctor': '이재호', 'dept': '마취통증의학과', 'external_id': 'NHIMC-17-6'}`

### 경찰병원 (NPH) — 서울
- 의사 67명, 진료과 29개, 실행 1.4s
- C11: 일정 없음 안내 누락 9명
  - 샘플(최대 5개):
    - `{'doctor': '박태희', 'dept': '진단검사의학과', 'external_id': 'NPH-04000-박태희'}`
    - `{'doctor': '이정은', 'dept': '영상의학과', 'external_id': 'NPH-03700-이정은'}`
    - `{'doctor': '김호균', 'dept': '영상의학과', 'external_id': 'NPH-03700-김호균'}`
    - `{'doctor': '정지윤', 'dept': '병리과', 'external_id': 'NPH-03900-정지윤'}`
    - `{'doctor': '이진효', 'dept': '응급의학과', 'external_id': 'NPH-04200-이진효'}`

### 오산한국병원 (OSHANKOOK) — 경기
- 의사 51명, 진료과 23개, 실행 5.4s
- C11: 일정 없음 안내 누락 8명
  - 샘플(최대 5개):
    - `{'doctor': '�����������명��', 'dept': '��멸낵', 'external_id': 'OSHANKOOK-727'}`
    - `{'doctor': '議�������蹂�������', 'dept': '���寃쎌�멸낵', 'external_id': 'OSHANKOOK-639'}`
    - `{'doctor': '誘����吏���명��', 'dept': '������泥�������怨�', 'external_id': 'OSHANKOOK-729'}`
    - `{'doctor': '怨����������湲���ㅼ��', 'dept': '���湲�������怨�', 'external_id': 'OSHANKOOK-642'}`
    - `{'doctor': '媛�������怨쇱��', 'dept': '���湲�������怨�', 'external_id': 'OSHANKOOK-643'}`

### 인제대학교 부산백병원 (PAIKBS) — 부산
- 의사 361명, 진료과 75개, 실행 2.6s
- C11: 일정 없음 안내 누락 39명
  - 샘플(최대 5개):
    - `{'doctor': '이동준', 'dept': '권역모자의료센터', 'external_id': 'PAIKBS-2109'}`
    - `{'doctor': '김소정', 'dept': '권역모자의료센터', 'external_id': 'PAIKBS-2111'}`
    - `{'doctor': '배우종', 'dept': '마취통증의학과', 'external_id': 'PAIKBS-2087'}`
    - `{'doctor': '김현태', 'dept': '마취통증의학과', 'external_id': 'PAIKBS-2215'}`
    - `{'doctor': '최석환', 'dept': '마취통증의학과', 'external_id': 'PAIKBS-2216'}`

### 부산대학교병원 (PNUH) — 부산
- 의사 429명, 진료과 51개, 실행 20.9s
- C11: 일정 없음 안내 누락 115명
  - 샘플(최대 5개):
    - `{'doctor': '이문원', 'dept': '소화기내과', 'external_id': 'PNUH-I1-97776'}`
    - `{'doctor': '김아란', 'dept': '류마티스내과', 'external_id': 'PNUH-I8-118913'}`
    - `{'doctor': '김수홍', 'dept': '소아외과', 'external_id': 'PNUH-GS2-2013198'}`
    - `{'doctor': '이숙민', 'dept': '신경과', 'external_id': 'PNUH-NL-127004'}`
    - `{'doctor': '김영대', 'dept': '심장혈관흉부외과', 'external_id': 'PNUH-TS-041164'}`

### 양산부산대학교병원 (PNUYH) — 부산
- 의사 231명, 진료과 29개, 실행 6.0s
- C11: 일정 없음 안내 누락 68명
  - 샘플(최대 5개):
    - `{'doctor': '박은주', 'dept': '가정의학과', 'external_id': 'PNUYH-FMC-2009096'}`
    - `{'doctor': '이영인', 'dept': '가정의학과', 'external_id': 'PNUYH-FMC-2014083'}`
    - `{'doctor': '배지현', 'dept': '내분비대사내과', 'external_id': 'PNUYH-EDC-2018266'}`
    - `{'doctor': '이승희', 'dept': '내분비대사내과', 'external_id': 'PNUYH-EDC-2019322'}`
    - `{'doctor': '박상일', 'dept': '방사선종양학과', 'external_id': 'PNUYH-RO-2025398'}`

### 평택성모병원 (PTSM) — 경기
- 의사 69명, 진료과 23개, 실행 13.2s
- C11: 일정 없음 안내 누락 29명
  - 샘플(최대 5개):
    - `{'doctor': '배상수', 'dept': '내시경센터', 'external_id': 'PTSM-1753170846'}`
    - `{'doctor': '김보혜', 'dept': '내시경센터', 'external_id': 'PTSM-1753170823'}`
    - `{'doctor': '서원우', 'dept': '내시경센터', 'external_id': 'PTSM-1753170865'}`
    - `{'doctor': '전병민', 'dept': '내시경센터', 'external_id': 'PTSM-1753170882'}`
    - `{'doctor': '박진민', 'dept': '내시경센터', 'external_id': 'PTSM-1756947626'}`

### 사랑의병원 (SARANG) — 경기
- 의사 41명, 진료과 12개, 실행 0.7s
- C11: 일정 없음 안내 누락 12명
  - 샘플(최대 5개):
    - `{'doctor': '박지현', 'dept': '마취통증의학과', 'external_id': 'SARANG-79c129a123'}`
    - `{'doctor': '서동혁', 'dept': '마취통증의학과', 'external_id': 'SARANG-47abdef19b'}`
    - `{'doctor': '한세희', 'dept': '마취통증의학과', 'external_id': 'SARANG-159e8acb41'}`
    - `{'doctor': '한성민', 'dept': '응급의학과', 'external_id': 'SARANG-c130507953'}`
    - `{'doctor': '배준일', 'dept': '응급의학과', 'external_id': 'SARANG-2c114807ab'}`

### 부천순천향병원 (SCHBC) — 경기
- 의사 240명, 진료과 37개, 실행 145.6s
- C10: 공휴일에 열린 날짜별 일정 89건
  - 샘플(최대 5개):
    - `{'doctor': '김형철', 'dept': '간담췌외과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김철희', 'dept': '내분비대사내과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김철희', 'dept': '내분비대사내과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '목지오', 'dept': '내분비대사내과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '목지오', 'dept': '내분비대사내과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 73명
  - 샘플(최대 5개):
    - `{'doctor': '최덕현', 'dept': '내분비대사내과', 'external_id': 'SCHBC-406'}`
    - `{'doctor': '이정석', 'dept': '마취통증의학과', 'external_id': 'SCHBC-791'}`
    - `{'doctor': '진희철', 'dept': '마취통증의학과', 'external_id': 'SCHBC-790'}`
    - `{'doctor': '채원석', 'dept': '마취통증의학과', 'external_id': 'SCHBC-789'}`
    - `{'doctor': '김상현', 'dept': '마취통증의학과', 'external_id': 'SCHBC-788'}`

### 순천향대학교서울병원 (SCHMC) — 서울
- 의사 247명, 진료과 36개, 실행 148.3s
- C10: 공휴일에 열린 날짜별 일정 137건
  - 샘플(최대 5개):
    - `{'doctor': '유병욱', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '조현', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '조현', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '지영민', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '백수아', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 81명
  - 샘플(최대 5개):
    - `{'doctor': '곽영환', 'dept': '가정의학과', 'external_id': 'SCHMC-125'}`
    - `{'doctor': '곽영환', 'dept': '국제진료센터', 'external_id': 'SCHMC-3566'}`
    - `{'doctor': '김상호', 'dept': '마취통증의학과', 'external_id': 'SCHMC-757'}`
    - `{'doctor': '정지원', 'dept': '마취통증의학과', 'external_id': 'SCHMC-385'}`
    - `{'doctor': '김문규', 'dept': '마취통증의학과', 'external_id': 'SCHMC-1264'}`

### 신천연합병원 (SCSUH) — 인천
- 의사 16명, 진료과 12개, 실행 6.7s
- C10: 공휴일에 열린 날짜별 일정 37건
  - 샘플(최대 5개):
    - `{'doctor': '남준철', 'dept': '외과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '배수성', 'dept': '치과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '오경중', 'dept': '영상의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '홍미정', 'dept': '마취통증의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '윤창은', 'dept': '진단검사의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 1명
  - 샘플(최대 5개):
    - `{'doctor': '나현진', 'dept': '돌봄의료센터', 'external_id': 'SCSUH-72'}`

### 삼성창원병원 (SCWH) — 경남
- 의사 176명, 진료과 34개, 실행 12.1s
- C10: 공휴일에 열린 날짜별 일정 89건
  - 샘플(최대 5개):
    - `{'doctor': '김광민', 'dept': '소화기내과', 'date': '2026-06-06', 'slot': 'morning', 'status': '마감'}`
    - `{'doctor': '고광철', 'dept': '소화기내과', 'date': '2026-06-06', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '심상군', 'dept': '소화기내과', 'date': '2026-06-06', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '이정원', 'dept': '소화기내과', 'date': '2026-06-06', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '성보람', 'dept': '소화기내과', 'date': '2026-06-06', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 56명
  - 샘플(최대 5개):
    - `{'doctor': '박선영', 'dept': '신장내과', 'external_id': 'SCWH-303'}`
    - `{'doctor': '옥지훈', 'dept': '산부인과', 'external_id': 'SCWH-77'}`
    - `{'doctor': '전우영', 'dept': '소아청소년과', 'external_id': 'SCWH-202'}`
    - `{'doctor': '김주영', 'dept': '소아청소년과', 'external_id': 'SCWH-284'}`
    - `{'doctor': '최민환', 'dept': '소아청소년과', 'external_id': 'SCWH-104'}`

### 인제대학교 상계백병원 (SGPAIK) — 서울
- 의사 237명, 진료과 67개, 실행 2.0s
- C11: 일정 없음 안내 누락 43명
  - 샘플(최대 5개):
    - `{'doctor': '김계민', 'dept': '마취통증의학과', 'external_id': 'SGPAIK-1391'}`
    - `{'doctor': '이상석', 'dept': '마취통증의학과', 'external_id': 'SGPAIK-1393'}`
    - `{'doctor': '유병훈', 'dept': '마취통증의학과', 'external_id': 'SGPAIK-1392'}`
    - `{'doctor': '임윤희', 'dept': '마취통증의학과', 'external_id': 'SGPAIK-1522'}`
    - `{'doctor': '전인정', 'dept': '마취통증의학과', 'external_id': 'SGPAIK-1394'}`

### 서울현대병원 (SHH) — 서울
- 의사 22명, 진료과 13개, 실행 0.2s
- C11: 일정 없음 안내 누락 4명
  - 샘플(최대 5개):
    - `{'doctor': '이주현', 'dept': '마취통증의학과', 'external_id': 'SHH-18'}`
    - `{'doctor': '신지예', 'dept': '검진센터＆가정의학과', 'external_id': 'SHH-22'}`
    - `{'doctor': '이쌍현', 'dept': '응급실', 'external_id': 'SHH-26'}`
    - `{'doctor': '이창훈', 'dept': '응급실', 'external_id': 'SHH-29'}`

### 삼성서울병원 (SMC) — 서울
- 의사 729명, 진료과 57개, 실행 43.7s
- C11: 일정 없음 안내 누락 293명
  - 샘플(최대 5개):
    - `{'doctor': '이승후', 'dept': '감염내과', 'external_id': 'SMC-3508'}`
    - `{'doctor': '변성훈', 'dept': '소화기내과', 'external_id': 'SMC-3539'}`
    - `{'doctor': '김지연', 'dept': '소화기내과', 'external_id': 'SMC-3538'}`
    - `{'doctor': '이나경', 'dept': '소화기내과', 'external_id': 'SMC-3768'}`
    - `{'doctor': '윤도경', 'dept': '소화기내과', 'external_id': 'SMC-3772'}`

### 서울의료원 (SMC2) — 서울
- 의사 160명, 진료과 37개, 실행 4.1s
- C11: 일정 없음 안내 누락 43명
  - 샘플(최대 5개):
    - `{'doctor': '이수형', 'dept': '건강증진센터', 'external_id': 'SMC2-HC-02353M'}`
    - `{'doctor': '강민승', 'dept': '건강증진센터', 'external_id': 'SMC2-HC-02127'}`
    - `{'doctor': '윤루비', 'dept': '건강증진센터', 'external_id': 'SMC2-HC-29419'}`
    - `{'doctor': '서지수', 'dept': '건강증진센터', 'external_id': 'SMC2-HC-40001'}`
    - `{'doctor': '김현목', 'dept': '내분비대사내과', 'external_id': 'SMC2-IME-04936'}`

### 서울특별시 동부병원 (SMGDB) — 서울
- 의사 28명, 진료과 16개, 실행 0.2s
- C11: 일정 없음 안내 누락 3명
  - 샘플(최대 5개):
    - `{'doctor': '이계숙', 'dept': '진단검사의학과', 'external_id': 'SMGDB-진단검사의학과-이계숙'}`
    - `{'doctor': '권양숙', 'dept': '영상의학과', 'external_id': 'SMGDB-영상의학과-권양숙'}`
    - `{'doctor': '이창준', 'dept': '영상의학과', 'external_id': 'SMGDB-영상의학과-이창준'}`

### 성남중앙병원 (SNJA) — 경기
- 의사 0명, 진료과 0개, 실행 0.0s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 서울특별시 서남병원 (SNMC) — 서울
- 의사 39명, 진료과 22개, 실행 4.6s
- C11: 일정 없음 안내 누락 4명
  - 샘플(최대 5개):
    - `{'doctor': '김은정', 'dept': '마취통증의학과 · 통증클리닉', 'external_id': 'SNMC-92-34'}`
    - `{'doctor': '이정민', 'dept': '마취통증의학과 · 통증클리닉', 'external_id': 'SNMC-265-34'}`
    - `{'doctor': '강한나', 'dept': '병리과', 'external_id': 'SNMC-213-60'}`
    - `{'doctor': '정채림', 'dept': '진단검사의학과', 'external_id': 'SNMC-42-35'}`

### 성남시의료원 (SNMCC) — 경기
- 의사 0명, 진료과 0개, 실행 15.3s
- C2: 의사 수 부족 (0명)
- C3: 진료과 0개

### 분당서울대병원 (SNUBH) — 경기
- 의사 395명, 진료과 30개, 실행 9.3s
- C11: 일정 없음 안내 누락 4명
  - 샘플(최대 5개):
    - `{'doctor': '임상강사(족부)', 'dept': '정형외과', 'external_id': 'SNUBH-JOS12'}`
    - `{'doctor': '임상강사(슬관절1)', 'dept': '정형외과', 'external_id': 'SNUBH-JOS06'}`
    - `{'doctor': '임상강사(수부)', 'dept': '정형외과', 'external_id': 'SNUBH-JRCFF'}`
    - `{'doctor': '임상강사(견관절)', 'dept': '정형외과', 'external_id': 'SNUBH-JRCFA'}`

### 서울대학교병원 (SNUH) — 서울
- 의사 482명, 진료과 91개, 실행 2.0s
- C11: 일정 없음 안내 누락 7명
  - 샘플(최대 5개):
    - `{'doctor': '김중엽', 'dept': '호흡기내과', 'external_id': 'SNUH-김중엽'}`
    - `{'doctor': '박상혁', 'dept': '간담췌외과', 'external_id': 'SNUH-박상혁'}`
    - `{'doctor': '이호진', 'dept': '마취통증의학과', 'external_id': 'SNUH-이호진'}`
    - `{'doctor': '윤수지', 'dept': '마취통증의학과', 'external_id': 'SNUH-윤수지'}`
    - `{'doctor': '윤수혁', 'dept': '마취통증의학과', 'external_id': 'SNUH-윤수혁'}`

### 서울적십자병원 (SRCH) — 서울
- 의사 41명, 진료과 24개, 실행 8.2s
- C11: 일정 없음 안내 누락 2명
  - 샘플(최대 5개):
    - `{'doctor': '전고운', 'dept': '마취통증의학과', 'external_id': 'SRCH-C10-전고운'}`
    - `{'doctor': '서혜정', 'dept': '마취통증의학과', 'external_id': 'SRCH-C10-서혜정'}`

### 서울성심병원 (SSHH) — 서울
- 의사 29명, 진료과 12개, 실행 0.2s
- C11: 일정 없음 안내 누락 2명
  - 샘플(최대 5개):
    - `{'doctor': '조용현', 'dept': '마취통증의학과', 'external_id': 'SSHH-m0190421'}`
    - `{'doctor': '신옥영', 'dept': '마취통증의학과', 'external_id': 'SSHH-마취통증의학과-신옥영'}`

### 성애병원 (SUNGAE) — 서울
- 의사 59명, 진료과 26개, 실행 5.2s
- C11: 일정 없음 안내 누락 6명
  - 샘플(최대 5개):
    - `{'doctor': '신윤재', 'dept': '소화기내과', 'external_id': 'SUNGAE-SH1591-DT3199'}`
    - `{'doctor': '한지선', 'dept': '소화기내과', 'external_id': 'SUNGAE-SH1591-DT3207'}`
    - `{'doctor': '이진영', 'dept': '재활의학과', 'external_id': 'SUNGAE-SH1614-DT2503'}`
    - `{'doctor': '유지혜', 'dept': '정신건강의학과', 'external_id': 'SUNGAE-SH1604-DT2474'}`
    - `{'doctor': '김영진', 'dept': '진단검사의학과', 'external_id': 'SUNGAE-SH1606-DT2480'}`

### 수원덕산병원 (SWDS) — 경기
- 의사 52명, 진료과 29개, 실행 2.0s
- C11: 일정 없음 안내 누락 21명
  - 샘플(최대 5개):
    - `{'doctor': '김재욱', 'dept': '내과', 'external_id': 'SWDS-233'}`
    - `{'doctor': '김대희', 'dept': '마취통증의학과', 'external_id': 'SWDS-177'}`
    - `{'doctor': '윤두균', 'dept': '마취통증의학과', 'external_id': 'SWDS-222'}`
    - `{'doctor': '이종석', 'dept': '마취통증의학과', 'external_id': 'SWDS-225'}`
    - `{'doctor': '장용수', 'dept': '부인과', 'external_id': 'SWDS-218'}`

### 포천우리병원 (SWOORI) — 경기
- 의사 63명, 진료과 26개, 실행 0.2s
- C11: 일정 없음 안내 누락 63명
  - 샘플(최대 5개):
    - `{'doctor': '장진', 'dept': '정형외과', 'external_id': 'SWOORI-1-jangjin'}`
    - `{'doctor': '김승환', 'dept': '제2정형외과', 'external_id': 'SWOORI-1-kimsh'}`
    - `{'doctor': '김응식', 'dept': '정형외과', 'external_id': 'SWOORI-1-kimes'}`
    - `{'doctor': '강전형', 'dept': '정형외과', 'external_id': 'SWOORI-1-kangjh'}`
    - `{'doctor': '고영록', 'dept': '정형외과', 'external_id': 'SWOORI-1-koyr'}`

### 삼육서울병원 (SYMC) — 서울
- 의사 89명, 진료과 30개, 실행 0.5s
- C11: 일정 없음 안내 누락 16명
  - 샘플(최대 5개):
    - `{'doctor': '조혜제', 'dept': '병리과', 'external_id': 'SYMC-10203'}`
    - `{'doctor': '김규영', 'dept': '소화기내과', 'external_id': 'SYMC-10420'}`
    - `{'doctor': '김경욱', 'dept': '소화기내과', 'external_id': 'SYMC-10421'}`
    - `{'doctor': '임필용', 'dept': '소화기내과', 'external_id': 'SYMC-10422'}`
    - `{'doctor': '최하나', 'dept': '신장내과', 'external_id': 'SYMC-10423'}`

### 의정부을지대학교병원 (UEMC) — 경기
- 의사 173명, 진료과 39개, 실행 3.7s
- C11: 일정 없음 안내 누락 15명
  - 샘플(최대 5개):
    - `{'doctor': '김정환', 'dept': '가정의학과', 'external_id': 'UEMC-ABPAAA-208168'}`
    - `{'doctor': '김지희', 'dept': '마취통증의학과', 'external_id': 'UEMC-ABVAAA-20231580'}`
    - `{'doctor': '이근수', 'dept': '마취통증의학과', 'external_id': 'UEMC-ABVAAA-20210386'}`
    - `{'doctor': '임현재', 'dept': '마취통증의학과', 'external_id': 'UEMC-ABVAAA-20240001'}`
    - `{'doctor': '최서문', 'dept': '마취통증의학과', 'external_id': 'UEMC-ABVAAA-20241199'}`

### 의정부백병원 (UPAIK) — 경기
- 의사 21명, 진료과 14개, 실행 0.8s
- C11: 일정 없음 안내 누락 6명
  - 샘플(최대 5개):
    - `{'doctor': '이정우', 'dept': '응급의학과', 'external_id': 'UPAIK-12-1'}`
    - `{'doctor': '김상희', 'dept': '응급의학과', 'external_id': 'UPAIK-12-2'}`
    - `{'doctor': '박기영', 'dept': '응급의학과', 'external_id': 'UPAIK-12-3'}`
    - `{'doctor': '박삼열', 'dept': '응급의학과', 'external_id': 'UPAIK-12-4'}`
    - `{'doctor': '정지우', 'dept': '영상의학과', 'external_id': 'UPAIK-14-1'}`

### 울산대학교병원 (UUH) — 울산
- 의사 260명, 진료과 36개, 실행 71.9s
- C10: 공휴일에 열린 날짜별 일정 362건
  - 샘플(최대 5개):
    - `{'doctor': '정태흠', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '정태흠', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '정태흠', 'dept': '가정의학과', 'date': '2026-05-24', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '황혜아', 'dept': '가정의학과', 'date': '2026-05-24', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '전재범', 'dept': '감염내과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 59명
  - 샘플(최대 5개):
    - `{'doctor': '김보경', 'dept': '건강의학과', 'external_id': 'UUH-438'}`
    - `{'doctor': '김선정', 'dept': '건강의학과', 'external_id': 'UUH-303'}`
    - `{'doctor': '김재영', 'dept': '건강의학과', 'external_id': 'UUH-119'}`
    - `{'doctor': '성시정', 'dept': '건강의학과', 'external_id': 'UUH-531'}`
    - `{'doctor': '이지민', 'dept': '건강의학과', 'external_id': 'UUH-569'}`

### 중앙보훈병원 (VHS) — 서울
- 의사 169명, 진료과 36개, 실행 3.0s
- C11: 일정 없음 안내 누락 24명
  - 샘플(최대 5개):
    - `{'doctor': '전희정', 'dept': '마취통증의학과(통증센터)', 'external_id': 'VHS-104667'}`
    - `{'doctor': '조삼순', 'dept': '마취통증의학과(통증센터)', 'external_id': 'VHS-104950'}`
    - `{'doctor': '김민아', 'dept': '병리과', 'external_id': 'VHS-183338'}`
    - `{'doctor': '이미지', 'dept': '병리과', 'external_id': 'VHS-114849'}`
    - `{'doctor': '이용상', 'dept': '치과병원 보철과', 'external_id': 'VHS-109128'}`

### 윌스기념병원 (WILLS) — 경기
- 의사 92명, 진료과 23개, 실행 28.6s
- C11: 일정 없음 안내 누락 22명
  - 샘플(최대 5개):
    - `{'doctor': '안재범', 'dept': '척추센터', 'external_id': 'WILLS-608'}`
    - `{'doctor': '이한규', 'dept': '척추센터', 'external_id': 'WILLS-632'}`
    - `{'doctor': '윤임준', 'dept': '척추센터', 'external_id': 'WILLS-631'}`
    - `{'doctor': '심정보', 'dept': '척추센터', 'external_id': 'WILLS-703'}`
    - `{'doctor': '이원재', 'dept': '척추센터', 'external_id': 'WILLS-702'}`

### 원광종합병원 (WKGH) — 경기
- 의사 15명, 진료과 12개, 실행 0.1s
- C11: 일정 없음 안내 누락 15명
  - 샘플(최대 5개):
    - `{'doctor': '이경환', 'dept': '내과', 'external_id': 'WKGH-881293de25'}`
    - `{'doctor': '손명진', 'dept': '신경과', 'external_id': 'WKGH-cfa98fec02'}`
    - `{'doctor': '이형석', 'dept': '내과', 'external_id': 'WKGH-e07c85afb7'}`
    - `{'doctor': '김정권', 'dept': '종합검진센터', 'external_id': 'WKGH-d70ef5b285'}`
    - `{'doctor': '신교정', 'dept': '정신건강의학과', 'external_id': 'WKGH-1f1d6bf88e'}`

### 원광대학교병원 (WKUH) — 전북
- 의사 158명, 진료과 38개, 실행 17.4s
- C10: 공휴일에 열린 날짜별 일정 241건
  - 샘플(최대 5개):
    - `{'doctor': '신새론', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '신새론', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김영준', 'dept': '감염내과', 'date': '2026-05-25', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김영준', 'dept': '감염내과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '이명수', 'dept': '관절류마티스내과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
- C11: 일정 없음 안내 누락 49명
  - 샘플(최대 5개):
    - `{'doctor': '한아름', 'dept': '가정의학과', 'external_id': 'WKUH-173'}`
    - `{'doctor': '정종혁', 'dept': '관절류마티스내과', 'external_id': 'WKUH-184'}`
    - `{'doctor': '김의중', 'dept': '소화기내과', 'external_id': 'WKUH-526'}`
    - `{'doctor': '조재영', 'dept': '순환기내과', 'external_id': 'WKUH-228'}`
    - `{'doctor': '정진원', 'dept': '순환기내과', 'external_id': 'WKUH-693'}`

### 원광대학교산본병원 (WMCSB) — 경기
- 의사 45명, 진료과 21개, 실행 3.3s
- C11: 일정 없음 안내 누락 18명
  - 샘플(최대 5개):
    - `{'doctor': '허솔미', 'dept': '소화기내과', 'external_id': 'WMCSB-1-139'}`
    - `{'doctor': '박우행', 'dept': '소화기내과', 'external_id': 'WMCSB-1-162'}`
    - `{'doctor': '박세희', 'dept': '산부인과', 'external_id': 'WMCSB-14-124'}`
    - `{'doctor': '김교상', 'dept': '마취통증의학과', 'external_id': 'WMCSB-17-24'}`
    - `{'doctor': '최유선', 'dept': '마취통증의학과', 'external_id': 'WMCSB-17-60'}`

### 청담 우리들병원 (WOORIDUL) — 서울
- 의사 28명, 진료과 9개, 실행 18.0s
- C11: 일정 없음 안내 누락 13명
  - 샘플(최대 5개):
    - `{'doctor': '이상호', 'dept': '척추진료부', 'external_id': 'WOORIDUL-1'}`
    - `{'doctor': '배영식', 'dept': '흉추진료부 / 척추측만증 치료부', 'external_id': 'WOORIDUL-18'}`
    - `{'doctor': '황의동', 'dept': '흉추진료부 / 척추측만증 치료부', 'external_id': 'WOORIDUL-19'}`
    - `{'doctor': '이선우', 'dept': '척추진료부', 'external_id': 'WOORIDUL-160'}`
    - `{'doctor': '허수영', 'dept': '척추진료부', 'external_id': 'WOORIDUL-162'}`

### 영남대학교병원 (YUMC) — 대구
- 의사 192명, 진료과 39개, 실행 2.8s
- C11: 일정 없음 안내 누락 39명
  - 샘플(최대 5개):
    - `{'doctor': '권희정', 'dept': '병리과', 'external_id': 'YUMC-750'}`
    - `{'doctor': '김기백', 'dept': '신장내과', 'external_id': 'YUMC-784'}`
    - `{'doctor': '김미은', 'dept': '건강증진센터', 'external_id': 'YUMC-676'}`
    - `{'doctor': '김민종', 'dept': '병리과', 'external_id': 'YUMC-708'}`
    - `{'doctor': '김세동', 'dept': '정형외과', 'external_id': 'YUMC-800'}`

### 원주세브란스기독병원 (YWMC) — 강원
- 의사 192명, 진료과 40개, 실행 8.7s
- C10: 공휴일에 열린 날짜별 일정 350건
  - 샘플(최대 5개):
    - `{'doctor': '김종구', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'afternoon', 'status': '진료'}`
    - `{'doctor': '김종구', 'dept': '가정의학과', 'date': '2026-05-25', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '김종구', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '박연철', 'dept': '가정의학과', 'date': '2026-05-05', 'slot': 'morning', 'status': '진료'}`
    - `{'doctor': '정태하', 'dept': '가정의학과', 'date': '2026-06-03', 'slot': 'afternoon', 'status': '진료'}`
- C11: 일정 없음 안내 누락 28명
  - 샘플(최대 5개):
    - `{'doctor': '최현준', 'dept': '방사선종양학과', 'external_id': 'YWMC-RT-wGmghCccYDHlO8zHoYumGg..'}`
    - `{'doctor': '정상운', 'dept': '방사선종양학과', 'external_id': 'YWMC-NA-방사선종양학과-정상운'}`
    - `{'doctor': '민세라', 'dept': '소아청소년과', 'external_id': 'YWMC-NA-소아청소년과-민세라'}`
    - `{'doctor': '이진석', 'dept': '소아청소년과', 'external_id': 'YWMC-NA-소아청소년과-이진석'}`
    - `{'doctor': '최재욱', 'dept': '소아청소년과', 'external_id': 'YWMC-NA-소아청소년과-최재욱'}`

## 통계

- C10: 23개 병원 (CBNUH, CHNUH, DAMC, DKUH, DSMC, HYUGR, JISAM, KBSMC, KNUH, KNUHCG, KUANAM, KUANSAN, KUGURO, KUH, KYUH...)
- C11: 103개 병원 (AJOUMC, AYSAM, BCSEJONG, BCWOORI, BEDRO, BESEOUL, BRMH, BUMIN, CAU, CAUGM, CBNUH, CGSS, CHABD, CHAGN, CHAIS...)
- C2: 12개 병원 (CMCBC, CMCEP, CMCSEOUL, CMCSV, CMCUJB, CMCYD, DSWHOSP, GANSEV, MEDIFIELD, METRO, SNJA, SNMCC)
- C3: 12개 병원 (CMCBC, CMCEP, CMCSEOUL, CMCSV, CMCUJB, CMCYD, DSWHOSP, GANSEV, HSYUIL, METRO, SNJA, SNMCC)
- C6: 1개 병원 (HSYUIL)
- C8: 1개 병원 (CHNUH)
