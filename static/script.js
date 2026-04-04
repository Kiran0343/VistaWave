const navToggle = document.querySelector('.nav-toggle');
const nav = document.querySelector('.primary-nav');

if (navToggle && nav) {
  navToggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });

  document.addEventListener('click', (event) => {
    if (!nav.classList.contains('is-open')) return;
    if (nav.contains(event.target) || navToggle.contains(event.target)) return;
    nav.classList.remove('is-open');
    navToggle.setAttribute('aria-expanded', 'false');
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    nav.classList.remove('is-open');
    navToggle.setAttribute('aria-expanded', 'false');
  });

  nav.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      nav.classList.remove('is-open');
      navToggle.setAttribute('aria-expanded', 'false');
    });
  });
}

const scrollTopButton = document.createElement('button');
scrollTopButton.className = 'scroll-top-btn';
scrollTopButton.type = 'button';
scrollTopButton.setAttribute('aria-label', 'Scroll to top');
scrollTopButton.textContent = '↑';
document.body.appendChild(scrollTopButton);

const toggleScrollTopButton = () => {
  if (window.scrollY > 240) {
    scrollTopButton.classList.add('is-visible');
    return;
  }
  scrollTopButton.classList.remove('is-visible');
};

window.addEventListener('scroll', toggleScrollTopButton, { passive: true });
toggleScrollTopButton();

scrollTopButton.addEventListener('click', () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

const revealElements = document.querySelectorAll('.reveal');

if (!('IntersectionObserver' in window)) {
  revealElements.forEach((element) => element.classList.add('visible'));
} else {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          revealObserver.unobserve(entry.target);
        }
      });
    },
    {
      threshold: 0.05,
      rootMargin: '0px 0px -8% 0px',
    }
  );

  revealElements.forEach((element, index) => {
    element.style.transitionDelay = `${Math.min(index * 20, 120)}ms`;
    revealObserver.observe(element);
  });
}

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

const metricEls = {
  fillRate: document.getElementById('metric-fill-rate'),
  submissionDays: document.getElementById('metric-submission-days'),
  qualifiedCandidates: document.getElementById('metric-qualified-candidates'),
  activeReqs: document.getElementById('metric-active-reqs'),
};

const recommendationList = document.getElementById('recommendation-list');
const talentPoolGrid = document.getElementById('talent-pool-grid');
const jobsGrid = document.getElementById('jobs-grid');
const apiStatusText = document.getElementById('api-status-text');
const contactForm = document.getElementById('contact-form');
const contactStatus = document.getElementById('contact-status');
const applyForm = document.getElementById('apply-form');
const applyStatus = document.getElementById('apply-status');
const applyPosition = document.getElementById('apply-position');
const apiBaseUrl = (document.body?.dataset.apiBaseUrl || '').replace(/\/$/, '');
const thankYouAssessmentUrl = '/thank-you/assessment';
const thankYouApplicationUrl = '/thank-you/application';

const getApiUrl = (path) => (apiBaseUrl ? `${apiBaseUrl}${path}` : path);

const readErrorMessage = async (response, fallbackMessage) => {
  try {
    const data = await response.json();
    if (typeof data?.message === 'string' && data.message.trim()) {
      return data.message;
    }
  } catch (error) {
    // Keep fallback below.
  }
  return fallbackMessage;
};

const setMetricValue = (el, value, formatter = (v) => String(v)) => {
  if (!el) return;
  el.textContent = formatter(value);
};

const renderMetrics = (payload) => {
  setMetricValue(metricEls.fillRate, payload.fill_rate);
  setMetricValue(metricEls.submissionDays, payload.submission_to_interview_days, (v) => Number(v).toFixed(1));
  setMetricValue(metricEls.qualifiedCandidates, payload.qualified_candidates);
  setMetricValue(metricEls.activeReqs, payload.active_client_requisitions);

  if (recommendationList && Array.isArray(payload.recommendations)) {
    recommendationList.innerHTML = payload.recommendations
      .map((item) => `<li>${item}</li>`)
      .join('');
  }
};

const renderTalentPool = (payload) => {
  if (!talentPoolGrid || !Array.isArray(payload.categories)) return;

  talentPoolGrid.innerHTML = payload.categories
    .map(
      (item) => `
      <article class="talent-card reveal visible">
        <h3>${item.technology}</h3>
        <p><strong>${item.available}</strong> consultants</p>
        <p>${item.avg_experience_years}+ yrs avg experience</p>
      </article>`
    )
    .join('');
};

const renderJobs = (jobs) => {
  if (!jobsGrid || !Array.isArray(jobs)) return;

  jobsGrid.innerHTML = jobs
    .map(
      (job) => `
      <article class="job-card reveal visible">
        <div class="job-header">
          <h3>${job.title}</h3>
          <span class="job-type">${job.type}</span>
        </div>
        <p class="job-company">${job.company}</p>
        <p class="job-location">${job.location}</p>
        <p class="job-description">${job.description}</p>
        <div class="job-meta">
          <span class="job-exp">Exp: ${job.experience_required}</span>
          <span class="job-salary">${job.salary_range}</span>
        </div>
        <div class="job-skills">
          ${job.skills.map((s) => `<span class="skill-tag">${s}</span>`).join('')}
        </div>
        <button class="btn btn-small apply-job" data-job-id="${job.id}" data-job-title="${job.title}">
          Apply Now
        </button>
      </article>`
    )
    .join('');

  document.querySelectorAll('.apply-job').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const jobTitle = e.target.dataset.jobTitle;
      if (applyPosition) applyPosition.value = jobTitle;
      document.querySelector('#apply').scrollIntoView({ behavior: 'smooth' });
      if (applyStatus) applyStatus.textContent = `Applying for: ${jobTitle}`;
    });
  });
};

const loadStatus = async () => {
  if (!apiStatusText) return;

  try {
    const response = await fetch(getApiUrl('/api/v1/status'), { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Status unavailable');
    const data = await response.json();
    apiStatusText.textContent = `Online · ${data.version} · ${new Date(data.timestamp).toLocaleTimeString()}`;
  } catch (error) {
    apiStatusText.textContent = 'Degraded';
  }
};

const loadMetrics = async () => {
  try {
    const response = await fetch(getApiUrl('/api/v1/metrics'), { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Metrics unavailable');
    const data = await response.json();
    renderMetrics(data);
  } catch (error) {
    // Keep silent: realtime stream or later polls can recover.
  }
};

const loadTalentPool = async () => {
  try {
    const response = await fetch(getApiUrl('/api/v1/talent-pool'), { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Talent pool unavailable');
    const data = await response.json();
    renderTalentPool(data);
  } catch (error) {
    // Keep silent and retry in periodic refresh.
  }
};

const loadJobs = async () => {
  try {
    const response = await fetch(getApiUrl('/api/v1/jobs'), { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Jobs unavailable');
    const data = await response.json();
    renderJobs(data.jobs);
  } catch (error) {
    // Keep silent and retry in periodic refresh.
  }
};

const connectLiveMetrics = () => {
  if (!window.EventSource) {
    window.setInterval(loadMetrics, 12000);
    return;
  }

  const eventSource = new EventSource(getApiUrl('/api/v1/events'));
  eventSource.addEventListener('metrics', (event) => {
    try {
      const payload = JSON.parse(event.data);
      renderMetrics(payload);
    } catch (error) {
      // Ignore malformed event payloads.
    }
  });

  eventSource.addEventListener('error', () => {
    eventSource.close();
    window.setTimeout(connectLiveMetrics, 3000);
  });
};

if (contactForm) {
  contactForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(contactForm);
    const payload = {
      name: String(formData.get('name') || '').trim(),
      work_email: String(formData.get('work_email') || '').trim(),
      company: String(formData.get('company') || '').trim(),
      area_of_interest: String(formData.get('area_of_interest') || '').trim(),
      technologies_involved: String(formData.get('technologies_involved') || '').trim(),
      engagement_type: String(formData.get('engagement_type') || '').trim(),
      team_size: String(formData.get('team_size') || '').trim(),
      desired_timeline: String(formData.get('desired_timeline') || '').trim(),
      project_goals: String(formData.get('project_goals') || '').trim(),
    };

    if (!payload.technologies_involved) {
      if (contactStatus) {
        contactStatus.textContent = 'Please provide the technologies involved.';
        contactStatus.classList.add('is-error');
      }
      return;
    }

    if (contactStatus) {
      contactStatus.textContent = 'Submitting staffing request...';
      contactStatus.classList.remove('is-error', 'is-success');
    }

    try {
      const response = await fetch(getApiUrl('/api/v1/staffing-request'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'Failed to submit assessment request'));
      }

      if (contactStatus) {
        contactStatus.textContent = 'Request submitted. We will reach out within 24 hours.';
        contactStatus.classList.add('is-success');
      }
      contactForm.reset();
      loadMetrics();
      window.setTimeout(() => {
        window.location.assign(thankYouAssessmentUrl);
      }, 500);
    } catch (error) {
      if (contactStatus) {
        contactStatus.textContent = error.message || 'Unable to submit request right now.';
        contactStatus.classList.add('is-error');
      }
    }
  });
}

if (applyForm) {
  applyForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const formData = new FormData(applyForm);
    const resumeFile = formData.get('resume');

    if (!(resumeFile instanceof File) || !resumeFile.name) {
      if (applyStatus) {
        applyStatus.textContent = 'Please attach your resume PDF.';
        applyStatus.classList.add('is-error');
      }
      return;
    }

    if (!resumeFile.name.toLowerCase().endsWith('.pdf')) {
      if (applyStatus) {
        applyStatus.textContent = 'Resume must be uploaded as a PDF.';
        applyStatus.classList.add('is-error');
      }
      return;
    }

    if (applyStatus) {
      applyStatus.textContent = 'Submitting application...';
      applyStatus.classList.remove('is-error', 'is-success');
    }

    try {
      const response = await fetch(getApiUrl('/api/v1/apply'), {
        method: 'POST',
        headers: {
          Accept: 'application/json',
        },
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response, 'Failed to submit application'));
      }

      if (applyStatus) {
        applyStatus.textContent = 'Application submitted. Our team will review it shortly.';
        applyStatus.classList.add('is-success');
      }
      applyForm.reset();
      window.setTimeout(() => {
        window.location.assign(thankYouApplicationUrl);
      }, 500);
    } catch (error) {
      if (applyStatus) {
        applyStatus.textContent = error.message || 'Unable to submit application right now.';
        applyStatus.classList.add('is-error');
      }
    }
  });
}

loadStatus();
loadMetrics();
loadTalentPool();
loadJobs();
connectLiveMetrics();
window.setInterval(loadStatus, 30000);
window.setInterval(loadTalentPool, 40000);
window.setInterval(loadJobs, 45000);
