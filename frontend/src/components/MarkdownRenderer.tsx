import ReactMarkdown from 'react-markdown';

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div style={{ fontSize: 14, lineHeight: 1.8, color: '#8b949e' }}>
      <ReactMarkdown
        components={{
          h1: ({ children }) => <h1 style={{ fontSize: 22, color: '#e6edf3', borderBottom: '1px solid rgba(48,54,61,0.9)', paddingBottom: 8 }}>{children}</h1>,
          h2: ({ children }) => <h2 style={{ fontSize: 18, color: '#e6edf3', marginTop: 24 }}>{children}</h2>,
          h3: ({ children }) => <h3 style={{ fontSize: 15, color: '#e6edf3', marginTop: 16 }}>{children}</h3>,
          p: ({ children }) => <p style={{ marginBottom: 12 }}>{children}</p>,
          strong: ({ children }) => <strong style={{ color: '#e6edf3' }}>{children}</strong>,
          ul: ({ children }) => <ul style={{ paddingLeft: 20 }}>{children}</ul>,
          li: ({ children }) => <li style={{ marginBottom: 4 }}>{children}</li>,
          ol: ({ children }) => <ol style={{ paddingLeft: 20 }}>{children}</ol>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
