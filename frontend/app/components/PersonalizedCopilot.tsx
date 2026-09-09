'use client';

import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../lib/api';

export type CatalogProduct = {
  product_id: string; name: string; brand: string; category: string;
  nutrition: Record<string, unknown>; ingredients: string[];
};
type Score = {
  base_score: number; personal_score: number | null; compatibility: string;
  drivers: { factor: string; impact: number; reason: string }[];
  penalties: { factor: string; impact: number; reason: string }[];
  hard_constraint_failures: string[];
};
type Alternative = { product: CatalogProduct; scoring: Score; base_score_delta: number; ranking_reasons: string[] };
type Reply = {
  intent: string; response: string; errors: string[]; suggested_actions: string[];
  confidence: number; grounding: { data_sources: string[]; score_version: string };
  tool_result: {
    current_product?: { product: CatalogProduct; scoring: Score };
    ranked_alternatives?: Alternative[];
    swaps?: { current_product: { product: CatalogProduct }; alternative: Alternative }[];
    current_score?: number; optimized_score?: number; score_gain?: number;
  };
};
const prompts: Record<string, string> = {
  explain_score: 'Explain score', compare_alternatives: 'Find a better alternative',
  optimize_bag: 'Optimize my bag', build_workout_plan: 'Build a workout plan',
};

export default function PersonalizedCopilot({ apiUrl, currentName, bagNames, goal, onApply }: {
  apiUrl?: string; currentName: string; bagNames: string[]; goal: string;
  onApply: (product: CatalogProduct, originalName: string) => void;
}) {
  const [catalog, setCatalog] = useState<CatalogProduct[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState('');
  const [retry, setRetry] = useState(0);
  const [allergies, setAllergies] = useState('');
  const [diet, setDiet] = useState('');
  const [target, setTarget] = useState(120);
  const [consumed, setConsumed] = useState(30);
  const [result, setResult] = useState<Reply | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const requestVersion = useRef(0);
  const product = catalog.find(p => p.name === currentName);
  const bagKey = bagNames.join('|');

  useEffect(() => {
    const controller = new AbortController();
    setCatalogLoading(true); setCatalogError('');
    if (!apiUrl) { setCatalogError('Connect the backend to load product intelligence.'); setCatalogLoading(false); return; }
    fetch(`${apiUrl.replace(/\/$/, '')}/v2/products`, { signal: controller.signal })
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(errorMessage(data, response.status));
        if (!Array.isArray(data) || !data.every(p => typeof p.product_id === 'string' && typeof p.name === 'string')) throw new Error('Product catalog could not be read.');
        setCatalog(data);
      })
      .catch(err => { if (!controller.signal.aborted) setCatalogError(err instanceof Error ? err.message : 'Catalog unavailable.'); })
      .finally(() => { if (!controller.signal.aborted) setCatalogLoading(false); });
    return () => controller.abort();
  }, [apiUrl, retry]);

  useEffect(() => {
    requestVersion.current += 1; setResult(null); setBusy(false); setError('');
  }, [currentName, bagKey, goal, allergies, diet, target, consumed]);

  async function ask(message: string) {
    const version = ++requestVersion.current;
    setBusy(true); setError(''); setResult(null); setSuccess('');
    try {
      if (!apiUrl || !product) throw new Error('Select one of the catalog demo products above.');
      const ids = bagNames.map(name => catalog.find(p => p.name === name)?.product_id);
      if (message.toLowerCase().includes('bag') && ids.some(id => !id)) throw new Error('The bag contains a scan without a verified catalog match. Use catalog products for personalized optimization.');
      const response = await fetch(`${apiUrl.replace(/\/$/, '')}/v2/copilot/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, product_id: product.product_id, bag_product_ids: ids.filter(Boolean),
          user_profile: { primary_goal: goal, protein_target: target, allergies: allergies.split(',').map(s => s.trim()).filter(Boolean), dietary_preferences: diet ? [diet] : [] },
          daily_nutrition_state: { protein_consumed: consumed } }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(errorMessage(data, response.status));
      if (typeof data.response !== 'string' || !Array.isArray(data.errors) || !data.grounding || !data.tool_result) throw new Error('The copilot returned an unreadable result.');
      if (version === requestVersion.current) setResult(data);
    } catch (err) {
      if (version === requestVersion.current) setError(err instanceof Error ? err.message : 'Please try again.');
    } finally { if (version === requestVersion.current) setBusy(false); }
  }

  function apply(alternative: Alternative, originalName: string) {
    onApply(alternative.product, originalName);
    setResult(null);
    setSuccess(`Applied ${alternative.product.name} to the active product and matching items in this demo bag. Your saved bag is unchanged.`);
  }

  const score = result?.tool_result.current_product?.scoring;
  const alternatives = result?.tool_result.ranked_alternatives ?? [];
  return <section className="personal-copilot" aria-labelledby="personal-heading">
    <div className="personal-heading"><div><span className="personal-eyebrow">Guiltless · Made for you</span>
      <h3 id="personal-heading">Good food. Better for your day.</h3>
      <p>See how {currentName} fits your goals, then choose a compatible swap.</p></div>
      <span className="personal-badge">Demo nutrition data</span></div>
    <div className="personal-fields">
      <label>Daily protein target (g)<input type="number" min="1" max="500" value={target} onChange={e => setTarget(Number(e.target.value))} /></label>
      <label>Protein eaten today (g)<input type="number" min="0" value={consumed} onChange={e => setConsumed(Number(e.target.value))} /></label>
      <label>Allergies (comma separated)<input value={allergies} onChange={e => setAllergies(e.target.value)} placeholder="e.g. milk, peanuts" /></label>
      <label>Dietary requirement<select value={diet} onChange={e => setDiet(e.target.value)}><option value="">No restriction</option><option value="vegan">Vegan</option><option value="vegetarian">Vegetarian</option><option value="gluten-free">Gluten-free</option></select></label>
    </div>
    <p className="personal-note">Using the shared goal: {goal}. These day-level settings are a preview and do not change your saved profile.</p>
    {catalogLoading && <p role="status">Loading product catalog…</p>}
    {catalogError && <p role="alert">{catalogError} <button onClick={() => setRetry(v => v + 1)}>Retry</button></p>}
    {!catalogLoading && !catalogError && !product && <p role="status">This scan has no catalog match yet. Choose a demo product above to explore personalized scores.</p>}
    <div className="personal-actions">
      <button className="personal-primary" disabled={busy || !product || target <= 0 || consumed < 0} onClick={() => ask('Explain score')}>{busy ? 'Checking your fit…' : 'Why for you?'}</button>
      <button disabled={busy || !product} onClick={() => ask('Find a better alternative')}>Find personalized swaps</button>
      <button disabled={busy || !product} onClick={() => ask('Optimize my bag')}>Optimize my bag</button>
    </div>
    <div aria-live="polite">{error && <p className="personal-error" role="alert">{error}</p>}{success && <p className="personal-success">{success}</p>}</div>
    {result && <div className="personal-results">
      <p className="personal-eyebrow">{result.intent.replaceAll('_', ' ')}</p><p>{result.response}</p>
      {result.errors.length > 0 && <ul className="personal-error">{result.errors.map(e => <li key={e}>{e}</li>)}</ul>}
      {score && <>
        <div className="personal-scores"><div><span>Base Guiltless</span><strong>{score.base_score}<small>/100</small></strong></div>
          <div><span>G-Personal</span><strong>{score.personal_score ?? '—'}<small>{score.personal_score !== null ? '/100' : ''}</small></strong></div>
          <div><span>Your compatibility</span><strong className={score.compatibility === 'compatible' ? 'personal-compatible' : 'personal-error'}>{score.compatibility === 'compatible' ? 'Compatible' : 'Incompatible'}</strong></div></div>
        <h4>Why for you?</h4>
        {score.hard_constraint_failures.length > 0 && <ul className="personal-error">{score.hard_constraint_failures.map(reason => <li key={reason}>{reason}</li>)}</ul>}
        <ul className="personal-factors">{[...score.drivers, ...score.penalties].map(factor => <li key={factor.factor}><span>{factor.reason}</span><strong>{factor.impact >= 0 ? '+' : ''}{factor.impact.toFixed(2)}</strong></li>)}</ul>
      </>}
      {alternatives.map(alternative => <article className="personal-alternative" key={alternative.product.product_id}>
        <div><h4>{alternative.product.name}</h4><p>Base {alternative.scoring.base_score} · G-Personal {alternative.scoring.personal_score} · Compatible</p>
          <p>Base score change: {alternative.base_score_delta > 0 ? '+' : ''}{alternative.base_score_delta}</p><ul>{alternative.ranking_reasons.slice(0, 3).map(reason => <li key={reason}>{reason}</li>)}</ul></div>
        <button className="personal-primary" onClick={() => apply(alternative, currentName)}>Apply Swap</button></article>)}
      {result.intent === 'find_swap' && !alternatives.length && !result.errors.length && <p>No compatible improving alternatives were found in this catalog.</p>}
      {result.tool_result.current_score !== undefined && <p>Bag base score: <strong>{result.tool_result.current_score} → {result.tool_result.optimized_score}</strong> · Change {result.tool_result.score_gain}</p>}
      {result.tool_result.swaps?.map((swap, index) => <article className="personal-alternative" key={`${swap.current_product.product.product_id}-${index}`}>
        <p>{swap.current_product.product.name} → <strong>{swap.alternative.product.name}</strong></p>
        <button className="personal-primary" onClick={() => apply(swap.alternative, swap.current_product.product.name)}>Apply Swap</button></article>)}
      <div className="personal-actions">{result.suggested_actions.filter(action => prompts[action]).map(action => <button key={action} onClick={() => ask(prompts[action])} disabled={busy}>{action.replaceAll('_', ' ')}</button>)}</div>
      <p className="personal-note">Data confidence: {Math.round(result.confidence * 100)}% · {result.grounding.data_sources.join(', ') || 'No catalog recommendation'} · Scores apply to one serving and use a demo rubric.</p>
    </div>}
  </section>;
}
