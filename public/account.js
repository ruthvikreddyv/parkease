const start = document.getElementById('start');
const active = document.getElementById('active');
function show(signedIn) {
  start.hidden = signedIn;
  active.hidden = !signedIn;
}
try { show(sessionStorage.getItem('pe-driver') === 'demo'); } catch { show(false); }
document.getElementById('enter').onclick = () => {
  try { sessionStorage.setItem('pe-driver', 'demo'); } catch {}
  show(true);
  active.querySelector('a').focus();
};
document.getElementById('exit').onclick = () => {
  try { sessionStorage.removeItem('pe-driver'); } catch {}
  show(false);
  document.getElementById('enter').focus();
};
