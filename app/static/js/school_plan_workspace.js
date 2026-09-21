(function () {
  function initializeSchoolPlanMenu() {
    var sidebar = document.getElementById('schoolPlanSidebar');
    var overlay = document.getElementById('schoolPlanSidebarOverlay');
    var openButton = document.getElementById('schoolPlanMenuButton');
    var closeButton = document.getElementById('schoolPlanMenuClose');

    if (!sidebar || !overlay || !openButton) return;

    function setMenuOpen(opened) {
      sidebar.classList.toggle('is-open', opened);
      overlay.classList.toggle('is-open', opened);
      document.body.classList.toggle('sp-sidebar-open', opened);
      openButton.setAttribute('aria-expanded', opened ? 'true' : 'false');
      if (opened && closeButton) closeButton.focus();
      if (!opened && document.activeElement === closeButton) openButton.focus();
    }

    openButton.addEventListener('click', function () {
      setMenuOpen(!sidebar.classList.contains('is-open'));
    });
    overlay.addEventListener('click', function () { setMenuOpen(false); });
    if (closeButton) closeButton.addEventListener('click', function () { setMenuOpen(false); });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && sidebar.classList.contains('is-open')) setMenuOpen(false);
    });
    window.addEventListener('resize', function () {
      if (window.innerWidth >= 992) setMenuOpen(false);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSchoolPlanMenu);
  } else {
    initializeSchoolPlanMenu();
  }
})();
