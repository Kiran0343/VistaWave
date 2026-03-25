const navToggle = document.querySelector('.nav-toggle');
const nav = document.querySelector('.primary-nav');

if (navToggle && nav) {
  navToggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });

  nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      nav.classList.remove('is-open');
      navToggle.setAttribute('aria-expanded', 'false');
    });
  });
}

const revealElements = document.querySelectorAll('.reveal');

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.18 }
);

revealElements.forEach((element, index) => {
  element.style.transitionDelay = `${Math.min(index * 40, 220)}ms`;
  revealObserver.observe(element);
});

const counters = document.querySelectorAll('[data-counter]');

const runCounter = (counter) => {
  const target = Number(counter.dataset.counter || 0);
  let current = 0;
  const duration = 1000;
  const increment = Math.max(1, Math.round(target / (duration / 20)));

  const timer = window.setInterval(() => {
    current += increment;
    if (current >= target) {
      counter.textContent = String(target);
      window.clearInterval(timer);
      return;
    }
    counter.textContent = String(current);
  }, 20);
};

const counterObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        runCounter(entry.target);
        counterObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.45 }
);

counters.forEach((counter) => counterObserver.observe(counter));
