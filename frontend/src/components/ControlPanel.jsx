import React, { useState } from 'react';
import { 
  Lightbulb, 
  Camera, 
  ShieldAlert, 
  Radio, 
  Scan, 
  Bot, 
  Moon, 
  Layers,
  Save,
  CheckCircle2,
  Usb,
  Wifi,
  Hand,
  Trash2,
  PlusCircle,
  Sliders,
  Monitor
} from 'lucide-react';

export default function ControlPanel({ 
  config, 
  activeMode, 
  onModeChange, 
  onConfigUpdate, 
  onFlashToggle, 
  flashState, 
  flashBrightness, 
  onBrightnessChange, 
  onSnapshot,
  isCapturing,
  stats = {},
  onClearCaptions,
  onTrainGesture
}) {
  const [comPort, setComPort] = useState(config.com_port || 'COM9');
  const [ipInput, setIpInput] = useState(config.esp32_ip || '192.168.4.1');
  const [sourceType, setSourceType] = useState(config.source_type || 'screen');
  const [savedBadge, setSavedBadge] = useState(false);
  const [autoCapture, setAutoCapture] = useState(config.auto_capture_motion || false);
  const [motionSens, setMotionSens] = useState(25);
  const [customPhrase, setCustomPhrase] = useState('');
  const [trainingStatus, setTrainingStatus] = useState(null);
  const [isTraining, setIsTraining] = useState(false);

  const handleTrainSubmit = async (e) => {
    e.preventDefault();
    if (!customPhrase.trim()) return;
    setIsTraining(true);
    setTrainingStatus(null);
    try {
      const res = await onTrainGesture(customPhrase.trim());
      if (res.success) {
        setTrainingStatus({ type: 'success', msg: `Trained '${res.phrase}' successfully!` });
        setCustomPhrase('');
      } else {
        setTrainingStatus({ type: 'error', msg: res.error || 'Failed to train sign' });
      }
    } catch {
      setTrainingStatus({ type: 'error', msg: 'Failed to train sign' });
    } finally {
      setIsTraining(false);
      setTimeout(() => setTrainingStatus(null), 4000);
    }
  };

  const handleSaveNetwork = (e) => {
    e.preventDefault();
    onConfigUpdate({ 
      source_type: sourceType,
      com_port: comPort,
      esp32_ip: ipInput,
      auto_capture_motion: autoCapture,
      motion_threshold: motionSens
    });
    setSavedBadge(true);
    setTimeout(() => setSavedBadge(false), 2000);
  };

  const aiModes = [
    { id: 'gesture', name: 'Sign language & trails', icon: Hand, desc: 'MediaPipe ASL, gestures & laser finger movement trails', colorVar: 'var(--color-accent)' },
    { id: 'objects', name: 'Neural objects', icon: Bot, desc: 'YOLOv8 inference: people, vehicles, devices, pets', colorVar: 'var(--color-emerald)' },
    { id: 'face', name: 'Face & landmark tracker', icon: Scan, desc: 'YuNet neural face detector & 5-point facial landmarks', colorVar: 'var(--color-accent)' },
    { id: 'motion', name: 'Motion sentry', icon: ShieldAlert, desc: 'Frame differential analysis and moving entity detection', colorVar: 'var(--color-alert)' },
    { id: 'edges', name: 'Canny matrix', icon: Layers, desc: 'High-contrast edge gradient geometry filter', colorVar: 'var(--color-amber)' },
    { id: 'night_vision', name: 'Night vision', icon: Moon, desc: 'Adaptive histogram contrast equalizer for low light', colorVar: 'var(--color-emerald)' },
    { id: 'raw', name: 'Direct sensor', icon: Camera, desc: 'Unfiltered direct hardware optical feed', colorVar: 'var(--color-muted)' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Connection & Stream Source Card */}
      <div className="console-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Radio size={16} color="var(--color-accent)" />
            <h2 style={{ fontSize: 'var(--text-title)', fontWeight: 600, color: 'var(--color-ink)' }}>Connection mode</h2>
          </div>
          {savedBadge && (
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-emerald)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={14} /> Synchronized
            </span>
          )}
        </div>

        <form onSubmit={handleSaveNetwork} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
            {[
              { id: 'screen', label: 'Laptop screen', icon: Monitor },
              { id: 'usb_serial', label: 'USB serial (ESP32)', icon: Usb },
              { id: 'esp32_wifi', label: 'Wi-Fi network', icon: Wifi },
              { id: 'webcam', label: 'USB webcam', icon: Camera }
            ].map((src) => {
              const Icon = src.icon;
              const isSelected = sourceType === src.id;
              return (
                <button
                  type="button"
                  key={src.id}
                  onClick={() => {
                    setSourceType(src.id);
                    onConfigUpdate({ source_type: src.id });
                  }}
                  className="btn"
                  style={{
                    padding: '8px 10px',
                    fontSize: 'var(--text-xs)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    justifyContent: 'center',
                    backgroundColor: isSelected ? 'var(--color-paper-3)' : 'var(--color-paper)',
                    borderColor: isSelected ? 'var(--color-accent)' : 'var(--color-rule)',
                    color: isSelected ? 'var(--color-accent)' : 'var(--color-ink-2)'
                  }}
                >
                  <Icon size={14} />
                  <span>{src.label}</span>
                </button>
              );
            })}
          </div>

          {sourceType === 'usb_serial' && (
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                aria-label="COM port name"
                value={comPort}
                onChange={(e) => setComPort(e.target.value)}
                placeholder="Port (e.g. COM9)"
                className="input-field"
                style={{ flex: 1 }}
              />
              <button type="submit" className="btn btn-primary">
                <Save size={14} /> Connect USB
              </button>
            </div>
          )}

          {sourceType === 'esp32_wifi' && (
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                aria-label="ESP32 IP address"
                value={ipInput}
                onChange={(e) => setIpInput(e.target.value)}
                placeholder="192.168.4.1"
                className="input-field"
                style={{ flex: 1 }}
              />
              <button type="submit" className="btn btn-primary">
                <Save size={14} /> Connect host
              </button>
            </div>
          )}
        </form>
      </div>

      {/* AI Computer Vision Mode Selector */}
      <div className="console-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
          <Scan size={16} color="var(--color-emerald)" />
          <h2 style={{ fontSize: 'var(--text-title)', fontWeight: 600, color: 'var(--color-ink)' }}>Vision pipeline</h2>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
          {aiModes.map((m) => {
            const Icon = m.icon;
            const isSelected = activeMode === m.id;
            return (
              <button
                type="button"
                key={m.id}
                onClick={() => onModeChange(m.id)}
                className="console-panel-interactive"
                style={{
                  padding: '12px',
                  backgroundColor: isSelected ? 'var(--color-paper-3)' : 'var(--color-paper)',
                  borderColor: isSelected ? m.colorVar : 'var(--color-rule)',
                  cursor: 'pointer',
                  textAlign: 'left',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Icon size={16} color={isSelected ? m.colorVar : 'var(--color-muted)'} />
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: isSelected ? 'var(--color-ink)' : 'var(--color-ink-2)' }}>
                    {m.name}
                  </span>
                </div>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-muted)', lineHeight: '1.3' }}>
                  {m.desc}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Sign Language Studio (Active when mode is gesture) */}
      {activeMode === 'gesture' && (
        <div className="console-panel" style={{ padding: '20px', borderColor: 'var(--color-accent)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Hand size={16} color="var(--color-accent)" />
              <h2 style={{ fontSize: 'var(--text-title)', fontWeight: 600, color: 'var(--color-ink)' }}>Sign language & custom trainer</h2>
            </div>
            <span
              style={{
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-mono)',
                color: 'var(--color-accent)',
                backgroundColor: 'var(--color-paper-3)',
                padding: '2px 8px',
                borderRadius: 'var(--radius-sm)',
                border: 'var(--rule-hair) solid var(--color-rule)'
              }}
            >
              {stats.custom_gestures_count || 0} custom signs
            </span>
          </div>

          {/* Real-time Subtitle readout */}
          <div
            style={{
              backgroundColor: 'var(--color-paper-3)',
              padding: '12px',
              borderRadius: 'var(--radius-sm)',
              border: 'var(--rule-hair) solid var(--color-rule)',
              marginBottom: '14px'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-muted)', fontWeight: 600 }}>
                Live CC Sentence Buffer
              </span>
              <button
                type="button"
                onClick={onClearCaptions}
                className="btn btn-secondary"
                style={{ padding: '2px 8px', fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: '4px' }}
                title="Clear subtitle buffer"
              >
                <Trash2 size={12} /> Clear
              </button>
            </div>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-sm)',
                color: stats.current_sentence ? 'var(--color-emerald)' : 'var(--color-muted)',
                minHeight: '24px',
                wordBreak: 'break-word'
              }}
            >
              {stats.current_sentence ? `"${stats.current_sentence}"` : '(Hold hands in view to sign…)'}
            </div>
          </div>

          {/* Quick Sign Pose Trainer */}
          <form onSubmit={handleTrainSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-ink-2)' }}>
              Train new sign from current hand pose:
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={customPhrase}
                onChange={(e) => setCustomPhrase(e.target.value)}
                placeholder="Sign name (e.g. HELP, WATER)"
                className="input-field"
                style={{ flex: 1, textTransform: 'uppercase' }}
                aria-label="New sign phrase name"
              />
              <button
                type="submit"
                disabled={isTraining || !customPhrase.trim()}
                className="btn btn-primary"
                style={{ whiteSpace: 'nowrap' }}
              >
                <PlusCircle size={14} />
                <span>{isTraining ? 'Training…' : 'Train sign'}</span>
              </button>
            </div>

            {trainingStatus && (
              <div
                style={{
                  fontSize: 'var(--text-xs)',
                  color: trainingStatus.type === 'success' ? 'var(--color-emerald)' : 'var(--color-alert)',
                  marginTop: '4px'
                }}
              >
                {trainingStatus.msg}
              </div>
            )}
          </form>
        </div>
      )}

      {/* Hardware Flashlight & Triggers */}
      <div className="console-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <Lightbulb size={16} color="var(--color-amber)" />
          <h2 style={{ fontSize: 'var(--text-title)', fontWeight: 600, color: 'var(--color-ink)' }}>Hardware illuminator (GPIO 4)</h2>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-ink-2)' }}>
              LED flashlight state
            </span>
            <label className="switch">
              <input 
                type="checkbox" 
                aria-label="Toggle flashlight state"
                checked={flashState} 
                onChange={(e) => onFlashToggle(e.target.checked)} 
              />
              <span className="slider" />
            </label>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--color-muted)', marginBottom: '6px' }}>
              <span>Flash intensity (PWM)</span>
              <span className="num" style={{ fontFamily: 'var(--font-mono)' }}>{flashBrightness} / 255</span>
            </div>
            <input
              type="range"
              aria-label="Flash brightness level"
              min="0"
              max="255"
              value={flashBrightness}
              onChange={(e) => onBrightnessChange(Number(e.target.value))}
            />
          </div>
        </div>

        {/* Motion Auto Capture & Sensitivity */}
        <div style={{ paddingTop: '14px', borderTop: 'var(--rule-hair) solid var(--color-rule-subtle)', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-ink-2)' }}>
              Auto-save on movement
            </span>
            <label className="switch">
              <input 
                type="checkbox" 
                aria-label="Auto-save capture on motion detection"
                checked={autoCapture} 
                onChange={(e) => {
                  setAutoCapture(e.target.checked);
                  onConfigUpdate({ auto_capture_motion: e.target.checked });
                }} 
              />
              <span className="slider" />
            </label>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 'var(--text-xs)', color: 'var(--color-muted)', marginBottom: '6px' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Sliders size={12} /> Motion threshold sensitivity
              </span>
              <span className="num" style={{ fontFamily: 'var(--font-mono)' }}>{motionSens} Δ</span>
            </div>
            <input
              type="range"
              aria-label="Motion threshold sensitivity"
              min="10"
              max="80"
              value={motionSens}
              onChange={(e) => {
                const val = Number(e.target.value);
                setMotionSens(val);
                onConfigUpdate({ motion_threshold: val });
              }}
            />
          </div>

          <button
            type="button"
            onClick={onSnapshot}
            disabled={isCapturing}
            className="btn btn-primary"
            style={{ width: '100%', marginTop: '8px' }}
          >
            <Camera size={16} />
            <span>{isCapturing ? 'Capturing frame…' : 'Capture high-resolution frame'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
