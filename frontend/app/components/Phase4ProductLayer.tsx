'use client';

import { useEffect, useState } from 'react';

import { requestJson } from '../lib/api';

type JsonObject = Record<string, any>;
type Tab = 'profile' | 'bag' | 'plans' | 'clients';

const DEMO_ITEM = {
  name: 'Roasted Chickpea Bites', brand: 'Good Crunch', category: 'Savory snack',
  nutrition: { calories: 180, protein_g: 9, fiber_g: 6, sugar_g: 2, sodium_mg: 220 }, ingredients: ['chickpeas', 'olive oil', 'spices'],
};

function csv(value: string) { return value.split(',').map((item) => item.trim()).filter(Boolean); }

export default function Phase4ProductLayer({ apiUrl, latestMealPlan, latestWorkoutPlan }: { apiUrl?: string; latestMealPlan?: JsonObject | null; latestWorkoutPlan?: JsonObject | null }) {
  const [tab, setTab] = useState<Tab>('profile');
  const [profile, setProfile] = useState({ goal: 'balanced nutrition', diet: 'no restriction', allergies: '', disliked_foods: '', budget: 'flexible', preferred_store: 'Instacart', training_days: 3, equipment: '', calorie_target: 2200 });
  const [bag, setBag] = useState<JsonObject[]>([]);
  const [plans, setPlans] = useState<JsonObject>({ meal_plans: [], workout_plans: [] });
  const [clients, setClients] = useState<JsonObject[]>([]);
  const [clientPlans, setClientPlans] = useState<JsonObject[]>([]);
  const [selectedClient, setSelectedClient] = useState('');
  const [newClientName, setNewClientName] = useState('Demo Client 2');
  const [bagOptimization, setBagOptimization] = useState<JsonObject | null>(null);
  const [checkout, setCheckout] = useState<JsonObject | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function request(path: string, options?: RequestInit) {
    return requestJson(apiUrl, path, options);
  }

  async function refreshAll() {
    if (!apiUrl) return;
    setLoading(true);
    try {
      const [profilePayload, bagPayload, planPayload, clientPayload] = await Promise.all([
        request('/profile/demo-user'), request('/bag/demo-user'), request('/plans/demo-user'), request('/coach/clients'),
      ]);
      setProfile({
        goal: profilePayload.goal ?? '', diet: profilePayload.diet ?? '', allergies: (profilePayload.allergies ?? []).join(', '), disliked_foods: (profilePayload.disliked_foods ?? []).join(', '),
        budget: profilePayload.budget ?? '', preferred_store: profilePayload.preferred_store ?? '', training_days: Number(profilePayload.training_days ?? 3), equipment: (profilePayload.equipment ?? []).join(', '), calorie_target: Number(profilePayload.calorie_target ?? 2200),
      });
      setBag(bagPayload.items ?? []); setPlans(planPayload); setClients(clientPayload.clients ?? []);
    } catch (loadError) { setError(loadError instanceof Error ? loadError.message : 'Unable to load saved product state'); }
    finally { setLoading(false); }
  }

  useEffect(() => { refreshAll(); }, [apiUrl]);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label); setError(null); setNotice(null);
    try { await action(); } catch (actionError) { setError(actionError instanceof Error ? actionError.message : 'Action failed'); }
    finally { setBusy(null); }
  }

  function saveProfile() {
    return run('profile', async () => {
      await request('/profile/demo-user', { method: 'PUT', body: JSON.stringify({ ...profile, allergies: csv(profile.allergies), disliked_foods: csv(profile.disliked_foods), equipment: csv(profile.equipment) }) });
      setNotice('Profile memory saved. Future Copilot requests can load it.'); await refreshAll();
    });
  }

  function addDemoItem() {
    return run('bag', async () => { const payload = await request('/bag/demo-user/add', { method: 'POST', body: JSON.stringify({ product: DEMO_ITEM, quantity: 1 }) }); setBag(payload.items ?? []); setNotice('Demo item added to the persistent bag.'); });
  }

  function clearSavedBag() {
    return run('bag', async () => { await request('/bag/demo-user/clear', { method: 'DELETE' }); setBag([]); setBagOptimization(null); setCheckout(null); setNotice('Persistent bag cleared.'); });
  }

  function optimizeSavedBag() {
    return run('optimize', async () => { if (!bag.length) throw new Error('Add an item before optimizing.'); setBagOptimization(await request('/bag/optimize', { method: 'POST', body: JSON.stringify({ items: bag.map((item) => item.product), goal: profile.goal }) })); });
  }

  function checkoutInstacart() {
    return run('checkout', async () => { const result = await request('/checkout/instacart', { method: 'POST', body: JSON.stringify({ user_id: 'demo-user' }) }); setCheckout(result); setNotice('Mock Instacart handoff prepared.'); });
  }

  function savePlan(kind: 'meal' | 'workout', plan: JsonObject | null | undefined) {
    return run(`save-${kind}`, async () => { if (!plan) throw new Error(`Generate a ${kind} plan first.`); await request(`/plans/demo-user/${kind}`, { method: 'POST', body: JSON.stringify({ plan }) }); setPlans(await request('/plans/demo-user')); setNotice(`${kind === 'meal' ? 'Meal' : 'Workout'} plan saved.`); });
  }

  function createClient() {
    return run('client', async () => {
      const client = await request('/coach/clients', { method: 'POST', body: JSON.stringify({ client_name: newClientName, goal: 'fat loss', diet: 'high protein', days_per_week: 4, equipment: ['gym'], calorie_target: 2200 }) });
      setSelectedClient(client.id); setClients((current) => [client, ...current.filter((item) => item.id !== client.id)]); setNotice('Trainer client saved.');
    });
  }

  function viewClientPlans(clientId: string) {
    setSelectedClient(clientId); if (!clientId) { setClientPlans([]); return; }
    return run('client-plans', async () => { const payload = await request(`/coach/clients/${clientId}/plans`); setClientPlans(payload.plans ?? []); });
  }

  return (
    <section id="product-layer" className="phase4-shell">
      <header className="phase4-header">
        <div><span>Your Guiltless workspace</span><h2>Your plans, preferences, and bag</h2><p>Keep your preferences, save your plans, and pick up where you left off.</p></div>
        <strong>demo-user</strong>
      </header>
      <nav className="phase4-tabs" aria-label="Saved product areas">
        {([['profile','Profile / Memory'],['bag','Persistent Bag'],['plans','Saved Plans'],['clients','Trainer Clients']] as [Tab,string][]).map(([value,label]) => <button key={value} className={tab === value ? 'active' : ''} onClick={() => setTab(value)}>{label}</button>)}
      </nav>
      {loading && <div className="phase4-alert">Loading saved product state…</div>}
      {(notice || error) && <div className={error ? 'phase4-alert error' : 'phase4-alert'}>{error ?? notice}</div>}

      {tab === 'profile' && <div className="phase4-panel"><div className="phase4-panel-heading"><span>Shared memory</span><h3>Profile / Memory</h3><p>Preferences become reusable context for meal, workout, bag, and Copilot actions.</p></div><div className="phase4-form-grid">
        <label>Goal<input value={profile.goal} onChange={(e) => setProfile({ ...profile, goal: e.target.value })} /></label><label>Diet<input value={profile.diet} onChange={(e) => setProfile({ ...profile, diet: e.target.value })} /></label>
        <label>Allergies<input value={profile.allergies} onChange={(e) => setProfile({ ...profile, allergies: e.target.value })} placeholder="comma separated" /></label><label>Calorie target<input type="number" min={800} max={6000} step={50} value={profile.calorie_target} onChange={(e) => setProfile({ ...profile, calorie_target: Number(e.target.value) })} /></label>
        <label>Training days<input type="number" min={1} max={7} value={profile.training_days} onChange={(e) => setProfile({ ...profile, training_days: Number(e.target.value) })} /></label><label>Preferred store<input value={profile.preferred_store} onChange={(e) => setProfile({ ...profile, preferred_store: e.target.value })} /></label>
      </div><button className="phase4-primary" onClick={saveProfile} disabled={busy === 'profile'}>{busy === 'profile' ? 'Saving memory…' : 'Save profile memory'}</button></div>}

      {tab === 'bag' && <div className="phase4-panel"><div className="phase4-panel-heading"><span>Persistent commerce context</span><h3>Saved Bag</h3><p>Bag contents survive refreshes and feed optimization and checkout actions.</p></div><div className="phase4-actions"><button onClick={addDemoItem}>Add demo item</button><button onClick={optimizeSavedBag}>Optimize bag</button><button onClick={checkoutInstacart}>Checkout with Instacart mock</button><button className="danger" onClick={clearSavedBag}>Clear bag</button></div><div className="phase4-card-grid">{bag.length ? bag.map((item) => <article key={item.id}><span>{item.quantity}×</span><strong>{item.product?.name}</strong><small>{item.product?.brand}</small></article>) : <div className="phase4-empty">No saved bag items yet.</div>}</div>{bagOptimization && <div className="phase4-result"><strong>Optimized score: {bagOptimization.projected_score}</strong><span>Gain +{bagOptimization.score_gain}</span></div>}{checkout && <div className="phase4-result checkout"><strong>{checkout.checkout_provider} · {checkout.status}</strong><span>{checkout.items?.length ?? 0} items ready</span><a href={checkout.checkout_url}>Open mock checkout ↗</a></div>}</div>}

      {tab === 'plans' && <div className="phase4-panel"><div className="phase4-panel-heading"><span>Reusable plans</span><h3>Saved Plans</h3><p>Save the latest generated plan and reopen it across sessions.</p></div><div className="phase4-actions"><button onClick={() => savePlan('meal', latestMealPlan)}>Save latest meal plan</button><button onClick={() => savePlan('workout', latestWorkoutPlan)}>Save latest workout plan</button></div><div className="saved-plan-columns"><PlanList title="Meal plans" items={plans.meal_plans ?? []} /><PlanList title="Workout plans" items={plans.workout_plans ?? []} /></div></div>}

      {tab === 'clients' && <div className="phase4-panel"><div className="phase4-panel-heading"><span>B2B memory</span><h3>Trainer Clients</h3><p>Create clients and inspect their saved plan history.</p></div><div className="client-create"><input value={newClientName} onChange={(e) => setNewClientName(e.target.value)} /><button onClick={createClient}>Create client</button></div><div className="trainer-client-layout"><div className="client-list">{clients.map((client) => <button key={client.id} className={selectedClient === client.id ? 'active' : ''} onClick={() => viewClientPlans(client.id)}><strong>{client.client_name}</strong><small>{client.goal} · {client.days_per_week} days</small></button>)}</div><PlanList title="Client plan history" items={clientPlans} /></div></div>}
    </section>
  );
}

function PlanList({ title, items }: { title: string; items: JsonObject[] }) {
  return <div className="plan-list"><h4>{title}</h4>{items.length ? items.map((item) => <article key={item.id}><strong>{item.plan?.summary ?? item.plan?.goal ?? 'Saved plan'}</strong><small>{item.created_at ? new Date(item.created_at).toLocaleDateString() : 'Saved now'}</small></article>) : <div className="phase4-empty">Nothing saved yet.</div>}</div>;
}
