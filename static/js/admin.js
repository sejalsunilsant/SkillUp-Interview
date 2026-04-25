document.addEventListener('DOMContentLoaded', () => {
    fetchStats();
    fetchRequests();
});

async function fetchStats() {
    try {
        const response = await fetch('/api/admin/stats');
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('totalUsers').textContent = data.total_users;
            document.getElementById('totalSessions').textContent = data.total_sessions;
        }
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

async function fetchRequests() {
    try {
        const response = await fetch('/api/admin/requests');
        const requests = await response.json();
        
        const container = document.getElementById('requestsContainer');
        document.getElementById('pendingRequestsCount').textContent = requests.length;

        if (requests.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="ph-bold ph-check-circle empty-icon" style="color: var(--success);"></i>
                    <p>No pending admin requests at the moment.</p>
                </div>
            `;
            return;
        }

        let html = `
            <table class="request-table">
                <thead>
                    <tr>
                        <th>User Name</th>
                        <th>Email</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        requests.forEach(req => {
            html += `
                <tr>
                    <td>
                        <div style="font-weight: 600; color: var(--text-white);">${req.name}</div>
                    </td>
                    <td>${req.email}</td>
                    <td>
                        <span class="status-badge status-warning">Pending</span>
                    </td>
                    <td>
                        <div class="action-btns">
                            <button class="btn-primary btn-sm" onclick="handleRequest(${req.user_id}, 'approve')">
                                <i class="ph-bold ph-check"></i> Approve
                            </button>
                            <button class="btn-danger btn-sm" onclick="handleRequest(${req.user_id}, 'reject')">
                                <i class="ph-bold ph-x"></i> Reject
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        });

        html += `
                </tbody>
            </table>
        `;
        container.innerHTML = html;
    } catch (error) {
        console.error('Error fetching requests:', error);
        document.getElementById('requestsContainer').innerHTML = `
            <div class="empty-state">
                <i class="ph-bold ph-warning-circle empty-icon" style="color: var(--danger);"></i>
                <p>Failed to load requests. Please try again later.</p>
            </div>
        `;
    }
}

async function handleRequest(userId, action) {
    if (!confirm(`Are you sure you want to ${action} this admin request?`)) return;

    try {
        const response = await fetch('/api/admin/handle-request', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId,
                action: action
            })
        });

        const data = await response.json();
        if (data.success) {
            // Refresh data
            fetchStats();
            fetchRequests();
            // Show notification if available (not implemented here, but good practice)
        } else {
            alert(data.message || 'Action failed');
        }
    } catch (error) {
        console.error(`Error ${action}ing request:`, error);
        alert('An error occurred. Please try again.');
    }
}
