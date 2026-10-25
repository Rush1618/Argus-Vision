import React, { useState, useRef } from 'react';
import { Maximize2, Minimize2, Eye, ShieldAlert, Camera, Sparkles } from 'lucide-react';

export default function LiveFeed({ stats, _isConnected, onSnapshot, isFlashing }) {
  const [useAiStream, setUseAiStream] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const videoContainerRef = useRef(null);

  const streamUrl = useAiStream
    ? 'http://localhost:5000/video_feed'
    : 'http://localhost:5000/raw_feed';

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      videoContainerRef.current?.requestFullscreen?.();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen?.();
      setIsFullscreen(false);
    }
  };

  return (
    <div
      ref={videoContainerRef}
      className="console-panel"
      style={{
        position: 'relative',
        overflow: 'hidden',
        backgroundColor: 'var(--color-paper)',
        borderColor: stats.motion_detected ? 'var(--color-alert)' : 'var(--color-rule)'
      }}
    >
      {/* Camera Capture Shutter Flash */}
      {isFlashing && <div className="capture-flash" />}

      {/* Main Video Viewport */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          minHeight: '440px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'var(--color-paper)'
        }}
      >
        <img
          src={streamUrl}
          alt="ESP32-CAM optical feed"
          style={{
            width: '100%',
            height: 'auto',
            maxHeight: isFullscreen ? '100vh' : '560px',
            objectFit: 'contain',
            display: 'block'
          }}
          onError={(e) => {
            setTimeout(() => {
              e.target.src = `${streamUrl}?t=${Date.now()}`;
            }, 2000);
          }}
        />

        {/* Motion Alarm Top Banner */}
        {stats.motion_detected && (
          <div
            role="alert"
            style={{
              position: 'absolute',
              top: '16px',
              left: '50%',
              transform: 'translateX(-50%)',
              backgroundColor: 'var(--color-alert)',
              color: 'var(--color-ink)',
              padding: '6px 16px',
              borderRadius: 'var(--radius-pill)',
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              zIndex: 'var(--z-raised)',
              fontFamily: 'var(--font-mono)'
            }}
          >
            <ShieldAlert size={16} />
            <span>Motion event detected ({stats.motion_level}%)</span>
          </div>
        )}

        {/* Top Controls Overlay */}
        <div
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            display: 'flex',
            gap: '8px',
            zIndex: 'var(--z-raised)'
          }}
        >
          {/* Stream Type Toggle */}
          <button
            type="button"
            onClick={() => setUseAiStream(!useAiStream)}
            className="btn btn-secondary"
            style={{
              padding: '6px 12px',
              fontSize: 'var(--text-xs)',
              backgroundColor: useAiStream ? 'var(--color-paper-3)' : 'var(--color-paper)',
              borderColor: useAiStream ? 'var(--color-accent)' : 'var(--color-rule)'
            }}
          >
            {useAiStream ? <Sparkles size={14} color="var(--color-accent)" /> : <Eye size={14} />}
            <span>{useAiStream ? 'Neural overlay' : 'Raw sensor'}</span>
          </button>

          {/* Quick Snapshot Button */}
          <button
            type="button"
            onClick={onSnapshot}
            className="btn btn-secondary"
            style={{
              padding: '6px 12px',
              fontSize: 'var(--text-xs)'
            }}
            title="Snap frame"
          >
            <Camera size={14} color="var(--color-emerald)" />
            <span>Capture</span>
          </button>

          {/* Fullscreen Toggle */}
          <button
            type="button"
            onClick={toggleFullscreen}
            className="btn btn-secondary"
            style={{
              padding: '6px 10px'
            }}
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>

        {/* Bottom Status Readout */}
        <div
          style={{
            position: 'absolute',
            bottom: '16px',
            left: '16px',
            right: '16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            pointerEvents: 'none',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            zIndex: 'var(--z-raised)'
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--color-paper-3)',
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              border: 'var(--rule-hair) solid var(--color-rule)',
              display: 'flex',
              gap: '12px',
              color: 'var(--color-ink-2)'
            }}
          >
            <span>Source: <strong>{(stats.source || 'ESP32').toLowerCase()}</strong></span>
            <span>Resolution: <strong style={{ color: 'var(--color-accent)' }}>{stats.resolution || '640x480'}</strong></span>
          </div>

          <div
            style={{
              backgroundColor: 'var(--color-paper-3)',
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              border: 'var(--rule-hair) solid var(--color-rule)',
              display: 'flex',
              gap: '12px',
              color: 'var(--color-ink-2)'
            }}
          >
            <span>
              Targets: <strong style={{ color: 'var(--color-emerald)' }}>{stats.detections || 0}</strong>
            </span>
            <span>
              Fps: <strong style={{ color: (stats.fps || 0) > 20 ? 'var(--color-emerald)' : 'var(--color-amber)' }}>{stats.fps || 0}</strong>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
