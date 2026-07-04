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
  const [appliedSwap, setAppliedSwap] = useState<string | null>(null);

  const [copilotMessage, setCopilotMessage] = useState('Should I swap this snack for something better?');
  const [copilotResult, setCopilotResult] = useState<JsonObject | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [copilotError, setCopilotError] = useState<string | null>(null);

  const currentProduct = DEMO_PRODUCTS[explainIndex];
  const currentProductScore = explainResult?.score;
  const mainSwap = (bagResult?.swaps ?? [])[0] as JsonObject | undefined;

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

  function selectProduct(index: number) {
    setExplainIndex(index);
    setExplainResult(null);
    setCopilotResult(null);
    const alternativeIndex = index === 0 ? 2 : 0;
    setCompareIndexes([index, alternativeIndex]);
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
    setAppliedSwap(null);
  }

  function applySuggestedSwap() {
    if (!mainSwap) return;
    const originalIndex = DEMO_PRODUCTS.findIndex((product) => product.name === mainSwap.replace);
    if (originalIndex >= 0) setBagIndexes((current) => current.filter((index) => index !== originalIndex));
    setAppliedSwap(`${mainSwap.replace} → ${mainSwap.with}`);
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
          product: currentProduct,
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
          <p style={styles.eyebrow}>Guiltless AI Copilot</p>
          <h2 style={styles.heading}>Turn a food label into a decision</h2>
          <p style={styles.subtitle}>Explain scores, compare alternatives, optimize the bag, and ask a context-aware copilot.</p>
        </div>
        <label style={styles.goalLabel}>
          Shared nutrition goal
          <input style={styles.input} value={goal} onChange={(event) => setGoal(event.target.value)} />
        </label>
      </div>

      <div style={styles.workflow} aria-label="Guiltless AI decision workflow">
        {['Product', 'Explain', 'Compare', 'Optimize', 'Copilot'].map((item, index) => (
          <div key={item} style={styles.workflowItem}>
            <span style={styles.workflowNumber}>{index + 1}</span>
            <strong>{item}</strong>
            {index < 4 && <span style={styles.workflowArrow}>→</span>}
          </div>
        ))}
      </div>

      <div style={styles.grid}>
        <article style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>01</span>
            <div><h3 style={styles.cardTitle}>Product Explainability</h3><p style={styles.cardCopy}>See the score, strengths, cautions, and goal fit.</p></div>
          </div>
          <select style={styles.select} value={explainIndex} onChange={(event) => selectProduct(Number(event.target.value))}>
            {DEMO_PRODUCTS.map((product, index) => <option key={product.name} value={index}>{product.name}</option>)}
          </select>
          <ProductFacts product={DEMO_PRODUCTS[explainIndex]} />
          <button type="button" style={styles.primaryButton} onClick={explainProduct} disabled={explainLoading}>{explainLoading ? 'Explaining…' : 'Explain this product'}</button>
          <InlineError message={explainError} />
          {explainResult && <ExplanationResult result={explainResult} onAction={setCopilotMessage} />}
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
          {compareResult && <ComparisonResult result={compareResult} products={DEMO_PRODUCTS} />}
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
            <div style={styles.optimizerResult}>
              <div style={styles.scoreSummary}>
                <Score label="Current score" value={bagResult.current_score} />
                <span style={styles.arrow}>→</span>
                <Score label="Optimized score" value={bagResult.projected_score} good />
                <Score label="Score gain" value={`+${bagResult.score_gain ?? 0}`} good />
              </div>
              {mainSwap ? (
                <div style={styles.mainSwap}>
                  <span style={styles.resultLabel}>Main suggested swap</span>
                  <strong style={styles.swapTitle}>{mainSwap.replace} <span style={styles.swapArrow}>→</span> {mainSwap.with}</strong>
                  <p style={styles.resultText}>{mainSwap.reason}</p>
                  <button type="button" style={styles.applyButton} onClick={applySuggestedSwap} disabled={Boolean(appliedSwap)}>
                    {appliedSwap ? 'Suggested swap applied' : 'Apply suggested swap'}
                  </button>
                </div>
              ) : <p style={styles.resultText}>This bag already looks strong for the selected goal.</p>}
              {appliedSwap && <div style={styles.successNotice}>✓ Applied in this demo: {appliedSwap}</div>}
            </div>
          )}
        </article>

        <article style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>04</span>
            <div><h3 style={styles.cardTitle}>Ask Guiltless Copilot</h3><p style={styles.cardCopy}>Your product, goal, and bag context travel with every question.</p></div>
          </div>
          <div style={styles.contextPanel}>
            <span style={styles.contextLabel}>Current decision context</span>
            <div style={styles.contextGrid}>
              <ContextMetric label="Product" value={currentProduct.name} />
              <ContextMetric label="Product score" value={currentProductScore ?? 'Run Explain'} />
              <ContextMetric label="Goal" value={goal} />
              <ContextMetric label="Bag score" value={bagResult?.current_score ?? 'Run Optimize'} />
            </div>
          </div>
          <div style={styles.promptChips}>
            {['Why is this score low?', 'Compare alternatives', 'Add to breakfast plan', 'Optimize my bag'].map((prompt) => (
              <button key={prompt} type="button" style={styles.promptChip} onClick={() => setCopilotMessage(prompt)}>{prompt}</button>
            ))}
          </div>
          <form style={styles.form} onSubmit={askCopilot}>
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

      <footer style={styles.integrationFooter}>
        <span>Designed to plug into:</span>
        {['Snap', 'Product Detail', 'Shopping Bag', 'Meal Planner', 'Tracker'].map((item) => <strong key={item}>{item}</strong>)}
      </footer>
    </section>
  );
}

function ProductFacts({ product }: { product: Product }) {
  return <div style={styles.facts}><ProductOption product={product} /><span>{product.nutrition.fiber_g}g fiber · {product.nutrition.sodium_mg}mg sodium</span></div>;
}

function ExplanationResult({ result, onAction }: { result: JsonObject; onAction: (action: string) => void }) {
  const nextActions = ['Compare alternatives', 'Add to meal plan', 'Build breakfast', 'Add to shopping list'];
  return (
    <div style={styles.resultBox}>
      <div style={styles.explainTop}><div><span style={styles.resultLabel}>Verdict</span><strong style={styles.resultTitle}>{result.verdict}</strong></div><span style={styles.scoreCircle}>{result.score}</span></div>
      <p style={styles.resultText}>{result.summary}</p>
      <div style={styles.signals}>
        {(result.positives ?? []).map((item: string) => <span key={item} style={styles.positive}>+ {item}</span>)}
        {(result.cautions ?? []).map((item: string) => <span key={item} style={styles.caution}>• {item}</span>)}
      </div>
      <div style={styles.nextActions}>
        <span style={styles.resultLabel}>Recommended next actions</span>
        <div style={styles.actionChips}>
          {nextActions.map((action) => <button key={action} type="button" style={styles.actionChip} onClick={() => onAction(action)}>{action}</button>)}
        </div>
      </div>
    </div>
  );
}

function ComparisonResult({ result, products }: { result: JsonObject; products: Product[] }) {
  return (
    <div style={styles.resultBox}>
      <div style={styles.tableWrap}>
        <table style={styles.table}>
          <thead>
            <tr>
              {['Product', 'Protein', 'Sugar', 'Fiber', 'Score'].map((heading) => <th key={heading} style={styles.th}>{heading}</th>)}
            </tr>
          </thead>
          <tbody>
            {(result.products ?? []).map((item: JsonObject) => {
              const product = products.find((candidate) => candidate.name === item.product?.name);
              const isWinner = result.winner?.name === item.product?.name;
              return (
                <tr key={item.product?.name} style={isWinner ? styles.winnerRow : undefined}>
                  <td style={styles.td}><strong>{item.product?.name}</strong>{isWinner && <span style={styles.bestBadge}>Best fit</span>}</td>
                  <td style={styles.td}>{product?.nutrition.protein_g ?? '—'}g</td>
                  <td style={styles.td}>{product?.nutrition.sugar_g ?? '—'}g</td>
                  <td style={styles.td}>{product?.nutrition.fiber_g ?? '—'}g</td>
                  <td style={styles.td}><strong style={styles.tableScore}>{item.score}</strong></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p style={styles.recommendation}>{result.recommendation}</p>
    </div>
  );
}

function InlineError({ message }: { message: string | null }) {
  return message ? <div role="alert" style={styles.error}>{message}</div> : null;
}

function ContextMetric({ label, value }: { label: string; value: string | number }) {
  return <div style={styles.contextMetric}><span>{label}</span><strong>{value}</strong></div>;
}

function Score({ label, value, good = false }: { label: string; value: string | number; good?: boolean }) {
  return <div><span style={styles.resultLabel}>{label}</span><strong style={{ ...styles.bigScore, color: good ? '#047857' : '#0f172a' }}>{value}</strong></div>;
}

const styles: Record<string, any> = {
  section: { marginTop: 28, background: 'linear-gradient(145deg,#073b2a,#0b4f38)', color: '#fff', borderRadius: 28, padding: 26, boxShadow: '0 24px 60px rgba(6,78,59,.2)' },
  sectionHeader: { display: 'flex', justifyContent: 'space-between', gap: 20, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 22 },
  eyebrow: { margin: '0 0 7px', color: '#86efac', fontWeight: 900, letterSpacing: '.12em', textTransform: 'uppercase', fontSize: 11 },
  heading: { margin: 0, fontSize: 30 },
  subtitle: { margin: '8px 0 0', color: '#d1fae5', lineHeight: 1.55 },
  goalLabel: { display: 'flex', flexDirection: 'column', gap: 7, minWidth: 250, color: '#e2e8f0', fontWeight: 800, fontSize: 13 },
  input: { border: '1px solid #4d8b73', borderRadius: 12, padding: '10px 12px', background: '#0b513a', color: '#fff', fontSize: 15 },
  workflow: { display: 'grid', gridTemplateColumns: 'repeat(5,minmax(0,1fr))', gap: 8, marginBottom: 20, border: '1px solid rgba(167,243,208,.25)', borderRadius: 16, padding: 10, background: 'rgba(255,255,255,.08)' },
  workflowItem: { position: 'relative', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 7, minWidth: 0, borderRadius: 11, padding: '9px 6px', color: '#ecfdf5', fontSize: 12 },
  workflowNumber: { display: 'grid', placeItems: 'center', width: 22, height: 22, borderRadius: 999, background: '#bbf7d0', color: '#14532d', fontWeight: 900, fontSize: 10 },
  workflowArrow: { position: 'absolute', right: -8, color: '#6ee7b7', fontSize: 16 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(285px,1fr))', gap: 16 },
  card: { display: 'flex', flexDirection: 'column', gap: 13, minWidth: 0, background: '#fff', color: '#12372a', borderRadius: 20, padding: 18, boxShadow: '0 12px 30px rgba(6,78,59,.12)' },
  cardHeader: { display: 'flex', gap: 12, alignItems: 'flex-start' },
  step: { display: 'grid', placeItems: 'center', flex: '0 0 auto', width: 34, height: 34, borderRadius: 10, background: '#dcfce7', color: '#166534', fontSize: 12, fontWeight: 900 },
  cardTitle: { margin: 0, fontSize: 18 },
  cardCopy: { margin: '5px 0 0', color: '#64748b', fontSize: 13, lineHeight: 1.45 },
  select: { width: '100%', border: '1px solid #cbd5e1', borderRadius: 11, padding: '10px 11px', background: '#fff', color: '#0f172a', fontSize: 14 },
  facts: { display: 'flex', flexDirection: 'column', gap: 5, borderRadius: 12, padding: 12, background: '#f8fafc', color: '#475569', fontSize: 12, fontWeight: 700 },
  primaryButton: { width: '100%', border: 0, borderRadius: 999, padding: '11px 15px', background: '#166534', color: '#fff', fontWeight: 900, cursor: 'pointer' },
  resultBox: { marginTop: 2, border: '1px solid #d1fae5', borderRadius: 15, padding: 14, background: '#f7fef9' },
  resultLabel: { display: 'block', color: '#64748b', fontSize: 10, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '.08em' },
  resultTitle: { display: 'block', marginTop: 3, color: '#0f172a', fontSize: 16 },
  resultText: { margin: '9px 0 0', color: '#475569', fontSize: 13, lineHeight: 1.5 },
  nextActions: { marginTop: 12, borderTop: '1px solid #d1fae5', paddingTop: 10 },
  tableWrap: { overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 11, color: '#334155' },
  th: { padding: '7px 6px', borderBottom: '1px solid #cbd5e1', color: '#64748b', textAlign: 'left', textTransform: 'uppercase', fontSize: 9, letterSpacing: '.04em' },
  td: { padding: '9px 6px', borderBottom: '1px solid #e2e8f0', verticalAlign: 'middle' },
  winnerRow: { background: '#ecfdf5' },
  bestBadge: { display: 'inline-block', marginTop: 4, borderRadius: 999, padding: '3px 6px', background: '#bbf7d0', color: '#166534', fontSize: 8, fontWeight: 900, textTransform: 'uppercase' },
  tableScore: { display: 'inline-grid', placeItems: 'center', minWidth: 28, height: 28, borderRadius: 999, background: '#166534', color: '#fff' },
  recommendation: { margin: '11px 0 0', borderRadius: 10, padding: 10, background: '#dcfce7', color: '#14532d', fontSize: 12, fontWeight: 700, lineHeight: 1.45 },
  checkList: { display: 'flex', flexDirection: 'column', gap: 9 },
  checkRow: { display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 9, alignItems: 'center', padding: 9, borderRadius: 11, background: '#f8fafc', color: '#334155', fontSize: 13 },
  smallText: { display: 'block', marginTop: 2, color: '#94a3b8' },
  optimizerResult: { marginTop: 2, border: '1px solid #bbf7d0', borderRadius: 15, padding: 14, background: 'linear-gradient(180deg,#f0fdf4,#fff)' },
  scoreSummary: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 12, flexWrap: 'wrap' },
  bigScore: { display: 'block', fontSize: 28, lineHeight: 1.1 },
  arrow: { color: '#94a3b8', fontSize: 22 },
  mainSwap: { borderTop: '1px solid #bbf7d0', paddingTop: 12 },
  swapTitle: { display: 'block', marginTop: 5, color: '#14532d', lineHeight: 1.45, fontSize: 14 },
  swapArrow: { color: '#16a34a', padding: '0 3px' },
  applyButton: { marginTop: 11, border: 0, borderRadius: 999, padding: '9px 12px', background: '#166534', color: '#fff', cursor: 'pointer', fontWeight: 900, fontSize: 11 },
  successNotice: { marginTop: 10, borderRadius: 10, padding: 9, background: '#dcfce7', color: '#166534', fontSize: 11, fontWeight: 800 },
  contextPanel: { border: '1px solid #bbf7d0', borderRadius: 13, padding: 12, background: '#f0fdf4' },
  contextLabel: { display: 'block', marginBottom: 8, color: '#166534', fontSize: 9, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '.08em' },
  contextGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  contextMetric: { display: 'flex', flexDirection: 'column', gap: 3, minWidth: 0, color: '#64748b', fontSize: 9, textTransform: 'uppercase' },
  promptChips: { display: 'flex', flexWrap: 'wrap', gap: 6 },
  promptChip: { border: '1px solid #bbf7d0', borderRadius: 999, padding: '6px 8px', background: '#fff', color: '#166534', cursor: 'pointer', fontSize: 10, fontWeight: 800 },
  form: { display: 'flex', flexDirection: 'column', gap: 11 },
  textarea: { width: '100%', boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: 11, padding: 11, resize: 'vertical', fontFamily: 'inherit', fontSize: 14 },
  intentBadge: { display: 'inline-flex', borderRadius: 999, padding: '5px 8px', background: '#dcfce7', color: '#166534', fontSize: 10, fontWeight: 900, textTransform: 'uppercase' },
  intentRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' },
  modeLabel: { color: '#64748b', fontSize: 10, fontWeight: 800, textTransform: 'uppercase' },
  copilotAnswer: { margin: '10px 0 0', color: '#334155', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' },
  actionChips: { display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 12 },
  actionChip: { border: '1px solid #bbf7d0', borderRadius: 999, padding: '6px 9px', background: '#fff', color: '#166534', cursor: 'pointer', fontSize: 11, fontWeight: 800 },
  toolDetails: { marginTop: 12, borderTop: '1px solid #e2e8f0', paddingTop: 10 },
  toolSummary: { color: '#475569', cursor: 'pointer', fontSize: 12, fontWeight: 800 },
  toolPreview: { maxHeight: 220, overflow: 'auto', margin: '9px 0 0', borderRadius: 10, padding: 10, background: '#0f172a', color: '#e2e8f0', fontSize: 10, lineHeight: 1.45, whiteSpace: 'pre-wrap' },
  explainTop: { display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' },
  scoreCircle: { display: 'grid', placeItems: 'center', width: 48, height: 48, borderRadius: 999, background: '#166534', color: '#fff', fontWeight: 900, fontSize: 18 },
  signals: { display: 'flex', flexDirection: 'column', gap: 4, marginTop: 10 },
  positive: { color: '#047857', fontSize: 12 },
  caution: { color: '#b45309', fontSize: 12 },
  error: { border: '1px solid #fecaca', borderRadius: 11, padding: 10, background: '#fef2f2', color: '#b91c1c', fontSize: 12, lineHeight: 1.4 },
  integrationFooter: { display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 18, borderTop: '1px solid rgba(167,243,208,.25)', paddingTop: 16, color: '#d1fae5', fontSize: 11 },
};
