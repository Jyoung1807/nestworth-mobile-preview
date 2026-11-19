// Presentation only: no financial values, credentials, storage, or server events.
export default function({ data }) {
  const update = () => {
    const viewport = window.visualViewport;
    const active = document.activeElement;
    const editing = active && ['TEXTAREA', 'INPUT'].includes(active.tagName) && !['checkbox', 'radio'].includes(active.type);
    const narrow = window.matchMedia('(max-width:768px)').matches;
    const keyboard = narrow && editing && ((viewport && window.innerHeight - viewport.height > 140) || window.innerHeight < 450);
    document.documentElement.classList.toggle('budget-keyboard-open', !!keyboard);
  };
  window.visualViewport?.addEventListener('resize', update);
  window.addEventListener('resize', update);
  document.addEventListener('focusin', update);
  document.addEventListener('focusout', update);
  update();
  const key = '__householdBudgetPresentation';
  if (window[key]?.route !== data.route) {
    window[key] = {route: data.route};
    requestAnimationFrame(() => document.querySelector('[data-testid="stMain"]')?.scrollTo({top: 0, left: 0, behavior: 'instant'}));
  }
  return () => {
    window.visualViewport?.removeEventListener('resize', update);
    window.removeEventListener('resize', update);
    document.removeEventListener('focusin', update);
    document.removeEventListener('focusout', update);
  };
}
