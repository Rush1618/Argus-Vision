import React from 'react';
import { Activity, Target, ShieldCheck, Zap } from 'lucide-react';

export default function TelemetryBar({ stats, isConnected }) {
  const fps = stats.fps || 0;
  const detections = stats.detections || 0;
  const motion = stats.motion_level || 0;

  const cards = [
    {
      title: 'Stream throughput',
      value: `${fps} fps`,
      sub: fps > 22 ? 'Optimal 30 Hz target' : fps > 10 ? 'Standard ingestion' : 'Low throughput',
      colorVar: fps > 20 ? 'var(--color-emerald)' : fps > 10 ? 'var(--color-amber)' : 'var(--color-alert)',
      icon: Activity,
      metric: `${Math.min(100, (fps / 30) * 100)}%`
    },
    {
      title: 'Active targets',
      value: detections === 1 ? '1 target' : `${detections} targets`,
      sub: detections > 0 ? `${detections} entity in frame` : 'Scanning environment',
      colorVar: detections > 0 ? 'var(--color-accent)' : 'var(--color-muted)',
      icon: Target,
      metric: `${Math.min(100, detections * 25)}%`
    },
    {
      title: 'Motion level',
      value: `${motion}%`,
      sub: stats.motion_detected ? 'Active movement detected' : 'Static background',
      colorVar: stats.motion_detected ? 'var(--color-alert)' : 'var(--color-emerald)',
      icon: ShieldCheck,
      metric: `${Math.min(100, motion * 2)}%`
    },
    {
      title: 'Pipeline status',
      value: isConnected ? 'Connected' : 'Offline',
      sub: isConnected ? 'ESP32 sensor stream active' : 'Awaiting hardware connection',
      colorVar: isConnected ? 'var(--color-emerald)' : 'var(--color-amber)',
      icon: Zap,
      metric: isConnected ? '100%' : '15%'
    }
  ];

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '16px',
        marginBottom: '20px'
      }}
    >
      {cards.map((c, i) => {
        const Icon = c.icon;
        return (
          <div
            key={i}
            className="console-panel"
            style={{
              padding: '16px',
              position: 'relative',
              overflow: 'hidden'
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '8px'
              }}
            >
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-muted)',
                  fontWeight: 500
                }}
              >
                {c.title}
              </span>
              <Icon size={16} color={c.colorVar} />
            </div>

            <div
              className="num"
              style={{
                fontSize: 'var(--text-xl)',
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                color: c.colorVar,
                marginBottom: '4px'
              }}
            >
              {c.value}
            </div>

            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--color-ink-2)',
                marginBottom: '10px'
              }}
            >
              {c.sub}
            </div>

            {/* Gauge meter */}
            <div
              style={{
                width: '100%',
                height: '4px',
                backgroundColor: 'var(--color-paper)',
                borderRadius: 'var(--radius-sm)',
                overflow: 'hidden',
                border: 'var(--rule-hair) solid var(--color-rule-subtle)'
              }}
            >
              <div
                style={{
                  width: c.metric,
                  height: '100%',
                  backgroundColor: c.colorVar,
                  transition: 'width var(--dur-long) var(--ease-out)'
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
