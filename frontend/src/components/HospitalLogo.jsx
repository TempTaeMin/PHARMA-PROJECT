import { useState, useEffect } from 'react';

const EXTENSIONS = ['svg', 'png'];

export default function HospitalLogo({ code, size = 44, radius = 10 }) {
  const [extIndex, setExtIndex] = useState(0);

  useEffect(() => { setExtIndex(0); }, [code]);

  const boxStyle = {
    width: size,
    height: size,
    borderRadius: radius,
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  };

  if (!code || extIndex >= EXTENSIONS.length) {
    return (
      <div style={{ ...boxStyle, background: 'var(--ac-d)', fontSize: Math.round(size * 0.5) }}>
        🏥
      </div>
    );
  }

  return (
    <div style={boxStyle}>
      <img
        key={extIndex}
        src={`/hospital-logos/${code}.${EXTENSIONS[extIndex]}`}
        alt={code}
        onError={() => setExtIndex(i => i + 1)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
        }}
      />
    </div>
  );
}
