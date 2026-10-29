document.addEventListener('DOMContentLoaded', () => {
  const workspace = document.getElementById('workspaceShell');
  const content = workspace?.querySelector('.sp-content');
  const topbarTitle = workspace?.querySelector('.sp-topbar-context [role="heading"]');
  if (!content || !topbarTitle) return;

  const heading = [...content.querySelectorAll('h1, .page-head .page-title')]
    .find((item) => !item.closest('.modal, dialog, [aria-hidden="true"]') && item.textContent.trim());
  if (!heading) return;

  topbarTitle.textContent = heading.textContent.trim().replace(/\s+/g, ' ');
  heading.classList.add('ws-heading-promoted');

  const header = heading.closest('.page-head, .classic-page-header, .sp-page-head, .classroom-group-header, .ws-page-head');
  if (!header) return;

  const homeHref = workspace.querySelector('.sp-topbar-home')?.href;
  const duplicateHomeLinks = [...header.querySelectorAll('a[href]')]
    .filter((link) => link.href === homeHref && /^(на главную|главная)$/i.test(link.textContent.trim()));
  duplicateHomeLinks.forEach((link) => {
    link.hidden = true;
    link.style.setProperty('display', 'none', 'important');
  });

  const breadcrumb = header.querySelector('nav.small, nav[aria-label="breadcrumb"]');
  if (breadcrumb && workspace.querySelector('.sp-topbar-back')) breadcrumb.hidden = true;

  let remainingText = [...header.childNodes]
    .map((node) => node.textContent || '')
    .join('')
    .replace(heading.textContent, '')
    .replace(breadcrumb?.textContent || '', '')
    .trim();
  duplicateHomeLinks.forEach((link) => {
    remainingText = remainingText.replace(link.textContent, '').trim();
  });
  const hasActions = [...header.querySelectorAll('a, button, input, select, textarea')]
    .some((item) => !item.hidden && !item.closest('nav[hidden]'));
  if (!remainingText && !hasActions) {
    header.hidden = true;
  } else {
    header.classList.add('ws-page-head-compact');
  }
});
