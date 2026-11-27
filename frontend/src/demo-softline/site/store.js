const chat = document.querySelector('#sl-chat');
const launcher = chat.querySelector('.slc-launcher');
const input = chat.querySelector('input[aria-label="Сообщение"]');
const panel = chat.querySelector('.slc-panel');
const header = panel.querySelector('.slc-head');
const handle = document.createElement('button');
handle.type = 'button';
handle.dataset.moveChat = '';
handle.textContent = '⠿';
handle.title = 'Перетащите окно или используйте клавиши со стрелками';
handle.setAttribute('aria-label', 'Переместить окно чата');
header.insertBefore(handle, header.querySelector('[data-act="menu"]'));

function openStoreChat(prompt = '') {
  if (!chat.classList.contains('is-open')) launcher.click();
  if (prompt && !input.value.trim()) {
    input.value = prompt;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
  input.focus({ preventScroll: true });
}

document.querySelectorAll('[data-open-chat]').forEach(button => {
  button.addEventListener('click', () => openStoreChat(button.dataset.openChat));
});
const searchForm = document.querySelector('.product-search');
searchForm.addEventListener('submit', event => {
  event.preventDefault();
  const product = searchForm.elements.product.value.trim();
  if (product) openStoreChat(`Нужна цена на ${product}`);
});

let drag;
function positionPanel(x, y) {
  const padding = 8;
  const maxX = Math.max(padding, document.documentElement.clientWidth - panel.offsetWidth - padding);
  const maxY = Math.max(padding, window.innerHeight - panel.offsetHeight - padding);
  panel.style.left = `${Math.min(maxX, Math.max(padding, x))}px`;
  panel.style.top = `${Math.min(maxY, Math.max(padding, y))}px`;
  panel.style.right = 'auto';
  panel.style.bottom = 'auto';
}

header.addEventListener('pointerdown', event => {
  const control = event.target.closest('button, a');
  if (drag || event.button !== 0 || (control && control !== handle)) return;
  const { left, top } = panel.getBoundingClientRect();
  drag = { id: event.pointerId, x: event.clientX - left, y: event.clientY - top };
  header.setPointerCapture(event.pointerId);
  panel.classList.add('is-moving');
});
header.addEventListener('pointermove', event => {
  if (drag?.id === event.pointerId) positionPanel(event.clientX - drag.x, event.clientY - drag.y);
});
function stopDragging(event) {
  if (drag?.id !== event.pointerId) return;
  drag = undefined;
  panel.classList.remove('is-moving');
}
header.addEventListener('pointerup', stopDragging);
header.addEventListener('pointercancel', stopDragging);
header.addEventListener('lostpointercapture', stopDragging);
handle.addEventListener('keydown', event => {
  const delta = { ArrowLeft: [-24, 0], ArrowRight: [24, 0], ArrowUp: [0, -24], ArrowDown: [0, 24] }[event.key];
  if (!delta) return;
  event.preventDefault();
  const { left, top } = panel.getBoundingClientRect();
  positionPanel(left + delta[0], top + delta[1]);
});
window.addEventListener('resize', () => {
  if (panel.style.left) positionPanel(parseFloat(panel.style.left), parseFloat(panel.style.top));
});
