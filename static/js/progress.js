const API_BASE = "http://127.0.0.1:5000";

async function loadProgress() {
    try {
        const res = await fetch(`${API_BASE}/get-user-sessions`);
        if (!res.ok) throw new Error("Failed to fetch sessions");
        
        const sessions = await res.json();
        
        if (sessions.length === 0) {
            document.querySelector(".container").innerHTML += "<p style='text-align:center;'>No interview sessions found. Start an interview to see your progress!</p>";
            return;
        }

        // OVERVIEW
        document.getElementById("totalSessions").innerText = sessions.length;

        const totalScore = sessions.reduce((sum, s) => sum + (s.score || 0), 0);
        const avgScore = totalScore / sessions.length;
        document.getElementById("avgScore").innerText = avgScore.toFixed(1);

        document.getElementById("latestScore").innerText = sessions[0].score || 0;

        // For skill averages, since we don't have separate columns, 
        // we'll use the overall score as a baseline for all skills in this simplified version.
        // In a real app, you'd parse feedback or have separate DB columns.
        document.getElementById("techSkill").value = avgScore;
        document.getElementById("commSkill").value = avgScore * 0.9; // Simulating variation
        document.getElementById("confSkill").value = avgScore * 0.85;

        document.getElementById("bestSkill").innerText = "JD-Based Interviewing";

        // SESSION TABLE
        const table = document.getElementById("sessionTable");
        table.innerHTML = ""; // Clear existing
        
        sessions.forEach(s => {
            const row = document.createElement("tr");
            const date = new Date(s.session_date).toLocaleDateString();
            
            // Truncate feedback if too long
            const displayFeedback = s.feedback.length > 100 
                ? s.feedback.substring(0, 100) + "..." 
                : s.feedback;
                
            row.innerHTML = `
                <td>${date}</td>
                <td title="${s.topic}">${s.topic}</td>
                <td><strong>${s.score}/10</strong></td>
                <td><small>${displayFeedback}</small></td>
            `;
            table.appendChild(row);
        });

    } catch (e) {
        console.error("Load progress error:", e);
        // alert("Failed to load progress data.");
    }
}

// Initialize on load
document.addEventListener("DOMContentLoaded", loadProgress);
