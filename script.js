
const BACKEND_URL = 'http://localhost:5000'; 

// GLOBALS
let currentUser = null;
let savedBills = JSON.parse(localStorage.getItem('savedBills') || '[]');
let userSettings = JSON.parse(localStorage.getItem('userSettings') || '{"ageGroup":"adult","autoSave":false,"detailLevel":"detailed"}');
let currentQuery = '';
let currentPage = 1;
let hasMoreBills = false;
let isLoading = false;
let allLoadedBills = [];
let modelsReady = false;

// ------------------ AUTH & TABS ------------------
function switchTab(tab) {
  const signinForm = document.getElementById('signinForm');
  const signupForm = document.getElementById('signupForm');
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => btn.classList.remove('active'));
  if (tab === 'signin') {
    signinForm && signinForm.classList.add('active');
    signupForm && signupForm.classList.remove('active');
    if (tabBtns[0]) tabBtns[0].classList.add('active');
  } else {
    signupForm && signupForm.classList.add('active');
    signinForm && signinForm.classList.remove('active');
    if (tabBtns[tabBtns.length - 1]) tabBtns[tabBtns.length - 1].classList.add('active');
  }
  clearAuthError();
}

async function signIn() {
  const email = (document.getElementById('signinEmail') || {}).value?.trim() || '';
  const password = (document.getElementById('signinPassword') || {}).value || '';
  const btn = document.getElementById('signinBtn');
  if (!email || !password) { showAuthError('Please fill in all fields'); return; }


  btn && (btn.disabled = true);
  btn && (btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Signing in...</span>');

  try {
    await window.signInWithEmailAndPassword(window.firebaseAuth, email, password);
    clearAuthError();
  } catch (error) {
    console.error('Sign in error:', error);
    showAuthError(getAuthErrorMessage(error.code));
  } finally {
    btn && (btn.disabled = false);
    btn && (btn.innerHTML = '<i class="fas fa-sign-in-alt"></i><span>Sign In</span>');
  }
}

async function signUp() {
  const name = (document.getElementById('signupName') || {}).value?.trim() || '';
  const email = (document.getElementById('signupEmail') || {}).value?.trim() || '';
  const password = (document.getElementById('signupPassword') || {}).value || '';
  const confirmPassword = (document.getElementById('confirmPassword') || {}).value || '';
  const btn = document.getElementById('signupBtn');

  if (!name || !email || !password || !confirmPassword) { showAuthError('Please fill in all fields'); return; }
  if (password !== confirmPassword) { showAuthError('Passwords do not match'); return; }
  if (password.length < 6) { showAuthError('Password must be at least 6 characters'); return; }

  if (!window.firebaseAuth || !window.createUserWithEmailAndPassword) {
    showAuthError('Signup requires Firebase. Use demo login or load Firebase SDK.');
    return;
  }

  btn && (btn.disabled = true);
  btn && (btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Creating account...</span>');

  try {
    const userCredential = await window.createUserWithEmailAndPassword(window.firebaseAuth, email, password);
    if (window.updateProfile) await window.updateProfile(userCredential.user, { displayName: name });
    clearAuthError();
  } catch (error) {
    console.error('Sign up error:', error);
    showAuthError(getAuthErrorMessage(error.code));
  } finally {
    btn && (btn.disabled = false);
    btn && (btn.innerHTML = '<i class="fas fa-user-plus"></i><span>Create Account</span>');
  }
}



async function signOut() {
  try {
    if (window.firebaseAuth && window.firebaseSignOut) await window.firebaseSignOut(window.firebaseAuth);
    hideDropdown();
    currentUser = null;
    showLoginScreen();
  } catch (error) { console.error('Sign out error:', error); }
}

async function resetPassword() {
  const email = (document.getElementById('signinEmail') || {}).value?.trim() || '';
  if (!email) { showAuthError('Please enter your email address first'); return; }
  if (!window.firebaseAuth || !window.sendPasswordResetEmail) { showAuthError('Password reset requires Firebase.'); return; }
  try {
    await window.sendPasswordResetEmail(window.firebaseAuth, email);
    showAuthError('Password reset email sent! Check your inbox.', 'success');
  } catch (error) {
    console.error('Reset password error:', error);
    showAuthError(getAuthErrorMessage(error.code));
  }
}

// ------------------ UI HELPERS ------------------
function showAuthError(message, type = 'error') {
  const errorDiv = document.getElementById('authError');
  if (!errorDiv) return;
  errorDiv.textContent = message;
  errorDiv.className = `auth-error show ${type}`;
  if (type === 'success') {
    errorDiv.style.background = 'linear-gradient(135deg, #f0fff4, #c6f6d5)';
    errorDiv.style.borderColor = '#68d391';
    errorDiv.style.color = '#2f855a';
  } else {
    errorDiv.style.background = '';
    errorDiv.style.borderColor = '';
    errorDiv.style.color = '';
  }
}

function clearAuthError() {
  const errorDiv = document.getElementById('authError');
  if (!errorDiv) return;
  errorDiv.classList.remove('show');
  errorDiv.style.background = '';
  errorDiv.style.borderColor = '';
  errorDiv.style.color = '';
  errorDiv.textContent = '';
}

function getAuthErrorMessage(errorCode) {
  switch (errorCode) {
    case 'auth/user-not-found': return 'No account found with this email address';
    case 'auth/wrong-password': return 'Incorrect password';
    case 'auth/email-already-in-use': return 'An account with this email already exists';
    case 'auth/weak-password': return 'Password is too weak';
    case 'auth/invalid-email': return 'Invalid email address';
    case 'auth/too-many-requests': return 'Too many failed attempts. Please try again later';
    case 'auth/popup-closed-by-user': return 'Sign-in popup was closed';
    default: return 'An error occurred. Please try again';
  }
}

function showLoginScreen() {
  const login = document.getElementById('loginScreen');
  const loading = document.getElementById('loadingScreen');
  const main = document.getElementById('mainApp');
  if (login) login.style.display = 'flex';
  if (loading) loading.style.display = 'none';
  if (main) main.style.display = 'none';
}

function demoLogin() {
  const demoUser = { displayName: 'Demo User', email: 'demo@billfinder.ai', photoURL: null, uid: 'demo-user-123' };
  currentUser = demoUser;
  showMainApp(demoUser);
}

function showMainApp(user) {
  currentUser = user;
  const login = document.getElementById('loginScreen');
  const loading = document.getElementById('loadingScreen');
  const main = document.getElementById('mainApp');
  if (login) login.style.display = 'none';
  if (loading) loading.style.display = 'none';
  if (main) main.style.display = 'flex';
  updateUserInfo(user);
  checkModelsReady();
}

function updateUserInfo(user) {
  const userName = document.getElementById('userName');
  const userAvatar = document.getElementById('userAvatar');
  if (userName) userName.textContent = user.displayName || (user.email || '').split('@')[0];
  if (userAvatar) userAvatar.src = user.photoURL || `https://ui-avatars.com/api/?name=${encodeURIComponent(user.displayName || user.email || 'User')}&background=667eea&color=fff`;
}

function toggleDropdown() {
  const dropdown = document.getElementById('dropdownMenu');
  const userInfo = document.getElementById('userInfo');
  dropdown && dropdown.classList.toggle('show');
  userInfo && userInfo.classList.toggle('active');
}
function hideDropdown() {
  const dropdown = document.getElementById('dropdownMenu');
  const userInfo = document.getElementById('userInfo');
  dropdown && dropdown.classList.remove('show');
  userInfo && userInfo.classList.remove('active');
}
function showSavedBills() { hideDropdown(); displaySavedBills(); }

// ------------------ SAVED BILLS ------------------
function saveBill(bill) {
  const billId = bill.number;
  if (savedBills.find(b => b.number === billId)) { showNotification('Bill already saved!', 'info'); return; }
  savedBills.push({ ...bill, savedAt: new Date().toISOString() });
  localStorage.setItem('savedBills', JSON.stringify(savedBills));
  showNotification('Bill saved successfully!', 'success');
  updateSaveButton(billId, true);
}
function removeSavedBill(billNumber) {
  savedBills = savedBills.filter(b => b.number !== billNumber);
  localStorage.setItem('savedBills', JSON.stringify(savedBills));
  showNotification('Bill removed from saved list', 'info');
  updateSaveButton(billNumber, false);
}
function updateSaveButton(billNumber, isSaved) {
  const saveBtn = document.querySelector(`[data-bill="${billNumber}"] .save-btn`);
  if (!saveBtn) return;
  if (isSaved) {
    saveBtn.innerHTML = '<i class="fas fa-bookmark"></i> Saved';
    saveBtn.classList.add('saved');
  } else {
    saveBtn.innerHTML = '<i class="far fa-bookmark"></i> Save';
    saveBtn.classList.remove('saved');
  }
}
function displaySavedBills() {
  const billsContainer = document.getElementById('billsContainer');
  if (!billsContainer) return;
  if (savedBills.length === 0) {
    billsContainer.innerHTML = `
      <div class="empty-state"><div class="empty-state-icon">📚</div><h3>No Saved Bills</h3><p>Bills you save will appear here for easy access</p></div>`;
    return;
  }
  const header = `<div class="results-header"><h2><i class="fas fa-bookmark"></i> Your Saved Bills (${savedBills.length})</h2><p>Bills you've bookmarked for later reference</p></div>`;
  const billsHTML = savedBills.map((bill, index) => createBillCardHTML(bill, index, true)).join('');
  billsContainer.innerHTML = header + `<div class="bills-grid">${billsHTML}</div>`;
}

// ------------------ NOTIFICATIONS ------------------
function showNotification(message, type = 'info') {
  const notification = document.createElement('div');
  notification.className = `notification ${type}`;
  notification.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i><span>${message}</span>`;
  document.body.appendChild(notification);
  setTimeout(() => notification.classList.add('show'), 100);
  setTimeout(() => { notification.classList.remove('show'); setTimeout(() => { try { document.body.removeChild(notification); } catch (e) { } }, 300); }, 3000);
}

// ------------------ INITIALIZE MAIN APP ------------------
function initializeMainApp() {
  updateUserInfo(currentUser);
  const searchInput = document.getElementById('searchInput');
  if (searchInput) searchInput.addEventListener('keypress', function (e) { if (e.key === 'Enter') searchBills(); });

  const billsContainer = document.getElementById('billsContainer');
  if (billsContainer && !billsContainer.innerHTML.trim()) {
    billsContainer.innerHTML = `<div class="empty-state"><div class="empty-state-icon">🏛️</div><h3>Discover Congressional Bills</h3><p>Enter a topic above to find and browse recent congressional legislation with AI-generated summaries and semantic matching</p></div>`;
  }

  const quizBtn = document.getElementById('quizBtn'); if (quizBtn) quizBtn.onclick = generateQuiz;
  const quizClose = document.getElementById('quizClose'); if (quizClose) quizClose.onclick = closeQuiz;
  const chatInput = document.getElementById('chatInput'); if (chatInput) chatInput.addEventListener('keypress', handleChatKeypress);
}

// ------------------ UTIL ------------------
function parseDate(dateStr) {
  if (!dateStr || dateStr === 'N/A') return new Date(0);
  const formats = [/(\d{1,2})\/(\d{1,2})\/(\d{4})/, /(\d{4})-(\d{1,2})-(\d{1,2})/];
  for (let format of formats) {
    const match = dateStr.match(format);
    if (match) {
      if (format === formats[0]) return new Date(match[3], match[1] - 1, match[2]);
      else return new Date(match[1], match[2] - 1, match[3]);
    }
  }
  const yearMatch = dateStr.match(/(\d{4})/);
  if (yearMatch) return new Date(yearMatch[1], 0, 1);
  return new Date(0);
}

function escapeHtml(text) {
  if (text === undefined || text === null) return '';
  const div = document.createElement('div'); div.textContent = String(text); return div.innerHTML;
}

// ------------------ SEARCH / BILLS ------------------
async function searchBills(loadMore = false) {
  const query = (document.getElementById('searchInput') || {}).value?.trim() || '';
  const billsContainer = document.getElementById('billsContainer');
  const errorContainer = document.getElementById('errorContainer');
  const searchBtn = document.getElementById('searchBtn');

  if (!loadMore) {
    errorContainer && (errorContainer.innerHTML = '');
    currentPage = 1; allLoadedBills = []; currentQuery = query;
  }

  if (!query) {
    if (errorContainer) errorContainer.innerHTML = '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> Please enter a search term</div>';
    return;
  }

  if (isLoading) return;
  isLoading = true;

  if (!loadMore) { searchBtn && (searchBtn.disabled = true); if (billsContainer) billsContainer.innerHTML = '<div class="loading"><div class="spinner"></div><div>🚀 AI is quickly finding the most relevant bills...</div></div>'; }
  else { const loadMoreBtn = document.getElementById('loadMoreBtn'); if (loadMoreBtn) { loadMoreBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading more...'; loadMoreBtn.disabled = true; } }

  try {
    const response = await fetch(`${BACKEND_URL}/search_bills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, page: currentPage, per_page: 5 })
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `API error: ${response.status}`);
    }

    const data = await response.json();
    if (!data.bills || data.bills.length === 0) {
      if (!loadMore) throw new Error('No relevant bills found. Try a different search term or broader keywords.');
      return;
    }

    const bills = data.bills.map(bill => ({
      number: bill.number ? `H.R. ${bill.number}` : 'Unknown',
      title: bill.title || 'No title',
      sponsor: bill.sponsor || 'N/A',
      status: bill.status || 'N/A',
      date: bill.date || 'N/A',
      summary: bill.summary || '',
      relevance: bill.relevance_score || 0,
      url: bill.url || '',
      dateObj: parseDate(bill.date)
    }));

    allLoadedBills = loadMore ? [...allLoadedBills, ...bills] : bills;
    hasMoreBills = !!data.has_more;
    currentPage++;

    displayBills(allLoadedBills, query, data.total_found);
    updateNavStats(allLoadedBills.length, data.total_found);
  } catch (error) {
    console.error('Search error:', error);
    if (!loadMore) {
      billsContainer && (billsContainer.innerHTML = '');
      errorContainer && (errorContainer.innerHTML = `<div class="error-message"><i class="fas fa-exclamation-circle"></i> ${escapeHtml(error.message)}</div>`);
    } else {
      showNotification('Failed to load more bills', 'error');
    }
  } finally {
    isLoading = false;
    if (!loadMore) { searchBtn && (searchBtn.disabled = false); if (searchBtn) searchBtn.innerHTML = '<i class="fas fa-search"></i><span>Search</span>'; }
    else { const loadMoreBtn = document.getElementById('loadMoreBtn'); if (loadMoreBtn) { loadMoreBtn.innerHTML = '<i class="fas fa-plus"></i> Load More Bills'; loadMoreBtn.disabled = false; } }
  }
}

function loadMoreBills() { if (hasMoreBills && !isLoading) searchBills(true); }
function searchCategory(category) { const input = document.getElementById('searchInput'); if (input) input.value = category; searchBills(); }

function displayBills(bills, query, totalFound = null) {
  const billsContainer = document.getElementById('billsContainer');
  if (!billsContainer) return;
  const showingText = totalFound && totalFound > bills.length ? `Showing ${bills.length} of ${totalFound} bills` : `Found ${bills.length} bills`;
  const resultsHeader = `<div class="results-header"><h2><i class="fas fa-search"></i> ${showingText} for "${escapeHtml(query)}"</h2><p>Results sorted by date (newest first) and relevance • Click any bill to chat with AI about it</p></div>`;
  const billsHTML = bills.map((bill, index) => createBillCardHTML(bill, index, false)).join('');
  const loadMoreButton = hasMoreBills ? `<div class="load-more-container"><button class="load-more-btn" id="loadMoreBtn" onclick="loadMoreBills()"><i class="fas fa-plus"></i> Load More Bills</button><p class="load-more-text">Loading 5 bills at a time for faster performance</p></div>` : '';
  billsContainer.innerHTML = resultsHeader + `<div class="bills-grid">${billsHTML}</div>` + loadMoreButton;

  if (userSettings.autoSave) bills.forEach(b => { if (b.relevance > 0.7) saveBill(b); });
}

function createBillCardHTML(bill, index, isSavedView = false) {
  const relevancePercent = Math.round((bill.relevance || 0) * 100);
  const relevanceColor = relevancePercent > 70 ? '#51cf66' : relevancePercent > 50 ? '#ffd43b' : '#ff6b6b';
  const isSaved = savedBills.find(b => b.number === bill.number);
  const personalizedScore = bill.personalized_score ? Math.round(bill.personalized_score * 100) : null;

  return `
    <div class="bill-card enhanced" style="animation-delay: ${index * 0.1}s" data-bill="${escapeHtml(bill.number || '')}">
      <div class="relevance-badge" style="background-color: ${relevanceColor}">${relevancePercent}%</div>
      ${personalizedScore ? `<div class="personalized-badge">📍 ${personalizedScore}% match</div>` : ''}
      
      <div class="bill-header">
        <div class="bill-number">${escapeHtml(bill.number)}</div>
        <div class="bill-title">${escapeHtml(bill.title)}</div>
      </div>
      
      <div class="bill-summary">${escapeHtml(bill.summary)}</div>
      
      <div class="bill-meta">
        <div class="meta-item"><span><i class="fas fa-clipboard-list"></i></span><span class="bill-status" data-bill="${escapeHtml(bill.number)}">${escapeHtml(bill.status)}</span></div>
        <div class="meta-item"><span><i class="fas fa-user-tie"></i></span><span class="bill-sponsor" data-bill="${escapeHtml(bill.number)}">${escapeHtml(bill.sponsor)}</span></div>
        <div class="meta-item"><span><i class="fas fa-calendar-alt"></i></span><span class="bill-date" data-bill="${escapeHtml(bill.number)}">${escapeHtml(bill.date)}</span></div>
      </div>
      
      <div class="enhanced-features">
        <button class="feature-btn timeline-btn" onclick="event.stopPropagation(); showBillTimeline('${escapeHtml(bill.number)}')">
          <i class="fas fa-history"></i> Timeline
        </button>
        <button class="feature-btn heatmap-btn" onclick="event.stopPropagation(); showVotingHeatmap('${escapeHtml(bill.number)}')">
          <i class="fas fa-map"></i> Voting
        </button>
      </div>
      
      <div class="bill-actions">
        <button class="view-bill-btn" ${isSaved ? 'saved' : ''}" onclick="event.stopPropagation(); ${isSaved ? `removeSavedBill('${escapeHtml(bill.number)}')` : `saveBill(${JSON.stringify(bill).replace(/"/g, '&quot;')})`}"><i class="fas fa-bookmark"></i>${isSaved ? 'Saved' : 'Save'}</button>
        ${bill.url ? `<a href="${escapeHtml(bill.url)}" target="_blank" class="view-bill-btn" onclick="event.stopPropagation()"><i class="fas fa-external-link-alt"></i> View Full</a>` : ''}
        ${isSavedView ? `<button class="view-bill-btn" onclick="event.stopPropagation(); removeSavedBill('${escapeHtml(bill.number)}')"><i class="fas fa-trash"></i> Remove</button>` : ''}
      </div>
    </div>`;
}

async function loadBillDetails(billNumber) {
  try {
    const response = await fetch(`${BACKEND_URL}/get_bill_details`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bill_number: (billNumber || '').replace('H.R. ', '') })
    });
    if (!response.ok) return;
    const data = await response.json();
    const details = data.details || {};
    const billCard = document.querySelector(`[data-bill="${billNumber}"]`);
    if (billCard) {
      const statusEl = billCard.querySelector('.bill-status');
      const sponsorEl = billCard.querySelector('.bill-sponsor');
      const dateEl = billCard.querySelector('.bill-date');
      if (statusEl && details.status) statusEl.textContent = details.status;
      if (sponsorEl && details.sponsor) sponsorEl.textContent = details.sponsor;
      if (dateEl && details.date) dateEl.textContent = details.date;
    }
  } catch (error) { console.error('Error loading bill details:', error); }
}

function handleChatKeypress(event) { if (event.key === 'Enter') sendChatMessage(); }

// ------------------ GLOBAL EVENT HANDLERS ------------------
document.addEventListener('click', function (event) {
  const userMenu = document.querySelector('.user-menu');
  if (userMenu && !userMenu.contains(event.target)) hideDropdown();
  if (event.target === settingsModal) closeSettings();
});

document.addEventListener('keypress', function (e) {
  if (e.key === 'Enter') {
    const activeForm = document.querySelector('.auth-form.active');
    if (activeForm) {
      if (activeForm.id === 'signinForm') signIn();
      else if (activeForm.id === 'signupForm') signUp();
    }
  }
});

function updateNavStats(billCount, totalFound = null) {
  const navStats = document.getElementById('navStats');
  if (!navStats) return;
  const displayText = (totalFound && totalFound > billCount) ? `${billCount}/${totalFound} Results` : `${billCount} Results`;
  navStats.innerHTML = `
    <span class="stat-item"><i class="fas fa-check-circle"></i><span>${escapeHtml(displayText)}</span></span>
    <span class="stat-item"><i class="fas fa-zap"></i><span>Fast Load</span></span>
  `;
}

// ------------------ ENHANCED FEATURES ------------------

// Bill Timeline
async function showBillTimeline(billNumber) {
  try {
    const response = await fetch(`${BACKEND_URL}/bill_progression`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bill_number: billNumber.replace('H.R. ', '') })
    });

    if (!response.ok) throw new Error('Failed to get bill timeline');

    const data = await response.json();
    displayTimelineModal(data);
  } catch (error) {
    console.error('Timeline error:', error);
    showNotification('Failed to load bill timeline', 'error');
  }
}

function displayTimelineModal(data) {
  const modal = createModal('timeline-modal', `Bill ${data.bill_number} Timeline`);
  const progression = data.progression || [];

  const content = `
    <div class="bill-timeline">
      <div class="timeline-header">
        <h3>Legislative Progress</h3>
        <p>${progression.length} actions tracked</p>
      </div>
      
      <div class="timeline-container">
        ${progression.map((item, index) => `
          <div class="timeline-item ${index === 0 ? 'latest' : ''}">
            <div class="timeline-marker stage-${item.stage}">
              <i class="fas fa-${getStageIcon(item.stage)}"></i>
            </div>
            <div class="timeline-content">
              <div class="timeline-date">${formatDate(item.date)}</div>
              <div class="timeline-status">${item.status}</div>
              <div class="timeline-description">${item.description}</div>
            </div>
          </div>
        `).join('')}
      </div>
      
      <div class="stage-legend">
        <div class="legend-item"><span class="legend-marker stage-1"></span>Introduced</div>
        <div class="legend-item"><span class="legend-marker stage-2"></span>Committee</div>
        <div class="legend-item"><span class="legend-marker stage-3"></span>Floor Vote</div>
        <div class="legend-item"><span class="legend-marker stage-4"></span>Passed House</div>
        <div class="legend-item"><span class="legend-marker stage-5"></span>Senate</div>
        <div class="legend-item"><span class="legend-marker stage-6"></span>Signed/Vetoed</div>
      </div>
    </div>
  `;

  modal.querySelector('.modal-body').innerHTML = content;
  document.body.appendChild(modal);
}

function getStageIcon(stage) {
  const icons = {
    1: 'file-alt',
    2: 'users',
    3: 'gavel',
    4: 'check',
    5: 'building',
    6: 'signature'
  };
  return icons[stage] || 'circle';
}

// Voting Heatmap
async function showVotingHeatmap(billNumber) {
  try {
    const response = await fetch(`${BACKEND_URL}/voting_heatmap`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bill_number: billNumber.replace('H.R. ', '') })
    });

    if (!response.ok) throw new Error('Failed to get voting data');

    const data = await response.json();
    displayHeatmapModal(data);
  } catch (error) {
    console.error('Heatmap error:', error);
    showNotification('Failed to load voting heatmap', 'error');
  }
}

function displayHeatmapModal(data) {
  const modal = createModal('heatmap-modal', 'Voting Patterns by State');
  const votingData = data.voting_data;

  const content = `
    <div class="voting-heatmap">
      <div class="heatmap-header">
        <h3>State-by-State Support</h3>
        <p>Voting patterns for ${data.bill_number}</p>
      </div>
      
      <div class="heatmap-legend">
        <span>Low Support</span>
        <div class="legend-gradient"></div>
        <span>High Support</span>
      </div>
      
      <div class="heatmap-grid">
        ${Object.entries(votingData).map(([state, votes]) => `
          <div class="state-item" style="background-color: ${getHeatmapColor(votes.support_percentage)}" title="${state}: ${votes.support_percentage}% support">
            <span class="state-code">${state}</span>
            <span class="support-percent">${votes.support_percentage}%</span>
          </div>
        `).join('')}
      </div>
      
      <div class="voting-summary">
        <div class="summary-stats">
          <div class="stat-item">
            <span class="stat-label">Average Support:</span>
            <span class="stat-value">${calculateAverageSupport(votingData)}%</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">States Above 60%:</span>
            <span class="stat-value">${countHighSupport(votingData)}</span>
          </div>
        </div>
      </div>
      
      <div class="heatmap-disclaimer">
        <p><i class="fas fa-info-circle"></i> This is sample data for demonstration. Real implementation would use actual congressional voting records.</p>
      </div>
    </div>
  `;

  modal.querySelector('.modal-body').innerHTML = content;
  document.body.appendChild(modal);
}

function getHeatmapColor(percentage) {
  const intensity = percentage / 100;
  const red = Math.round(255 * (1 - intensity));
  const green = Math.round(255 * intensity);
  return `rgb(${red}, ${green}, 100)`;
}

function calculateAverageSupport(votingData) {
  const values = Object.values(votingData);
  const average = values.reduce((sum, vote) => sum + vote.support_percentage, 0) / values.length;
  return Math.round(average);
}

function countHighSupport(votingData) {
  return Object.values(votingData).filter(vote => vote.support_percentage > 60).length;
}

// Utility Functions
function createModal(id, title) {
  // Remove existing modal if present
  const existing = document.getElementById(id);
  if (existing) existing.remove();

  const modal = document.createElement('div');
  modal.id = id;
  modal.className = 'enhanced-modal';
  modal.innerHTML = `
    <div class="modal-overlay" onclick="closeModal('${id}')"></div>
    <div class="modal-content">
      <div class="modal-header">
        <h2>${title}</h2>
        <button class="modal-close" onclick="closeModal('${id}')">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div class="modal-body"></div>
    </div>
  `;

  return modal;
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('closing');
    setTimeout(() => modal.remove(), 300);
  }
}

function formatDate(dateStr) {
  if (!dateStr || dateStr === 'N/A') return 'Unknown date';

  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  } catch (error) {
    return dateStr;
  }
}


// Initialize enhanced features when main app loads
function initializeEnhancedFeatures() {
  addPersonalizedFeedButton();
}

// Call initialization when main app is ready
const originalInitializeMainApp = initializeMainApp;
initializeMainApp = function () {
  originalInitializeMainApp();
  initializeEnhancedFeatures();
};

