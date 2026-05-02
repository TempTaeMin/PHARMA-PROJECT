import { LogIn } from 'lucide-react';
import { authApi } from '../api/client';

export default function Login() {
  const handleLogin = () => {
    window.location.href = authApi.loginUrl();
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg-0)', padding: 24,
    }}>
      <div style={{
        width: '100%', maxWidth: 400, padding: 40, borderRadius: 16,
        background: 'var(--bg-1)', border: '1px solid var(--bd-s)',
        boxShadow: '0 10px 40px rgba(0,0,0,.05)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24,
      }}>
        <div style={{
          fontFamily: 'Manrope', fontSize: 28, fontWeight: 800, color: 'var(--t1)',
          textAlign: 'center', letterSpacing: '-.02em',
        }}>
          MediSync
        </div>
        <div style={{
          fontSize: 13, color: 'var(--t3)', textAlign: 'center', lineHeight: 1.5,
        }}>
          제약 영업사원을 위한<br />
          교수 진료일정 & 학회 일정 관리
        </div>
        <button
          onClick={handleLogin}
          style={{
            width: '100%', padding: '12px 18px', borderRadius: 10,
            background: '#fff', color: '#1f1f1f',
            border: '1px solid #dadce0', cursor: 'pointer',
            fontSize: 14, fontWeight: 600, fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
            boxShadow: '0 1px 2px rgba(60,64,67,.1)',
            transition: 'box-shadow .15s, background .15s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.boxShadow = '0 2px 6px rgba(60,64,67,.15)';
            e.currentTarget.style.background = '#f8f9fa';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.boxShadow = '0 1px 2px rgba(60,64,67,.1)';
            e.currentTarget.style.background = '#fff';
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg>
          Google 로 로그인
        </button>
        <div style={{
          fontSize: 11, color: 'var(--t3)', textAlign: 'center', lineHeight: 1.5,
        }}>
          본 서비스는 테스터 계정으로 운영 중이며,<br />
          관리자가 등록한 Gmail 계정만 로그인할 수 있습니다.
        </div>
      </div>
    </div>
  );
}
