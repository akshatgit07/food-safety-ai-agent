'use client';

import { FormEvent, useState } from 'react';

type Product = {
  name: string;
  brand: string;
  category: string;
  nutrition: Record<string, number>;
  ingredients: string[];
};

type JsonObject = Record<string, any>;

const DEMO_PRODUCTS: Product[] = [
  {
    name: 'Plain Greek Yogurt',
    brand: 'Daily Cultures',
    category: 'Yogurt',
    nutrition: { calories: 120, protein_g: 17, fiber_g: 0, sugar_g: 5, sodium_mg: 65 },
    ingredients: ['cultured milk'],
  },
  {
    name: 'Frosted Snack Bar',
    brand: 'Quick Bite',
    category: 'Snack bar',
    nutrition: { calories: 260, protein_g: 3, fiber_g: 1, sugar_g: 24, sodium_mg: 310 },
    ingredients: ['oats', 'corn syrup', 'artificial flavor'],
  },
  {
    name: 'Roasted Chickpea Bites',
    brand: 'Good Crunch',
    category: 'Savory snack',
    nutrition: { calories: 180, protein_g: 9, fiber_g: 6, sugar_g: 2, sodium_mg: 220 },
    ingredients: ['chickpeas', 'olive oil', 'spices'],
  },
];

async function readJson(response: Response): Promise<JsonObject> {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text || 'The backend returned a non-JSON response.' };
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.';
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? 'No tool result returned.';
  } catch {
    return 'The tool result could not be displayed.';
  }
}

function ProductOption({ product }: { product: Product }) {
  return (
    <>
      {product.name} · {product.nutrition.protein_g}g protein · {product.nutrition.sugar_g}g sugar
    </>
  );
}

export default function ProductIntelligence({ apiUrl, mealPlan }: { apiUrl?: string; mealPlan?: JsonObject | null }) {
  const [goal, setGoal] = useState('high protein');

  const [explainIndex, setExplainIndex] = useState(0);
  const [explainResult, setExplainResult] = useState<JsonObject | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  const [compareIndexes, setCompareIndexes] = useState<[number, number]>([0, 2]);
  const [compareResult, setCompareResult] = useState<JsonObject | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const [bagIndexes, setBagIndexes] = useState<number[]>([0, 1, 2]);
  const [bagResult, setBagResult] = useState<JsonObject | null>(null);
  const [bagLoading, setBagLoading] = useState(false);
  const [bagError, setBagError] = useState<string | null>(null);

  const [copilotProductIndex, setCopilotProductIndex] = useState(1);
  const [copilotMessage, setCopilotMessage] = useState('Should I swap this snack for something better?');
  const [copilotResult, setCopilotResult] = useState<JsonObject | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotError, setCopilotError] = useState<string | null>(null);

  function requireApiUrl() {
    if (!apiUrl) throw new Error('NEXT_PUBLIC_API_URL is not configured. Add it to frontend/.env.local and restart Next.js.');
    return apiUrl.replace(/\/$/, '');
  }

  async function post(path: string, body: JsonObject) {
    const response = await fetch(`${requireApiUrl()}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.detail || `Backend returned ${response.status}.`);
    return payload;
  }

  async function explainProduct() {
    setExplainLoading(true);
    setExplainError(null);
    setExplainResult(null);
    try {
      setExplainResult(await post('/product/explain', { product: DEMO_PRODUCTS[explainIndex], goal }));
    } catch (error) {
      setExplainError(errorMessage(error));
    } finally {
      setExplainLoading(false);
    }
  }

  async function compareProducts() {
    setCompareLoading(true);
    setCompareError(null);
    setCompareResult(null);
    try {
      if (compareIndexes[0] === compareIndexes[1]) throw new Error('Choose two different products to compare.');
      setCompareResult(await post('/product/compare', {
        products: compareIndexes.map((index) => DEMO_PRODUCTS[index]),
        goal,
      }));
    } catch (error) {
      setCompareError(errorMessage(error));
    } finally {
      setCompareLoading(false);
    }
  }

  function toggleBagProduct(index: number) {
    setBagIndexes((current) => current.includes(index) ? current.filter((value) => value !== index) : [...current, index]);
    setBagResult(null);
    setBagError(null);
  }

  async function optimizeBag() {
    setBagLoading(true);
    setBagError(null);
    setBagResult(null);
    try {
      if (bagIndexes.length === 0) throw new Error('Select at least one product for the bag.');
      setBagResult(await post('/bag/optimize', {
        items: bagIndexes.map((index) => DEMO_PRODUCTS[index]),
        goal,
      }));
    } catch (error) {
      setBagError(errorMessage(error));
    } finally {
      setBagLoading(false);
    }
  }

  async function askCopilot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCopilotLoading(true);
    setCopilotError(null);
    setCopilotResult(null);
    try {
      if (!copilotMessage.trim()) throw new Error('Enter a question for the copilot.');
      setCopilotResult(await post('/copilot/chat', {
        message: copilotMessage.trim(),
        context: {
          goal,
          product: DEMO_PRODUCTS[copilotProductIndex],
          products: DEMO_PRODUCTS,
          bag: bagIndexes.map((index) => DEMO_PRODUCTS[index]),
          meal_plan: mealPlan,
          servings: 1,
          preferences: ['simple ingredients', 'higher protein'],
        },
      }));
    } catch (error) {
      setCopilotError(errorMessage(error));
    } finally {
      setCopilotLoading(false);
    }
  }

  return (
    <section style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <p style={styles.eyebrow}>Sprint 2 · Agentic copilot</p>
          <h2 style={styles.heading}>Route a question to the right nutrition tool</h2>
          <p style={styles.subtitle}>Explain, compare, optimize, plan, shop, or cook through one context-aware entry point.</p>
        </div>
        <label style={styles.goalLabel}>
          Shared nutrition goal
          <input style={styles.input} value={goal} onChange={(event) => setGoal(event.target.value)} />
        </label>
      </div>

      <div style={styles.grid}>
        <article style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>01</span>
            <div><h3 style={styles.cardTitle}>Product Explainability</h3><p style={styles.cardCopy}>See the score, strengths, cautions, and goal fit.</p></div>
          </div>
          <select style={styles.select} value={explainIndex} onChange={(event) => { setExplainIndex(Number(event.target.value)); setExplainResult(null); }}>
            {DEMO_PRODUCTS.map((product, index) => <option key={product.name} value={index}>{product.name}</option>)}
          </select>
          <ProductFacts product={DEMO_PRODUCTS[explainIndex]} />
          <button type="button" style={styles.primaryButton} onClick={explainProduct} disabled={explainLoading}>{explainLoading ? 'Explaining…' : 'Explain this product'}</button>
          <InlineError message={explainError} />
          {explainResult && <ExplanationResult result={explainResult} />}
        </article>

        <article style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>02</span>
            <div><h3 style={styles.cardTitle}>Product Comparison</h3><p style={styles.cardCopy}>Put two products head-to-head for the current goal.</p></div>
          </div>
          {compareIndexes.map((selectedIndex, position) => (
            <select
              key={position}
              aria-label={`Comparison product ${position + 1}`}
              style={styles.select}
              value={selectedIndex}
              onChange={(event) => {
                const next = [...compareIndexes] as [number, number];
                next[position] = Number(event.target.value);
                setCompareIndexes(next);
                setCompareResult(null);
              }}
            >
              {DEMO_PRODUCTS.map((product, index) => <option key={product.name} value={index}>{product.name}</option>)}
            </select>
          ))}
          <button type="button" style={styles.primaryButton} onClick={compareProducts} disabled={compareLoading}>{compareLoading ? 'Comparing…' : 'Compare products'}</button>
          <InlineError message={compareError} />
          {compareResult && (
            <div style={styles.resultBox}>
              <span style={styles.resultLabel}>Best fit</span>
              <strong style={styles.resultTitle}>{compareResult.winner?.name ?? 'No winner'}</strong>
              <p style={styles.resultText}>{compareResult.recommendation}</p>
              <div style={styles.scoreList}>
                {(compareResult.products ?? []).map((item: JsonObject) => <span key={item.product?.name}>{item.product?.name}: <strong>{item.score}</strong></span>)}
              </div>
            </div>
          )}
        </article>

        <article style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>03</span>
            <div><h3 style={styles.cardTitle}>Bag Optimization</h3><p style={styles.cardCopy}>Score a basket and preview practical healthier swaps.</p></div>
          </div>
          <div style={styles.checkList}>
            {DEMO_PRODUCTS.map((product, index) => (
              <label key={product.name} style={styles.checkRow}>
                <input type="checkbox" checked={bagIndexes.includes(index)} onChange={() => toggleBagProduct(index)} />
                <span><strong>{product.name}</strong><small style={styles.smallText}>{product.brand}</small></span>
              </label>
            ))}
          </div>
          <button type="button" style={styles.primaryButton} onClick={optimizeBag} disabled={bagLoading}>{bagLoading ? 'Optimizing…' : 'Optimize this bag'}</button>
          <InlineError message={bagError} />
          {bagResult && (
            <div style={styles.resultBox}>
              <div style={styles.scoreSummary}><Score label="Current" value={bagResult.current_score} /><span style={styles.arrow}>→</span><Score label="Optimized" value={bagResult.projected_score} good /></div>
              {(bagResult.swaps ?? []).length === 0 ? <p style={styles.resultText}>This bag already looks strong for the selected goal.</p> : (bagResult.swaps ?? []).map((swap: JsonObject) => (
                <div key={swap.replace} style={styles.swapRow}><span>{swap.replace} → <strong>{swap.with}</strong></span><span style={styles.gain}>+{swap.score_gain}</span></div>
              ))}
            </div>
          )}
        </article>

        <article style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>04</span>
            <div><h3 style={styles.cardTitle}>Context-aware Copilot</h3><p style={styles.cardCopy}>Ask with the product, bag, goal, and preferences attached.</p></div>
          </div>
          <form style={styles.form} onSubmit={askCopilot}>
            <select style={styles.select} value={copilotProductIndex} onChange={(event) => setCopilotProductIndex(Number(event.target.value))}>
              {DEMO_PRODUCTS.map((product, index) => <option key={product.name} value={index}>{product.name}</option>)}
            </select>
            <textarea style={styles.textarea} rows={4} value={copilotMessage} onChange={(event) => setCopilotMessage(event.target.value)} />
            <button type="submit" style={styles.primaryButton} disabled={copilotLoading}>{copilotLoading ? 'Thinking with context…' : 'Ask the copilot'}</button>
          </form>
          <InlineError message={copilotError} />
          {copilotResult && (
            <div style={styles.resultBox}>
              <div style={styles.intentRow}>
                <span style={styles.intentBadge}>{String(copilotResult.intent ?? 'general_chat').replaceAll('_', ' ')}</span>
                {copilotResult.mode && <span style={styles.modeLabel}>{String(copilotResult.mode).replaceAll('_', ' ')}</span>}
              </div>
              <p style={styles.copilotAnswer}>{copilotResult.response}</p>
              {(copilotResult.suggested_actions ?? []).length > 0 && (
                <div style={styles.actionChips}>
                  {(copilotResult.suggested_actions ?? []).map((action: string) => (
                    <button key={action} type="button" style={styles.actionChip} onClick={() => setCopilotMessage(action)}>{action}</button>
                  ))}
                </div>
              )}
              {copilotResult.tool_result != null && (
                <details style={styles.toolDetails}>
                  <summary style={styles.toolSummary}>Tool result preview</summary>
                  <pre style={styles.toolPreview}>{safeJson(copilotResult.tool_result)}</pre>
                </details>
              )}
            </div>
          )}
        </article>
      </div>
    </section>
  );
}

function ProductFacts({ product }: { product: Product }) {
  return <div style={styles.facts}><ProductOption product={product} /><span>{product.nutrition.fiber_g}g fiber · {product.nutrition.sodium_mg}mg sodium</span></div>;
}

function ExplanationResult({ result }: { result: JsonObject }) {
  return (
    <div style={styles.resultBox}>
      <div style={styles.explainTop}><div><span style={styles.resultLabel}>Verdict</span><strong style={styles.resultTitle}>{result.verdict}</strong></div><span style={styles.scoreCircle}>{result.score}</span></div>
      <p style={styles.resultText}>{result.summary}</p>
      <div style={styles.signals}>
        {(result.positives ?? []).map((item: string) => <span key={item} style={styles.positive}>+ {item}</span>)}
        {(result.cautions ?? []).map((item: string) => <span key={item} style={styles.caution}>• {item}</span>)}
      </div>
    </div>
  );
}

function InlineError({ message }: { message: string | null }) {
  return message ? <div role="alert" style={styles.error}>{message}</div> : null;
}

function Score({ label, value, good = false }: { label: string; value: number; good?: boolean }) {
  return <div><span style={styles.resultLabel}>{label}</span><strong style={{ ...styles.bigScore, color: good ? '#047857' : '#0f172a' }}>{value}</strong></div>;
}

const styles: Record<string, any> = {
  section: { marginTop: 28, background: '#0f172a', color: '#fff', borderRadius: 24, padding: 24, boxShadow: '0 24px 60px rgba(15,23,42,.18)' },
  sectionHeader: { display: 'flex', justifyContent: 'space-between', gap: 20, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 22 },
  eyebrow: { margin: '0 0 7px', color: '#a5b4fc', fontWeight: 900, letterSpacing: '.12em', textTransform: 'uppercase', fontSize: 11 },
  heading: { margin: 0, fontSize: 28 },
  subtitle: { margin: '8px 0 0', color: '#cbd5e1' },
  goalLabel: { display: 'flex', flexDirection: 'column', gap: 7, minWidth: 250, color: '#e2e8f0', fontWeight: 800, fontSize: 13 },
  input: { border: '1px solid #475569', borderRadius: 11, padding: '10px 12px', background: '#1e293b', color: '#fff', fontSize: 15 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(285px,1fr))', gap: 16 },
  card: { display: 'flex', flexDirection: 'column', gap: 13, minWidth: 0, background: '#fff', color: '#0f172a', borderRadius: 18, padding: 18 },
  cardHeader: { display: 'flex', gap: 12, alignItems: 'flex-start' },
  step: { display: 'grid', placeItems: 'center', flex: '0 0 auto', width: 34, height: 34, borderRadius: 10, background: '#eef2ff', color: '#4338ca', fontSize: 12, fontWeight: 900 },
  cardTitle: { margin: 0, fontSize: 18 },
  cardCopy: { margin: '5px 0 0', color: '#64748b', fontSize: 13, lineHeight: 1.45 },
  select: { width: '100%', border: '1px solid #cbd5e1', borderRadius: 11, padding: '10px 11px', background: '#fff', color: '#0f172a', fontSize: 14 },
  facts: { display: 'flex', flexDirection: 'column', gap: 5, borderRadius: 12, padding: 12, background: '#f8fafc', color: '#475569', fontSize: 12, fontWeight: 700 },
  primaryButton: { width: '100%', border: 0, borderRadius: 999, padding: '11px 15px', background: '#4f46e5', color: '#fff', fontWeight: 900, cursor: 'pointer' },
  resultBox: { marginTop: 2, border: '1px solid #e2e8f0', borderRadius: 14, padding: 14, background: '#f8fafc' },
  resultLabel: { display: 'block', color: '#64748b', fontSize: 10, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '.08em' },
  resultTitle: { display: 'block', marginTop: 3, color: '#0f172a', fontSize: 16 },
  resultText: { margin: '9px 0 0', color: '#475569', fontSize: 13, lineHeight: 1.5 },
  scoreList: { display: 'flex', flexDirection: 'column', gap: 5, marginTop: 10, color: '#334155', fontSize: 13 },
  checkList: { display: 'flex', flexDirection: 'column', gap: 9 },
  checkRow: { display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 9, alignItems: 'center', padding: 9, borderRadius: 11, background: '#f8fafc', color: '#334155', fontSize: 13 },
  smallText: { display: 'block', marginTop: 2, color: '#94a3b8' },
  scoreSummary: { display: 'flex', alignItems: 'center', gap: 14, marginBottom: 8 },
  bigScore: { display: 'block', fontSize: 28, lineHeight: 1.1 },
  arrow: { color: '#94a3b8', fontSize: 22 },
  swapRow: { display: 'flex', justifyContent: 'space-between', gap: 8, padding: '8px 0', borderTop: '1px solid #e2e8f0', color: '#334155', fontSize: 12 },
  gain: { color: '#047857', fontWeight: 900 },
  form: { display: 'flex', flexDirection: 'column', gap: 11 },
  textarea: { width: '100%', boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 11, padding: 11, resize: 'vertical', fontFamily: 'inherit', fontSize: 14 },
  intentBadge: { display: 'inline-flex', borderRadius: 999, padding: '5px 8px', background: '#eef2ff', color: '#4338ca', fontSize: 10, fontWeight: 900, textTransform: 'uppercase' },
  intentRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' },
  modeLabel: { color: '#64748b', fontSize: 10, fontWeight: 800, textTransform: 'uppercase' },
  copilotAnswer: { margin: '10px 0 0', color: '#334155', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' },
  actionChips: { display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 12 },
  actionChip: { border: '1px solid #c7d2fe', borderRadius: 999, padding: '6px 9px', background: '#fff', color: '#4338ca', cursor: 'pointer', fontSize: 11, fontWeight: 800 },
  toolDetails: { marginTop: 12, borderTop: '1px solid #e2e8f0', paddingTop: 10 },
  toolSummary: { color: '#475569', cursor: 'pointer', fontSize: 12, fontWeight: 800 },
  toolPreview: { maxHeight: 220, overflow: 'auto', margin: '9px 0 0', borderRadius: 10, padding: 10, background: '#0f172a', color: '#e2e8f0', fontSize: 10, lineHeight: 1.45, whiteSpace: 'pre-wrap' },
  explainTop: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' },
  scoreCircle: { display: 'grid', placeItems: 'center', width: 48, height: 48, borderRadius: 999, background: '#111827', color: '#fff', fontWeight: 900, fontSize: 18 },
  signals: { display: 'flex', flexDirection: 'column', gap: 4, marginTop: 10 },
  positive: { color: '#047857', fontSize: 12 },
  caution: { color: '#b45309', fontSize: 12 },
  error: { border: '1px solid #fecaca', borderRadius: 11, padding: 10, background: '#fef2f2', color: '#b91c1c', fontSize: 12, lineHeight: 1.4 },
};
