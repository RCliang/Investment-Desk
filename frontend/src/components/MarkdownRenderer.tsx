import ReactMarkdown from 'react-markdown';

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div style={{ fontSize: 16, lineHeight: 1.6, color: 'var(--ink-soft)', fontFamily: "'Patrick Hand', 'Caveat', cursive" }}>
      <ReactMarkdown
        components={{
          h1: ({ children }) => <h1 style={{ fontFamily: "'Caveat', cursive", fontWeight: 700, fontSize: 28, color: 'var(--ink)', borderBottom: '2px dashed var(--pencil)', paddingBottom: 6, marginTop: 24 }}>{children}</h1>,
          h2: ({ children }) => <h2 style={{ fontFamily: "'Caveat', cursive", fontWeight: 700, fontSize: 22, color: 'var(--ink)', marginTop: 22 }}>{children}</h2>,
          h3: ({ children }) => <h3 style={{ fontFamily: "'Caveat', cursive", fontWeight: 700, fontSize: 18, color: 'var(--ink)', marginTop: 16 }}>{children}</h3>,
          p: ({ children }) => <p style={{ marginBottom: 12, fontSize: 16 }}>{children}</p>,
          strong: ({ children }) => <strong style={{ color: 'var(--ink)', background: 'var(--hi-yellow)', padding: '0 4px' }}>{children}</strong>,
          ul: ({ children }) => <ul style={{ paddingLeft: 20, marginBottom: 12 }}>{children}</ul>,
          li: ({ children }) => <li style={{ marginBottom: 4, fontSize: 16 }}>{children}</li>,
          ol: ({ children }) => <ol style={{ paddingLeft: 20, marginBottom: 12 }}>{children}</ol>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
