document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('toggle-search');
  const panel = document.getElementById('search-panel');

  if (toggleBtn && panel) {
    const toggle = () => {
      const nowHidden = panel.classList.toggle('hidden');
      toggleBtn.setAttribute('aria-expanded', (!nowHidden).toString());
      panel.setAttribute('aria-hidden', nowHidden.toString());
      // Active state while open
      toggleBtn.classList.toggle('active', !nowHidden);
    };
    toggleBtn.addEventListener('click', toggle);

    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !panel.classList.contains('hidden')) {
        panel.classList.add('hidden');
        toggleBtn.setAttribute('aria-expanded', 'false');
        panel.setAttribute('aria-hidden', 'true');
        toggleBtn.classList.remove('active');
      }
    });
  }

  // Smooth anchor scroll + active state
  const anchorLinks = Array.from(document.querySelectorAll('.nav-list a[href^="#"]'));
  const setActiveFromHash = () => {
    const hash = window.location.hash;
    anchorLinks.forEach(l => l.classList.remove('active'));
    if (!hash) return;
    const match = anchorLinks.find(l => l.getAttribute('href') === hash);
    if (match) match.classList.add('active');
  };

  // Limit smooth-scroll to anchors inside .nav-list to avoid conflicting with profile sidebar links
  document.querySelectorAll('.nav-list a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const id = a.getAttribute('href').slice(1);
      const target = document.getElementById(id);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      // Set active immediately on click
      anchorLinks.forEach(l => l.classList.remove('active'));
      a.classList.add('active');
      // Update hash without jump
      history.replaceState(null, '', `#${id}`);
    });
  });

  window.addEventListener('hashchange', setActiveFromHash, { passive: true });
  setActiveFromHash();

  // Header scroll shadow
  const header = document.querySelector('.site-header');
  const onScroll = () => {
    if (!header) return;
    const scrolled = window.scrollY > 10;
    header.classList.toggle('scrolled', scrolled);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Login/Signup panel toggles
  const main = document.querySelector('main.main');
  const loginPanel = document.getElementById('login-panel');
  const signupPanel = document.getElementById('signup-panel');
  const showSignup = (show) => {
    if (!loginPanel || !signupPanel) return;
    signupPanel.classList.toggle('hidden', !show);
    loginPanel.classList.toggle('hidden', show);
  };
  document.querySelectorAll('[data-toggle-signup]').forEach(el => {
    el.addEventListener('click', (e) => { e.preventDefault(); showSignup(true); });
  });
  document.querySelectorAll('[data-toggle-login]').forEach(el => {
    el.addEventListener('click', (e) => { e.preventDefault(); showSignup(false); });
  });
  const defaultShowSignup = main && main.getAttribute('data-show-signup') === 'true';
  if (defaultShowSignup || window.location.hash === '#signup') {
    showSignup(true);
  }
  // Profile page section toggles
  const sidebarLinks = Array.from(document.querySelectorAll('.profile-sidebar a[data-section]'));
  const panels = {
    profile: document.getElementById('section-profile'),
    achievements: document.getElementById('section-achievements'),
    experiences: document.getElementById('section-experiences'),
    projects: document.getElementById('section-projects'),
    cv: document.getElementById('section-cv'),
  };
  const showSection = (key) => {
    Object.values(panels).forEach(p => p && p.classList.add('hidden'));
    if (panels[key]) panels[key].classList.remove('hidden');
    sidebarLinks.forEach(a => a.classList.toggle('active', a.getAttribute('data-section') === key));
  };
  sidebarLinks.forEach(a => a.addEventListener('click', (e) => {
    e.preventDefault();
    showSection(a.getAttribute('data-section'));
  }));
  if (panels.profile) showSection('profile');

  // Profile: Professional Summary word counter (max 100 words)
  const summaryTA = document.getElementById('professional_summary');
  const summaryCounter = document.getElementById('professional_summary_counter');
  if (summaryTA && summaryCounter) {
    const LIMIT = 100;
    const form = summaryTA.closest('form');
    const submitBtn = form ? form.querySelector('button[type="submit"]') : null;

    function countWords(text) {
      const matches = text.trim().match(/\S+/g);
      return matches ? matches.length : 0;
    }

    function updateSummaryCounter() {
      const count = countWords(summaryTA.value);
      const over = count > LIMIT;
      summaryCounter.textContent = `${count}/${LIMIT} words` + (over ? ` — over by ${count - LIMIT}` : '');
      summaryCounter.style.color = over ? 'var(--danger)' : 'var(--muted)';
      summaryTA.style.borderColor = over ? 'var(--danger)' : 'var(--input-border)';
      if (submitBtn) submitBtn.disabled = over;
    }

    summaryTA.addEventListener('input', updateSummaryCounter);
    updateSummaryCounter();

    if (form) {
      form.addEventListener('submit', (e) => {
        if (countWords(summaryTA.value) > LIMIT) {
          e.preventDefault();
          const profilePanel = document.getElementById('section-profile');
          if (profilePanel) {
            Object.values(panels).forEach(p => p && p.classList && p.classList.add('hidden'));
            profilePanel.classList.remove('hidden');
          }
          summaryTA.focus();
        }
      });
    }
  }

  // Publication: conditional venue fields visibility based on Work Type
  const workTypeSelect = document.getElementById('work_type');
  const conferenceTitleLabel = document.querySelector('label[for="conference_title"]');
  const conferenceTitleInput = document.getElementById('conference_title');
  const journalTitleLabel = document.querySelector('label[for="journal_title"]');
  const journalTitleInput = document.getElementById('journal_title');
  const bookTitleLabel = document.querySelector('label[for="book_title"]');
  const bookTitleInput = document.getElementById('book_title');
  const toggleVenueFields = () => {
    if (!workTypeSelect) return;
    const v = workTypeSelect.value;
    const showConference = ['conference_paper','conference_presentation','conference_poster'].includes(v);
    const showJournal = v === 'journal_article';
    const showBook = v === 'book' || v === 'book_chapter';
    const pairs = [
      [conferenceTitleLabel, conferenceTitleInput, showConference],
      [journalTitleLabel, journalTitleInput, showJournal],
      [bookTitleLabel, bookTitleInput, showBook],
    ];
    pairs.forEach(([label, input, show]) => {
      if (label) label.classList.toggle('hidden', !show);
      if (input) input.classList.toggle('hidden', !show);
    });
  };
  if (workTypeSelect) {
    workTypeSelect.addEventListener('change', toggleVenueFields);
    toggleVenueFields();
  }

  // Publications page: collapse toggles for Abstract and BibTeX
  document.querySelectorAll('[data-toggle="collapse"]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = btn.getAttribute('data-target');
      const target = targetId && document.getElementById(targetId);
      if (!target) return;
      const nowHidden = target.classList.toggle('hidden');
      btn.classList.toggle('active', !nowHidden);

      // If we just opened this one, close any other collapsibles in the same pub-card
      if (!nowHidden) {
        const card = btn.closest('.pub-card');
        if (card) {
          card.querySelectorAll('.collapsible').forEach(el => {
            if (el !== target) el.classList.add('hidden');
          });
        }
      }
    });
  });

  // Click-to-copy BibTeX inside its box; no extra button needed
  (function(){
    function copy(text){
      if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text);
      }
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch(_) {}
      document.body.removeChild(ta);
      return Promise.resolve();
    }

    function showToast(container, msg){
      const note = document.createElement('div');
      note.textContent = msg;
      note.style.position = 'absolute';
      note.style.right = '10px';
      note.style.top = '10px';
      note.style.background = 'var(--surface)';
      note.style.border = '1px solid var(--border)';
      note.style.padding = '4px 8px';
      note.style.borderRadius = '8px';
      note.style.fontSize = '12px';
      note.style.boxShadow = 'var(--shadow-1)';
      note.style.zIndex = '10';
      container.appendChild(note);
      setTimeout(() => note.remove(), 1200);
    }

    // Set title hint and click handler on all BibTeX <pre> blocks
    document.querySelectorAll('.collapsible[id^="bib-"] pre').forEach(pre => {
      pre.title = 'Click to copy BibTeX';
      pre.addEventListener('click', () => {
        const text = pre.textContent.trim();
        if (!text) return;
        const box = pre.closest('.collapsible') || pre.parentElement;
        copy(text)
          .then(() => showToast(box, 'Copied'))
          .catch(() => showToast(box, 'Copy failed'));
      });
    });
  })();

  // Publications page: simple auto slideshow for publication images
  document.querySelectorAll('.pub-slideshow').forEach(slide => {
    const slides = Array.from(slide.querySelectorAll('.slide'));
    if (slides.length === 0) return;
    let index = 0;
    slides.forEach((s, i) => s.classList.toggle('active', i === 0));
    if (slides.length === 1) return; // show single image, no auto-advance
    const interval = parseInt(slide.getAttribute('data-interval'), 10) || 3000;
    setInterval(() => {
      slides[index].classList.remove('active');
      index = (index + 1) % slides.length;
      slides[index].classList.add('active');
    }, interval);
  });

  // Ongoing Research Projects: click-to-open image lightbox
  (function(){
    const section = document.querySelector('.ongoing-projects');
    if (!section) return;

    let lb = document.getElementById('img-lightbox');
    if (!lb) {
      lb = document.createElement('div');
      lb.id = 'img-lightbox';
      lb.className = 'img-lightbox';
      lb.innerHTML = '<div class="lb-content"><button class="lb-close" aria-label="Close">✕</button><img class="lb-image" alt=""></div>';
      document.body.appendChild(lb);
    }
    const imgEl = lb.querySelector('.lb-image');
    const closeBtn = lb.querySelector('.lb-close');

    function openLB(src, alt){
      if (imgEl) {
        imgEl.src = src;
        imgEl.alt = alt || '';
      }
      lb.classList.add('open');
      document.body.classList.add('no-scroll');
    }
    function closeLB(){
      lb.classList.remove('open');
      document.body.classList.remove('no-scroll');
      // small delay to avoid flicker when reopening
      setTimeout(() => { if (imgEl) imgEl.src = ''; }, 150);
    }

    // Open on image click within the ongoing projects details
    section.addEventListener('click', (e) => {
      const img = e.target.closest('.image-row img');
      if (!img) return;
      e.preventDefault();
      openLB(img.src, img.alt);
    });
    // Close on clicking the backdrop
    lb.addEventListener('click', (e) => { if (e.target === lb) closeLB(); });
    // Close button
    if (closeBtn) closeBtn.addEventListener('click', (e) => { e.preventDefault(); closeLB(); });
    // Close on Escape
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLB(); });
  })();

  // Publication images (Selected Publications, Publications tab): click-to-open image lightbox
  (function(){
    // If there are no publication images, skip
    const hasPubImages = document.querySelector('.pub-slideshow img');
    if (!hasPubImages) return;

    // Reuse or create the shared lightbox overlay
    let lb = document.getElementById('img-lightbox');
    if (!lb) {
      lb = document.createElement('div');
      lb.id = 'img-lightbox';
      lb.className = 'img-lightbox';
      lb.innerHTML = '<div class="lb-content"><button class="lb-close" aria-label="Close">✕</button><img class="lb-image" alt=""></div>';
      document.body.appendChild(lb);
    }
    const imgEl = lb.querySelector('.lb-image');
    const closeBtn = lb.querySelector('.lb-close');

    function openLB(src, alt){
      if (imgEl) {
        imgEl.src = src;
        imgEl.alt = alt || '';
      }
      lb.classList.add('open');
      document.body.classList.add('no-scroll');
    }
    function closeLB(){
      lb.classList.remove('open');
      document.body.classList.remove('no-scroll');
      setTimeout(() => { if (imgEl) imgEl.src = ''; }, 150);
    }

    // Open on click of any publication slideshow image (works on profile, publications, research pages)
    document.addEventListener('click', (e) => {
      const img = e.target.closest('.pub-slideshow img');
      if (!img) return;
      e.preventDefault();
      openLB(img.src, img.alt || 'Publication image');
    });
    // Close on clicking the backdrop
    lb.addEventListener('click', (e) => { if (e.target === lb) closeLB(); });
    // Close via button
    if (closeBtn) closeBtn.addEventListener('click', (e) => { e.preventDefault(); closeLB(); });
    // Close on Escape
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLB(); });
  })();

  // Research page: click-to-open image lightbox for any project photos
  (function(){
    const page = document.querySelector('.research-page');
    if (!page) return;

    let lb = document.getElementById('img-lightbox');
    if (!lb) {
      lb = document.createElement('div');
      lb.id = 'img-lightbox';
      lb.className = 'img-lightbox';
      lb.innerHTML = '<div class="lb-content"><button class="lb-close" aria-label="Close">✕</button><img class="lb-image" alt=""></div>';
      document.body.appendChild(lb);
    }
    const imgEl = lb.querySelector('.lb-image');
    const closeBtn = lb.querySelector('.lb-close');

    function openLB(src, alt){
      if (imgEl) {
        imgEl.src = src;
        imgEl.alt = alt || '';
      }
      lb.classList.add('open');
      document.body.classList.add('no-scroll');
    }
    function closeLB(){
      lb.classList.remove('open');
      document.body.classList.remove('no-scroll');
      setTimeout(() => { if (imgEl) imgEl.src = ''; }, 150);
    }

    // Delegate clicks anywhere within research page for images inside .image-row
    page.addEventListener('click', (e) => {
      const img = e.target.closest('.image-row img');
      if (!img) return;
      e.preventDefault();
      openLB(img.src, img.alt || 'Project image');
    });
    lb.addEventListener('click', (e) => { if (e.target === lb) closeLB(); });
    if (closeBtn) closeBtn.addEventListener('click', (e) => { e.preventDefault(); closeLB(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeLB(); });
  })();

  // Publications page: filters and sorting (scoped to Publications tab or page)
  (function(){
    const page = document.querySelector('#tab-publications') || document.querySelector('.pub-page');
    if (!page) return;

    const searchInput = page.querySelector('#pub-search');
    const typeSelect = page.querySelector('#pub-type');
    const yearSelect = page.querySelector('#pub-year');
    const sortSelect = page.querySelector('#pub-sort');
    const areaBar = page.querySelector('.pub-area-chips');
    const pubCards = Array.from(page.querySelectorAll('.pub-card'));

    // Research area selection state
    function getParam(name){
      const p = new URLSearchParams(window.location.search);
      return p.get(name);
    }
    function setParam(name, value){
      const p = new URLSearchParams(window.location.search);
      if (!value || value === 'all') p.delete(name); else p.set(name, value);
      const url = `${window.location.pathname}${p.toString() ? ('?' + p.toString()) : ''}`;
      window.history.replaceState(null, '', url);
    }
    let selectedArea = getParam('area') || 'all';
    if (areaBar) {
      const chips = Array.from(areaBar.querySelectorAll('.chip'));
      // Initialize active state from URL param if present
      chips.forEach(ch => ch.classList.toggle('active', (ch.getAttribute('data-value')||'all') === selectedArea));
      areaBar.addEventListener('click', (e) => {
        const chip = e.target.closest('.chip');
        if (!chip) return;
        e.preventDefault();
        const val = chip.getAttribute('data-value') || 'all';
        selectedArea = val;
        chips.forEach(c => c.classList.toggle('active', c === chip));
        setParam('area', selectedArea);
        applyFilters();
      });
    }

    // Populate year options from available cards
    if (yearSelect) {
      const years = Array.from(new Set(pubCards.map(c => c.dataset.year).filter(Boolean))).sort((a, b) => b.localeCompare(a));
      const opts = ['<option value="all">All years</option>'].concat(years.map(y => `<option value="${y}">${y}</option>`));
      yearSelect.innerHTML = opts.join('');
    }

    function matchesSearch(card, q){
      if (!q) return true;
      const t = (card.dataset.title || '').toLowerCase();
      const a = (card.dataset.authors || '').toLowerCase();
      return t.includes(q) || a.includes(q);
    }
    function matchesType(card, type){
      return !type || type === 'all' || (card.dataset.type === type);
    }
    function matchesYear(card, year){
      return !year || year === 'all' || (card.dataset.year === year);
    }
    function matchesArea(card, area){
      if (!area || area === 'all') return true;
      const areasAttr = card.getAttribute('data-areas') || card.getAttribute('data-area') || '';
      const areas = areasAttr.split(',').map(s => s.trim()).filter(Boolean);
      return areas.includes(area);
    }

    function applyFilters(){
      const q = (searchInput && searchInput.value || '').trim().toLowerCase();
      const type = typeSelect ? typeSelect.value : 'all';
      const year = yearSelect ? yearSelect.value : 'all';
      pubCards.forEach(card => {
        const visible = matchesSearch(card, q) && matchesType(card, type) && matchesYear(card, year) && matchesArea(card, selectedArea);
        card.classList.toggle('hidden', !visible);
      });

      // Hide profile blocks with no visible publications
      page.querySelectorAll('.profile-block').forEach(block => {
        const anyVisible = Array.from(block.querySelectorAll('.pub-card')).some(c => !c.classList.contains('hidden'));
        block.style.display = anyVisible ? '' : 'none';
      });

      // Hide entire role sections if they contain no visible publications
      page.querySelectorAll('.user-section').forEach(section => {
        const anyVisible = Array.from(section.querySelectorAll('.pub-card')).some(c => !c.classList.contains('hidden'));
        section.style.display = anyVisible ? '' : 'none';
      });
    }

    [searchInput, typeSelect, yearSelect].forEach(el => {
      if (!el) return;
      const evt = el.tagName.toLowerCase() === 'input' ? 'input' : 'change';
      el.addEventListener(evt, applyFilters);
    });

    // Sorting within each profile block
    function sortCards(){
      const mode = sortSelect ? sortSelect.value : 'year_desc';
      page.querySelectorAll('.profile-block').forEach(block => {
        const cards = Array.from(block.querySelectorAll('.pub-card'));
        const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
        const sorted = cards.sort((a, b) => {
          switch (mode) {
            case 'year_asc':
              return collator.compare(a.dataset.year || '', b.dataset.year || '');
            case 'title_az':
              return collator.compare(a.dataset.title || '', b.dataset.title || '');
            default: // year_desc
              return collator.compare(b.dataset.year || '', a.dataset.year || '');
          }
        });
        sorted.forEach(c => block.appendChild(c));
      });
    }

    if (sortSelect) sortSelect.addEventListener('change', sortCards);

    // Removed separate Copy Bib button; copy handled by clicking the BibTeX box

    // Initial filter
    applyFilters();
})();

  // Mail portal redirect for mailto links (open Gmail compose)
  document.querySelectorAll('a[href^="mailto:"]').forEach(a => {
    a.addEventListener('click', (e) => {
      // Opt-out attribute to keep native mailto behavior
      if (a.hasAttribute('data-mailto-direct')) return;
      e.preventDefault();
      const email = a.getAttribute('href').replace(/^mailto:/, '');
      const gmailUrl = `https://mail.google.com/mail/u/0/?view=cm&fs=1&to=${encodeURIComponent(email)}`;
      window.open(gmailUrl, '_blank', 'noopener');
    });
  });

  // Show password toggles
  document.querySelectorAll('input[type="checkbox"][data-toggle-password]').forEach(chk => {
    const sel = chk.getAttribute('data-toggle-password');
    const targets = sel ? Array.from(document.querySelectorAll(sel)) : [];
    const update = () => {
      targets.forEach(t => {
        if (!t) return;
        const isPasswordLike = t.tagName.toLowerCase() === 'input' && (t.type === 'password' || t.type === 'text');
        if (!isPasswordLike) return;
        t.type = chk.checked ? 'text' : 'password';
      });
    };
    chk.addEventListener('change', update);
    update();
  });
});

// Existing helpers and utilities

// Formatting helpers for Achievements textarea
(function(){
  function wrapSelection(textarea, before, after){
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    const value = textarea.value;
    const selected = value.slice(start, end) || '';
    const replacement = before + selected + after;
    textarea.value = value.slice(0, start) + replacement + value.slice(end);
    const caret = start + replacement.length;
    textarea.setSelectionRange(caret, caret);
    textarea.focus();
  }
  function insertLink(textarea){
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    const value = textarea.value;
    const selected = value.slice(start, end) || 'text';
    const url = prompt('Enter URL (http/https only):','https://');
    if (!url) return;
    const replacement = '['+selected+'](' + url + ')';
    textarea.value = value.slice(0, start) + replacement + value.slice(end);
    const caret = start + replacement.length;
    textarea.setSelectionRange(caret, caret);
    textarea.focus();
  }
  function findTarget(btn){
    const targetId = btn.getAttribute('data-target');
    if (targetId){
      return document.getElementById(targetId);
    }
    // fallback: closest form then its textarea named description
    const form = btn.closest('form');
    return form ? form.querySelector('textarea[name="description"]') : null;
  }
  function handleClick(e){
    const btn = e.target.closest('.fmt-bold, .fmt-link');
    if (!btn) return;
    const ta = findTarget(btn);
    if (!ta) return;
    e.preventDefault();
    if (btn.classList.contains('fmt-bold')){
      wrapSelection(ta, '**', '**');
    } else {
      insertLink(ta);
    }
  }
  document.addEventListener('click', handleClick);
})();


  // Admin drag-and-drop reordering for sortable lists
  function getCSRFToken() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  async function postReorder(model, ids, group) {
    try {
      const res = await fetch('/admin/reorder/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCSRFToken()
        },
        body: JSON.stringify({ model, ids, group })
      });
      if (!res.ok) {
        console.warn('Reorder failed', await res.text());
      }
    } catch (e) {
      console.warn('Reorder error', e);
    }
  }

  function getDragAfterElement(container, y) {
    const elements = Array.from(container.querySelectorAll('.sortable-item:not(.dragging)'));
    let closest = { offset: Number.NEGATIVE_INFINITY, element: null };
    for (const child of elements) {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        closest = { offset, element: child };
      }
    }
    return closest.element;
  }

  function initSortable() {
    document.querySelectorAll('.sortable').forEach(container => {
      const model = container.getAttribute('data-model');
      const group = container.getAttribute('data-group') || null;
      let dragEl = null;

      container.addEventListener('dragstart', e => {
        const item = e.target.closest('.sortable-item[draggable="true"]');
        if (!item) return;
        dragEl = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.dataset.id || '');
      });

      container.addEventListener('dragend', () => {
        if (dragEl) dragEl.classList.remove('dragging');
        // On drag end, compute new order and send update to be robust
        const ids = Array.from(container.querySelectorAll('.sortable-item')).map(el => el.dataset.id);
        if (ids && ids.length && model) {
          postReorder(model, ids, group);
        }
        dragEl = null;
      });

      container.addEventListener('dragover', e => {
        e.preventDefault();
        const afterEl = getDragAfterElement(container, e.clientY);
        if (!dragEl) return;
        if (afterEl == null) {
          container.appendChild(dragEl);
        } else {
          container.insertBefore(dragEl, afterEl);
        }
      });

      container.addEventListener('drop', e => {
        e.preventDefault();
        const ids = Array.from(container.querySelectorAll('.sortable-item')).map(el => el.dataset.id);
        if (!ids.length || !model) return;
        postReorder(model, ids, group);
      });
    });
  }

  initSortable();

// Research page filters and Copy Bib (scoped to Projects tab)
(function(){
  const page = document.querySelector('#tab-projects') || document.querySelector('.research-page');
  if(!page) return;

  const searchInput = page.querySelector('#research-search');
  const typeSelect = page.querySelector('#research-type');
  const yearSelect = page.querySelector('#research-year');
  const sortSelect = page.querySelector('#research-sort');
  const sections = Array.from(page.querySelectorAll('.user-section'));
  const cards = Array.from(page.querySelectorAll('.pub-card'));

  // If controls are missing (we don't render filters), skip setup entirely
  if (!searchInput || !typeSelect || !yearSelect) return;

  // Build type options dynamically from cards' data-work-type-label
  const typeLabels = new Map(); // key: work_type value, val: display label
  cards.forEach(card => {
    const val = card.getAttribute('data-work-type');
    const label = card.getAttribute('data-work-type-label');
    if (val && label && !typeLabels.has(val)) {
      typeLabels.set(val, label);
    }
  });
  const sortedTypeEntries = Array.from(typeLabels.entries()).sort((a,b)=>a[1].localeCompare(b[1]));
  // preserve existing 'All types'
  sortedTypeEntries.forEach(([value,label]) => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    if (typeSelect) typeSelect.appendChild(opt);
  });

  // Build year options from cards
  const years = new Set();
  cards.forEach(card => {
    const y = parseInt(card.getAttribute('data-year'), 10);
    if (!isNaN(y)) years.add(y);
  });
  const sortedYears = Array.from(years).sort((a,b)=>b-a);
  sortedYears.forEach(y => {
    const opt = document.createElement('option');
    opt.value = String(y);
    opt.textContent = String(y);
    if (yearSelect) yearSelect.appendChild(opt);
  });

  // Helpers for URL params
  function getParams(){
    const p = new URLSearchParams(window.location.search);
    return {
      q: p.get('q') || '',
      type: p.get('type') || 'all',
      year: p.get('year') || 'all',
      sort: p.get('sort') || 'year_desc'
    };
  }
  function setParams(state){
    const p = new URLSearchParams();
    if (state.q) p.set('q', state.q);
    if (state.type && state.type !== 'all') p.set('type', state.type);
    if (state.year && state.year !== 'all') p.set('year', state.year);
    if (state.sort && state.sort !== 'year_desc') p.set('sort', state.sort);
    const url = `${window.location.pathname}?${p.toString()}`;
    window.history.replaceState(null, '', url);
  }

  // Apply params to controls on load
  const initial = getParams();
  if (searchInput) searchInput.value = initial.q;
  // Ensure type exists; if not, fall back to 'all'
  const typeValues = new Set(['all', ...sortedTypeEntries.map(([v])=>v)]);
  if (typeSelect) typeSelect.value = typeValues.has(initial.type) ? initial.type : 'all';
  const yearValues = new Set(['all', ...sortedYears.map(String)]);
  if (yearSelect) yearSelect.value = yearValues.has(String(initial.year)) ? String(initial.year) : 'all';
  if (sortSelect) sortSelect.value = initial.sort || 'year_desc';

  function matches(card, {q, type, year}){
    const title = (card.getAttribute('data-title')||'').toLowerCase();
    const authors = (card.getAttribute('data-authors')||'').toLowerCase();
    const t = card.getAttribute('data-work-type');
    const y = card.getAttribute('data-year');

    const qOk = !q || title.includes(q.toLowerCase()) || authors.includes(q.toLowerCase());
    const typeOk = type === 'all' || (t === type);
    const yearOk = year === 'all' || (String(y) === String(year));
    return qOk && typeOk && yearOk;
  }

  function applyFilter(){
    const state = {
      q: searchInput ? searchInput.value.trim() : '',
      type: typeSelect ? typeSelect.value : 'all',
      year: yearSelect ? yearSelect.value : 'all',
      sort: sortSelect ? sortSelect.value : 'year_desc'
    };
    setParams(state);

    // Filter cards
    let visibleCountBySection = new Map();
    cards.forEach(card => {
      const show = matches(card, state);
      card.style.display = show ? '' : 'none';
      const area = card.getAttribute('data-area');
      if (show) {
        visibleCountBySection.set(area, (visibleCountBySection.get(area)||0) + 1);
      }
    });

    // Sort visible cards within each projects container
    const containers = Array.from(page.querySelectorAll('.ongoing-projects'));
    const byYear = (a,b,dir) => {
      const ya = parseInt(a.getAttribute('data-year')||'0', 10) || 0;
      const yb = parseInt(b.getAttribute('data-year')||'0', 10) || 0;
      return dir === 'desc' ? (yb - ya) : (ya - yb);
    };
    const byTitle = (a,b) => {
      const ta = (a.getAttribute('data-title')||'').toLowerCase();
      const tb = (b.getAttribute('data-title')||'').toLowerCase();
      return ta.localeCompare(tb);
    };
    containers.forEach(container => {
      const children = Array.from(container.querySelectorAll('.pub-card'));
      const visible = children.filter(el => el.style.display !== 'none');
      const hidden = children.filter(el => el.style.display === 'none');
      if (!visible.length) return;
      let cmp;
      if (state.sort === 'year_asc') {
        cmp = (a,b) => byYear(a,b,'asc');
      } else if (state.sort === 'title_az') {
        cmp = (a,b) => byTitle(a,b);
      } else {
        cmp = (a,b) => byYear(a,b,'desc');
      }
      visible.sort(cmp);
      // Re-append in sorted order, then hidden items
      [...visible, ...hidden].forEach(el => container.appendChild(el));
    });

    // Hide empty sections
    sections.forEach(sec => {
      const key = sec.id.replace('area-', '');
      const count = visibleCountBySection.get(key)||0;
      sec.style.display = count > 0 ? '' : 'none';
    });
  }

  // Events
  let debounceTimer;
  searchInput && searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(applyFilter, 200);
  });
  typeSelect && typeSelect.addEventListener('change', applyFilter);
  yearSelect && yearSelect.addEventListener('change', applyFilter);
  sortSelect && sortSelect.addEventListener('change', applyFilter);

  // Initial filter
  applyFilter();
})();

// Research tabs toggling (Publications vs Projects)
(function(){
  const tabsNav = document.getElementById('research-tabs');
  const pubPanel = document.getElementById('tab-publications');
  const projPanel = document.getElementById('tab-projects');
  if (!tabsNav || !pubPanel || !projPanel) return;

  function showTab(key){
    const showPub = key === 'publications';
    pubPanel.classList.toggle('hidden', !showPub);
    projPanel.classList.toggle('hidden', showPub);
    Array.from(tabsNav.querySelectorAll('a[data-tab]')).forEach(a => {
      a.classList.toggle('active', a.getAttribute('data-tab') === key);
      a.setAttribute('aria-selected', (a.getAttribute('data-tab') === key).toString());
    });
  }
  tabsNav.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-tab]');
    if (!a) return;
    e.preventDefault();
    showTab(a.getAttribute('data-tab'));
  });
  const params = new URLSearchParams(window.location.search);
  const initial = params.get('tab') || (window.location.hash === '#projects' ? 'projects' : 'publications');
  showTab(initial);
})();