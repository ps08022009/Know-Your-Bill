
const API_KEY = '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';

async function searchBills() {
    const query = document.getElementById('searchInput').value.trim();
    const billsContainer = document.getElementById('billsContainer');
    const errorContainer = document.getElementById('errorContainer');
    const searchBtn = document.getElementById('searchBtn');
    
    errorContainer.innerHTML = '';
    
    if (!query) {
        errorContainer.innerHTML = '<div class="error-message">Please enter a search term</div>';
        return;
    }
    
    searchBtn.disabled = true;
    searchBtn.textContent = 'Searching...';
    
    billsContainer.innerHTML = '<div class="loading"><div class="spinner"></div><div>AI is searching for bills and generating summaries...</div></div>';
    
    try {
        const searchPrompt = `You are a congressional research assistant. Search for and provide information about recent US congressional bills related to: "${query}"

Please provide 3-5 bills in the following format for each bill. IMPORTANT: List bills from MOST RECENT to OLDEST by date.

BILL: [Bill number, e.g., H.R. 1234 or S. 567]
TITLE: [Full official title]
SPONSOR: [Primary sponsor name and party]
STATUS: [Current status, e.g., Introduced, Passed House, etc.]
DATE: [Introduction or last action date in MM/DD/YYYY format]
SUMMARY: [2-3 sentence summary of the bill's purpose and key provisions]

---

Make sure to include real, recent bills if you know them, or clearly indicate if you're providing representative examples. Focus on bills from the 118th Congress (2023-2025) when possible. Sort by most recent date first.`;

        const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${API_KEY}`,
                'HTTP-Referer': window.location.href,
                'X-Title': 'Congressional Bill Browser'
            },
            body: JSON.stringify({
                model: 'openai/gpt-4o-mini',
                messages: [
                    { role: 'system', content: 'You are a congressional research assistant who helps users find and understand recent US legislation.' },
                    { role: 'user', content: searchPrompt }
                ],
                max_tokens: 2000,
                temperature: 0.7
            })
        });
        
        if (!response.ok) {
            const errorData = await response.text();
            throw new Error(`API error: ${response.status} - ${errorData}`);
        }
        
        const data = await response.json();
        const aiResponse = data.choices[0].message.content;
        const bills = parseBillsFromAI(aiResponse);
        
        if (bills.length === 0) {
            throw new Error('No bills found. Try a different search term.');
        }
        
        displayBills(bills);
        
    } catch (error) {
        billsContainer.innerHTML = '';
        errorContainer.innerHTML = `<div class="error-message">Search failed: ${error.message}</div>`;
    } finally {
        searchBtn.disabled = false;
        searchBtn.textContent = 'Search';
    }
}

function parseBillsFromAI(text) {
    const bills = [];
    const billSections = text.split('---').filter(s => s.trim());
    
    billSections.forEach(section => {
        const billMatch = section.match(/BILL:\s*(.+)/i);
        const titleMatch = section.match(/TITLE:\s*(.+)/i);
        const sponsorMatch = section.match(/SPONSOR:\s*(.+)/i);
        const statusMatch = section.match(/STATUS:\s*(.+)/i);
        const dateMatch = section.match(/DATE:\s*(.+)/i);
        const summaryMatch = section.match(/SUMMARY:\s*(.+?)(?=\n\n|\n[A-Z]+:|$)/is);
        
        if (billMatch && titleMatch && summaryMatch) {
            let summary = summaryMatch[1].trim();
            summary = summary.replace(/\*\*/g, '').replace(/\*/g, '');
            
            bills.push({
                number: billMatch[1].trim(),
                title: titleMatch[1].trim(),
                sponsor: sponsorMatch ? sponsorMatch[1].trim() : 'N/A',
                status: statusMatch ? statusMatch[1].trim() : 'N/A',
                date: dateMatch ? dateMatch[1].trim() : 'N/A',
                summary: summary,
                dateObj: parseDate(dateMatch ? dateMatch[1].trim() : '')
            });
        }
    });
    
    bills.sort((a, b) => b.dateObj - a.dateObj);
    return bills;
}

function parseDate(dateStr) {
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

function searchCategory(category) {
    document.getElementById('searchInput').value = category;
    searchBills();
}

function displayBills(bills) {
    const billsContainer = document.getElementById('billsContainer');
    
    const billsHTML = bills.map(bill => `
        <div class="bill-card">
            <div class="bill-header">
                <div class="bill-number">${escapeHtml(bill.number)}</div>
                <div class="bill-title">${escapeHtml(bill.title)}</div>
            </div>
            <div class="bill-summary">${escapeHtml(bill.summary)}</div>
            <div class="bill-meta">
                <div class="meta-item">
                    <span>📋</span>
                    <span>${escapeHtml(bill.status)}</span>
                </div>
                <div class="meta-item">
                    <span>👤</span>
                    <span>${escapeHtml(bill.sponsor)}</span>
                </div>
                <div class="meta-item">
                    <span>📅</span>
                    <span>${escapeHtml(bill.date)}</span>
                </div>
            </div>
        </div>
    `).join('');
    
    billsContainer.innerHTML = `<div class="bills-grid">${billsHTML}</div>`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.getElementById('searchInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        searchBills();
    }
});

document.getElementById('billsContainer').innerHTML = `
    <div class="empty-state">
        <div class="empty-state-icon">🏛️</div>
        <h3>Search for Bills</h3>
        <p>Enter a topic above to find and browse recent congressional legislation with AI-generated summaries</p>
    </div>
`;