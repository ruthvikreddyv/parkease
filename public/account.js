const form = document.querySelector('form');
const notice = document.querySelector('#notice');
const password = document.querySelector('#password');
const toggle = document.querySelector('#toggle');
const submit = form.querySelector('[type="submit"]');

const confirmation = form.elements.confirm_password;
function validateSignup() {
  if (!confirmation) return;
  const {full_name, contact} = form.elements;
  full_name.setCustomValidity(full_name.value.trim() ? '' : 'Enter your full name.');
  const digits = contact.value.replace(/[ ()-]/g, '');
  contact.setCustomValidity(/^\+?[0-9]{7,15}$/.test(digits) ? '' : 'Enter a contact number with 7–15 digits.');
  confirmation.setCustomValidity(confirmation.value === password.value ? '' : 'Passwords do not match.');
}
form.addEventListener('input', validateSignup);

toggle.addEventListener('click', () => {
  const show = password.type === 'password';
  password.type = show ? 'text' : 'password';
  toggle.textContent = show ? 'Hide' : 'Show';
  toggle.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (submit.disabled) return;
  validateSignup();
  if (!form.reportValidity()) return;
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
