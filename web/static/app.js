async function generate() {
  const prompt = document.getElementById('prompt').value.trim();
  const engine = document.getElementById('engine').value;
  const aspect = document.getElementById('aspect').value;
  const btn = document.getElementById('generate');
  const status = document.getElementById('status');
  const stages = document.getElementById('stages');
  if (!prompt) { alert('Enter a prompt first.'); return; }
  btn.disabled = true;
  status.classList.remove('hidden');
  stages.classList.add('hidden'); stages.innerHTML = '';
  status.textContent = '⏳ Running the 6-stage pipeline…';

  const res = await fetch('/api/generate', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({prompt, engine, aspect})
  });
  const {job_id, error} = await res.json();
  if (error) { status.textContent = '❌ ' + error; btn.disabled = false; return; }

  const poll = setInterval(async () => {
    const r = await fetch('/api/jobs/' + job_id);
    const job = await r.json();
    if (!job.done) return;
    clearInterval(poll);
    btn.disabled = false;
    const rec = job.record;
    if (job.error) { status.textContent = '❌ ' + job.error; return; }
    status.innerHTML = `Finished: <b>${rec.status}</b>` +
      (rec.file ? ` — <a href="/outputs/${rec.file}" target="_blank">view image</a>` : '') +
      (rec.polite_message ? `<br>ℹ️ ${rec.polite_message}` : '') +
      (rec.error ? `<br>⚠️ ${rec.error}` : '');
    stages.classList.remove('hidden');
    stages.innerHTML = rec.stages.map(s =>
      `<div class="st ${s.status}"><b>${s.stage}</b> — ${s.status}<br><span>${s.detail}</span></div>`
    ).join('');
    loadAssets();
  }, 1500);
}

async function loadAssets() {
  const r = await fetch('/api/assets');
  const assets = await r.json();
  const g = document.getElementById('gallery');
  if (!assets.length) { g.innerHTML = '<p style="color:#9aa7bd">No generations yet.</p>'; return; }
  g.innerHTML = assets.map(a => `
    <div class="card">
      ${a.file ? `<a href="/outputs/${a.file}" target="_blank"><img src="/outputs/${a.file}" loading="lazy"></a>` : ''}
      <div class="meta">
        <span class="badge ${a.status}">${a.status}</span><br><br>
        <b>${(a.prompt || '').slice(0, 70)}</b><br>
        ${a.engine} · ${a.aspect || ''}${a.width ? ` · ${a.width}×${a.height}` : ''}<br>
        ${a.qa ? `aesthetic ${a.qa.aesthetic.score}/10 · semantic ${a.qa.semantic.score}` : ''}
      </div>
    </div>`).join('');
}
loadAssets();
