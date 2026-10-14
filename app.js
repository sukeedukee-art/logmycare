/**
 * CareLink Live Monitor - Frontend Application Logic
 * Implements real-time data polling, instant push-reload animations,
 * filtering, search, modal inspection, and KPI updates.
 */

(function () {
  'use strict';

  // State
  let currentData = null;
  let lastKnownTimestamp = null;
  let activeTab = 'all';
  let searchQuery = '';
  let countdownSeconds = 600; // 10 minutes (600s)
  const TOTAL_CYCLE_SECONDS = 600;

  // DOM Elements
  const progressBar = document.getElementById('top-sync-progress-bar');
  const lastUpdatedEl = document.getElementById('last-updated-text');
  const countdownEl = document.getElementById('next-sync-countdown');
  const btnRefresh = document.getElementById('btn-manual-refresh');

  const countResidents = document.getElementById('count-residents');
  const countNeedsReview = document.getElementById('count-needs-review');
  const countOpen = document.getElementById('count-open');
  const countSupportPlans = document.getElementById('count-support-plans');
  const countGoals = document.getElementById('count-goals');
  const countFuturePlans = document.getElementById('count-future-plans');

  const tabBtns = document.querySelectorAll('.tab-btn');
  const searchInput = document.getElementById('filter-search-input');
  const searchClearBtn = document.getElementById('search-clear-btn');
  const cardsWrapper = document.getElementById('cards-content-wrapper');
  const cardsGrid = document.getElementById('cards-grid');

  // Modal Elements
  const modal = document.getElementById('item-details-modal');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalOkBtn = document.getElementById('modal-ok-btn');
  const modalCategoryBadge = document.getElementById('modal-category-badge');
  const modalStatusBadge = document.getElementById('modal-status-badge');
  const modalTitle = document.getElementById('modal-title');
  const modalResident = document.getElementById('modal-resident');
  const modalDate = document.getElementById('modal-date');
  const modalExtra = document.getElementById('modal-extra');
  const modalDetails = document.getElementById('modal-details');

  // Toast
  const toast = document.getElementById('live-toast');
  const toastText = document.getElementById('toast-text');

  // Show Toast
  function showToast(message) {
    if (!toast) return;
    toastText.textContent = message;
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 3200);
  }

  // Format Date for Display
  function formatTimestamp(isoStr) {
    if (!isoStr) return 'Just now';
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' (' + d.toLocaleDateString([], { day: '2-digit', month: 'short' }) + ')';
    } catch {
      return isoStr;
    }
  }

  // Countdown & Progress Bar Timer
  function updateCountdown() {
    countdownSeconds -= 1;
    if (countdownSeconds <= 0) {
      countdownSeconds = TOTAL_CYCLE_SECONDS;
      fetchData(true); // Trigger fetch
    }

    const mins = Math.floor(countdownSeconds / 60);
    const secs = countdownSeconds % 60;
    countdownEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    const progressPct = ((TOTAL_CYCLE_SECONDS - countdownSeconds) / TOTAL_CYCLE_SECONDS) * 100;
    if (progressBar) {
      progressBar.style.width = `${progressPct}%`;
    }
  }

  // Fetch Data from data.json
  async function fetchData(forceAnimation = false) {
    btnRefresh.classList.add('refreshing');
    try {
      const response = await fetch(`data.json?_=${Date.now()}`);
      if (!response.ok) throw new Error('Data file not available yet');

      const data = await response.json();
      const isNewTimestamp = data.last_updated && data.last_updated !== lastKnownTimestamp;

      if (isNewTimestamp || forceAnimation || !currentData) {
        lastKnownTimestamp = data.last_updated;
        currentData = data;
        countdownSeconds = TOTAL_CYCLE_SECONDS; // Reset 10-minute timer

        // Trigger the light animation push-reload
        performPushReload(data);
        showToast('Live dashboard updated');
        window.dispatchEvent(new CustomEvent('dashboard:updated', { detail: data }));
      }
    } catch (err) {
      console.warn('[CareLink Monitor] Polling update info:', err.message);
    } finally {
      setTimeout(() => {
        btnRefresh.classList.remove('refreshing');
      }, 500);
    }
  }

  // Trigger Live Scraper via Backend API on Click
  let isTriggeringScrape = false;

  async function triggerLiveScrape() {
    if (isTriggeringScrape) return;

    btnRefresh.classList.add('refreshing');
    const labelSpan = btnRefresh.querySelector('span');
    if (labelSpan) labelSpan.textContent = 'Connecting...';

    try {
      const resp = await fetch('/api/trigger-scrape', { method: 'POST' });
      if (resp.ok) {
        isTriggeringScrape = true;
        btnRefresh.disabled = true;
        if (labelSpan) labelSpan.textContent = 'Scraping live data (~60s)...';
        showToast('⚡ Scraper started! Extracting live Log My Care updates...');

        const pollInterval = setInterval(async () => {
          try {
            const statusResp = await fetch('/api/scrape-status');
            if (statusResp.ok) {
              const statusData = await statusResp.json();
              if (!statusData.running) {
                clearInterval(pollInterval);
                isTriggeringScrape = false;
                btnRefresh.disabled = false;
                if (labelSpan) labelSpan.textContent = 'Refresh Now';
                btnRefresh.classList.remove('refreshing');
                await fetchData(true);
                showToast('✓ Scrape finished! Fresh data displayed.');
              }
            }
          } catch {
            // Keep polling
          }
        }, 3000);

        setTimeout(() => {
          clearInterval(pollInterval);
          isTriggeringScrape = false;
          btnRefresh.disabled = false;
          if (labelSpan) labelSpan.textContent = 'Refresh Now';
          btnRefresh.classList.remove('refreshing');
        }, 150000);

        return;
      }
    } catch {
      // Backend API not reachable (static file server mode)
    }

    // Static fallback: refresh data.json directly
    btnRefresh.disabled = false;
    if (labelSpan) labelSpan.textContent = 'Refresh Now';
    btnRefresh.classList.remove('refreshing');
    await fetchData(true);
  }

  // Perform Push Reload Animation with exact millisecond transition
  function performPushReload(data) {
    // Phase 1: Light exit animation
    cardsWrapper.classList.remove('push-reload-enter');
    cardsWrapper.classList.add('push-reload-exit');

    // Phase 2: Exact same millisecond swap (after 200ms exit transition)
    setTimeout(() => {
      updateKPIs(data.stats, data.last_updated);
      renderCards(data);

      // Phase 3: Entrance animation
      cardsWrapper.classList.remove('push-reload-exit');
      cardsWrapper.classList.add('push-reload-enter');

      setTimeout(() => {
        cardsWrapper.classList.remove('push-reload-enter');
      }, 350);
    }, 200);
  }

  // Update KPI counters
  function updateKPIs(stats, timestamp) {
    if (!stats) return;
    lastUpdatedEl.textContent = formatTimestamp(timestamp);

    countResidents.textContent = stats.total_active_residents || '--';
    countNeedsReview.textContent = stats.incidents_needs_review || 0;
    countOpen.textContent = stats.incidents_open || 0;
    countSupportPlans.textContent = stats.support_plans_overdue || 0;
    countGoals.textContent = stats.goals_overdue || 0;
    countFuturePlans.textContent = stats.future_plans_overdue || 0;

    // Update tab count badges
    const allCount = (stats.incidents_needs_review || 0) +
                     (stats.incidents_open || 0) +
                     (stats.support_plans_overdue || 0) +
                     (stats.goals_overdue || 0) +
                     (stats.future_plans_overdue || 0);

    document.getElementById('tab-count-all').textContent = allCount;
    document.getElementById('tab-count-needs-review').textContent = stats.incidents_needs_review || 0;
    document.getElementById('tab-count-open').textContent = stats.incidents_open || 0;
    document.getElementById('tab-count-support-plans').textContent = stats.support_plans_overdue || 0;
    document.getElementById('tab-count-goals').textContent = stats.goals_overdue || 0;
    document.getElementById('tab-count-future-plans').textContent = stats.future_plans_overdue || 0;
  }

  // Flatten and filter cards
  function getFilteredItems(data) {
    if (!data) return [];

    let items = [];

    // 1. Incidents Needs Review
    (data.incidents_needs_review || []).forEach(item => {
      items.push({
        ...item,
        section: 'incidents_needs_review',
        category: 'needs_review',
        categoryLabel: 'Incident • Needs Review',
        categoryClass: 'cat-needs_review',
        statusClass: 'status-amber',
        extraText: item.severity ? `Severity: ${item.severity}` : 'Pending Lead Review'
      });
    });

    // 2. Open Incidents
    (data.incidents_open || []).forEach(item => {
      items.push({
        ...item,
        section: 'incidents_open',
        category: 'open',
        categoryLabel: 'Incident • Open',
        categoryClass: 'cat-open',
        statusClass: 'status-blue',
        extraText: item.severity ? `Severity: ${item.severity}` : 'Action Plan Active'
      });
    });

    // 3. Support Plans Overdue (one entry per resident, each with a list of overdue plans)
    (data.support_plans_overdue || []).forEach(item => {
      const plans = item.plans || [];
      items.push({
        ...item,
        section: 'support_plans_overdue',
        category: 'support_plans',
        categoryLabel: 'Support Plans',
        categoryClass: 'cat-support_plans',
        statusClass: 'status-rose',
        status: `${plans.length} overdue`,
        title: `${plans.length} support plan${plans.length === 1 ? '' : 's'} overdue`,
        date: plans.length ? `Up to ${plans[0].overdue_text} overdue` : 'Overdue',
        summary: plans.map(p => `${p.name} — ${p.overdue_text} overdue`).join('\n'),
        extraText: `${plans.length} plan${plans.length === 1 ? '' : 's'}`,
        searchText: plans.map(p => p.name).join(' '),
        rows: plans.map(p => ({ name: p.name, right: p.overdue_text }))
      });
    });

    // 4. Goals Overdue (one entry per resident, each with a list of goals whose review is overdue)
    (data.goals_overdue || []).forEach(item => {
      const goals = item.goals || [];
      items.push({
        ...item,
        section: 'goals_overdue',
        category: 'goals',
        categoryLabel: 'Goals',
        categoryClass: 'cat-goals',
        statusClass: 'status-purple',
        status: `${goals.length} overdue`,
        title: `${goals.length} goal review${goals.length === 1 ? '' : 's'} overdue`,
        date: 'Review overdue',
        summary: goals.map(g => `${g.title}${g.progress ? ` (${g.progress})` : ''}${g.last_reviewed ? `\n   ${g.last_reviewed}` : ''}`).join('\n'),
        extraText: `${goals.length} goal${goals.length === 1 ? '' : 's'}`,
        searchText: goals.map(g => g.title).join(' '),
        rows: goals.map(g => ({ name: g.title, right: g.progress || 'Overdue' }))
      });
    });

    // 5. Future Plans Overdue (one entry per resident, each with a list of plans tagged OVERDUE)
    (data.future_plans_overdue || []).forEach(item => {
      const plans = item.plans || [];
      items.push({
        ...item,
        section: 'future_plans_overdue',
        category: 'future_plans',
        categoryLabel: 'Future Plans',
        categoryClass: 'cat-future_plans',
        statusClass: 'status-orange',
        status: `${plans.length} overdue`,
        title: `${plans.length} future plan${plans.length === 1 ? '' : 's'} overdue`,
        date: plans.length ? `Up to ${plans[0].overdue_text} overdue` : 'Overdue',
        summary: plans.map(p => `${p.title} — ${p.overdue_text} overdue${p.next_review ? `\n   Review was due ${p.next_review}${p.last_reviewed ? ` (last reviewed ${p.last_reviewed})` : ''}` : ''}`).join('\n'),
        extraText: `${plans.length} plan${plans.length === 1 ? '' : 's'}`,
        searchText: plans.map(p => p.title).join(' '),
        rows: plans.map(p => ({ name: p.title, right: p.overdue_text }))
      });
    });

    // Filter by Active Tab
    if (activeTab !== 'all') {
      items = items.filter(i => i.category === activeTab);
    }

    // Filter by Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      items = items.filter(i => {
        return (i.resident && i.resident.toLowerCase().includes(q)) ||
               (i.title && i.title.toLowerCase().includes(q)) ||
               (i.summary && i.summary.toLowerCase().includes(q)) ||
               (i.status && i.status.toLowerCase().includes(q)) ||
               (i.categoryLabel && i.categoryLabel.toLowerCase().includes(q)) ||
               (i.searchText && i.searchText.toLowerCase().includes(q)) ||
               (i.staff_name && i.staff_name.toLowerCase().includes(q));
      });
    }

    return items;
  }

  // Get Avatar Initials
  function getInitials(name) {
    if (!name) return 'R';
    const parts = name.replace(/[()]/g, '').trim().split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  // Render Card Items into Grid
  function renderCards(data) {
    const items = getFilteredItems(data);
    cardsGrid.innerHTML = '';

    if (items.length === 0) {
      cardsGrid.innerHTML = `
        <div class="empty-state-box">
          <svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          <h3 class="empty-state-title">No Overdue Items Found</h3>
          <p class="empty-state-desc">${searchQuery ? 'No items match your search filter "' + searchQuery + '". Try clearing your search.' : 'All services, incidents, support plans, and goals in this section are currently up to date!'}</p>
        </div>
      `;
      return;
    }

    items.forEach((item, index) => {
      const card = document.createElement('article');
      card.className = `card-item ${item.categoryClass}`;
      card.id = `card-${item.category}-${index}`;

      if (item.rows) {
        card.innerHTML = renderResidentListCard(item, index);
      } else card.innerHTML = `
        <div class="card-top">
          <div class="resident-info">
            <div class="avatar-circle">${getInitials(item.resident)}</div>
            <div>
              <h2 class="resident-name">${escapeHTML(item.resident || 'Resident')}</h2>
              ${staffLine(item)}
            </div>
          </div>
          <span class="card-category-tag">${escapeHTML(item.categoryLabel)}</span>
        </div>

        <h3 class="card-title">${escapeHTML(item.title || 'Untitled Item')}</h3>

        <div class="card-meta-line">
          <span class="meta-chip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:13px;height:13px"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            ${escapeHTML(item.date || 'Recent')}
          </span>
          <span>•</span>
          <span class="meta-chip">${escapeHTML(item.extraText || '')}</span>
        </div>

        <p class="card-summary-snippet">${escapeHTML(item.summary || item.details || 'No additional summary recorded.')}</p>

        <div class="card-bottom">
          <span class="status-pill ${item.statusClass}">${escapeHTML(item.status || 'Active')}</span>
          <button class="btn-card-action" data-index="${index}">View Details</button>
        </div>
      `;

      // Attach Click for Modal
      card.querySelector('.btn-card-action').addEventListener('click', () => {
        openModal(item);
      });

      cardsGrid.appendChild(card);
    });
  }

  // Compact per-resident card (support plans, goals): initials, overdue count, one short line per item
  const RESIDENT_CARD_PREVIEW = 4;

  function renderResidentListCard(item, index) {
    const rows = item.rows || [];
    const shown = rows.slice(0, RESIDENT_CARD_PREVIEW);
    const hidden = rows.length - shown.length;

    return `
      <div class="card-top">
        <div class="resident-info">
          <div class="avatar-circle">${escapeHTML(item.initials || getInitials(item.resident))}</div>
          <div>
            <h2 class="resident-name">${escapeHTML(item.resident || 'Resident')}</h2>
            ${staffLine(item)}
          </div>
        </div>
        <span class="status-pill ${item.statusClass}">${rows.length} overdue</span>
      </div>

      <ul class="plan-list">
        ${shown.map(r => `
          <li class="plan-row">
            <span class="plan-name" title="${escapeHTML(r.name)}">${escapeHTML(r.name)}</span>
            <span class="plan-overdue">${escapeHTML(r.right)}</span>
          </li>`).join('')}
      </ul>

      <div class="card-bottom">
        <span class="plan-more">${hidden > 0 ? `+${hidden} more` : ''}</span>
        <button class="btn-card-action" data-index="${index}">View All</button>
      </div>
    `;
  }

  // "Key worker: Name" line shown under the resident name on every card
  function staffLine(item) {
    if (!item.staff_name) return '';
    return `<span class="staff-line" title="Key worker">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
      Key worker: <strong>${escapeHTML(item.staff_name)}</strong>
    </span>`;
  }

  // ---------------------------------------------------------------- Email the key worker
  // Email is sent by server.py (the recipient address never reaches the browser).
  // On a static host (e.g. GitHub Pages) there is no backend, so the button is disabled.
  const modalStaff = document.getElementById('modal-staff');
  const emailBtn = document.getElementById('modal-email-btn');
  const emailBtnLabel = document.getElementById('modal-email-label');
  const emailForm = document.getElementById('email-form');
  const emailStaffName = document.getElementById('email-staff-name');
  const emailSenderName = document.getElementById('email-sender-name');
  const emailSender = document.getElementById('email-sender');
  const emailNote = document.getElementById('email-note');
  const emailCopy = document.getElementById('email-copy');
  const emailStatus = document.getElementById('email-status');
  const emailSendBtn = document.getElementById('email-send-btn');
  const emailCancelBtn = document.getElementById('email-cancel-btn');

  const SENDER_KEY = 'carelink-email-sender';
  let emailEnabled = false;
  let modalItem = null;

  function rememberSender(name, email) {
    try { localStorage.setItem(SENDER_KEY, JSON.stringify({ name, email })); } catch { /* storage unavailable */ }
  }
  function recallSender() {
    try { return JSON.parse(localStorage.getItem(SENDER_KEY) || '{}'); } catch { return {}; }
  }

  async function checkEmailAvailable() {
    try {
      const resp = await fetch('/api/email-status', { cache: 'no-store' });
      emailEnabled = resp.ok && (await resp.json()).enabled === true;
    } catch {
      emailEnabled = false;
    }
  }

  function setEmailStatus(text, kind = '') {
    emailStatus.textContent = text;
    emailStatus.className = `email-status ${kind}`;
  }

  function resetEmailForm() {
    emailForm.hidden = true;
    emailNote.value = '';
    setEmailStatus('');
    emailSendBtn.disabled = false;
    emailSendBtn.textContent = 'Send email';
  }

  function configureEmailButton(item) {
    const staff = item.staff_name;
    emailBtnLabel.textContent = staff ? `Email ${staff}` : 'No key worker on file';
    emailStaffName.textContent = staff || 'key worker';
    emailBtn.disabled = !staff || !emailEnabled;
    emailBtn.title = !staff
      ? 'No key worker is assigned to this resident'
      : (!emailEnabled ? 'Email sending is available when the dashboard runs on the CareLink server (server.py)' : '');
  }

  function openEmailForm() {
    const saved = recallSender();
    if (saved.email && !emailSender.value) emailSender.value = saved.email;
    if (saved.name && !emailSenderName.value) emailSenderName.value = saved.name;
    emailForm.hidden = false;
    setEmailStatus('');
    (emailSender.value ? emailNote : emailSender).focus();
    emailForm.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  async function sendEmail(e) {
    e.preventDefault();
    if (!modalItem) return;

    const senderEmail = emailSender.value.trim();
    const senderName = emailSenderName.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(senderEmail)) {
      setEmailStatus('Please enter a valid email address.', 'error');
      emailSender.focus();
      return;
    }

    emailSendBtn.disabled = true;
    emailSendBtn.textContent = 'Sending...';
    setEmailStatus('');

    try {
      const resp = await fetch('/api/send-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section: modalItem.section,
          item_id: modalItem.id,
          sender_email: senderEmail,
          sender_name: senderName,
          note: emailNote.value.trim(),
          copy_sender: emailCopy.checked
        })
      });
      const result = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(result.error || 'The email could not be sent.');

      rememberSender(senderName, senderEmail);
      setEmailStatus(`Email sent to ${result.staff_name || modalItem.staff_name}.`, 'success');
      showToast(`✉ Email sent to ${result.staff_name || modalItem.staff_name}`);
      emailSendBtn.textContent = 'Sent';
      setTimeout(resetEmailForm, 2500);
    } catch (err) {
      setEmailStatus(err.message || 'The email could not be sent.', 'error');
      emailSendBtn.disabled = false;
      emailSendBtn.textContent = 'Send email';
    }
  }

  emailBtn.addEventListener('click', () => (emailForm.hidden ? openEmailForm() : resetEmailForm()));
  emailCancelBtn.addEventListener('click', resetEmailForm);
  emailSender.addEventListener('input', () => { if (emailStatus.classList.contains('error')) setEmailStatus(''); });
  emailForm.addEventListener('submit', sendEmail);

  // Open Modal Details
  function openModal(item) {
    modalItem = item;
    modalCategoryBadge.textContent = item.categoryLabel;
    modalCategoryBadge.className = `badge ${item.categoryClass}`;

    modalStatusBadge.textContent = item.status || 'Active';
    modalStatusBadge.className = `badge ${item.statusClass}`;

    modalTitle.textContent = item.title || 'Item Details';
    modalResident.textContent = item.resident || '--';
    modalDate.textContent = item.date || '--';
    modalExtra.textContent = item.extraText || '--';
    modalStaff.textContent = item.staff_name || 'Not assigned';
    modalDetails.textContent = item.summary || item.details || 'No additional details logged.';

    resetEmailForm();
    configureEmailButton(item);

    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeModal() {
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    modalItem = null;
    resetEmailForm();
  }

  // Helper Escape HTML
  function escapeHTML(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Event Listeners Setup
  function setupEvents() {
    // Manual Refresh Button triggers live scrape on click
    btnRefresh.addEventListener('click', triggerLiveScrape);

    // Tab Navigation
    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeTab = btn.dataset.tab;
        performPushReload(currentData);
      });
    });

    // KPI Cards Click to Filter
    document.querySelectorAll('.kpi-card').forEach(kpi => {
      kpi.addEventListener('click', () => {
        const filter = kpi.dataset.filter;
        if (!filter) return;
        activeTab = filter;
        tabBtns.forEach(b => {
          b.classList.toggle('active', b.dataset.tab === filter);
        });
        performPushReload(currentData);
      });
    });

    // Search Input
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      searchClearBtn.classList.toggle('visible', searchQuery.length > 0);
      renderCards(currentData);
    });

    searchClearBtn.addEventListener('click', () => {
      searchInput.value = '';
      searchQuery = '';
      searchClearBtn.classList.remove('visible');
      renderCards(currentData);
    });

    // Modal Close
    modalCloseBtn.addEventListener('click', closeModal);
    modalOkBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && modal.classList.contains('open')) {
        closeModal();
      }
    });

    // Countdown interval (1s)
    setInterval(updateCountdown, 1000);

    // Auto-poll data.json every 8 seconds for background file updates
    setInterval(() => {
      fetchData(false);
    }, 8000);
  }

  // Initialization
  setupEvents();
  checkEmailAvailable();
  fetchData(true);
})();
