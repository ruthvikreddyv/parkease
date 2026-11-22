const form = document.querySelector('form');
const notice = document.querySelector('#notice');
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/api/' + form.dataset.mode, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(Object.fromEntries(new FormData(form)))
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Account request failed.');
    location.assign('/#live');
  } catch (error) {
    notice.textContent = error instanceof SyntaxError ? 'Account service is unavailable.' : error.message;
  } finally { button.disabled = false; }
});
