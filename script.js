// Configuration - update this to your Flask backend URL
const BACKEND_URL = 'http://localhost:5000';

// Global variables
let currentUser = null;
let savedBills = JSON.parse(localStorage.getItem('savedBills') || '[]');
let userSettings = JSON.parse(localStorage.getItem('userSettings') || '{"ageGroup": "adult", "autoSave": false, "detailLevel": "detailed"}');
let currentChatBill = null;
let currentQuiz = null;
let currentQuestionIndex = 0;
let quizScore = 0;

function switchTab(tab) {
    const signinForm = document.getElementById('signinForm');
    const signupForm = document.getElementById('signupForm');
    const tabBtns = document.querySelectorAll('.tab-btn');

    tabBtns.forEach(btn => btn.classList.remove('active'));

    if (tab === 'signin') {
        signinForm.classList.add('active');
        signupForm.classList.remove('active');
        document.querySelector('.tab-btn:first-child').classList.add('active');
    } else {
        signupForm.classList.add('active');
        signinForm.classList.remove('active');
        document.querySelector('.tab-btn:last-child').classList.add('active');
    }

    clearAuthError();
}

async function signIn() {
    const email = document.getElementById('signinEmail').value.trim();
    const password = document.getElementById('signinPassword').value;
    const btn = document.getElementById('signinBtn');

    if (!email || !password) {
        showAuthError('Please fill in all fields');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Signing in...</span>';

    try {
        await window.signInWithEmailAndPassword(window.firebaseAuth, email, password);
        clearAuthError();
    } catch (error) {
        showAuthError(getAuthErrorMessage(error.code));
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sign-in-alt"></i><span>Sign In</span>';
    }
}

async function signUp() {
    const name = document.getElementById('signupName').value.trim();
    const email = document.getElementById('signupEmail').value.trim();
    const password = document.getElementById('signupPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const btn = document.getElementById('signupBtn');

    if (!name || !email || !password || !confirmPassword) {
        showAuthError('Please fill in all fields');
        return;
    }

    if (password !== confirmPassword) {
        showAuthError('Passwords do not match');
        return;
    }

    if (password.length < 6) {
        showAuthError('Password must be at least 6 characters');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Creating account...</span>';

    try {
        const userCredential = await window.createUserWithEmailAndPassword(window.firebaseAuth, email, password);
        await window.updateProfile(userCredential.user, { displayName: name });
        clearAuthError();
    } catch (error) {
        showAuthError(getAuthErrorMessage(error.code));
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-user-plus"></i><span>Create Account</span>';
    }
}

async function signInWithGoogle() {
    try {
        await window.signInWithPopup(window.firebaseAuth, window.googleProvider);
        clearAuthError();
    } catch (error) {
        showAuthError(getAuthErrorMessage(error.code));
    }
}

async function signOut() {
    try {
        await window.firebaseSignOut(window.firebaseAuth);
        hideDropdown();
    } catch (error) {
        console.error('Sign out error:', error);
    }
}

async function resetPassword() {
    const email = document.getElementById('signinEmail').value.trim();

    if (!email) {
        showAuthError('Please enter your email address first');
        return;
    }

    try {
        await window.sendPasswordResetEmail(window.firebaseAuth, email);
        showAuthError('Password reset email sent! Check your inbox.', 'success');
    } catch (error) {
        showAuthError(getAuthErrorMessage(error.code));
    }
}

function showAuthError(message, type = 'error') {
    const errorDiv = document.getElementById('authError');
    errorDiv.textContent = message;
    errorDiv.className = `auth-error show ${type}`;

    if (type === 'success') {
        errorDiv.style.background = 'linear-gradient(135deg, #f0fff4, #c6f6d5)';
        errorDiv.style.borderColor = '#68d391';
        errorDiv.style.color = '#2f855a';
    }
}

function clearAuthError() {
    const errorDiv = document.getElementById('authError');
    errorDiv.classList.remove('show');
    errorDiv.style.background = '';
    errorDiv.style.borderColor = '';
    errorDiv.style.color = '';
}

function getAuthErrorMessage(errorCode) {
    switch (errorCode) {
        case 'auth/user-not-found':
            return 'No account found with this email address';
        case 'auth/wrong-password':
            return 'Incorrect password';
        case 'auth/email-already-in-use':
            return 'An account with this email already exists';
        case 'auth/weak-password':
            return 'Password is too weak';
        case 'auth/invalid-email':
            return 'Invalid email address';
        case 'auth/too-many-requests':
            return 'Too many failed attempts. Please try again later';
        case 'auth/popup-closed-by-user':
            return 'Sign-in popup was closed';
        default:
            return 'An error occurred. Please try again';
    }
}

function showLoginScreen() {
    document.getElementById('loginScreen').style.display = 'flex';
    document.getElementById('loadingScreen').style.display = 'none';
    document.getElementById('mainApp').style.display = 'none';
}

function showMainApp(user) {
    currentUser = user;
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('loadingScreen').style.display = 'flex';

    // Update user info in navbar
    updateUserInfo(user);

    // Start loading models
    checkModelsReady();
}

function updateUserInfo(user) {
    const userName = document.getElementById('userName');
    const userAvatar = document.getElementById('userAvatar');

    if (userName) {
        userName.textContent = user.displayName || user.email.split('@')[0];
    }

    if (userAvatar) {
        userAvatar.src = user.photoURL || `https://ui-avatars.com/api/?name=${encodeURIComponent(user.displayName || user.email)}&background=667eea&color=fff`;
    }
}

function toggleDropdown() {
    const dropdown = document.getElementById('dropdownMenu');
    const userInfo = document.getElementById('userInfo');

    dropdown.classList.toggle('show');
    userInfo.classList.toggle('active');
}

function hideDropdown() {
    const dropdown = document.getElementById('dropdownMenu');
    const userInfo = document.getElementById('userInfo');

    dropdown.classList.remove('show');
    userInfo.classList.remove('active');
}

// Menu functions
function showProfile() {
    hideDropdown();
    alert('Profile feature coming soon!');
}

function showSavedBills() {
    hideDropdown();
    displaySavedBills();
}

function showSettings() {
    hideDropdown();
    openSettings();
}

// Settings functions
function openSettings() {
    const modal = document.getElementById('settingsModal');
    const ageGroup = document.getElementById('ageGroup');
    const autoSave = document.getElementById('autoSave');
    const detailLevel = document.getElementById('detailLevel');
    
    // Load current settings
    ageGroup.value = userSettings.ageGroup;
    autoSave.checked = userSettings.autoSave;
    detailLevel.value = userSettings.detailLevel;
    
    modal.style.display = 'flex';
}

function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}

function saveSettings() {
    const ageGroup = document.getElementById('ageGroup').value;
    const autoSave = document.getElementById('autoSave').checked;
    const detailLevel = document.getElementById('detailLevel').value;
    
    userSettings = { ageGroup, autoSave, detailLevel };
    localStorage.setItem('userSettings', JSON.stringify(userSettings));
}

// Saved bills functions
function saveBill(bill) {
    const billId = bill.number;
    
    // Check if already saved
    if (savedBills.find(b => b.number === billId)) {
        showNotification('Bill already saved!', 'info');
        return;
    }
    
    savedBills.push({
        ...bill,
        savedAt: new Date().toISOString()
    });
    
    localStorage.setItem('savedBills', JSON.stringify(savedBills));
    showNotification('Bill saved successfully!', 'success');
    
    // Update save button
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
    if (saveBtn) {
        if (isSaved) {
            saveBtn.innerHTML = '<i class="fas fa-bookmark"></i> Saved';
            saveBtn.classList.add('saved');
        } else {
            saveBtn.innerHTML = '<i class="far fa-bookmark"></i> Save';
            saveBtn.classList.remove('saved');
        }
    }
}

function displaySavedBills() {
    const billsContainer = document.getElementById('billsContainer');
    
    if (savedBills.length === 0) {
        billsContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📚</div>
                <h3>No Saved Bills</h3>
                <p>Bills you save will appear here for easy access</p>
            </div>
        `;
        return;
    }
    
    const resultsHeader = `
        <div class="results-header">
            <h2><i class="fas fa-bookmark"></i> Your Saved Bills (${savedBills.length})</h2>
            <p>Bills you've bookmarked for later reference</p>
        </div>
    `;
    
    const billsHTML = savedBills.map((bill, index) => {
        return createBillCardHTML(bill, index, true);
    }).join('');
    
    billsContainer.innerHTML = resultsHeader + `<div class="bills-grid">${billsHTML}</div>`;
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => notification.classList.add('show'), 100);
    
    // Remove after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => document.body.removeChild(notification), 300);
    }, 3000);
}

// Loading screen management
let loadingProgress = 0;
let modelsReady = false;

async function checkModelsReady() {
    const loadingScreen = document.getElementById('loadingScreen');
    const mainApp = document.getElementById('mainApp');
    const progressBar = document.getElementById('loadingProgress');
    const loadingText = document.getElementById('loadingText');
    const step1 = document.getElementById('step1');
    const step2 = document.getElementById('step2');
    const step3 = document.getElementById('step3');

    // Simulate loading steps
    updateLoadingStep(step1, 'active');
    updateProgress(20, 'Connecting to server...');

    try {
        // Check if server is running
        await new Promise(resolve => setTimeout(resolve, 500));
        updateProgress(40, 'Loading semantic model...');
        updateLoadingStep(step1, 'completed');
        updateLoadingStep(step2, 'active');

        await new Promise(resolve => setTimeout(resolve, 800));
        updateProgress(70, 'Loading summarization model...');

        // Check if models are ready
        const response = await fetch(`${BACKEND_URL}/models_ready`);

        if (response.ok) {
            updateProgress(90, 'Models ready!');
            updateLoadingStep(step2, 'completed');
            updateLoadingStep(step3, 'active');

            await new Promise(resolve => setTimeout(resolve, 500));
            updateProgress(100, 'Launching BillFinder AI...');
            updateLoadingStep(step3, 'completed');

            await new Promise(resolve => setTimeout(resolve, 800));

            // Hide loading screen and show main app
            loadingScreen.classList.add('fade-out');
            setTimeout(() => {
                loadingScreen.style.display = 'none';
                mainApp.style.display = 'block';
                initializeMainApp();
            }, 500);

        } else {
            throw new Error('Models not ready');
        }

    } catch (error) {
        console.log('Server not ready, retrying...', error);
        updateProgress(10, 'Server starting up...');
        // Retry after 2 seconds
        setTimeout(checkModelsReady, 2000);
    }
}

function updateProgress(percent, text) {
    const progressBar = document.getElementById('loadingProgress');
    const loadingText = document.getElementById('loadingText');

    progressBar.style.width = `${percent}%`;
    loadingText.textContent = text;
}

function updateLoadingStep(stepElement, status) {
    stepElement.className = `step ${status}`;
}

function initializeMainApp() {
    // Update user info in the existing navbar
    updateUserInfo(currentUser);

    // Re-attach event listeners
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                searchBills();
            }
        });
    }

    // Initialize empty state if needed
    const billsContainer = document.getElementById('billsContainer');
    if (billsContainer && !billsContainer.innerHTML.trim()) {
        billsContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🏛️</div>
                <h3>Discover Congressional Bills</h3>
                <p>Enter a topic above to find and browse recent congressional legislation with AI-generated summaries and semantic matching</p>
            </div>
        `;
    }
}

function parseDate(dateStr) {
    if (!dateStr || dateStr === 'N/A') {
        return new Date(0);
    }

    const formats = [
        /(\d{1,2})\/(\d{1,2})\/(\d{4})/,
        /(\d{4})-(\d{1,2})-(\d{1,2})/,
    ];

    for (let format of formats) {
        const match = dateStr.match(format);
        if (match) {
            if (format === formats[0]) {
                return new Date(match[3], match[1] - 1, match[2]);
            } else {
                return new Date(match[1], match[2] - 1, match[3]);
            }
        }
    }

    const yearMatch = dateStr.match(/(\d{4})/);
    if (yearMatch) {
        return new Date(yearMatch[1], 0, 1);
    }

    return new Date(0);
}

async function searchBills() {
    const query = document.getElementById('searchInput').value.trim();
    const billsContainer = document.getElementById('billsContainer');
    const errorContainer = document.getElementById('errorContainer');
    const searchBtn = document.getElementById('searchBtn');

    errorContainer.innerHTML = '';

    if (!query) {
        errorContainer.innerHTML = '<div class="error-message"><i class="fas fa-exclamation-triangle"></i> Please enter a search term</div>';
        return;
    }

    searchBtn.disabled = true;
    const originalContent = searchBtn.innerHTML;
    searchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Searching...</span>';

    billsContainer.innerHTML = '<div class="loading"><div class="spinner"></div><div>🤖 AI is analyzing 250+ bills and generating smart summaries...</div></div>';

    try {
        const response = await fetch(`${BACKEND_URL}/search_bills`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `API error: ${response.status}`);
        }

        const data = await response.json();

        if (!data.bills || data.bills.length === 0) {
            throw new Error('No relevant bills found. Try a different search term or broader keywords.');
        }

        // Transform backend data to match original format
        const bills = data.bills.map(bill => ({
            number: `H.R. ${bill.number}`,
            title: bill.title,
            sponsor: bill.sponsor || 'N/A',
            status: bill.status || 'N/A',
            date: bill.date || 'N/A',
            summary: bill.summary,
            relevance: bill.relevance_score || 0,
            url: bill.url,
            dateObj: parseDate(bill.date)
        }));

        displayBills(bills, query);
        updateNavStats(bills.length);

    } catch (error) {
        billsContainer.innerHTML = '';
        errorContainer.innerHTML = `<div class="error-message"><i class="fas fa-exclamation-circle"></i> ${error.message}</div>`;
    } finally {
        searchBtn.disabled = false;
        searchBtn.innerHTML = originalContent;
    }
}

function searchCategory(category) {
    document.getElementById('searchInput').value = category;
    searchBills();
}

function displayBills(bills, query) {
    const billsContainer = document.getElementById('billsContainer');

    const resultsHeader = `
        <div class="results-header">
            <h2><i class="fas fa-search"></i> Found ${bills.length} bills for "${escapeHtml(query)}"</h2>
            <p>Results sorted by AI relevance score</p>
        </div>
    `;

    const billsHTML = bills.map((bill, index) => {
        const relevancePercent = Math.round(bill.relevance * 100);
        const relevanceColor = relevancePercent > 70 ? '#51cf66' : relevancePercent > 50 ? '#ffd43b' : '#ff6b6b';

        return `
        <div class="bill-card" style="animation-delay: ${index * 0.1}s">
            <div class="relevance-badge" style="background-color: ${relevanceColor}">
                ${relevancePercent}%
            </div>
            <div class="bill-header">
                <div class="bill-number">${escapeHtml(bill.number)}</div>
                <div class="bill-title">${escapeHtml(bill.title)}</div>
            </div>
            <div class="bill-summary">${escapeHtml(bill.summary)}</div>
            <div class="bill-meta">
                <div class="meta-item">
                    <span><i class="fas fa-clipboard-list"></i></span>
                    <span>${escapeHtml(bill.status)}</span>
                </div>
                <div class="meta-item">
                    <span><i class="fas fa-user-tie"></i></span>
                    <span>${escapeHtml(bill.sponsor)}</span>
                </div>
                <div class="meta-item">
                    <span><i class="fas fa-calendar-alt"></i></span>
                    <span>${escapeHtml(bill.date)}</span>
                </div>
            </div>
            ${bill.url ? `
            <div class="bill-actions">
                <a href="${bill.url}" target="_blank" class="view-bill-btn">
                    <i class="fas fa-external-link-alt"></i>
                    View Full Bill
                </a>
            </div>
            ` : ''}
        </div>
    `}).join('');

    billsContainer.innerHTML = resultsHeader + `<div class="bills-grid">${billsHTML}</div>`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function updateNavStats(billCount) {
    const navStats = document.getElementById('navStats');
    if (navStats && billCount) {
        navStats.innerHTML = `
            <span class="stat-item">
                <i class="fas fa-check-circle"></i>
                <span>${billCount} Results</span>
            </span>
            <span class="stat-item">
                <i class="fas fa-robot"></i>
                <span>AI Powered</span>
            </span>
        `;
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', function (event) {
    const userMenu = document.querySelector('.user-menu');
    if (userMenu && !userMenu.contains(event.target)) {
        hideDropdown();
    }
});

// Add Enter key support for forms
document.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        const activeForm = document.querySelector('.auth-form.active');
        if (activeForm) {
            if (activeForm.id === 'signinForm') {
                signIn();
            } else if (activeForm.id === 'signupForm') {
                signUp();
            }
        }
    }
});

// Start the authentication flow when page loads
document.addEventListener('DOMContentLoaded', function () {
    // Firebase auth state will be handled by the onAuthStateChanged listener in the HTML
});