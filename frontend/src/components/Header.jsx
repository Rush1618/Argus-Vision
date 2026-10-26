import React, { useState, useEffect } from 'react';
import { Camera, Clock, Cpu } from 'lucide-react';

export default function Header({ stats, isConnected, esp32Ip }) {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header
      className="console-panel"
      style={{
        padding: '16px 20px',
        marginBottom: '20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '16px'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            width: '40px',
            height: '40px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--color-accent-dim)',
            border: 'var(--rule-hair) solid var(--color-accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        >
          <Camera size={20} color="var(--color-accent)" />
        </div>
        <div>
          <h1
            style={{
              fontSize: 'var(--text-lg)',
              fontWeight: 600,
              color: 'var(--color-ink)',
              margin: 0
            }}
          >
            ESP32-CAM AI Vision Console
          </h1>
          <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-muted)', margin: 0 }}>
            Real-time edge neural stream and control console
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        {/* Hardware Status Pill */}
        <div
          role="status"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            backgroundColor: 'var(--color-paper-3)',
            padding: '6px 12px',
            borderRadius: 'var(--radius-sm)',
            border: 'var(--rule-hair) solid var(--color-rule)',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)'
          }}
        >
          <span className={`beacon-dot ${isConnected ? 'beacon-online' : 'beacon-offline'}`} />
          <span style={{ color: isConnected ? 'var(--color-emerald)' : 'var(--color-alert)', fontWeight: 600 }}>
            {isConnected ? 'Online' : 'Disconnected'}
          </span>
          <span style={{ color: 'var(--color-ink-2)' }}>
            {esp32Ip || '192.168.4.1'}
          </span>
        </div>

        {/* AI Mode Active Tag */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            backgroundColor: 'var(--color-paper-3)',
            padding: '6px 12px',
            borderRadius: 'var(--radius-sm)',
            border: 'var(--rule-hair) solid var(--color-rule)',
            color: 'var(--color-ink-2)',
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-mono)'
          }}
        >
          <Cpu size={14} color="var(--color-accent)" />
          <span>
            Mode: {stats.mode || 'face'}
            {stats.gesture && stats.gesture !== 'None' ? ` (${stats.gesture})` : ''}
          </span>
        </div>

        {/* System Clock */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            color: 'var(--color-muted)',
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-mono)'
          }}
        >
          <Clock size={14} />
          <span className="num">{time}</span>
        </div>
      </div>
    </header>
  );
}
