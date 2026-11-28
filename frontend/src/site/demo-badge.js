(function () {
  var badge = document.getElementById('prototype-badge');
  var close = badge.querySelector('.prototype-badge__close');
  var launcher = document.querySelector('.prototype-badge__launcher');
  var menu = document.querySelector('.prototype-badge__menu');

  function showBadge(visible) {
    badge.hidden = !visible;
    launcher.textContent = visible ? 'Метка' : 'Демо';
    launcher.setAttribute('aria-expanded', String(visible));
    launcher.setAttribute('aria-label', visible ? 'Скрыть бейджик демо' : 'Показать бейджик демо');
    menu.textContent = visible ? 'Скрыть бейджик демо' : 'Показать бейджик демо';
    menu.setAttribute('aria-expanded', String(visible));
  }

  function toggleBadge() {
    showBadge(badge.hidden);
  }

  close.addEventListener('click', function () {
    showBadge(false);
    launcher.focus();
  });
  launcher.addEventListener('click', toggleBadge);
  menu.addEventListener('click', toggleBadge);
})();
