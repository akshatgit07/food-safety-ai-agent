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

type MealPlanRequest = {
  days: number;
  goal: string;
  diet: string;
  calorie_target?: number;
  meals_per_day: number;
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

  const [mealPlanForm, setMealPlanForm] = useState<MealPlanRequest>({
    days: 5,
    goal: 'muscle gain',
    diet: 'vegetarian',
    calorie_target: 2400,
    meals_per_day: 3,
  });
  const [mealPlanResult, setMealPlanResult] = useState<any>(null);
  const [mealPlanLoading, setMealPlanLoading] = useState(false);
  const [mealPlanError, setMealPlanError] = useState<string | null>(null);

  const [shoppingListResult, setShoppingListResult] = useState<any>(null);
  const [shoppingListLoading, setShoppingListLoading] = useState(false);
  const [shoppingListError, setShoppingListError] = useState<string | null>(null);

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
        headers: { 'Content-Type': 'application/json' },
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

  async function handleGenerateMealPlan() {
    if (!apiUrl || mealPlanLoading) return;

    setMealPlanLoading(true);
    setMealPlanError(null);
    setShoppingListResult(null);
    setShoppingListError(null);

    try {
      const response = await fetch(`${apiUrl}/meal-plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(mealPlanForm),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || `Backend returned ${response.status}`);
      }

      setMealPlanResult(payload);
    } catch (err) {
      setMealPlanError(err instanceof Error ? err.message : 'Unable to generate meal plan');
    } finally {
      setMealPlanLoading(false);
    }
  }

  async function handleGenerateShoppingList() {
    if (!apiUrl || shoppingListLoading || !mealPlanResult) return;

    setShoppingListLoading(true);
    setShoppingListError(null);

    try {
      const response = await fetch(`${apiUrl}/shopping-list`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meal_plan: mealPlanResult, servings: 1 }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload?.detail || `Backend returned ${response.status}`);
      }

      setShoppingListResult(payload);
    } catch (err) {
      setShoppingListError(err instanceof Error ? err.message : 'Unable to generate shopping list');
    } finally {
      setShoppingListLoading(false);
    }
  }

  return (
    <main style={styles.pageShell}>
      <section style={styles.heroCard}>
        <p style={styles.eyebrow}>Guiltless AI Prototype</p>
        <h1 style={styles.heading}>Food Safety AI Agent</h1>
        <p style={styles.subtitle}>
          A nutrition assistant for meal planning, food recommendations,
          shopping lists, and product intelligence.
        </p>

        <div style={styles.statusCard}>
          <span
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

        <div style={styles.grid}>
          <div style={styles.column}>
            <div style={styles.chatShell}>
              <div style={styles.chatHeader}>
                <h2 style={styles.sectionTitle}>Nutrition Chat</h2>
                <p style={styles.sectionSubtitle}>Ask a food or meal question and hit the live /chat endpoint.</p>
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
          </div>

          <div style={styles.column}>
            <div style={styles.panel}>
              <div style={styles.panelHeader}>
                <h2 style={styles.sectionTitle}>Meal Plan Generator</h2>
                <p style={styles.sectionSubtitle}>Generate a structured meal plan using the live /meal-plan endpoint.</p>
              </div>

              <div style={styles.formStack}>
                <label style={styles.label}>
                  Goal
                  <input
                    value={mealPlanForm.goal}
                    onChange={(event) => setMealPlanForm((current) => ({ ...current, goal: event.target.value }))}
                    style={styles.input}
                  />
                </label>
                <label style={styles.label}>
                  Diet
                  <input
                    value={mealPlanForm.diet}
                    onChange={(event) => setMealPlanForm((current) => ({ ...current, diet: event.target.value }))}
                    style={styles.input}
                  />
                </label>
                <div style={styles.twoCol}>
                  <label style={styles.label}>
                    Days
                    <input
                      type="number"
                      min={1}
                      max={7}
                      value={mealPlanForm.days}
                      onChange={(event) => setMealPlanForm((current) => ({ ...current, days: Number(event.target.value) }))}
                      style={styles.input}
                    />
                  </label>
                  <label style={styles.label}>
                    Meals / day
                    <input
                      type="number"
                      min={1}
                      max={6}
                      value={mealPlanForm.meals_per_day}
                      onChange={(event) => setMealPlanForm((current) => ({ ...current, meals_per_day: Number(event.target.value) }))}
                      style={styles.input}
                    />
                  </label>
                </div>
                <label style={styles.label}>
                  Calorie target
                  <input
                    type="number"
                    value={mealPlanForm.calorie_target ?? ''}
                    onChange={(event) => setMealPlanForm((current) => ({
                      ...current,
                      calorie_target: event.target.value ? Number(event.target.value) : undefined,
                    }))}
                    style={styles.input}
                  />
                </label>

                <div style={styles.buttonRow}>
                  <button onClick={handleGenerateMealPlan} disabled={mealPlanLoading} style={styles.button}>
                    {mealPlanLoading ? 'Generating…' : 'Generate meal plan'}
                  </button>
                  <button
                    onClick={handleGenerateShoppingList}
                    disabled={!mealPlanResult || shoppingListLoading}
                    style={{
                      ...styles.button,
                      background: mealPlanResult ? '#4f46e5' : '#94a3b8',
                    }}
                  >
                    {shoppingListLoading ? 'Building…' : 'Build shopping list'}
                  </button>
                </div>
                {mealPlanError && <p style={styles.errorText}>{mealPlanError}</p>}
                {shoppingListError && <p style={styles.errorText}>{shoppingListError}</p>}
              </div>
            </div>

            <div style={styles.outputPanel}>
              <h3 style={styles.outputTitle}>Meal plan output</h3>
              <pre style={styles.pre}>{mealPlanResult ? JSON.stringify(mealPlanResult, null, 2) : 'No meal plan generated yet.'}</pre>
            </div>

            <div style={styles.outputPanel}>
              <h3 style={styles.outputTitle}>Shopping list output</h3>
              <pre style={styles.pre}>{shoppingListResult ? JSON.stringify(shoppingListResult, null, 2) : 'Generate a meal plan first, then build a shopping list.'}</pre>
            </div>
          </div>
        </div>
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
    maxWidth: '1280px',
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
  grid: {
    display: 'grid',
    gridTemplateColumns: '1.05fr 0.95fr',
    gap: '24px',
    alignItems: 'start',
  },
  column: {
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
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
  panel: {
    border: '1px solid #e5e7eb',
    borderRadius: '20px',
    background: '#ffffff',
    overflow: 'hidden',
  },
  panelHeader: {
    padding: '20px 24px',
    borderBottom: '1px solid #e5e7eb',
    background: '#fafafa',
  },
  sectionTitle: {
    margin: 0,
    fontSize: '22px',
    color: '#0f172a',
  },
  sectionSubtitle: {
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
  buttonRow: {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap',
  },
  errorText: {
    marginTop: '12px',
    color: '#dc2626',
    fontWeight: 600,
  },
  formStack: {
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    padding: '24px',
  },
  label: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    color: '#334155',
    fontWeight: 600,
  },
  input: {
    borderRadius: '14px',
    border: '1px solid #cbd5e1',
    padding: '12px 14px',
    fontSize: '15px',
  },
  twoCol: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '12px',
  },
  outputPanel: {
    border: '1px solid #e5e7eb',
    borderRadius: '20px',
    padding: '20px',
    background: '#ffffff',
  },
  outputTitle: {
    marginTop: 0,
    marginBottom: '12px',
    color: '#0f172a',
  },
  pre: {
    margin: 0,
    background: '#0f172a',
    color: '#e2e8f0',
    padding: '16px',
    borderRadius: '16px',
    overflowX: 'auto',
    whiteSpace: 'pre-wrap',
    fontSize: '13px',
    lineHeight: 1.5,
  },
};
