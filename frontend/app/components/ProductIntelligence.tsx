'use client';

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react';

import { errorMessage as detailMessage } from '../lib/api';
import PersonalizedCopilot, { CatalogProduct } from './PersonalizedCopilot';
import AppHelper from './AppHelper';

type Product = {
  product_id?: string;
  name: string;
  brand: string;
  category: string;
  nutrition: Record<string, number>;
  ingredients: string[];
};

type JsonObject = Record<string, any>;

const DEMO_PRODUCTS: Product[] = [
  {
    product_id: 'demo-yogurt',
    name: 'Plain Greek Yogurt',
    brand: 'Daily Cultures',
    category: 'Yogurt',
    nutrition: { calories: 120, protein_g: 17, fiber_g: 0, sugar_g: 5, sodium_mg: 65 },
    ingredients: ['cultured milk'],
  },
  {
    product_id: 'demo-bar',
    name: 'Frosted Snack Bar',
    brand: 'Quick Bite',
    category: 'Snack bar',
    nutrition: { calories: 260, protein_g: 3, fiber_g: 1, sugar_g: 24, sodium_mg: 310 },
    ingredients: ['oats', 'corn syrup', 'artificial flavor'],
  },
  {
    product_id: 'demo-chickpeas',
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

function actionLabel(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (character) => character.toUpperCase());
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
  const [activeFeature, setActiveFeature] = useState(0);
  const featureTabs = useRef<(HTMLButtonElement | null)[]>([]);
  const features = ['Product Explainability', 'Product Comparison', 'Bag Optimization', 'Ask Guiltless'];

  function openFeature(index: number, scroll = false) {
    setActiveFeature(index);
    if (scroll) document.getElementById('decision-features')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function followAction(action: string) {
    if (action === 'Compare alternatives') {
      openFeature(1, true);
    } else {
      setCopilotMessage(action);
      openFeature(3, true);
    }
  }
  const [customProducts, setCustomProducts] = useState<Product[]>([]);
  const [scanOpen, setScanOpen] = useState(false);
  const [scanText, setScanText] = useState('Protein Oat Bar\nGood Foods\nCalories 190\nProtein 10g\nDietary Fiber 6g\nTotal Sugars 5g\nSodium 180mg\nIngredients: oats, almonds, dates');
  const [scanImage, setScanImage] = useState<string | null>(null);
  const [scanFileName, setScanFileName] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<JsonObject | null>(null);
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const [explainIndex, setExplainIndex] = useState(1);
  const [explainResult, setExplainResult] = useState<JsonObject | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  const [compareIndexes, setCompareIndexes] = useState<[number, number]>([1, 2]);
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

  const products = useMemo(() => [...DEMO_PRODUCTS, ...customProducts], [customProducts]);
  const currentProduct = products[explainIndex] ?? DEMO_PRODUCTS[1];
  const currentProductScore = explainResult?.score;
  const isDemoProduct = currentProduct.product_id?.startsWith('demo-');
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
    if (!response.ok) throw new Error(detailMessage(payload, response.status));
    return payload;
  }

  useEffect(() => {
    if (!apiUrl || !currentProduct) return;

    const controller = new AbortController();
    let active = true;
    setExplainLoading(true);
    setExplainError(null);
    setExplainResult(null);

    fetch(`${apiUrl.replace(/\/$/, '')}/product/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product: currentProduct, goal }),
      signal: controller.signal,
    })
      .then(async (response) => {
        const payload = await readJson(response);
        if (!response.ok) throw new Error(detailMessage(payload, response.status));
        return payload;
      })
      .then((payload) => {
        if (active) setExplainResult(payload);
      })
      .catch((error) => {
        if (active && error instanceof Error && error.name !== 'AbortError') setExplainError(errorMessage(error));
      })
      .finally(() => {
        if (active) setExplainLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [apiUrl, currentProduct, goal]);

  function handleScanFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setScanError(null);
    setScanResult(null);
    if (file.size > 4_000_000) {
      setScanError('Choose an image smaller than 4 MB.');
      event.target.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setScanImage(typeof reader.result === 'string' ? reader.result : null);
      setScanFileName(file.name);
    };
    reader.onerror = () => setScanError('The label image could not be read.');
    reader.readAsDataURL(file);
  }

  async function scanProductLabel() {
    setScanLoading(true);
    setScanError(null);
    setScanResult(null);
    try {
      const payload = await post('/product/scan', { label_text: scanText.trim() || null, image_data_url: scanImage });
      const product = payload.product as Product | undefined;
      if (!product?.name || !product.nutrition) throw new Error('The scan did not return a usable product.');
      setCustomProducts(current => [...current, product]);
      const scannedIndex = DEMO_PRODUCTS.length + customProducts.length;
      setExplainIndex(scannedIndex);
      setExplainResult(null);
      setCompareIndexes([scannedIndex, 2]);
      setCompareResult(null);
      setBagIndexes((current) => current.includes(scannedIndex) ? current : [...current, scannedIndex]);
      setBagResult(null);
      setCopilotResult(null);
      setScanResult(payload);
    } catch (error) {
      setScanError(errorMessage(error));
    } finally {
      setScanLoading(false);
    }
  }

  async function explainProduct() {
    setExplainLoading(true);
    setExplainError(null);
    setExplainResult(null);
    try {
      setExplainResult(await post('/product/explain', { product: products[explainIndex], goal }));
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
        products: compareIndexes.map((index) => products[index]),
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
    const originalIndex = products.findIndex((product) => product.name === mainSwap.replace);
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
        items: bagIndexes.map((index) => products[index]).filter(Boolean),
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
        user_id: 'demo-user',
        load_memory: true,
        context: {
          goal,
          product: currentProduct,
          products,
          bag: bagIndexes.map((index) => products[index]).filter(Boolean),
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

  function applyPersonalizedSwap(replacement: CatalogProduct, originalId: string) {
    const existingIndex = products.findIndex(p => p.product_id === replacement.product_id);
    const index = existingIndex >= 0 ? existingIndex : products.length;
    if (existingIndex < 0) {
      const nutrition = Object.fromEntries(Object.entries(replacement.nutrition).filter((entry): entry is [string, number] => typeof entry[1] === 'number'));
      setCustomProducts(current => [...current, { ...replacement, nutrition }]);
    }
    setBagIndexes(current => current.map(i => originalId && products[i]?.product_id === originalId ? index : i));
    setExplainIndex(index); setExplainResult(null); setCompareResult(null); setBagResult(null); setCopilotResult(null);
  }

  return (
    <section id="decision" className="decision-engine" style={styles.section}>
      <div className="decision-hero" style={styles.hero}>
        <div style={styles.heroCopy}>
          <p style={styles.eyebrow}>Food Label Decision Engine</p>
          <h2 style={styles.heading}>Turn a food label<br />into a better decision.</h2>
          <p style={styles.subtitle}>Explain scores, compare alternatives, optimize the bag, and ask a context-aware copilot.</p>
          <div style={styles.activeContext}>
            <span>Active product</span>
            <strong>{currentProduct.name}</strong>
            <span style={styles.contextDivider} />
            <span>Score</span>
            <strong style={styles.contextScore}>{currentProductScore != null ? `${currentProductScore} / 100` : explainLoading ? 'Scoring…' : 'Score unavailable'}</strong>
            {isDemoProduct && <small style={styles.scoreSource}>Guiltless score from the demo nutrition label</small>}
          </div>
          <label style={styles.goalLabel}>
            Shared nutrition goal
            <input style={styles.input} value={goal} onChange={(event) => setGoal(event.target.value)} />
          </label>
          <button type="button" style={styles.heroScanButton} onClick={() => setScanOpen(true)}>▣ Scan or paste a label</button>
        </div>
        <aside className="decision-snapshot" style={styles.snapshot} aria-label="Current product nutrition snapshot">
          <div style={styles.snapshotHeader}>
            <div><span style={styles.snapshotLabel}>Current decision</span><strong>{currentProduct.name}</strong></div>
            <span style={styles.snapshotScore}>{currentProductScore != null ? `${currentProductScore} / 100` : explainLoading ? 'Scoring…' : 'Score unavailable'}</span>
          </div>
          <div style={styles.snapshotRule} />
          <strong style={styles.driverTitle}>What is driving the score</strong>
          <NutritionDriver label="Protein" value={`${currentProduct.nutrition.protein_g}g`} width={Math.min(100, currentProduct.nutrition.protein_g * 5)} />
          <NutritionDriver label="Sugar" value={`${currentProduct.nutrition.sugar_g}g`} width={Math.min(100, currentProduct.nutrition.sugar_g * 4)} caution />
          <NutritionDriver label="Fiber" value={`${currentProduct.nutrition.fiber_g}g`} width={Math.min(100, currentProduct.nutrition.fiber_g * 12)} />
          <button type="button" style={styles.snapshotAction} onClick={() => openFeature(1, true)}>↗ Compare a healthier alternative next</button>
        </aside>
      </div>

      <section id="scan-label" className="scan-panel" style={styles.scanPanel}>
        <div style={styles.scanPanelHeader}>
          <div><span style={styles.scanKicker}>New · Scan-to-decision</span><h3 style={styles.scanTitle}>Bring a real food label into the workflow</h3><p style={styles.scanCopy}>Upload a photo or paste label text. Review the extraction, then use it everywhere below.</p></div>
          <button type="button" style={styles.scanToggle} onClick={() => setScanOpen((current) => !current)}>{scanOpen ? 'Close scanner' : 'Scan a label'}</button>
        </div>
        {scanOpen && (
          <div className="scan-grid" style={styles.scanGrid}>
            <label style={styles.uploadZone}>
              {scanImage ? <img src={scanImage} alt="Uploaded food label preview" style={styles.scanPreview} /> : <span style={styles.uploadIcon}>▣</span>}
              <strong>{scanFileName ?? 'Upload or capture label'}</strong>
              <small>JPG, PNG or WebP · maximum 4 MB</small>
              <input type="file" accept="image/png,image/jpeg,image/webp" capture="environment" onChange={handleScanFile} style={styles.fileInput} />
            </label>
            <div style={styles.scanEditor}>
              <label style={styles.scanTextLabel}>Label text <span>Editable before extraction</span></label>
              <textarea rows={8} style={styles.scanTextarea} value={scanText} onChange={(event) => setScanText(event.target.value)} />
              <button type="button" style={styles.primaryButton} onClick={scanProductLabel} disabled={scanLoading}>{scanLoading ? 'Reading nutrition label…' : 'Extract product and continue →'}</button>
              <InlineError message={scanError} />
            </div>
            {scanResult && (
              <div style={styles.scanSuccess}>
                <span style={styles.scanSuccessIcon}>✓</span>
                <div><strong>{scanResult.product?.name} is now active</strong><p>{Math.round(Number(scanResult.confidence ?? 0) * 100)}% extraction confidence · {String(scanResult.extraction_mode ?? 'scan').replaceAll('_', ' ')}</p>{(scanResult.warnings ?? []).map((warning: string) => <small key={warning}>{warning}</small>)}</div>
              </div>
            )}
          </div>
        )}
      </section>

      <div id="decision-features" className="feature-workspace">
        <div className="feature-workspace-heading"><div><span>YOUR DECISION WORKSPACE</span><h3>One focus. A better decision.</h3></div><p>Switch tools anytime. Your context stays with you.</p></div>
        <div className="feature-tabs" role="tablist" aria-label="Product intelligence features">
          {features.map((feature, index) => <button key={feature} ref={node => { featureTabs.current[index] = node; }} type="button" role="tab"
            id={`feature-tab-${index}`} aria-controls={`feature-panel-${index}`} aria-selected={activeFeature === index} tabIndex={activeFeature === index ? 0 : -1}
            onClick={() => openFeature(index)} onKeyDown={event => {
              const next = event.key === 'ArrowRight' ? (index + 1) % features.length : event.key === 'ArrowLeft' ? (index + features.length - 1) % features.length : event.key === 'Home' ? 0 : event.key === 'End' ? features.length - 1 : null;
              if (next !== null) { event.preventDefault(); openFeature(next); featureTabs.current[next]?.focus(); }
            }}><span className="feature-tab-number">0{index + 1}</span><strong>{feature}</strong><span className="feature-tab-indicator" aria-hidden="true">↗</span></button>)}
        </div>
        <div className="feature-shared-context"><span><small>PRODUCT</small> {currentProduct.name}</span><span><small>GOAL</small> {goal || 'Not set'}</span><span><small>BAG</small> {bagIndexes.length} items</span>
          <AppHelper apiUrl={apiUrl} productId={currentProduct.product_id} productName={currentProduct.name} bagIds={bagIndexes.map(index => products[index]?.product_id).filter((id): id is string => Boolean(id))} goal={goal} screen={['product_detail', 'comparison', 'bag', 'product_detail'][activeFeature]} onNavigate={action => {
            if (action === 'open_scan') { setScanOpen(true); document.getElementById('scan-label')?.scrollIntoView({behavior: 'smooth'}); }
            else openFeature(action === 'open_compare' ? 1 : action === 'open_bag' ? 2 : 0, true);
          }} />
        </div>
      <div className="decision-panels">
        <article id="feature-panel-0" role="tabpanel" aria-labelledby="feature-tab-0" tabIndex={0} hidden={activeFeature !== 0} className="decision-card feature-panel" style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>01</span>
            <div><h3 style={styles.cardTitle}>Product Explainability</h3><p style={styles.cardCopy}>See the score, strengths, cautions, and goal fit.</p></div>
          </div>
          <div className="feature-body"><div className="feature-controls">
          <label htmlFor="explain-product" className="feature-field-label">Choose your product</label>
          <select id="explain-product" style={styles.select} value={explainIndex} onChange={(event) => selectProduct(Number(event.target.value))}>
            {products.map((product, index) => <option key={`${product.name}-${index}`} value={index}>{product.name}</option>)}
          </select>
          <ProductFacts product={currentProduct} />
          <button type="button" style={styles.primaryButton} onClick={explainProduct} disabled={explainLoading}>{explainLoading ? 'Explaining…' : 'Explain this product'}</button>
          <InlineError message={explainError} />
          </div><div className="feature-output" aria-live="polite">
          {explainResult ? <ExplanationResult result={explainResult} onAction={followAction} /> : <FeatureEmpty title="Understand what’s inside" description="Choose a product and explain its score to see strengths, cautions, and your recommended next step." />}
          </div></div>
        </article>

        <article id="feature-panel-1" role="tabpanel" aria-labelledby="feature-tab-1" tabIndex={0} hidden={activeFeature !== 1} className="decision-card feature-panel" style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>02</span>
            <div><h3 style={styles.cardTitle}>Product Comparison</h3><p style={styles.cardCopy}>Put two products head-to-head for the current goal.</p></div>
          </div>
          <div className="feature-body"><div className="feature-controls">
          <p className="feature-field-label">Choose two products</p>
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
              {products.map((product, index) => <option key={`${product.name}-${index}`} value={index}>{product.name}</option>)}
            </select>
          ))}
          <button type="button" style={styles.primaryButton} onClick={compareProducts} disabled={compareLoading}>{compareLoading ? 'Comparing…' : 'Compare products'}</button>
          <InlineError message={compareError} />
          </div><div className="feature-output" aria-live="polite">
          {compareResult ? <ComparisonResult result={compareResult} products={products} /> : <FeatureEmpty title="Make room for a better choice" description="Compare protein, sugar, fiber, and scores side by side. Your recommendation will appear here." />}
          </div></div>
        </article>

        <article id="feature-panel-2" role="tabpanel" aria-labelledby="feature-tab-2" tabIndex={0} hidden={activeFeature !== 2} className="decision-card feature-panel" style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>03</span>
            <div><h3 style={styles.cardTitle}>Bag Optimization</h3><p style={styles.cardCopy}>Score a basket and preview practical healthier swaps.</p></div>
          </div>
          <div className="feature-body"><div className="feature-controls">
          <p className="feature-field-label">Build your bag</p>
          <div style={styles.checkList}>
            {products.map((product, index) => (
              <label key={`${product.name}-${index}`} style={styles.checkRow}>
                <input type="checkbox" checked={bagIndexes.includes(index)} onChange={() => toggleBagProduct(index)} />
                <span><strong>{product.name}</strong><small style={styles.smallText}>{product.brand}</small></span>
              </label>
            ))}
          </div>
          <button type="button" style={styles.primaryButton} onClick={optimizeBag} disabled={bagLoading}>{bagLoading ? 'Optimizing…' : 'Optimize this bag'}</button>
          <InlineError message={bagError} />
          </div><div className="feature-output" aria-live="polite">
          {!bagResult && <FeatureEmpty title="A stronger bag starts here" description="Select your items, then preview your before-and-after score and suggested swaps." />}
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
          </div></div>
        </article>

        <div id="feature-panel-3" role="tabpanel" aria-labelledby="feature-tab-3" tabIndex={0} hidden={activeFeature !== 3} className="feature-panel-group">
        <article className="decision-card feature-panel" style={styles.card}>
          <div style={styles.cardHeader}>
            <span style={styles.step}>04</span>
            <div><h3 style={styles.cardTitle}>Ask Guiltless Copilot</h3><p style={styles.cardCopy}>Your product, goal, and bag context travel with every question.</p></div>
          </div>
          <div className="feature-body"><div className="feature-controls">
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
            {['Explain score', 'Compare alternatives', 'Optimize bag', 'Build meal plan', 'Build workout plan', 'Trainer client plan'].map((prompt) => (
              <button key={prompt} type="button" style={styles.promptChip} onClick={() => setCopilotMessage(prompt)}>{prompt}</button>
            ))}
          </div>
          <form style={styles.form} onSubmit={askCopilot}>
            <textarea aria-label="Ask Guiltless a question" style={styles.textarea} rows={4} value={copilotMessage} onChange={(event) => setCopilotMessage(event.target.value)} />
            <button type="submit" style={styles.primaryButton} disabled={copilotLoading}>{copilotLoading ? 'Thinking with context…' : 'Ask the copilot'}</button>
          </form>
          <InlineError message={copilotError} />
          </div><div className="feature-output" aria-live="polite">
          {!copilotResult && <FeatureEmpty title="Let’s figure out your next step" description="Ask about your product, plan a meal, or improve your bag. Guiltless uses the context you’ve already shared." />}
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
                    <button key={action} type="button" style={styles.actionChip} onClick={() => setCopilotMessage(actionLabel(action))}>{actionLabel(action)}</button>
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
          </div></div>
        </article>
      <PersonalizedCopilot apiUrl={apiUrl} currentName={currentProduct.name} currentId={currentProduct.product_id} bagIds={bagIndexes.map(index => products[index]?.product_id)} goal={goal} onApply={applyPersonalizedSwap} />
        </div>
      </div>
      </div>

      <footer style={styles.integrationFooter}>
        <span>Designed to plug into:</span>
        {['Snap', 'Product Detail', 'Shopping Bag', 'Meal Planner', 'Tracker'].map((item) => <strong key={item}>{item}</strong>)}
      </footer>
    </section>
  );
}

function FeatureEmpty({ title, description }: { title: string; description: string }) {
  return <div className="feature-empty"><span aria-hidden="true">✳</span><h4>{title}</h4><p>{description}</p><small>Your results will appear here</small></div>;
}

function ProductFacts({ product }: { product: Product }) {
  return <div style={styles.facts}><ProductOption product={product} /><span>{product.nutrition.fiber_g}g fiber · {product.nutrition.sodium_mg}mg sodium</span></div>;
}

function NutritionDriver({ label, value, width, caution = false }: { label: string; value: string; width: number; caution?: boolean }) {
  return (
    <div style={styles.driver}>
      <div style={styles.driverRow}><span>{label}</span><strong>{value}</strong></div>
      <div style={styles.driverTrack}><span style={{ ...styles.driverValue, width: `${Math.max(8, width)}%`, background: caution ? '#f5b038' : '#baf0c2' }} /></div>
    </div>
  );
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
  section: { marginTop: 0, overflow: 'hidden', background: '#f9fbf4', color: '#09291c', border: '1px solid #e2eadf', borderRadius: 26, boxShadow: '0 24px 70px rgba(9,56,38,.1)' },
  hero: { display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 360px', gap: 64, alignItems: 'center', minHeight: 390, padding: '48px 52px', background: '#093826', color: '#fff' },
  heroCopy: { display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 16 },
  eyebrow: { margin: 0, borderRadius: 999, padding: '7px 11px', background: '#174f38', color: '#baf0c2', fontWeight: 900, letterSpacing: '.08em', textTransform: 'uppercase', fontSize: 11 },
  heading: { margin: 0, maxWidth: 720, fontSize: 'clamp(38px,4.5vw,58px)', lineHeight: 1.04, letterSpacing: '-.04em' },
  subtitle: { margin: 0, maxWidth: 700, color: '#cfe5d9', fontSize: 17, lineHeight: 1.55 },
  activeContext: { display: 'flex', alignItems: 'center', gap: 11, flexWrap: 'wrap', borderRadius: 14, padding: '11px 14px', background: '#0f4530', color: '#b8d1c2', fontSize: 12 },
  contextDivider: { width: 1, height: 22, background: '#3b6b57' },
  contextScore: { color: '#baf0c2' },
  scoreSource: { color: '#9ec8ac', fontSize: 9, lineHeight: 1.3 },
  goalLabel: { display: 'flex', alignItems: 'center', gap: 10, color: '#d1e8db', fontWeight: 800, fontSize: 12 },
  input: { minWidth: 190, border: '1px solid #3b6b57', borderRadius: 10, padding: '8px 11px', background: '#0f4530', color: '#fff', fontSize: 13 },
  snapshot: { display: 'flex', flexDirection: 'column', gap: 13, borderRadius: 20, padding: 20, background: '#0e4733', boxShadow: 'inset 0 0 0 1px rgba(186,240,194,.06)' },
  snapshotHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  snapshotLabel: { display: 'block', marginBottom: 3, color: '#baf0c2', fontSize: 9, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '.06em' },
  snapshotScore: { borderRadius: 999, padding: '7px 10px', background: '#fff', color: '#093826', fontSize: 11, fontWeight: 900 },
  snapshotRule: { height: 1, background: '#336652' },
  driverTitle: { color: '#d1e8db', fontSize: 11 },
  driver: { display: 'flex', flexDirection: 'column', gap: 5 },
  driverRow: { display: 'flex', justifyContent: 'space-between', color: '#a3bfb0', fontSize: 10 },
  driverTrack: { overflow: 'hidden', height: 6, borderRadius: 999, background: '#1a5942' },
  driverValue: { display: 'block', height: '100%', borderRadius: 999 },
  snapshotAction: { alignSelf: 'flex-start', border: 0, borderRadius: 11, padding: '10px 12px', background: '#14573d', color: '#fff', cursor: 'pointer', fontWeight: 800, fontSize: 10 },
  heroScanButton: { border: '1px solid #4d8069', borderRadius: 11, padding: '10px 13px', background: 'transparent', color: '#fff', cursor: 'pointer', fontSize: 11, fontWeight: 900 },
  workflow: { display: 'grid', gridTemplateColumns: 'repeat(5,minmax(0,1fr))', gap: 8, margin: '0 52px', transform: 'translateY(-18px)', border: '1px solid #e4eee7', borderRadius: 18, padding: 16, background: '#fff', boxShadow: '0 14px 30px rgba(9,56,38,.08)' },
  workflowItem: { position: 'relative', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 7, minWidth: 0, borderRadius: 11, padding: '9px 6px', color: '#576e63', fontSize: 12 },
  workflowNumber: { display: 'grid', placeItems: 'center', width: 22, height: 22, borderRadius: 999, background: '#bbf7d0', color: '#14532d', fontWeight: 900, fontSize: 10 },
  workflowArrow: { position: 'absolute', right: -8, color: '#6ee7b7', fontSize: 16 },
  scanPanel: { margin: '0 28px 18px', border: '1px solid #c9e0d1', borderRadius: 18, padding: 18, background: '#fff' },
  scanPanelHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 20 },
  scanKicker: { color: '#0f6340', fontSize: 9, fontWeight: 900, letterSpacing: '.08em', textTransform: 'uppercase' },
  scanTitle: { margin: '4px 0 0', color: '#09291c', fontSize: 17 },
  scanCopy: { margin: '5px 0 0', color: '#64746b', fontSize: 12, lineHeight: 1.45 },
  scanToggle: { flex: '0 0 auto', border: 0, borderRadius: 999, padding: '10px 14px', background: '#093826', color: '#fff', cursor: 'pointer', fontSize: 11, fontWeight: 900 },
  scanGrid: { display: 'grid', gridTemplateColumns: '.75fr 1.25fr', gap: 16, marginTop: 16, borderTop: '1px solid #e2eadf', paddingTop: 16 },
  uploadZone: { position: 'relative', display: 'flex', minHeight: 210, alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 8, overflow: 'hidden', border: '1.5px dashed #9fc9ae', borderRadius: 15, padding: 18, background: '#f5faf6', color: '#093826', textAlign: 'center', cursor: 'pointer' },
  uploadIcon: { display: 'grid', placeItems: 'center', width: 44, height: 44, borderRadius: 13, background: '#e0f7e8', color: '#0f6340', fontSize: 22 },
  scanPreview: { width: '100%', height: 120, borderRadius: 10, objectFit: 'cover' },
  fileInput: { position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' },
  scanEditor: { display: 'flex', flexDirection: 'column', gap: 9 },
  scanTextLabel: { display: 'flex', justifyContent: 'space-between', gap: 12, color: '#09291c', fontSize: 11, fontWeight: 900 },
  scanTextarea: { width: '100%', boxSizing: 'border-box', border: '1px solid #c9e0d1', borderRadius: 12, padding: 12, background: '#fbfdfb', color: '#213a2f', resize: 'vertical', fontFamily: 'inherit', fontSize: 12, lineHeight: 1.5 },
  scanSuccess: { gridColumn: '1 / -1', display: 'flex', gap: 11, alignItems: 'flex-start', borderRadius: 13, padding: 12, background: '#e8fceb', color: '#093826' },
  scanSuccessIcon: { display: 'grid', placeItems: 'center', flex: '0 0 auto', width: 28, height: 28, borderRadius: 999, background: '#0f6340', color: '#fff', fontWeight: 900 },
  grid: { display: 'grid', gridTemplateColumns: 'minmax(260px,.9fr) minmax(380px,1.3fr) minmax(280px,.95fr)', gap: 18, padding: '18px 28px 42px' },
  centerColumn: { display: 'flex', flexDirection: 'column', gap: 18, minWidth: 0 },
  card: { display: 'flex', flexDirection: 'column', gap: 13, minWidth: 0, background: '#fff', color: '#12372a', border: '1px solid #e5ece7', borderRadius: 20, padding: 18, boxShadow: '0 12px 30px rgba(6,78,59,.08)' },
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
  integrationFooter: { display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8, flexWrap: 'wrap', borderTop: '1px solid #e2eadf', padding: '22px 28px', background: '#fff', color: '#576e63', fontSize: 11 },
};
