import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import LiveFeed from './components/LiveFeed';
import ControlPanel from './components/ControlPanel';
import TelemetryBar from './components/TelemetryBar';
import SnapshotGallery from './components/SnapshotGallery';
import { HelpCircle } from 'lucide-react';
import { getApiUrl } from './config';

export default function App() {
  const [stats, setStats] = useState({
    fps: 0,
    detections: 0,
    motion_level: 0,
    motion_detected: false,
    mode: 'face',
    resolution: '640x480',
    source: 'standby',
    selected_source: 'standby',
    active_source: null,
    source_error: 'Standby mode active'
  });
  const [config, setConfig] = useState({
    esp32_ip: '192.168.4.1',
    source_type: 'standby',
    flash_state: false,
    flash_brightness: 255,
    auto_capture_motion: false
  });
  const [captures, setCaptures] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isFlashing, setIsFlashing] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [actionError, setActionError] = useState(null);

  // Poll real-time telemetry from AI backend
  useEffect(() => {
    let active = true;
    const fetchStats = async () => {
      try {
        const res = await fetch(getApiUrl('/api/stats'));
        if (res.ok && active) {
          const data = await res.json();
          setStats(data);
          setIsConnected(Boolean(data.connected));
        } else if (active) {
          setIsConnected(false);
        }
      } catch {
        if (active) setIsConnected(false);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 450);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const refreshCaptures = async () => {
    try {
      const res = await fetch(getApiUrl('/api/captures'));
      if (res.ok) {
        const data = await res.json();
        setCaptures(data);
      }
    } catch {
      // Offline fallback
    }
  };

  // Fetch initial config and captures
  useEffect(() => {
    let isMounted = true;
    const initData = async () => {
      try {
        const res = await fetch(getApiUrl('/api/config'));
        if (res.ok && isMounted) {
          const data = await res.json();
          if (data.config) setConfig(data.config);
        }
      } catch {
        // Offline fallback
      }
      try {
        const res = await fetch(getApiUrl('/api/captures'));
        if (res.ok && isMounted) {
          const data = await res.json();
          setCaptures(data);
        }
      } catch {
        // Offline fallback
      }
    };

    initData();
    return () => { isMounted = false; };
  }, []);

  const handleModeChange = async (mode) => {
    setStats((prev) => ({ ...prev, mode }));
    try {
      const res = await fetch(getApiUrl('/api/config'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setActionError(err.error || 'Failed to update vision mode');
        setTimeout(() => setActionError(null), 3500);
      }
    } catch (err) {
      console.error('Failed to change mode', err);
      setActionError('Network error changing vision mode');
      setTimeout(() => setActionError(null), 3500);
    }
  };

  const handleConfigUpdate = async (updatedFields) => {
    try {
      const res = await fetch(getApiUrl('/api/config'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedFields)
      });
      if (res.ok) {
        const data = await res.json();
        if (data.config) setConfig(data.config);
        return { success: true };
      } else {
        const err = await res.json().catch(() => ({}));
        const msg = err.error || 'Failed to update configuration';
        setActionError(msg);
        setTimeout(() => setActionError(null), 3500);
        return { success: false, error: msg };
      }
    } catch (err) {
      console.error('Failed to update config', err);
      setActionError('Network error connecting to backend');
      setTimeout(() => setActionError(null), 3500);
      return { success: false, error: 'Network connection failed' };
    }
  };

  const handleFlashToggle = async (state) => {
    try {
      const res = await fetch(getApiUrl('/api/flash'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state, brightness: config.flash_brightness })
      });
      if (res.ok) {
        setConfig((prev) => ({ ...prev, flash_state: state }));
      } else {
        const err = await res.json().catch(() => ({}));
        setActionError(err.error || 'Hardware LED command failed');
        setTimeout(() => setActionError(null), 3500);
      }
    } catch (err) {
      console.error('Flash trigger failed', err);
      setActionError('Failed to contact camera flash endpoint');
      setTimeout(() => setActionError(null), 3500);
    }
  };

  const handleBrightnessChange = async (brightness) => {
    try {
      const res = await fetch(getApiUrl('/api/flash'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state: config.flash_state, brightness })
      });
      if (res.ok) {
        setConfig((prev) => ({ ...prev, flash_brightness: brightness }));
      } else {
        const err = await res.json().catch(() => ({}));
        setActionError(err.error || 'Failed to set brightness');
        setTimeout(() => setActionError(null), 3500);
      }
    } catch {
      // Offline fallback
    }
  };

  const handleSnapshot = async () => {
    setIsCapturing(true);
    setIsFlashing(true);
    setTimeout(() => setIsFlashing(false), 300);

    try {
      const res = await fetch(getApiUrl('/api/capture'), { method: 'POST' });
      if (res.ok) {
        await refreshCaptures();
      } else {
        const err = await res.json().catch(() => ({}));
        setActionError(err.error || 'Failed to record snapshot');
        setTimeout(() => setActionError(null), 3500);
      }
    } catch (err) {
      console.error('Capture failed', err);
      setActionError('Capture network request failed');
      setTimeout(() => setActionError(null), 3500);
    } finally {
      setIsCapturing(false);
    }
  };

  const handleDeleteCapture = async (filename) => {
    try {
      const res = await fetch(getApiUrl(`/api/captures/${encodeURIComponent(filename)}`), {
        method: 'DELETE'
      });
      if (res.ok) {
        setCaptures((prev) => prev.filter((c) => c.filename !== filename));
      }
    } catch (err) {
      console.error('Delete capture failed', err);
    }
  };

  const handleClearCaptions = async () => {
    try {
      await fetch(getApiUrl('/api/captions'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'clear' })
      });
      setStats((prev) => ({ ...prev, current_sentence: '', gesture: 'None' }));
    } catch (err) {
      console.error('Clear captions failed', err);
    }
  };

  const handleTrainGesture = async (phrase) => {
    try {
      const res = await fetch(getApiUrl('/api/train_gesture'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phrase })
      });
      return await res.json();
    } catch (err) {
      console.error('Train gesture failed', err);
      return { success: false, error: 'Network error communicating with backend' };
    }
  };

  return (
    <div
      style={{
        maxWidth: 'var(--container)',
        margin: '0 auto',
        padding: '24px 20px 60px 20px',
        boxSizing: 'border-box'
      }}
    >
      <Header
        stats={stats}
        isConnected={isConnected}
        esp32Ip={config.esp32_ip}
      />

      <TelemetryBar
        stats={stats}
        isConnected={isConnected}
      />

      {actionError && (
        <div
          role="alert"
          style={{
            marginBottom: '16px',
            padding: '10px 16px',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid var(--color-alert)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--color-alert)',
            fontSize: 'var(--text-sm)',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-mono)'
          }}
        >
          <span>⚠ {actionError}</span>
          <button
            onClick={() => setActionError(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '16px' }}
          >
            ×
          </button>
        </div>
      )}

      {/* Main Grid: Viewport + Controls */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1.8fr) minmax(340px, 1fr)',
          gap: 'var(--gap-columns)',
          alignItems: 'start'
        }}
      >
        {/* Left Column: Video Live Stream & Captures */}
        <div>
          <LiveFeed
            stats={stats}
            isConnected={isConnected}
            onSnapshot={handleSnapshot}
            isFlashing={isFlashing}
            onClearCaptions={handleClearCaptions}
          />

          <SnapshotGallery
            captures={captures}
            onRefresh={refreshCaptures}
            onDelete={handleDeleteCapture}
          />
        </div>

        {/* Right Column: AI Model Selection & Control Deck */}
        <div>
          <ControlPanel
            config={config}
            activeMode={stats.mode || 'face'}
            onModeChange={handleModeChange}
            onConfigUpdate={handleConfigUpdate}
            onFlashToggle={handleFlashToggle}
            flashState={config.flash_state}
            flashBrightness={config.flash_brightness}
            onBrightnessChange={handleBrightnessChange}
            onSnapshot={handleSnapshot}
            isCapturing={isCapturing}
            stats={stats}
            onClearCaptions={handleClearCaptions}
            onTrainGesture={handleTrainGesture}
          />

          {/* Quick Hardware Pinout & Flashing Guide */}
          <div className="console-panel" style={{ padding: '16px 20px', marginTop: '20px' }}>
            <button
              type="button"
              onClick={() => setShowGuide(!showGuide)}
              className="btn btn-secondary"
              style={{
                width: '100%',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                whiteSpace: 'nowrap'
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-sm)' }}>
                <HelpCircle size={16} color="var(--color-accent)" />
                <span style={{ whiteSpace: 'nowrap' }}>Flashing guide</span>
              </span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--color-accent)' }}>
                {showGuide ? 'Hide' : 'View'}
              </span>
            </button>

            {showGuide && (
              <div style={{ marginTop: '16px', fontSize: 'var(--text-xs)', color: 'var(--color-ink-2)', lineHeight: '1.6' }}>
                <div
                  style={{
                    backgroundColor: 'var(--color-paper)',
                    border: 'var(--rule-hair) solid var(--color-rule)',
                    padding: '12px',
                    borderRadius: 'var(--radius-sm)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-xs)',
                    marginBottom: '12px'
                  }}
                >
                  <div style={{ color: 'var(--color-emerald)', fontWeight: 700, marginBottom: '6px' }}>
                    FTDI to ESP32-CAM wiring:
                  </div>
                  <div>GND to GND</div>
                  <div>5V to 5V (use stable 5V 2A power supply)</div>
                  <div>U0R to TX (FTDI)</div>
                  <div>U0T to RX (FTDI)</div>
                  <div style={{ color: 'var(--color-amber)', marginTop: '6px' }}>
                    GPIO 0 to GND (bridge during flashing only, disconnect to boot)
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <p>1. Open <code style={{ color: 'var(--color-accent)' }}>firmware/esp32_cam_streamer.ino</code> in Arduino IDE.</p>
                  <p>2. Select Board: <strong>“AI Thinker ESP32-CAM”</strong>.</p>
                  <p>3. Enter your Wi-Fi SSID and password.</p>
                  <p>4. Flash firmware, disconnect GPIO 0 from GND, then press RST button.</p>
                  <p>5. Enter the IP printed in Serial Monitor into the host address field above.</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
