'use client';

import { FormEvent, useEffect, useState } from 'react';

type HealthResponse = {
  status?: string;
  project?: string;
  healthy?: boolean;
};

type ChatApiResponse = {
  response: string;
};

type Message = {
  role: 'user' | 'assistant';
  text: string;
};

export default function Home() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      text: 'Hi — ask me about meals, ingredients, nutrition, or food choices and I’ll answer using the Render backend.',
    },
  ]);
  const [input, setInput] = useState('Is Greek yogurt healthy after a workout?');
  const [isSending, setIsSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  useEffect(() => {
    async function checkBackend() {
      if (!apiUrl) {
        setHealthError('NEXT_PUBLIC_API_URL is not configured in Vercel.');
        return;
      }

      try {
        const response = await fetch(`${apiUrl}/health`);
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        setHealth(await response.json());
      } catch (err) {
        setHealthError(err instanceof Error ? err.message : 'Unable to reach backend');
      }
    }

    checkBackend();
  }, [apiUrl]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isSending) return;

    if (!apiUrl) {
      setChatError('NEXT_PUBLIC_API_URL is not configured in Vercel.');
      return;
    }

    setChatError(null);
    setMessages((current) => [...current, { role: 'user', text: trimmed }]);
    setInput('');
    setIsSending(true);

    try {
      const response = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: trimmed }),
      });

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload?.detail || `Backend returned ${response.status}`);
      }

      const data = payload as ChatApiResponse;
      setMessages((current) => [...current, { role: 'assistant', text: data.response }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to reach backend';
      setChatError(message);
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          text: `I hit an error while calling the backend: ${message}`,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main className="page-shell" style={styles.pageShell}>
      <section className="hero-card" style={styles.heroCard}>
        <p className="eyebrow" style={styles.eyebrow}>Guiltless AI Prototype</p>
        <h1 style={styles.heading}>Food Safety AI Agent</h1>
        <p className="subtitle" style={styles.subtitle}>
          A nutrition assistant for meal planning, food recommendations,
          shopping lists, and product intelligence.
        </p>

        <div className="status-card" style={styles.statusCard}>
          <span
            className={`status-dot ${health ? 'online' : healthError ? 'offline' : ''}`}
            style={{
              ...styles.statusDot,
              backgroundColor: health ? '#22c55e' : healthError ? '#ef4444' : '#f59e0b',
            }}
          />
          <div>
            <strong>Backend status</strong>
            <p style={styles.statusText}>
              {health
                ? 'Connected to the FastAPI service on Render.'
                : healthError
                  ? healthError
                  : 'Checking Render backend...'}
            </p>
          </div>
        </div>

        <div style={styles.chatShell}>
          <div style={styles.chatHeader}>
            <div>
              <h2 style={styles.chatTitle}>Nutrition Chat</h2>
              <p style={styles.chatSubtitle}>Ask a food or meal question and hit the live /chat endpoint.</p>
            </div>
          </div>

          <div style={styles.messagesPanel}>
            {messages.map((message, index) => (
              <div
                key={`${message.role}-${index}`}
                style={{
                  ...styles.messageBubble,
                  alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
                  backgroundColor: message.role === 'user' ? '#111827' : '#f3f4f6',
                  color: message.role === 'user' ? '#ffffff' : '#111827',
                }}
              >
                <strong style={styles.messageRole}>{message.role === 'user' ? 'You' : 'Assistant'}</strong>
                <p style={styles.messageText}>{message.text}</p>
              </div>
            ))}
            {isSending && <p style={styles.loadingText}>Thinking…</p>}
          </div>

          <form onSubmit={handleSubmit} style={styles.form}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about a meal, ingredient, diet goal, or grocery choice..."
              rows={4}
              style={styles.textarea}
            />
            <div style={styles.formFooter}>
              <span style={styles.helperText}>Backend route: POST /chat</span>
              <button type="submit" disabled={isSending} style={styles.button}>
                {isSending ? 'Sending…' : 'Send question'}
              </button>
            </div>
            {chatError && <p style={styles.errorText}>{chatError}</p>}
          </form>
        </div>

        {health && <pre style={styles.pre}>{JSON.stringify(health, null, 2)}</pre>}
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  pageShell: {
    minHeight: '100vh',
    background: 'linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%)',
    padding: '40px 16px',
    fontFamily: 'Inter, Arial, sans-serif',
  },
  heroCard: {
    maxWidth: '920px',
    margin: '0 auto',
    background: '#ffffff',
    borderRadius: '24px',
    padding: '32px',
    boxShadow: '0 24px 60px rgba(15, 23, 42, 0.08)',
    border: '1px solid #e5e7eb',
  },
  eyebrow: {
    textTransform: 'uppercase',
    letterSpacing: '0.12em',
    fontSize: '12px',
    color: '#6366f1',
    fontWeight: 700,
    marginBottom: '12px',
  },
  heading: {
    fontSize: '40px',
    lineHeight: 1.1,
    margin: 0,
    color: '#0f172a',
  },
  subtitle: {
    fontSize: '18px',
    lineHeight: 1.6,
    color: '#475569',
    marginTop: '16px',
    marginBottom: '24px',
    maxWidth: '720px',
  },
  statusCard: {
    display: 'flex',
    gap: '12px',
    alignItems: 'flex-start',
    background: '#f8fafc',
    border: '1px solid #e5e7eb',
    borderRadius: '16px',
    padding: '16px',
    marginBottom: '28px',
  },
  statusDot: {
    width: '12px',
    height: '12px',
    borderRadius: '999px',
    marginTop: '6px',
    flexShrink: 0,
  },
  statusText: {
    margin: '4px 0 0',
    color: '#475569',
  },
  chatShell: {
    border: '1px solid #e5e7eb',
    borderRadius: '20px',
    overflow: 'hidden',
    background: '#ffffff',
  },
  chatHeader: {
    padding: '20px 24px',
    borderBottom: '1px solid #e5e7eb',
    background: '#fafafa',
  },
  chatTitle: {
    margin: 0,
    fontSize: '22px',
    color: '#0f172a',
  },
  chatSubtitle: {
    margin: '8px 0 0',
    color: '#64748b',
  },
  messagesPanel: {
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    padding: '24px',
    minHeight: '340px',
    background: '#fcfcfd',
  },
  messageBubble: {
    maxWidth: '80%',
    padding: '14px 16px',
    borderRadius: '18px',
    boxShadow: '0 8px 20px rgba(15, 23, 42, 0.05)',
  },
  messageRole: {
    display: 'block',
    marginBottom: '6px',
    fontSize: '12px',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  },
  messageText: {
    margin: 0,
    whiteSpace: 'pre-wrap',
    lineHeight: 1.6,
  },
  loadingText: {
    margin: 0,
    color: '#6366f1',
    fontWeight: 600,
  },
  form: {
    borderTop: '1px solid #e5e7eb',
    padding: '20px 24px 24px',
    background: '#ffffff',
  },
  textarea: {
    width: '100%',
    resize: 'vertical',
    borderRadius: '16px',
    border: '1px solid #cbd5e1',
    padding: '14px 16px',
    fontSize: '15px',
    lineHeight: 1.5,
    outline: 'none',
    boxSizing: 'border-box',
  },
  formFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '12px',
    marginTop: '14px',
    flexWrap: 'wrap',
  },
  helperText: {
    color: '#64748b',
    fontSize: '14px',
  },
  button: {
    background: '#111827',
    color: '#ffffff',
    border: 'none',
    borderRadius: '999px',
    padding: '12px 18px',
    fontWeight: 700,
    cursor: 'pointer',
  },
  errorText: {
    marginTop: '12px',
    color: '#dc2626',
    fontWeight: 600,
  },
  pre: {
    marginTop: '24px',
    background: '#0f172a',
    color: '#e2e8f0',
    padding: '16px',
    borderRadius: '16px',
    overflowX: 'auto',
  },
};
