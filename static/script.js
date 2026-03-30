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
const applyJobId = document.getElementById('apply-job-id');

const submitToFormspree = async (endpoint, payload, extraMeta = {}) => {
  const formData = new FormData();
  Object.entries(payload).forEach(([key, value]) => {
    if (Array.isArray(value)) {
      formData.append(key, value.join(', '));
      return;
    }
    formData.append(key, String(value ?? ''));
  });

  Object.entries(extraMeta).forEach(([key, value]) => {
    formData.append(key, String(value));
  });

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body: formData,
  });

  if (!response.ok) {
    let message = 'Form submission failed';
    try {
      const data = await response.json();
      if (Array.isArray(data.errors) && data.errors[0]?.message) {
        message = data.errors[0].message;
      }
    } catch (error) {
      // Keep default error message.
    }
    throw new Error(message);
  }
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
        <p><strong>${item.available}</strong> available candidates</p>
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
      const jobId = e.target.dataset.jobId;
      const jobTitle = e.target.dataset.jobTitle;
      applyJobId.value = jobId;
      document.querySelector('#apply').scrollIntoView({ behavior: 'smooth' });
      if (applyStatus) applyStatus.textContent = `Applying for: ${jobTitle}`;
    });
  });
};

const loadStatus = async () => {
  if (!apiStatusText) return;

  try {
    const response = await fetch('/api/v1/status', { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Status unavailable');
    const data = await response.json();
    apiStatusText.textContent = `Online · ${data.version} · ${new Date(data.timestamp).toLocaleTimeString()}`;
  } catch (error) {
    apiStatusText.textContent = 'Degraded';
  }
};

const loadMetrics = async () => {
  try {
    const response = await fetch('/api/v1/metrics', { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Metrics unavailable');
    const data = await response.json();
    renderMetrics(data);
  } catch (error) {
    // Keep silent: realtime stream or later polls can recover.
  }
};

const loadTalentPool = async () => {
  try {
    const response = await fetch('/api/v1/talent-pool', { headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Talent pool unavailable');
    const data = await response.json();
    renderTalentPool(data);
  } catch (error) {
    // Keep silent and retry in periodic refresh.
  }
};

const loadJobs = async () => {
  try {
    const response = await fetch('/api/v1/jobs', { headers: { Accept: 'application/json' } });
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

  const eventSource = new EventSource('/api/v1/events');
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
    const technologiesRaw = String(formData.get('technologies') || '').trim();
    const payload = {
      name: String(formData.get('name') || '').trim(),
      email: String(formData.get('email') || '').trim(),
      company: String(formData.get('company') || '').trim(),
      role_title: String(formData.get('role_title') || '').trim(),
      technologies: technologiesRaw
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      hiring_model: String(formData.get('hiring_model') || '').trim(),
      positions: Number(formData.get('positions') || 1),
      start_timeline: String(formData.get('start_timeline') || '').trim(),
      goals: String(formData.get('goals') || '').trim(),
    };

    if (!payload.technologies.length) {
      if (contactStatus) {
        contactStatus.textContent = 'Please provide at least one technology in the technologies field.';
        contactStatus.classList.add('is-error');
      }
      return;
    }

    if (contactStatus) {
      contactStatus.textContent = 'Submitting staffing request...';
      contactStatus.classList.remove('is-error', 'is-success');
    }

    const formspreeEndpoint = (contactForm.dataset.formspreeEndpoint || '').trim();

    try {
      if (formspreeEndpoint) {
        await submitToFormspree(formspreeEndpoint, payload, {
          form_type: 'staffing-request',
        });
      } else {
        const response = await fetch('/api/v1/staffing-request', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.message || 'Failed to submit staffing request');
        }
      }

      if (contactStatus) {
        contactStatus.textContent = 'Request submitted! Our recruiting team will reach out within 24 hours.';
        contactStatus.classList.add('is-success');
      }
      contactForm.reset();
      loadMetrics();
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
    const skillsRaw = String(formData.get('skills') || '').trim();
    const payload = {
      full_name: String(formData.get('full_name') || '').trim(),
      email: String(formData.get('email') || '').trim(),
      phone: String(formData.get('phone') || '').trim(),
      current_title: String(formData.get('current_title') || '').trim(),
      years_experience: Number(formData.get('years_experience') || 0),
      skills: skillsRaw
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
      linkedin_url: String(formData.get('linkedin_url') || '').trim(),
      resume_summary: String(formData.get('resume_summary') || '').trim(),
      job_id: String(formData.get('job_id') || '').trim() || 'general',
    };

    if (!payload.skills.length) {
      if (applyStatus) {
        applyStatus.textContent = 'Please provide at least one skill.';
        applyStatus.classList.add('is-error');
      }
      return;
    }

    if (applyStatus) {
      applyStatus.textContent = 'Submitting application...';
      applyStatus.classList.remove('is-error', 'is-success');
    }

    const formspreeEndpoint = (applyForm.dataset.formspreeEndpoint || '').trim();

    try {
      if (formspreeEndpoint) {
        await submitToFormspree(formspreeEndpoint, payload, {
          form_type: 'job-application',
        });
      } else {
        const response = await fetch('/api/v1/apply', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.message || 'Failed to submit application');
        }
      }

      if (applyStatus) {
        applyStatus.textContent = 'Application submitted! Check your email for updates.';
        applyStatus.classList.add('is-success');
      }
      applyForm.reset();
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
