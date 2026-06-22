'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';

type Message = { role: 'user' | 'assistant'; text: string };
type Meal = {
  name?: string;
  ingredients?: Array<string | { name?: string }>;
  estimated_calories?: number;
  estimated_protein_g?: number;
  nutrition_source?: string;
  grounded_ingredient_ratio?: string;
};
type DayPlan = { day?: number | string; meals?: Meal[] };
type MealPlan = {
  summary?: string;
  notes?: string | string[];
  days?: DayPlan[];
  nutrition_grounding?: {
    source?: string;
    grounded_ingredients?: number;
    total_ingredients?: number;
  };
};
type ShoppingList = {
  servings?: number;
  categories?: Record<string, Array<string | { name?: string; quantity?: string }>>;
  notes?: string | string[];
};

export default function Home() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  const [connected, setConnected] = useState(false);
  const [statusText, setStatusText] = useState('Checking Render backend...');
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', text: 'Ask me about food choices, nutrition, or meal planning.' },
  ]);
  const [input, setInput] = useState('Is Greek yogurt healthy after a workout?');
  const [isSending, setIsSending] = useState(false);
  const [mealPlan, setMealPlan] = useState<MealPlan | null>(null);
  const [shoppingList, setShoppingList] = useState<ShoppingList | null>(null);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    days: 5,
    goal: 'muscle gain',
    diet: 'vegetarian',
    calorie_target: 2400,
    meals_per_day: 3,
  });

  useEffect(() => {
    async function checkHealth() {
      if (!apiUrl) {
        setStatusText('NEXT_PUBLIC_API_URL is not configured in Vercel.');
        return;
      }
      try {
        const response = await fetch(`${apiUrl}/health`);
        if (!response.ok) throw new Error(`Backend returned ${response.status}`);
        setConnected(true);
        setStatusText('Connected to FastAPI on Render.');
      } catch (healthError) {
        setStatusText(healthError instanceof Error ? healthError.message : 'Unable to reach backend');
      }
    }
    checkHealth();
  }, [apiUrl]);

  const groundingLabel = useMemo(() => {
    const grounding = mealPlan?.nutrition_grounding;
    if (!grounding) return null;
    const grounded = grounding.grounded_ingredients ?? 0;
    const total = grounding.total_ingredients ?? 0;
    return `${grounded}/${total} ingredients grounded • ${grounding.source ?? 'nutrition data'}`;
  }, [mealPlan]);

  async function submitChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!apiUrl || !input.trim() || isSending) return;
    const question = input.trim();
    setMessages((current) => [...current, { role: 'user', text: question }]);
    setInput('');
    setIsSending(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail || `Backend returned ${response.status}`);
      setMessages((current) => [...current, { role: 'assistant', text: payload.response }]);
    } catch (chatError) {
      const message = chatError instanceof Error ? chatError.message : 'Unable to call chat endpoint';
      setError(message);
      setMessages((current) => [...current, { role: 'assistant', text: `Error: ${message}` }]);
    } finally {
      setIsSending(false);
    }
  }

  async function generateMealPlan() {
    if (!apiUrl || loadingPlan) return;
    setLoadingPlan(true);
    setError(null);
    setShoppingList(null);
    try {
      const response = await fetch(`${apiUrl}/meal-plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail || `Backend returned ${response.status}`);
      setMealPlan(payload);
    } catch (planError) {
      setError(planError instanceof Error ? planError.message : 'Unable to generate meal plan');
    } finally {
      setLoadingPlan(false);
    }
  }

  async function generateShoppingList() {
    if (!apiUrl || !mealPlan || loadingList) return;
    setLoadingList(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/shopping-list`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meal_plan: mealPlan, servings: 1 }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail || `Backend returned ${response.status}`);
      setShoppingList(payload);
    } catch (listError) {
      setError(listError instanceof Error ? listError.message : 'Unable to generate shopping list');
    } finally {
      setLoadingList(false);
    }
  }

  async function copyShoppingList() {
    if (!shoppingList) return;
    const text = Object.entries(shoppingList.categories ?? {})
      .map(([category, items]) => {
        const rows = items.map((item) => {
          if (typeof item === 'string') return `- ${item}`;
          return `- ${item.name ?? 'Item'}${item.quantity ? ` — ${item.quantity}` : ''}`;
        });
        return `${titleCase(category)}\n${rows.join('\n')}`;
      })
      .join('\n\n');
    await navigator.clipboard.writeText(text);
  }

  return (
    <main style={styles.page}>
      <section style={styles.shell}>
        <header style={styles.header}>
          <div>
            <p style={styles.eyebrow}>Guiltless AI Prototype</p>
            <h1 style={styles.h1}>Nutrition Copilot</h1>
            <p style={styles.subtitle}>Chat, generate meal plans, ground nutrition with USDA data, and build grocery lists.</p>
          </div>
          <div style={styles.statusPill}>
            <span style={{ ...styles.dot, background: connected ? '#22c55e' : '#f59e0b' }} />
            {statusText}
          </div>
        </header>

        {error && <div style={styles.error}>{error}</div>}

        <section style={styles.grid}>
          <div style={styles.card}>
            <div style={styles.cardHeader}>
              <div>
                <h2 style={styles.h2}>Nutrition Chat</h2>
                <p style={styles.muted}>Ask about ingredients, meals, or food choices.</p>
              </div>
            </div>
            <div style={styles.messages}>
              {messages.map((message, index) => (
                <div key={`${message.role}-${index}`} style={{
                  ...styles.bubble,
                  alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
                  background: message.role === 'user' ? '#111827' : '#f3f4f6',
                  color: message.role === 'user' ? '#fff' : '#111827',
                }}>
                  <strong style={styles.role}>{message.role === 'user' ? 'You' : 'Assistant'}</strong>
                  <p style={styles.messageText}>{message.text}</p>
                </div>
              ))}
              {isSending && <p style={styles.loading}>Thinking…</p>}
            </div>
            <form onSubmit={submitChat} style={styles.chatForm}>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} rows={4} style={styles.textarea} />
              <button style={styles.primaryButton} disabled={isSending}>Send question</button>
            </form>
          </div>

          <div style={styles.stack}>
            <div style={styles.card}>
              <div style={styles.cardHeader}>
                <div>
                  <h2 style={styles.h2}>Meal Plan Generator</h2>
                  <p style={styles.muted}>Create a personalized plan and enrich it with nutrition data.</p>
                </div>
              </div>
              <div style={styles.formGrid}>
                <label style={styles.label}>Goal<input style={styles.input} value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} /></label>
                <label style={styles.label}>Diet<input style={styles.input} value={form.diet} onChange={(e) => setForm({ ...form, diet: e.target.value })} /></label>
                <label style={styles.label}>Days<input style={styles.input} type="number" min={1} max={7} value={form.days} onChange={(e) => setForm({ ...form, days: Number(e.target.value) })} /></label>
                <label style={styles.label}>Meals / day<input style={styles.input} type="number" min={1} max={6} value={form.meals_per_day} onChange={(e) => setForm({ ...form, meals_per_day: Number(e.target.value) })} /></label>
                <label style={styles.label}>Calories<input style={styles.input} type="number" value={form.calorie_target} onChange={(e) => setForm({ ...form, calorie_target: Number(e.target.value) })} /></label>
              </div>
              <div style={styles.actions}>
                <button onClick={generateMealPlan} style={styles.primaryButton} disabled={loadingPlan}>{loadingPlan ? 'Generating…' : 'Generate meal plan'}</button>
                <button onClick={generateShoppingList} style={styles.secondaryButton} disabled={!mealPlan || loadingList}>{loadingList ? 'Building…' : 'Build shopping list'}</button>
              </div>
            </div>
          </div>
        </section>

        {mealPlan && (
          <section style={styles.section}>
            <div style={styles.sectionHeader}>
              <div>
                <h2 style={styles.h2}>Your Meal Plan</h2>
                <p style={styles.muted}>{mealPlan.summary ?? 'Personalized meal plan'}</p>
              </div>
              {groundingLabel && <span style={styles.badge}>USDA-aware • {groundingLabel}</span>}
            </div>
            <div style={styles.dayGrid}>
              {(mealPlan.days ?? []).map((day, dayIndex) => (
                <article key={dayIndex} style={styles.dayCard}>
                  <h3 style={styles.dayTitle}>Day {day.day ?? dayIndex + 1}</h3>
                  <div style={styles.mealStack}>
                    {(day.meals ?? []).map((meal, mealIndex) => (
                      <div key={mealIndex} style={styles.mealCard}>
                        <div style={styles.mealTopRow}>
                          <strong style={styles.mealName}>{meal.name ?? `Meal ${mealIndex + 1}`}</strong>
                          <span style={meal.nutrition_source?.toLowerCase().includes('usda') ? styles.usdaBadge : styles.estimateBadge}>
                            {meal.nutrition_source ?? 'model estimate'}
                          </span>
                        </div>
                        <div style={styles.metrics}>
                          <span>🔥 {meal.estimated_calories ?? '—'} kcal</span>
                          <span>💪 {meal.estimated_protein_g ?? '—'} g protein</span>
                          {meal.grounded_ingredient_ratio && <span>✓ {meal.grounded_ingredient_ratio} grounded</span>}
                        </div>
                        <div style={styles.chips}>
                          {(meal.ingredients ?? []).map((ingredient, ingredientIndex) => {
                            const label = typeof ingredient === 'string' ? ingredient : ingredient.name ?? 'Ingredient';
                            return <span key={ingredientIndex} style={styles.chip}>{label}</span>;
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {shoppingList && (
          <section style={styles.section}>
            <div style={styles.sectionHeader}>
              <div>
                <h2 style={styles.h2}>Shopping List</h2>
                <p style={styles.muted}>Grouped by grocery category for {shoppingList.servings ?? 1} serving(s).</p>
              </div>
              <button onClick={copyShoppingList} style={styles.secondaryButton}>Copy list</button>
            </div>
            <div style={styles.shoppingGrid}>
              {Object.entries(shoppingList.categories ?? {}).map(([category, items]) => (
                <article key={category} style={styles.shoppingCard}>
                  <h3 style={styles.categoryTitle}>{titleCase(category)}</h3>
                  <div style={styles.checkList}>
                    {items.map((item, index) => (
                      <label key={index} style={styles.checkRow}>
                        <input type="checkbox" />
                        <span>{typeof item === 'string' ? item : item.name ?? 'Item'}</span>
                        {typeof item !== 'string' && item.quantity && <small style={styles.quantity}>{item.quantity}</small>}
                      </label>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}
      </section>
    </main>
  );
}

function titleCase(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: '100vh', background: 'linear-gradient(180deg,#f8fafc,#eef2ff)', padding: '32px 16px', fontFamily: 'Inter,Arial,sans-serif' },
  shell: { maxWidth: '1280px', margin: '0 auto' },
  header: { display: 'flex', justifyContent: 'space-between', gap: 24, alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap' },
  eyebrow: { margin: 0, color: '#4f46e5', fontWeight: 800, letterSpacing: '.14em', textTransform: 'uppercase', fontSize: 12 },
  h1: { margin: '8px 0', fontSize: 42, color: '#0f172a' },
  h2: { margin: 0, fontSize: 24, color: '#0f172a' },
  subtitle: { color: '#475569', fontSize: 18, maxWidth: 760, lineHeight: 1.6 },
  muted: { margin: '8px 0 0', color: '#64748b', lineHeight: 1.5 },
  statusPill: { display: 'flex', gap: 10, alignItems: 'center', background: '#fff', border: '1px solid #e2e8f0', borderRadius: 999, padding: '10px 14px', color: '#334155' },
  dot: { width: 10, height: 10, borderRadius: 999 },
  error: { background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c', padding: 14, borderRadius: 14, marginBottom: 20 },
  grid: { display: 'grid', gridTemplateColumns: '1.1fr .9fr', gap: 24, alignItems: 'start' },
  stack: { display: 'flex', flexDirection: 'column', gap: 24 },
  card: { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 22, overflow: 'hidden', boxShadow: '0 18px 45px rgba(15,23,42,.06)' },
  cardHeader: { padding: 22, borderBottom: '1px solid #e2e8f0', background: '#fafafa' },
  messages: { minHeight: 360, display: 'flex', flexDirection: 'column', gap: 14, padding: 22, background: '#fcfcfd' },
  bubble: { maxWidth: '82%', borderRadius: 18, padding: '14px 16px', boxShadow: '0 8px 18px rgba(15,23,42,.05)' },
  role: { display: 'block', textTransform: 'uppercase', letterSpacing: '.08em', fontSize: 11, marginBottom: 6 },
  messageText: { margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.6 },
  loading: { color: '#4f46e5', fontWeight: 700 },
  chatForm: { borderTop: '1px solid #e2e8f0', padding: 20, display: 'flex', flexDirection: 'column', gap: 12 },
  textarea: { width: '100%', boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 14, padding: 14, fontSize: 15, resize: 'vertical' },
  formGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, padding: 22 },
  label: { display: 'flex', flexDirection: 'column', gap: 7, color: '#334155', fontWeight: 700 },
  input: { border: '1px solid #cbd5e1', borderRadius: 12, padding: '11px 12px', fontSize: 15 },
  actions: { display: 'flex', gap: 12, padding: '0 22px 22px', flexWrap: 'wrap' },
  primaryButton: { background: '#111827', color: '#fff', border: 0, borderRadius: 999, padding: '12px 18px', fontWeight: 800, cursor: 'pointer' },
  secondaryButton: { background: '#4f46e5', color: '#fff', border: 0, borderRadius: 999, padding: '12px 18px', fontWeight: 800, cursor: 'pointer' },
  section: { marginTop: 28, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 22, padding: 24, boxShadow: '0 18px 45px rgba(15,23,42,.05)' },
  sectionHeader: { display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap', marginBottom: 20 },
  badge: { background: '#ecfdf5', color: '#047857', border: '1px solid #a7f3d0', borderRadius: 999, padding: '8px 12px', fontSize: 13, fontWeight: 800 },
  dayGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(280px,1fr))', gap: 18 },
  dayCard: { border: '1px solid #e2e8f0', borderRadius: 18, padding: 18, background: '#f8fafc' },
  dayTitle: { margin: '0 0 14px', color: '#0f172a' },
  mealStack: { display: 'flex', flexDirection: 'column', gap: 12 },
  mealCard: { background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: 15 },
  mealTopRow: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' },
  mealName: { color: '#0f172a', lineHeight: 1.4 },
  usdaBadge: { background: '#ecfdf5', color: '#047857', borderRadius: 999, padding: '5px 8px', fontSize: 11, fontWeight: 800, whiteSpace: 'nowrap' },
  estimateBadge: { background: '#fff7ed', color: '#c2410c', borderRadius: 999, padding: '5px 8px', fontSize: 11, fontWeight: 800, whiteSpace: 'nowrap' },
  metrics: { display: 'flex', flexWrap: 'wrap', gap: 10, color: '#475569', fontSize: 13, marginTop: 12 },
  chips: { display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  chip: { background: '#eef2ff', color: '#4338ca', borderRadius: 999, padding: '6px 9px', fontSize: 12, fontWeight: 700 },
  shoppingGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 16 },
  shoppingCard: { border: '1px solid #e2e8f0', borderRadius: 16, padding: 16, background: '#f8fafc' },
  categoryTitle: { margin: '0 0 12px', color: '#0f172a' },
  checkList: { display: 'flex', flexDirection: 'column', gap: 10 },
  checkRow: { display: 'grid', gridTemplateColumns: 'auto 1fr auto', gap: 9, alignItems: 'center', color: '#334155' },
  quantity: { color: '#64748b' },
};
