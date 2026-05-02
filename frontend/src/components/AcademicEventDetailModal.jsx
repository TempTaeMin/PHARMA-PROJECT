import { X, BookOpen, Calendar, MapPin, Users, ExternalLink, Trash2, PinOff, GraduationCap } from 'lucide-react';

function formatKoreanDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T00:00:00');
  const dow = ['일', '월', '화', '수', '목', '금', '토'][d.getDay()];
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 (${dow})`;
}

export default function AcademicEventDetailModal({ open, event, onClose, onDelete }) {
  if (!open || !event) return null;

  const isManual = event.source === 'manual';
  const isKmaEdu = event.source === 'kma_edu';
  const kmaUrl = isKmaEdu && event.kma_eduidx
    ? `https://edu.kma.org/edu/schedule_view?eduidx=${event.kma_eduidx}`
    : null;
  const primaryUrl = isManual ? event.url : kmaUrl;
  const matchedCount = event.matched_doctor_count || 0;
  const matchedNames = Array.isArray(event.matched_doctor_names) ? event.matched_doctor_names : [];
  const dateText = event.end_date && event.end_date !== event.start_date
    ? `${formatKoreanDate(event.start_date)} ~ ${formatKoreanDate(event.end_date)}`
    : formatKoreanDate(event.start_date);

  const handleOpenUrl = () => {
    if (primaryUrl) window.open(primaryUrl, '_blank', 'noopener,noreferrer');
  };

  const handleDelete = async () => {
    const msg = isManual
      ? `"${event.name}" 을(를) 삭제하시겠습니까?`
      : `"${event.name}" 을(를) 내 일정에서 제거하시겠습니까?`;
    if (!confirm(msg)) return;
    try {
      await onDelete?.(event);
    } catch (e) {
      alert('처리 실패: ' + e.message);
    }
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)',
        zIndex: 380, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 16, animation: 'fadeIn .18s ease',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-1)', borderRadius: 18,
          padding: '22px 22px 20px', width: 480, maxWidth: '100%',
          maxHeight: '92vh', overflowY: 'auto',
          animation: 'fadeUp .22s ease',
        }}
      >
        {/* 헤더 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '3px 8px', borderRadius: 5,
              fontSize: 10, fontWeight: 800, letterSpacing: '.05em',
              background: '#f3e8ff', color: '#7c3aed', fontFamily: 'Manrope',
              marginBottom: 8,
            }}>
              <BookOpen size={10} />
              {isManual ? '수동 추가' : 'KMA 자동 수집'}
            </span>
            <div style={{ fontFamily: 'Manrope', fontSize: 18, fontWeight: 800, color: 'var(--t1)', lineHeight: 1.3 }}>
              {event.name}
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: 'var(--t3)',
            padding: 0, marginLeft: 8,
          }}><X size={20} /></button>
        </div>

        {/* 날짜 */}
        <InfoRow icon={<Calendar size={13} />} label="일정">
          {dateText}
        </InfoRow>

        {/* 장소 */}
        {event.location && (
          <InfoRow icon={<MapPin size={13} />} label="장소">
            {event.location}
          </InfoRow>
        )}

        {/* 주최 */}
        {event.organizer_name && (
          <InfoRow icon={<Users size={13} />} label="주최">
            {event.organizer_name}
          </InfoRow>
        )}

        {/* 내 의료진 매칭 요약 */}
        {matchedCount > 0 && (
          <div style={{
            marginTop: 14, padding: '10px 12px', borderRadius: 10,
            background: 'var(--ac-d)', border: '1px solid var(--ac)',
            display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
          }}>
            <GraduationCap size={14} style={{ color: 'var(--ac)' }} />
            <span style={{ fontSize: 11, fontWeight: 800, color: 'var(--ac)' }}>
              내 의료진 {matchedCount}명 강사 참여
            </span>
            {matchedNames.length > 0 && (
              <span style={{ fontSize: 11, color: 'var(--ac)', fontWeight: 600 }}>
                · {matchedNames.slice(0, 3).join(', ')}{matchedNames.length > 3 ? ` +${matchedNames.length - 3}명` : ''}
              </span>
            )}
          </div>
        )}

        {/* 설명 */}
        {event.description && (
          <div style={{ marginTop: 16 }}>
            <SectionLabel>설명</SectionLabel>
            <div style={{
              padding: '12px 14px', borderRadius: 10,
              background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
              fontSize: 13, color: 'var(--t2)', lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
            }}>
              {event.description}
            </div>
          </div>
        )}

        {/* 액션 */}
        <div style={{ display: 'flex', gap: 8, marginTop: 20, flexWrap: 'wrap' }}>
          {primaryUrl && (
            <button
              onClick={handleOpenUrl}
              style={{
                flex: '1 1 100%', padding: '12px 16px', borderRadius: 10,
                background: '#7c3aed', color: '#fff', border: 'none',
                cursor: 'pointer', fontSize: 13, fontWeight: 800, fontFamily: 'inherit',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}
            >
              <ExternalLink size={14} /> {isKmaEdu ? 'KMA 연수교육 페이지' : '학회 페이지 열기'}
            </button>
          )}
          <button
            onClick={handleDelete}
            style={{
              flex: 1, padding: '12px 14px', borderRadius: 10,
              background: 'var(--bg-2)', color: '#b91c1c',
              border: '1px solid var(--bd-s)', cursor: 'pointer',
              fontSize: 12, fontWeight: 700, fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
            }}
          >
            {isManual ? <Trash2 size={13} /> : <PinOff size={13} />}
            {isManual ? '삭제' : '내 일정에서 제거'}
          </button>
          <button
            onClick={onClose}
            style={{
              flex: 1, padding: '12px 16px', borderRadius: 10,
              background: 'var(--ac)', color: '#fff', border: 'none',
              cursor: 'pointer', fontSize: 13, fontWeight: 800, fontFamily: 'inherit',
            }}
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ icon, label, children }) {
  return (
    <div style={{ marginTop: 14 }}>
      <SectionLabel icon={icon}>{label}</SectionLabel>
      <div style={{
        padding: '11px 13px', borderRadius: 10,
        background: 'var(--bg-2)', border: '1px solid var(--bd-s)',
        fontSize: 14, color: 'var(--t1)', fontWeight: 600,
      }}>
        {children}
      </div>
    </div>
  );
}

function SectionLabel({ children, icon }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      fontSize: 11, fontWeight: 800, color: 'var(--t3)',
      letterSpacing: '.04em', marginBottom: 6,
    }}>
      {icon}{children}
    </div>
  );
}
