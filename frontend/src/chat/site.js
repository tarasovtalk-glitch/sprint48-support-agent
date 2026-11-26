/* Поведение сайта, которое в копии повторяем без их скриптов: средняя строка шапки (каталог, поиск, корзина)
   закрепляется сверху, когда верхняя строка уходит за край экрана. Логика та же, что в скрипте сайта. */
(function () {
  if (window.matchMedia('(max-width: 768px)').matches) return;
  var top = document.querySelector('.b-store-header__top');
  var mid = document.querySelector('.b-store-header__middle');
  if (!top || !mid || !('IntersectionObserver' in window)) return;
  var hidden = document.querySelectorAll('.b-store-header__bottom-item[data-hide]');
  new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) {
      mid.classList.remove('fixed'); top.style.marginBottom = '0';
      hidden.forEach(function (h) { h.style.display = ''; });
    } else {
      mid.classList.add('fixed'); top.style.marginBottom = mid.clientHeight + 'px';
      hidden.forEach(function (h) { h.style.display = 'none'; });
    }
  }, { root: null, threshold: 0, rootMargin: '0px 0px -100% 0px' }).observe(top);
})();
