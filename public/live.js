const el = id => document.getElementById(id);
let state;
let pending = false;
let generation = 0;
function draw() {
  const bays = state.snapshot.bays || [];
  const selected = el('live-bay').value;
  const free = bays.filter(b => !b.occupied && !state.holds.includes(b.id));
  const [ex,ey] = state.snapshot.entrance || [0,0];
  function distance(bay) {
    const [x,y] = bay.points.reduce(([x,y],[px,py])=>[x+px/4,y+py/4],[0,0]);
    return Math.hypot((x-ex)*state.snapshot.aspect, y-ey);
  }
  const closest = [...free].sort((a,b)=>distance(a)-distance(b))[0];
  el('feed').textContent = state.fresh ? 'Live' : 'Offline';
  el('live-message').textContent = state.fresh ? free.length+' of '+bays.length+' bays available.'+(closest?' Nearest: '+closest.id+'.':'') :
    'Waiting for current CCTV observations. Reservations are paused.';
  const select = el('live-bay');
  select.replaceChildren(...free.map(b=>new Option(b.id,b.id)));
  select.value = free.some(b=>b.id===selected) ? selected : closest?.id || '';
  select.disabled = !state.fresh || !free.length;
  el('book').disabled = pending || !state.fresh || !free.length || !!state.mine;
  el('book').textContent = state.username ? 'Reserve selected bay' : 'Log in to reserve';
  el('driver').textContent = state.username ? 'Driver: '+state.username : 'Log in to book';
  el('logout').hidden = !state.username;
  el('reservation').hidden = !state.mine;
  if (state.mine) el('my-hold').textContent = 'Bay '+state.mine.bay+' reserved until '+new Date(state.mine.expires*1000).toLocaleTimeString()+'.';
  const map = el('live-map');
  map.replaceChildren();
  if (!bays.length) return;
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 1000 '+(1000/state.snapshot.aspect));
  for (const b of bays) {
    const points=b.points.map(([x,y])=>[1000*x,1000*y/state.snapshot.aspect]);
    const polygon=document.createElementNS(ns,'polygon');
    polygon.setAttribute('points',points.map(p=>p.join(',')).join(' '));
    const status=b.occupied?'occupied':state.holds.includes(b.id)?'reserved':'available';
    polygon.setAttribute('class',status);
    const text=document.createElementNS(ns,'text');
    text.setAttribute('x',points.reduce((s,p)=>s+p[0],0)/4);
    text.setAttribute('y',points.reduce((s,p)=>s+p[1],0)/4);
    text.textContent=b.id;
    const title=document.createElementNS(ns,'title');title.textContent=b.id+' · '+status;
    polygon.append(title);
    if(status==='available') polygon.onclick=()=>{select.value=b.id;select.focus();};
    svg.append(polygon,text);
  }
  map.append(svg);
}
async function refresh() {
  const id=++generation;
  try {
    const res=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(6000)});
    if(!res.ok) throw new Error();
    const data=await res.json();
    if(id!==generation)return;
    state=data; draw();
  } catch {
    if(id!==generation)return;
    el('book').disabled=true; el('feed').textContent='Offline';
    el('live-message').textContent='Connection unavailable. Booking is paused.';
  }
}
async function act(action,data) {
  pending=true;el('book').disabled=true;
  try {
    const res=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    if(res.status===401){location.assign('/login/');return;}
    const result=await res.json();
    if(!res.ok)throw new Error(result.error);
    el('booking-message').textContent={book:'Reservation confirmed.',cancel:'Reservation cancelled.',logout:'Logged out.'}[action];
  } catch (error){el('booking-message').textContent=error.message||'Request failed.';}
  finally {pending=false;await refresh();}
}
el('book').onclick=()=>state?.username ? act('book',{bay:el('live-bay').value,revision:state.snapshot.revision}) : location.assign('/login/');
el('cancel-hold').onclick=()=>act('cancel',{});
el('logout').onclick=()=>act('logout',{});
async function poll(){await refresh();setTimeout(poll,5000);}
poll();
