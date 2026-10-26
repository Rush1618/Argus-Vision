import React, { useState } from 'react';
import { Images, Download, X, RefreshCw, Trash2 } from 'lucide-react';
import { getApiUrl } from '../config';

export default function SnapshotGallery({ captures, onRefresh, onDelete }) {
  const [selectedImage, setSelectedImage] = useState(null);

  const handleDelete = (filename) => {
    if (onDelete) {
      onDelete(filename);
      if (selectedImage && selectedImage.filename === filename) {
        setSelectedImage(null);
      }
    }
  };

  return (
    <div className="console-panel" style={{ padding: '20px', marginTop: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Images size={16} color="var(--color-accent)" />
          <h2 style={{ fontSize: 'var(--text-title)', fontWeight: 600, color: 'var(--color-ink)' }}>Detection snapshots</h2>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-muted)', fontFamily: 'var(--font-mono)' }}>
            ({captures.length} files)
          </span>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          className="btn btn-secondary"
          style={{ padding: '6px 12px', fontSize: 'var(--text-xs)' }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {captures.length === 0 ? (
        <div
          style={{
            padding: '36px',
            textAlign: 'center',
            color: 'var(--color-muted)',
            fontSize: 'var(--text-sm)',
            border: 'var(--rule-hair) dashed var(--color-rule)',
            borderRadius: 'var(--radius-sm)'
          }}
        >
          No snapshots recorded yet. Use the capture button or enable “Auto-save on movement” to record events.
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: '12px',
            maxHeight: '260px',
            overflowY: 'auto',
            paddingRight: '6px'
          }}
        >
          {captures.map((item, idx) => (
            <div
              key={idx}
              className="console-panel-interactive"
              style={{
                overflow: 'hidden',
                cursor: 'pointer',
                backgroundColor: 'var(--color-paper)'
              }}
              onClick={() => setSelectedImage(item)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') setSelectedImage(item);
              }}
            >
              <div style={{ width: '100%', height: '110px', overflow: 'hidden', position: 'relative' }}>
                <img
                  src={getApiUrl(item.url)}
                  alt={item.filename}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  fetchPriority={idx === 0 ? 'high' : 'auto'}
                  loading={idx === 0 ? 'eager' : 'lazy'}
                />
                <span
                  style={{
                    position: 'absolute',
                    bottom: '6px',
                    right: '6px',
                    backgroundColor: 'var(--color-paper)',
                    color: 'var(--color-ink-2)',
                    fontSize: 'var(--text-xs)',
                    fontFamily: 'var(--font-mono)',
                    padding: '2px 6px',
                    borderRadius: 'var(--radius-sm)',
                    border: 'var(--rule-hair) solid var(--color-rule)'
                  }}
                >
                  {item.size_kb} KB
                </span>
              </div>
              <div style={{ padding: '8px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--color-ink-2)',
                    fontFamily: 'var(--font-mono)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    maxWidth: '100px'
                  }}
                >
                  {item.filename}
                </span>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <a
                    href={`http://localhost:5000${item.url}`}
                    download={item.filename}
                    onClick={(e) => e.stopPropagation()}
                    className="btn"
                    style={{ padding: '4px', color: 'var(--color-accent)' }}
                    title="Download file"
                  >
                    <Download size={14} />
                  </a>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(item.filename);
                    }}
                    className="btn"
                    style={{ padding: '4px', color: 'var(--color-alert)' }}
                    title="Delete snapshot"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Image Modal Lightbox */}
      {selectedImage && (
        <div
          onClick={() => setSelectedImage(null)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'color-mix(in oklab, var(--color-paper) 85%, transparent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 'var(--z-modal)',
            padding: '20px'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="console-panel"
            style={{
              maxWidth: '900px',
              width: '100%',
              overflow: 'hidden',
              borderColor: 'var(--color-accent)'
            }}
          >
            <div
              style={{
                padding: '12px 16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                borderBottom: 'var(--rule-hair) solid var(--color-rule)',
                backgroundColor: 'var(--color-paper-3)'
              }}
            >
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--color-ink)' }}>
                {selectedImage.filename}
              </span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <a
                  href={getApiUrl(selectedImage.url)}
                  download={selectedImage.filename}
                  className="btn btn-secondary"
                  style={{ padding: '6px 12px', fontSize: 'var(--text-xs)' }}
                >
                  <Download size={14} /> Download
                </a>
                <button
                  type="button"
                  onClick={() => handleDelete(selectedImage.filename)}
                  className="btn btn-secondary"
                  style={{ padding: '6px 12px', fontSize: 'var(--text-xs)', color: 'var(--color-alert)' }}
                >
                  <Trash2 size={14} /> Delete
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedImage(null)}
                  className="btn btn-secondary"
                  style={{ padding: '6px 10px' }}
                  aria-label="Close modal"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            <div style={{ padding: '12px', backgroundColor: 'var(--color-paper)', display: 'flex', justifyContent: 'center' }}>
              <img
                src={`http://localhost:5000${selectedImage.url}`}
                alt={selectedImage.filename}
                style={{ maxWidth: '100%', maxHeight: '70vh', objectFit: 'contain' }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
