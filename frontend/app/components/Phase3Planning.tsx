'use client';

import { useEffect, useState } from 'react';

type JsonObject = Record<string, any>;
type Mode = 'consumer' | 'trainer';

function list(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

async function readJson(response: Response) {
  const text = await response.text();
  try { return text ? JSON.parse(text) : {}; } catch { return { detail: text || 'Non-JSON response from backend' }; }
}

export default function Phase3Planning({ apiUrl, shoppingList, onWorkoutPlan }: { apiUrl?: string; shoppingList?: JsonObject | null; onWorkoutPlan?: (plan: JsonObject) => void }) {
  const [mode, setMode] = useState<Mode>('consumer');
  const [workoutForm, setWorkoutForm] = useState({ goal: 'muscle gain', days_per_week: 4, equipment: 'dumbbells, gym', experience_level: 'beginner', session_minutes: 60 });
  const [coachForm, setCoachForm] = useState({ client_name: 'Demo Client', goal: 'fat loss', diet: 'high protein', days_per_week: 4, equipment: 'gym', calorie_target: 2200 });
  const [workoutResult, setWorkoutResult] = useState<JsonObject | null>(null);
  const [coachResult, setCoachResult] = useState<JsonObject | null>(null);
  const [workoutLoading, setWorkoutLoading] = useState(false);
  const [coachLoading, setCoachLoading] = useState(false);
  const [workoutError, setWorkoutError] = useState<string | null>(null);
  const [coachError, setCoachError] = useState<string | null>(null);
  const [clients, setClients] = useState<JsonObject[]>([]);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [checkoutResult, setCheckoutResult] = useState<JsonObject | null>(null);
  const [checkoutLoading, setCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  useEffect(() => {
    if (!apiUrl) return;
    fetch(`${apiUrl.replace(/\/$/, '')}/coach/clients`).then(readJson).then((payload) => setClients(Array.isArray(payload.clients) ? payload.clients : [])).catch(() => undefined);
  }, [apiUrl]);

  async function post(path: string, body: JsonObject) {
    if (!apiUrl) throw new Error('NEXT_PUBLIC_API_URL is not configured.');
    const response = await fetch(`${apiUrl.replace(/\/$/, '')}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.detail || `Backend returned ${response.status}`);
    return payload;
  }

  async function generateWorkout() {
    setWorkoutLoading(true); setWorkoutError(null);
    try {
      const result = await post('/workout-plan', { ...workoutForm, equipment: list(workoutForm.equipment), limitations: [] });
      setWorkoutResult(result);
      onWorkoutPlan?.(result);
    } catch (error) { setWorkoutError(error instanceof Error ? error.message : 'Unable to generate workout plan'); }
    finally { setWorkoutLoading(false); }
  }

  async function generateClientPlan() {
    setCoachLoading(true); setCoachError(null);
    try {
      const result = await post('/coach/client-plan', { ...coachForm, client_id: selectedClientId || null, equipment: list(coachForm.equipment), allergies: [] });
      setCoachResult(result);
      setSelectedClientId(result.persistence?.profile_id ?? '');
      const clientPayload = await fetch(`${apiUrl?.replace(/\/$/, '')}/coach/clients`).then(readJson);
      setClients(Array.isArray(clientPayload.clients) ? clientPayload.clients : []);
    } catch (error) { setCoachError(error instanceof Error ? error.message : 'Unable to generate client plan'); }
    finally { setCoachLoading(false); }
  }

  function loadClient(clientId: string) {
    setSelectedClientId(clientId);
    const client = clients.find((item) => item.id === clientId);
    if (!client) return;
    setCoachForm({
      client_name: client.client_name ?? 'Demo Client', goal: client.goal ?? 'general fitness', diet: client.diet ?? 'balanced',
      days_per_week: Number(client.days_per_week ?? 3), equipment: (client.equipment ?? []).join(', '), calorie_target: Number(client.calorie_target ?? 2200),
    });
  }

  async function prepareCoachCheckout() {
    setCheckoutLoading(true); setCheckoutError(null); setCheckoutResult(null);
    try {
      const strategy = coachResult?.shopping_strategy;
      if (!strategy && !shoppingList) throw new Error('Generate a client plan or shopping list first.');
      setCheckoutResult(await post('/checkout/prepare', {
        client_id: coachResult?.persistence?.profile_id || selectedClientId || null,
        retailer: 'Preferred retailer', shopping_strategy: strategy ?? null, shopping_list: shoppingList ?? null,
      }));
    } catch (error) { setCheckoutError(error instanceof Error ? error.message : 'Unable to prepare checkout'); }
    finally { setCheckoutLoading(false); }
  }

  return (
    <section id="coach-mode" className="phase3-shell">
      <header className="phase3-header">
        <div><span>Agentic Actions · Coach Foundation</span><h2>Consumer AI Copilot + B2B Trainer Copilot</h2><p>One planning engine, expressed for two valuable workflows.</p></div>
        <div className="phase3-mode" role="tablist" aria-label="Planning mode">
          <button className={mode === 'consumer' ? 'active' : ''} onClick={() => setMode('consumer')} role="tab">Consumer mode</button>
          <button className={mode === 'trainer' ? 'active' : ''} onClick={() => setMode('trainer')} role="tab">Coach / Trainer Mode</button>
        </div>
      </header>

      <div className="phase3-pathways">
        <div><span>Consumer</span><strong>Snap → Explain → Meal Plan → Bag</strong></div>
        <div><span>Trainer</span><strong>Client Goal → Meal Plan → Workout Plan → Shopping Strategy</strong></div>
      </div>

      {mode === 'consumer' ? (
        <div className="planner-layout">
          <article className="planner-form-card">
            <div className="planner-card-heading"><span>Consumer action</span><h3>Build workout plan</h3><p>Turn a nutrition goal into a practical weekly training split.</p></div>
            <div className="planner-form-grid">
              <label>Goal<input value={workoutForm.goal} onChange={(e) => setWorkoutForm({ ...workoutForm, goal: e.target.value })} /></label>
              <label>Days / week<input type="number" min={1} max={7} value={workoutForm.days_per_week} onChange={(e) => setWorkoutForm({ ...workoutForm, days_per_week: Number(e.target.value) })} /></label>
              <label>Equipment<input value={workoutForm.equipment} onChange={(e) => setWorkoutForm({ ...workoutForm, equipment: e.target.value })} /></label>
              <label>Experience<select value={workoutForm.experience_level} onChange={(e) => setWorkoutForm({ ...workoutForm, experience_level: e.target.value })}><option>beginner</option><option>intermediate</option><option>advanced</option></select></label>
            </div>
            <button className="planner-primary" onClick={generateWorkout} disabled={workoutLoading}>{workoutLoading ? 'Building your split…' : 'Generate workout plan'}</button>
            {workoutError && <div className="planner-error">{workoutError}</div>}
          </article>
          <WorkoutResult result={workoutResult} emptyText="Your weekly split will appear here." />
        </div>
      ) : (
        <div className="coach-layout">
          <article className="planner-form-card coach-form-card">
            <div className="planner-card-heading"><span>B2B trainer action</span><h3>Create connected client plan</h3><p>Generate the nutrition, training, and shopping foundation in one action.</p></div>
            <label className="saved-client-picker">Saved client<select value={selectedClientId} onChange={(e) => loadClient(e.target.value)}><option value="">New client</option>{clients.map((client) => <option key={client.id} value={client.id}>{client.client_name} · {client.goal}</option>)}</select><small>{clients.length} persisted client{clients.length === 1 ? '' : 's'}</small></label>
            <div className="planner-form-grid">
              <label>Client name<input value={coachForm.client_name} onChange={(e) => setCoachForm({ ...coachForm, client_name: e.target.value })} /></label>
              <label>Client goal<input value={coachForm.goal} onChange={(e) => setCoachForm({ ...coachForm, goal: e.target.value })} /></label>
              <label>Diet preference<input value={coachForm.diet} onChange={(e) => setCoachForm({ ...coachForm, diet: e.target.value })} /></label>
              <label>Training days<input type="number" min={1} max={7} value={coachForm.days_per_week} onChange={(e) => setCoachForm({ ...coachForm, days_per_week: Number(e.target.value) })} /></label>
              <label>Equipment<input value={coachForm.equipment} onChange={(e) => setCoachForm({ ...coachForm, equipment: e.target.value })} /></label>
              <label>Calorie target<input type="number" value={coachForm.calorie_target} onChange={(e) => setCoachForm({ ...coachForm, calorie_target: Number(e.target.value) })} /></label>
            </div>
            <button className="planner-primary" onClick={generateClientPlan} disabled={coachLoading}>{coachLoading ? 'Building client plan…' : 'Generate client plan'}</button>
            {coachError && <div className="planner-error">{coachError}</div>}
          </article>
          <CoachResult result={coachResult} checkoutResult={checkoutResult} checkoutLoading={checkoutLoading} checkoutError={checkoutError} onPrepareCheckout={prepareCoachCheckout} />
        </div>
      )}
    </section>
  );
}

function WorkoutResult({ result, emptyText }: { result: JsonObject | null; emptyText: string }) {
  if (!result) return <article className="planner-result-card planner-empty"><span>Weekly split</span><strong>{emptyText}</strong><p>Exercises, sets, reps, progression, and safety notes are returned as structured data.</p></article>;
  return (
    <article className="planner-result-card">
      <div className="planner-card-heading"><span>Generated weekly split</span><h3>{result.summary}</h3></div>
      <div className="workout-days">{(result.weekly_split ?? []).map((day: JsonObject) => <div key={day.day} className="workout-day"><span>Day {day.day}</span><strong>{day.focus}</strong><ul>{(day.exercises ?? []).map((exercise: JsonObject) => <li key={exercise.name}><b>{exercise.name}</b><small>{exercise.sets} sets · {exercise.reps}</small></li>)}</ul></div>)}</div>
      <div className="plan-note"><strong>Progression</strong><p>{result.progression_notes}</p></div>
    </article>
  );
}

function CoachResult({ result, checkoutResult, checkoutLoading, checkoutError, onPrepareCheckout }: { result: JsonObject | null; checkoutResult: JsonObject | null; checkoutLoading: boolean; checkoutError: string | null; onPrepareCheckout: () => void }) {
  if (!result) return <article className="planner-result-card planner-empty"><span>Trainer output</span><strong>A complete client foundation will appear here.</strong><p>Nutrition, workout split, shopping strategy, and coach notes stay connected.</p></article>;
  return (
    <div className="coach-results">
      <article><span>Nutrition plan</span><h3>{result.nutrition_plan?.summary}</h3><p>{result.nutrition_plan?.protein_target_g}g daily protein target</p></article>
      <article><span>Workout split</span><h3>{result.workout_plan?.summary}</h3><p>{(result.workout_plan?.weekly_split ?? []).map((day: JsonObject) => day.focus).join(' · ')}</p></article>
      <article><span>Shopping strategy</span><h3>{result.shopping_strategy?.summary}</h3><p>{(result.shopping_strategy?.priority_categories ?? []).join(' · ')}</p><button className="checkout-button" onClick={onPrepareCheckout} disabled={checkoutLoading}>{checkoutLoading ? 'Preparing handoff…' : 'Prepare checkout →'}</button>{checkoutError && <small className="checkout-error">{checkoutError}</small>}{checkoutResult && <div className="checkout-ready"><strong>{checkoutResult.item_count} items prepared</strong><small>{checkoutResult.checkout_url ? 'Retailer handoff ready' : 'Session saved · connect retailer URL for handoff'}</small>{checkoutResult.checkout_url && <a href={checkoutResult.checkout_url}>Open retailer checkout</a>}</div>}</article>
      <article><span>Coach notes</span><ul>{(result.coach_notes ?? []).map((note: string) => <li key={note}>{note}</li>)}</ul></article>
    </div>
  );
}
