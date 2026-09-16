'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { requestJson } from '../lib/api';

type Reply = {
  intent: string; response: string; steps: string[]; errors: string[]; limitations: string[];
  actions: { id: string; label: string; kind: string; requires_confirmation: boolean }[];
  tool_result: { base_explanation?: {score: number; positives: string[]; cautions: string[]}; current_product?: { scoring: { base_score: number; personal_score: number | null; compatibility: string;
    drivers: { reason: string }[]; penalties: { reason: string }[]; hard_constraint_failures: string[] } } };
};
type Proactive = {id: string; intent: string; message: string; reason: string;
  action: {id: string; label: string; kind: string; requires_confirmation: boolean}};
const screens = [['product_detail', 'Product detail'], ['groceries', 'Groceries & filters'], ['comparison', 'Product comparison'], ['bag', 'Shopping bag'], ['scan', 'Scan a food'], ['food_logging', 'Log / save food'], ['tracker', 'My Tracker']];

export default function AppHelper({ apiUrl, productId, productName, bagIds, goal, screen, onNavigate }: {
  apiUrl?: string; productId?: string; productName: string; bagIds: string[]; goal: string; screen: string;
  onNavigate: (action: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [activeScreen, setActiveScreen] = useState(screen);
  const [message, setMessage] = useState('How do I use this screen?');
  const [allergies, setAllergies] = useState('');
  const [externalScore, setExternalScore] = useState(false);
  const [reply, setReply] = useState<Reply | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [proactive, setProactive] = useState<Proactive | null>(null);
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const previousScreen = useRef(screen);
  const previousBagCount = useRef(bagIds.length);
  useEffect(() => {
    generation.current += 1; request.current?.abort(); setLoading(false); setReply(null); setError('');
  }, [activeScreen, productId, goal, allergies, externalScore, bagIds.join('|')]);
  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const events = [{event_type: 'screen_viewed', screen, product_id: productId, metadata: {source: 'web_copilot'}}];
        if (previousScreen.current === 'comparison' && screen !== 'comparison')
          events.push({event_type: 'comparison_abandoned', screen: 'comparison', product_id: productId, metadata: {source: 'web_copilot'}});
        if (bagIds.length > previousBagCount.current)
          events.push({event_type: 'product_added_to_bag', screen: 'bag', product_id: bagIds.at(-1), metadata: {source: 'web_copilot'}});
        previousScreen.current = screen; previousBagCount.current = bagIds.length;
        for (const event of events) await requestJson(apiUrl, '/app/events/demo-user', {method: 'POST', signal: controller.signal, body: JSON.stringify(event)});
        const result = await requestJson(apiUrl, '/helper/proactive/demo-user', {method: 'POST', signal: controller.signal,
          body: JSON.stringify({screen, product_id: productId, product_name: productName,
            bag_product_ids: bagIds})});
        setProactive(result.show ? result.suggestion : null);
      } catch { /* Guidance must never block the host app. */ }
    }, 800);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [apiUrl, screen, productId, productName, bagIds.join('|')]);

  async function recordSuggestion(eventType: 'suggestion_accepted' | 'suggestion_dismissed', suggestion: Proactive) {
    try { await requestJson(apiUrl, '/app/events/demo-user', {method: 'POST',
      body: JSON.stringify({event_type: eventType, screen, product_id: productId,
        metadata: {suggestion_id: suggestion.id, intent: suggestion.intent}})}); } catch { /* optional telemetry */ }
  }

  function open() { setActiveScreen(screen); setNotice(''); dialog.current?.showModal(); }
  async function ask(question: string) {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const current = ++generation.current;
    setMessage(question); setLoading(true); setError(''); setReply(null); setNotice('');
    try {
      const result = await requestJson(apiUrl, '/helper/chat', {method: 'POST', signal: controller.signal,
        body: JSON.stringify({message: question, screen: activeScreen, product_id: productId,
          bag_product_ids: bagIds, goal, allergies: allergies.split(',').map(x => x.trim()).filter(Boolean),
          score_source: externalScore ? 'mobile_app' : 'agent_catalog', user_id: 'demo-user'})});
      if (current === generation.current) setReply(result);
    } catch (e) {
      if (current === generation.current && !controller.signal.aborted) setError(e instanceof Error ? e.message : 'The helper is unavailable. Try again.');
    } finally { if (current === generation.current) setLoading(false); }
  }

  return <>
    <div className="helper-entry">
      {proactive && <aside className="helper-nudge" aria-live="polite">
        <button type="button" className="helper-nudge-close" aria-label="Dismiss suggestion" onClick={() => { void recordSuggestion('suggestion_dismissed', proactive); setProactive(null); }}>×</button>
        <small>GUILTLESS GUIDE</small><p>{proactive.message}</p>
        <button type="button" onClick={() => {
          void recordSuggestion('suggestion_accepted', proactive);
          const suggestion = proactive; setProactive(null);
          if (suggestion.intent === 'explain_health_score') { open(); void ask('Explain this score'); }
          else if (['open_scan', 'open_explain', 'open_compare', 'open_bag'].includes(suggestion.action.id)) onNavigate(suggestion.action.id);
        }}>{proactive.action.label}</button>
        <span>Why this appeared: {proactive.reason}</span>
      </aside>}
      <button type="button" className="helper-launch" onClick={open} aria-label="Open the Guiltless app guide">
        <span className="helper-launch-icon" aria-hidden="true"><Image src="/mascots/guiltless-guide.png" alt="" width={58} height={58} priority /></span>
        <span><strong>Guiltless Guide</strong><small>Ask how to use the app</small></span>
      </button>
    </div>
    <dialog ref={dialog} className="app-helper" aria-labelledby="helper-title">
      <header><div><span>YOUR IN-APP GUIDE · PREVIEW</span><h2 id="helper-title">Ask Guiltless</h2></div><button type="button" aria-label="Close helper" onClick={() => dialog.current?.close()}>×</button></header>
      <div className="helper-content">
        <p className="helper-context">{productName}<br /><small>Goal: {goal} · {bagIds.length} known catalog items in bag</small></p>
        <label>Help me on this screen<select value={activeScreen} onChange={e => setActiveScreen(e.target.value)}>{screens.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
        <label>Allergies to check<input value={allergies} onChange={e => setAllergies(e.target.value)} placeholder="e.g. milk, peanuts" /></label>
        <label className="helper-checkbox"><input type="checkbox" checked={externalScore} onChange={e => setExternalScore(e.target.checked)} /> My question is about the mobile app’s existing score</label>
        <div className="helper-prompts">{['How do I use this screen?', 'Explain this score', 'Compare alternatives', 'How do I log food?'].map(prompt => <button type="button" key={prompt} disabled={loading} onClick={() => void ask(prompt)}>{prompt}</button>)}</div>
        <form onSubmit={e => { e.preventDefault(); if (message.trim()) void ask(message); }}><label>Your question<textarea value={message} onChange={e => setMessage(e.target.value)} rows={3} /></label><button className="helper-primary" disabled={loading || !message.trim()}>{loading ? 'Checking your context…' : 'Ask Guiltless'}</button></form>
        {error && <p role="alert" className="helper-error">{error}</p>}
        <div aria-live="polite" aria-busy={loading}>
          {reply && <section className="helper-reply"><small>{reply.intent.replaceAll('_', ' ')}</small><h3>{reply.response}</h3>
            {!!reply.steps.length && <ol>{reply.steps.map(step => <li key={step}>{step}</li>)}</ol>}
            {reply.tool_result.base_explanation && <div className="helper-score"><strong>What drives the base score</strong><ul>{[...reply.tool_result.base_explanation.positives, ...reply.tool_result.base_explanation.cautions].map((reason, i) => <li key={i}>{reason}</li>)}</ul></div>}
            {reply.tool_result.current_product && <div className="helper-score"><strong>Agent catalog score: {reply.tool_result.current_product.scoring.base_score}/100</strong><p>Personal fit: {reply.tool_result.current_product.scoring.personal_score ?? 'Incompatible'}</p><ul>{[...reply.tool_result.current_product.scoring.drivers.map(x => x.reason), ...reply.tool_result.current_product.scoring.penalties.map(x => x.reason), ...reply.tool_result.current_product.scoring.hard_constraint_failures].map((reason, i) => <li key={i}>{reason}</li>)}</ul></div>}
            {reply.errors.map(item => <p key={item} className="helper-error">{item}</p>)}
            <div className="helper-prompts">{reply.actions.map(action => <button type="button" key={action.id} onClick={() => {
              if (action.requires_confirmation || action.kind === 'review') { setNotice('Nothing has been changed. Review and confirm in the feature itself. Mobile logging and checkout are not connected.'); return; }
              if (['open_scan', 'open_explain', 'open_compare', 'open_bag'].includes(action.id)) { dialog.current?.close(); onNavigate(action.id); }
            }}>{action.label}</button>)}</div>
            {!!Object.keys(reply.tool_result).length && <details><summary>View grounded result</summary><pre>{JSON.stringify(reply.tool_result, null, 2)}</pre></details>}
            {reply.limitations.map(item => <p className="helper-note" key={item}>{item}</p>)}
          </section>}
          {notice && <p role="status">{notice}</p>}
        </div>
        <p className="helper-note">Uses declared app events and your saved preferences—not screenshots or raw screen monitoring. You review actions before anything changes.</p>
      </div>
    </dialog>
  </>;
}
