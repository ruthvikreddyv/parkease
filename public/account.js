const form = document.querySelector('form');
const notice = document.querySelector('#notice');
const password = document.querySelector('#password');
const toggle = document.querySelector('#toggle');
const submit = form.querySelector('[type="submit"]');

toggle.addEventListener('click', () => {
  const show = password.type === 'password';
  password.type = show ? 'text' : 'password';
  toggle.textContent = show ? 'Hide' : 'Show';
  toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submit.disabled) return;
  submit.disabled = true;
  form.setAttribute('aria-busy', 'true');
  notice.textContent = '';
  try {
    const response = await fetch('/api/' + form.dataset.mode, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.fromEntries(new FormData(form)))
    });
    const data = await response.json();
    if (!response.ok) {
      notice.textContent = data.error || 'Account service is unavailable. Please try again.';
      return;
    }
    location.assign('/#live');
  } catch {
    notice.textContent = 'Could not reach ParkEase. Check your connection and try again.';
  } finally {
    submit.disabled = false;
    form.removeAttribute('aria-busy');
  }
});
