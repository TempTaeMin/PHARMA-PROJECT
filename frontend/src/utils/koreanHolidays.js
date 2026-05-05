const KOREAN_PUBLIC_HOLIDAYS = new Set([
  // 2026 official public holidays and substitute holidays.
  '2026-01-01',
  '2026-02-16',
  '2026-02-17',
  '2026-02-18',
  '2026-03-01',
  '2026-03-02',
  '2026-05-05',
  '2026-05-24',
  '2026-05-25',
  '2026-06-03',
  '2026-06-06',
  '2026-08-15',
  '2026-08-17',
  '2026-09-24',
  '2026-09-25',
  '2026-09-26',
  '2026-10-03',
  '2026-10-05',
  '2026-10-09',
  '2026-12-25',
]);

export function isKoreanPublicHoliday(dateStr) {
  return KOREAN_PUBLIC_HOLIDAYS.has(dateStr);
}

export function isClosedScheduleStatus(status) {
  return status === '휴진';
}

export function isDefaultOpenScheduleStatus(status) {
  return !status || status === '진료';
}

export function isOpenOnKoreanPublicHoliday(status) {
  return !isClosedScheduleStatus(status) && !isDefaultOpenScheduleStatus(status);
}
