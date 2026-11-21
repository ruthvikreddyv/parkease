const byId = id => document.getElementById(id);
async function start() {
  const response = await fetch('/snapshot.json');
  if (!response.ok) throw new Error('Snapshot unavailable');
  const { entrance, bays } = await response.json();
  const original = bays.map(bay => bay.occupied);
  const distance = bay => Math.hypot(bay.center[0] - entrance[0], bay.center[1] - entrance[1]);
  const nearest = () => bays.filter(bay => !bay.occupied).sort((a, b) => distance(a) - distance(b))[0];
  let selected = nearest() || bays[0];
  function bayButton(bay, map, closest) {
    const button = document.createElement('button');
    const state = bay.occupied ? 'Occupied' : 'Available';
    button.className = map ? 'bay' : 'result';
    button.dataset.state = bay.occupied ? 'occupied' : 'available';
    button.dataset.nearest = String(bay === closest);
    button.textContent = map ? bay.label : bay.label + ' · ' + state;
    button.setAttribute('aria-label', bay.label + ', ' + state);
    button.setAttribute('aria-pressed', String(selected === bay));
    button.onclick = () => { selected = bay; render(); byId('toggle').focus(); };
    return button;
  }
  function render() {
    const closest = nearest();
    const free = bays.filter(bay => !bay.occupied).length;
    byId('total').textContent = bays.length;
    byId('free').textContent = free;
    byId('busy').textContent = bays.length - free;
    byId('near').textContent = closest?.label || 'Full';
    byId('mode').textContent = bays.some((bay,i) => bay.occupied !== original[i]) ? 'Simulated occupancy' : 'Saved snapshot';
    for (const row of ['A','B']) {
      byId('row' + row).replaceChildren(...bays.filter(bay => bay.label.startsWith(row)).map(bay => bayButton(bay, true, closest)));
    }
    const query = byId('search').value.trim().toLowerCase();
    const matches = bays.filter(bay => (bay.label + ' ' + (bay.occupied ? 'occupied' : 'available')).toLowerCase().includes(query));
    byId('results').replaceChildren(...matches.map(bay => bayButton(bay, false, closest)));
    if (!matches.length) byId('results').textContent = 'No matching bays.';
    byId('selection').textContent = 'Bay ' + selected.label;
    byId('status').textContent = selected.occupied ? 'Occupied' : selected === closest ? 'Available · Nearest to entrance' : 'Available';
    byId('toggle').disabled = false;
    byId('toggle').textContent = selected.occupied ? 'Simulate departure' : 'Simulate arrival';
  }
  byId('toggle').onclick = () => { selected.occupied = !selected.occupied; render(); };
  byId('reset').onclick = () => { bays.forEach((bay,i) => bay.occupied = original[i]); selected = nearest() || bays[0]; byId('search').value = ''; render(); };
  byId('search').oninput = render;
  render();
}
start().catch(() => document.getElementById('status').textContent = 'Could not load the parking snapshot. Reload to retry.');
